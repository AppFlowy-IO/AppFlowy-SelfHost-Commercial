"""Backup source isolation, tool compatibility and installed Compose contracts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from configuration import ROOT, SOURCE_FILES, check_compose, isolated_source, source_fingerprint
from deployment import Deployment
from images import CORE, clean_environment


class BackupConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='appflowy-backup-source-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def source_fixture(self):
        source = self.root / 'operator-checkout'
        for name in SOURCE_FILES:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        (source / '.env').write_text('PRIVATE=operator-secret\n')
        (source / 'backup-ops/runtime').mkdir(parents=True)
        (source / 'backup-ops/runtime/cloud.env').write_text('RESTORED_BUCKET=private-live-bucket\n')
        return source

    def test_isolation_copies_only_reviewed_files_not_operator_selections(self):
        source = self.source_fixture()
        destination = isolated_source(self.root / 'isolated', source)
        copied = {str(path.relative_to(destination)) for path in destination.rglob('*') if path.is_file()}
        self.assertEqual(copied, set(SOURCE_FILES))
        self.assertFalse((destination / '.env').exists())
        self.assertFalse((destination / 'backup-ops').exists())
        self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
        self.assertEqual(source_fingerprint(source), source_fingerprint(destination))

    def test_every_versioned_backup_input_participates_in_fingerprint(self):
        source = self.source_fixture()
        original = source_fingerprint(source)
        for name in SOURCE_FILES:
            path = source / name
            content = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(content + b'\n# changed source\n')
                self.assertNotEqual(source_fingerprint(source), original)
                path.write_bytes(content)
        (source / '.env').write_text('PRIVATE=different-secret\n')
        (source / 'backup-ops/runtime/cloud.env').write_text('RESTORED_BUCKET=different-live-bucket\n')
        self.assertEqual(source_fingerprint(source), original)

    def test_isolation_refuses_symlinks_into_operator_state(self):
        source = self.source_fixture()
        path = source / 'docker/backup/source-appflowy_cloud.env'
        path.unlink()
        path.symlink_to(source / 'backup-ops/runtime/cloud.env')
        with self.assertRaisesRegex(RuntimeError, 'regular checked-in file'):
            isolated_source(self.root / 'isolated', source)

    def test_compose_version_fails_before_render_on_old_unknown_or_failed_tool(self):
        cases = [('2.29.7', 0, False), ('2.12.2', 0, False), ('garbage', 0, False),
                 ('2.30.0', 1, False), ('2.30.0', 0, True), ('v2.40.3-desktop.1', 0, True),
                 ('Docker Compose version v2.39.0', 0, True)]
        for output, code, supported in cases:
            result = subprocess.CompletedProcess([], code, stdout=output, stderr='private diagnostic')
            with self.subTest(output=output, code=code), patch('configuration.subprocess.run', return_value=result) as run:
                if supported:
                    self.assertTrue(check_compose({'PATH': '/safe/path'}))
                else:
                    with self.assertRaisesRegex(RuntimeError, '2.30'):
                        check_compose({'PATH': '/safe/path'})
                self.assertEqual(run.call_args.args[0], ['docker', 'compose', 'version', '--short'])
                self.assertEqual(run.call_args.kwargs['env'], {'PATH': '/safe/path'})

    def test_clean_environment_discards_compose_and_backup_operator_overrides(self):
        with patch.dict('os.environ', {'PATH': '/bin', 'COMPOSE_FILE': '/private/stack.yml',
                        'COMPOSE_PROJECT_NAME': 'live', 'APPFLOWY_BACKUP_BUCKET': 'private-bucket',
                        'APPFLOWY_DATABASE_URL': 'postgres://private'}, clear=True):
            self.assertEqual(clean_environment(), {'PATH': '/bin'})

    def test_compose_backup_is_disabled_until_the_profile_is_set(self):
        source = isolated_source(self.root / 'compose-defaults')
        settings = (source / 'deploy.env').read_text()
        self.assertIn('\nAPPFLOWY_BACKUP_PROFILE=\n', settings)
        for profile in ('', 'backup'):
            with self.subTest(profile=profile):
                (source / '.env').write_text(settings.replace(
                    '\nAPPFLOWY_BACKUP_PROFILE=\n', '\nAPPFLOWY_BACKUP_PROFILE=' + profile + '\n'))
                result = subprocess.run(['docker', 'compose', '--project-directory', str(source),
                                         'config', '--format', 'json'], env=clean_environment(),
                                        capture_output=True, text=True, check=True, timeout=30)
                config = json.loads(result.stdout)
                expected = CORE | {'ai'} | ({'appflowy_backup'} if profile else set())
                self.assertEqual(set(config['services']), expected)
                if profile:
                    self.assertEqual(config['services']['appflowy_backup']['command'], ['bootstrap'])
                    self.assertIn('backup_work', config['volumes'])
                else:
                    self.assertNotIn('backup_work', config['volumes'])

    def deployment(self, backup=True, mode='compose'):
        digest = 'sha256:' + 'a' * 64
        record = lambda name: {'source': name + ':latest', 'image': name + '@' + digest,
                               'digest': digest, 'config_digest': digest}
        self.lock = self.root / 'images.json'
        payload = {'services': {name: record(name) for name in CORE},
                   'backup_services': {'appflowy_backup': record('appflowy_backup')},
                   'source_sha256': source_fingerprint(),
                   'compose_sha256': hashlib.sha256((ROOT / 'docker-compose.yml').read_bytes()).hexdigest()}
        self.lock.write_text(json.dumps(payload))
        return Deployment(mode, self.root / 'runtime', self.root / 'artifacts', self.lock, backup=backup)

    def test_backup_requires_separate_pin_and_current_source_fingerprint(self):
        instance = self.deployment()
        self.assertEqual(instance.services, CORE | {'appflowy_backup'})
        payload = json.loads(self.lock.read_text())
        payload.pop('backup_services')
        self.lock.write_text(json.dumps(payload))
        with self.assertRaisesRegex(RuntimeError, 'pinned Backup image'):
            Deployment('compose', instance.runtime, instance.artifacts, self.lock, backup=True)
        payload['source_sha256'] = 'stale'
        self.lock.write_text(json.dumps(payload))
        with self.assertRaisesRegex(RuntimeError, 'different deployment or backup source'):
            Deployment('compose', instance.runtime, instance.artifacts, self.lock)
        with self.assertRaisesRegex(RuntimeError, 'requires Compose'):
            self.deployment(mode='swarm')

    def test_backup_render_keeps_source_env_files_and_isolated_bootstrap_mount(self):
        instance = self.deployment()
        # Compose resolution is represented only at its process boundary. Assertions
        # inspect what subsequent ordinary deployment/bootstrap actually consumes.
        services = {name: {'image': name + ':latest', 'environment': {}, 'healthcheck': {}}
                    for name in instance.services | {'ai'}}
        calls = []
        def run(*args, **kwargs):
            calls.append(args)
            return json.dumps({'services': services}) if '--format' in args else ''
        previous_umask = os.umask(0o077)
        try:
            with patch('deployment.check_compose', return_value='2.30.0'), patch.object(instance, 'run', side_effect=run):
                instance.render()
        finally:
            os.umask(previous_umask)
        self.assertIn(str(instance.source / 'docker-compose.backup.yml'), instance.compose)
        self.assertIn(str(instance.source / '.env'), instance.compose)
        self.assertNotIn(str(instance.runtime / 'compose.yml'), instance.compose)
        self.assertEqual((instance.source / 'docker-compose.yml').read_bytes(), (ROOT / 'docker-compose.yml').read_bytes())
        self.assertFalse((instance.source / 'backup-ops').exists())
        installed = (instance.source / '.env').read_text()
        self.assertIn('APPFLOWY_BACKUP_PROFILE=backup', installed)
        self.assertIn('COMPOSE_FILE=docker-compose.yml:docker-compose.backup.yml:ci.override.yml', installed)
        self.assertEqual((instance.source / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual(instance.runtime.stat().st_mode & 0o777, 0o700)
        deployment_group = (instance.source / '.env').stat().st_gid
        for name in (*SOURCE_FILES, 'ci.override.yml'):
            path = instance.source / name
            self.assertEqual(path.stat().st_gid, deployment_group)
            self.assertTrue(path.stat().st_mode & 0o040, name + ' must be group-readable')
            for directory in path.parents:
                self.assertEqual(directory.stat().st_gid, deployment_group)
                self.assertEqual(directory.stat().st_mode & 0o050, 0o050)
                if directory == instance.source:
                    break
        override = yaml.safe_load((instance.source / 'ci.override.yml').read_text())['services']
        self.assertEqual(override['appflowy_backup']['image'], instance.images['appflowy_backup']['image'])
        for service in ('appflowy_cloud', 'appflowy_worker', 'appflowy_search'):
            environment = override[service]['environment']
            self.assertEqual(environment['AI_ENABLED'], 'false')
            self.assertEqual(environment['APPFLOWY_BACKGROUND_INDEXER_ENABLED'], 'false')
            self.assertEqual(environment['APPFLOWY_INDEXER_ENABLED'], 'true')
            self.assertNotIn('APPFLOWY_INDEXER_DATABASE_ENABLED', environment)
            for key in ('APPFLOWY_S3_BUCKET', 'APPFLOWY_REDIS_URI', 'APPFLOWY_KEYWORD_INDEX_DIR'):
                self.assertNotIn(key, environment, 'Overrides must not shadow restored selections')
        self.assertIn('--profile', calls[0])
        self.assertEqual(calls[-1][-2:], ('config', '--quiet'))


if __name__ == '__main__':
    unittest.main()
