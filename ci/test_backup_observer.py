"""Independent restore observer contracts; no Docker daemon or database required."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_observer import ComposeRestoreObserver, environment, redis_namespace, writer_stop_evidence


WRITERS = ('appflowy_cloud', 'gotrue', 'appflowy_worker', 'appflowy_search')


def event(action, identity, when, service):
    return {'Action': action, 'timeNano': when,
            'Actor': {'ID': identity, 'Attributes': {'com.docker.compose.service': service}}}


class BackupObserverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='appflowy-observer-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'deployment/backup-ops/runtime'
        self.directory.mkdir(parents=True)
        self.inventory = {}
        for name in WRITERS + ('postgres', 'appflowy_backup'):
            env = {'APPFLOWY_S3_BUCKET': 'original-bucket', 'APPFLOWY_KEYWORD_INDEX_DIR': '/index'}
            key = {'appflowy_cloud': 'APPFLOWY_REDIS_URI', 'appflowy_worker': 'APPFLOWY_WORKER_REDIS_URL',
                   'appflowy_search': 'APPFLOWY_SEARCH_REDIS_URL'}.get(name)
            if key:
                env[key] = 'redis://:private-password@redis:6379/0'
            if name == 'appflowy_backup':
                env['APPFLOWY_BACKUP_COMPOSE_WRITERS'] = json.dumps(WRITERS)
            self.inventory[name] = [{'Id': 'old-' + name, 'State': {'Running': True},
                'Config': {'Env': [key + '=' + value for key, value in env.items()],
                           'Labels': {'com.docker.compose.project': 'disposable'}}}]
        self.results = Mock()
        self.runner = Mock(return_value='123')
        self.observer = ComposeRestoreObserver(self.root, self.runner, lambda name: self.inventory[name], self.results)
        self.start = 1_000_000_000
        with patch('backup_observer.time.time_ns', return_value=self.start):
            self.observer('before_restore', 'source')

    def activate(self):
        for name in WRITERS:
            row = self.inventory[name][0]
            if name == 'gotrue':
                continue
            env = environment(row)
            env.update({'APPFLOWY_S3_BUCKET': 'restored-bucket', 'APPFLOWY_KEYWORD_INDEX_DIR': '/index/restore-id'})
            for key in ('APPFLOWY_REDIS_URI', 'APPFLOWY_WORKER_REDIS_URL', 'APPFLOWY_SEARCH_REDIS_URL'):
                if key in env:
                    env[key] = env[key].removesuffix('/0') + '/3'
            persisted = dict(env)
            env['APPFLOWY_RESTORE_VERIFY_ONLY'] = 'false'
            self.inventory[name] = [{**row, 'Id': 'new-' + name,
                'Config': {**row['Config'], 'Env': [key + '=' + value for key, value in env.items()]}}]
            (self.directory / ('selection-' + name + '.env')).write_text(
                '\n'.join(key + '=' + value for key, value in persisted.items()))
        events = [event('die', 'old-' + name, self.start + 100 + index, name) for index, name in enumerate(WRITERS)]
        events += [event('start', ('old-' if name == 'gotrue' else 'new-') + name,
                         self.start + 200 + index, name) for index, name in enumerate(WRITERS)]
        self.runner.side_effect = ['456', '\n'.join(json.dumps(row) for row in events)]

    def test_delayed_http_poll_still_uses_independent_docker_stop_history(self):
        self.activate()
        self.observer('restore_poll', 'job')  # The entire stopped interval was between HTTP polls.
        self.observer('after_restore', 'job')
        name, receipt = self.results.call_args.args
        self.assertEqual(name, 'backup-restore-job.json')
        self.assertFalse(receipt['observed_all_stopped_during_poll'])
        self.assertTrue(receipt['all_stopped_before_first_restart'])
        self.assertEqual(receipt['writer_stop_events'], 4)
        self.assertEqual(receipt['old_database_oid'], 123)
        self.assertEqual(receipt['new_database_oid'], 456)
        self.assertNotIn('private-password', json.dumps(receipt))
        self.assertNotIn('restored-bucket', json.dumps(receipt))
        self.assertEqual(receipt['writers']['gotrue']['before'], receipt['writers']['gotrue']['after'])
        self.assertFalse((self.directory / 'selection-gotrue.env').exists())
        exec_call = self.runner.call_args_list[0].args
        self.assertEqual(exec_call[:4], ('docker', 'exec', 'old-postgres', 'sh'))
        self.assertNotIn('private-password', str(exec_call))

    def test_same_database_identity_cannot_pass_by_replacing_containers(self):
        self.activate()
        self.runner.side_effect = ['123']
        with self.assertRaisesRegex(RuntimeError, 'database identity'):
            self.observer('after_restore', 'job')
        self.results.assert_not_called()

    def test_stale_or_mixed_storage_and_missing_persistent_selections_fail(self):
        self.activate()
        after = self.observer.snapshot()
        selected = self.observer.validate_selections(after)
        self.assertEqual(len(selected), 3)
        path = self.directory / 'selection-appflowy_worker.env'
        path.unlink()
        with self.assertRaisesRegex(RuntimeError, 'persist'):
            self.observer.validate_selections(after)
        path.write_text('APPFLOWY_S3_BUCKET=other-bucket\n')
        with self.assertRaisesRegex(RuntimeError, 'differs'):
            self.observer.validate_selections(after)

    def test_no_claim_of_writer_drain_without_complete_ordered_evidence(self):
        before = {name: 'old-' + name for name in WRITERS}
        events = [event('die', identity, self.start + index + 1, name)
                  for index, (name, identity) in enumerate(before.items())]
        started = event('start', 'new-cloud', self.start + 100, 'appflowy_cloud')
        self.assertTrue(writer_stop_evidence(events + [started], before, self.start)['all_stopped_before_first_restart'])
        for bad in (events[:-1] + [started], events,
                    events + [event('start', 'premature', self.start + 1, 'appflowy_cloud')],
                    [event('die', identity, self.start - 1, name) for name, identity in before.items()] + [started]):
            with self.subTest(events=bad), self.assertRaises(RuntimeError):
                writer_stop_evidence(bad, before, self.start)

    def test_redis_namespace_parsing_preserves_host_port_database_without_credentials(self):
        self.assertEqual(redis_namespace('redis://:secret@redis:6379/3'), ('redis', 'redis', 6379, 3))
        self.assertEqual(redis_namespace('redis://redis'), ('redis', 'redis', 6379, 0))
        for value in ('http://redis/3', 'redis:///3', 'redis://redis/not-a-db'):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                redis_namespace(value)


if __name__ == '__main__':
    unittest.main()
