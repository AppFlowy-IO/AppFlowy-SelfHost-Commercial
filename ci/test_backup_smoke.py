"""Contracts for backup acceptance, without starting or mutating a deployment."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_smoke import API, BackupSmoke, NoRedirects, RequestFailure, validate_capture, write_private


class BackupSmokeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='appflowy-backup-contract-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name, value in {
            'credentials.json': {'admin_email': 'private@example.com', 'admin_password': 'private-password'},
            'ordinary-user.json': {'email': 'ordinary@example.com', 'password': 'private-password'},
            'api-state.json': {}, 'database-row-state.json': {},
        }.items():
            write_private(self.root / name, value)
        self.suite = BackupSmoke(self.root, 'http://localhost', None, Mock(), timeout=3)
        self.suite.record = Mock()

    def test_rejects_nonlocal_credential_urls_and_public_credentials(self):
        for url in ('https://example.com', 'http://user:password@localhost', 'http://localhost/path',
                    'http://localhost?token=private', 'file://localhost'):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                BackupSmoke(self.root, url, None, Mock())
        (self.root / 'credentials.json').chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, '0600'):
            BackupSmoke(self.root, 'http://127.0.0.1', None, Mock())

    def test_authenticated_binary_stream_is_private_and_bounded(self):
        content = b'PK fixture private export'
        self.suite.token = 'private-token'
        self.suite.opener.open = Mock(return_value=contextlib.closing(io.BytesIO(content)))
        destination = self.root / 'export.zip'
        result = self.suite.request('GET', API + '/id/download', destination=destination)
        self.assertEqual(result, {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
        request = self.suite.opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer private-token')
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        with patch('backup_smoke.MAX_ARCHIVE_BYTES', 2):
            self.suite.opener.open.return_value = contextlib.closing(io.BytesIO(content))
            with self.assertRaisesRegex(RuntimeError, 'archive limit'):
                self.suite.request('GET', API + '/id/download', destination=self.root / 'too-big.zip')

    def test_redirects_cannot_forward_bearer_tokens_and_errors_hide_bodies(self):
        with self.assertRaises(RequestFailure):
            NoRedirects().redirect_request(None, None, 302, '', {}, 'https://elsewhere.invalid')
        self.suite.opener.open = Mock(side_effect=urllib.error.HTTPError(
            'http://localhost', 503, 'private-password', {}, io.BytesIO(b'private-token')))
        with self.assertRaises(RequestFailure) as error:
            self.suite.request('GET', API)
        self.assertNotIn('private', str(error.exception))
        with self.assertRaises(ValueError):
            self.suite.request('GET', '//elsewhere.invalid')

    def test_recovery_and_export_use_supported_body_and_reuse_idempotency(self):
        self.suite.request = Mock(return_value={'snapshot_id': 'job'})
        self.suite.wait_job = Mock(return_value={'snapshot_id': 'job', 'status': 'completed'})
        self.suite.submit('recovery', include=True)
        first, repeated = self.suite.request.call_args_list
        self.assertEqual(first, repeated)
        self.assertEqual(first.args[:2], ('POST', API))
        self.assertEqual(first.args[2]['backup_type'], 'full')
        self.assertTrue(first.args[2]['include_search_index'])
        self.assertTrue(first.args[2]['include_embeddings'])
        self.assertTrue(first.kwargs['idempotency'])
        self.suite.request.reset_mock()
        self.suite.submit('export', 'source', 'sanitized_debug', content_mode='empty')
        payload = self.suite.request.call_args.args[2]
        self.assertNotIn('backup_type', payload)
        self.assertFalse(payload['include_search_index'])
        self.assertEqual(payload['source_snapshot_id'], 'source')
        self.assertEqual(payload['content_mode'], 'empty')

    def test_poll_only_tolerates_restore_outage_and_fails_terminal_jobs(self):
        complete = {'status': 'completed', 'phase': 'completed'}
        self.suite.request = Mock(side_effect=[RequestFailure(503), complete])
        self.suite.observe = Mock()
        with patch('backup_smoke.time.sleep'):
            self.assertEqual(self.suite.wait_job('job', restore=True), complete)
        self.assertEqual(self.suite.observe.call_count, 2)
        self.suite.request = Mock(side_effect=RequestFailure(503))
        with self.assertRaises(RequestFailure):
            self.suite.wait_job('job')
        self.suite.request = Mock(return_value={'status': 'failed', 'phase': 'restoring'})
        with self.assertRaisesRegex(RuntimeError, 'failed in restoring'):
            self.suite.wait_job('job', restore=True)
        self.suite.request = Mock(return_value={'status': 'running', 'phase': 'restoring'})
        with patch('backup_smoke.time.monotonic', side_effect=[0, 4]), self.assertRaisesRegex(RuntimeError, 'exceeded'):
            self.suite.wait_job('job', restore=True)

    def test_portable_upload_uses_server_part_size_idempotency_and_authenticated_chunks(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name in ('manifest.json', 'files.ndjson', 'validation.json', 'restore-metadata.json'):
                archive.writestr(name, '{}')
        content = buffer.getvalue()
        self.suite.submit = Mock(return_value={'snapshot_id': 'export', 'archive_size': len(content)})
        self.suite.wait_job = Mock(return_value={'profile': 'full'})
        self.suite.denied = Mock()
        calls = []
        def request(method, path, payload=None, **kwargs):
            calls.append((method, path, payload, kwargs))
            if 'destination' in kwargs:
                kwargs['destination'].write_bytes(content)
                return {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
            if path == API + '/uploads':
                return {'snapshot': {'snapshot_id': 'upload'}, 'part_bytes': 128}
        self.suite.request = request
        self.assertEqual(self.suite.export_import('source'), ('export', 'upload'))
        creation = next(row for row in calls if row[1] == API + '/uploads')
        self.assertEqual(creation[2]['bytes'], len(content))
        self.assertTrue(creation[3]['idempotency'])
        chunks = [row for row in calls if '/parts/' in row[1]]
        self.assertEqual(b''.join(row[3]['raw'] for row in chunks), content)
        self.assertTrue(all(len(row[3]['raw']) == 128 for row in chunks[:-1]))
        self.assertEqual([row[1].rsplit('/', 1)[-1] for row in chunks], [str(i + 1) for i in range(len(chunks))])
        self.assertEqual(calls[-1][:2], ('POST', API + '/uploads/upload/complete'))
        self.assertFalse((self.root / 'backup-export.zip').exists())

    def test_capture_claim_requires_explicit_online_mode_and_actual_option_selection(self):
        options = {'include_search_index': False, 'include_embeddings': False}
        manifest = {'capture': {'mode': 'online_interval', 'writes_paused': False,
                               'started_at': '2026-10-01T10:00:00Z', 'finished_at': '2026-10-01T10:00:01Z'},
                    'requested_backup_options': options, 'backup_options': options}
        validate_capture(manifest, options)
        for field, value in [('writes_paused', True), ('mode', 'unknown'), ('finished_at', '2026-10-01T09:00:00Z')]:
            changed = json.loads(json.dumps(manifest))
            changed['capture'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate_capture(changed, options)
        included = {'include_search_index': True, 'include_embeddings': True}
        with self.assertRaises(AssertionError):
            validate_capture(manifest, included)

    def test_schedule_uses_real_dispatch_and_checks_copied_retention(self):
        calls = []
        listed = 0
        def request(method, path, payload=None, **kwargs):
            nonlocal listed
            calls.append((method, path, payload, kwargs))
            if method == 'POST':
                return {'schedule_id': 'schedule'}
            if method == 'GET':
                listed += 1
                return {'items': [{'schedule_id': 'schedule', 'last_snapshot_id': 'job'}] if listed == 1 else []}
        self.suite.request = request
        job = {'snapshot_id': 'job', 'schedule_id': 'schedule', 'retention_hours': 1, 'never_expire': False,
               'finished_at': '2026-10-07T12:00:00Z', 'expires_at': '2026-10-07T13:00:00Z'}
        self.suite.wait_job = Mock(return_value=job)
        self.assertEqual(self.suite.scheduled_recovery(), job)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[0][2]['repeat'], 'once')
        self.assertTrue(calls[0][2]['enabled'])
        self.assertEqual(calls[0][2]['retention_hours'], 1)
        self.suite.wait_job.assert_called_once_with('job')
        self.assertIn(('DELETE', API + '/schedules/schedule', None, {}), calls)

    def test_download_denial_cannot_pass_on_unavailable_or_missing_endpoint(self):
        for status in (404, 500, 503):
            self.suite.request = Mock(side_effect=RequestFailure(status))
            with self.subTest(status=status), self.assertRaises(RequestFailure):
                self.suite.denied(API + '/job/download', None)
        for status in (401, 403):
            self.suite.request = Mock(side_effect=RequestFailure(status))
            self.suite.denied(API + '/job/download', None)
        self.suite.request = Mock(return_value=b'private')
        with self.assertRaisesRegex(AssertionError, 'unauthorized'):
            self.suite.denied(API + '/job/download', None)

    def test_restore_observation_surrounds_real_request_and_readback(self):
        events = []
        self.suite.observe = lambda event, snapshot: events.append((event, snapshot))
        self.suite.request = Mock(return_value={'snapshot_id': 'restore-job'})
        self.suite.wait_job = Mock()
        self.suite.ready = Mock()
        self.suite.verify_fixture = Mock()
        self.suite.restore('source', 'portable_zip')
        call = self.suite.request.call_args
        self.assertEqual(call.args, ('POST', API + '/source/restore',
                                     {'confirmation': 'RESTORE', 'maintenance_acknowledged': True}))
        self.assertTrue(call.kwargs['idempotency'])
        self.assertEqual(events, [('before_restore', 'source'), ('after_restore', 'restore-job')])
        self.suite.wait_job.assert_called_once_with('restore-job', restore=True)
        self.suite.verify_fixture.assert_called_once_with('portable_zip')


if __name__ == '__main__':
    unittest.main()
