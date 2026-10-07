#!/usr/bin/env python3
"""Backup acceptance for the disposable deployment owned by ci/deployment.py.

The caller owns isolation, container lifecycle and image checks. This module uses
the real Admin API and the application fixture created by the ordinary smoke lane.
It never starts a deployment or changes database rows through SQL.

``observe(event, snapshot_id)`` is called before restore, during every restore
poll and after completion. A deployment observer can check writer shutdown,
database identity and selected storage, or inject a controlled coordinator restart.
``redeploy()`` must recreate the ordinary Compose deployment and wait for readiness.
``verify()`` may add checks; built-in readback compares logical fixture values because
materializing collaboration updates can change their binary serialization.
"""
import hashlib
import json
import os
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile


API = '/api/admin/server-snapshots'
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
DEFAULT_TOKEN = object()
# AppError's Actix response uses HTTP 200 for these authorization failures:
# NotLoggedIn, NotEnoughPermissions, and UserUnAuthorized.
AUTH_DENIAL_CODES = {1011, 1012, 1024}


class RequestFailure(RuntimeError):
    """Safe transport failure: never include URLs with credentials or response bodies."""
    def __init__(self, status=None, code=None):
        self.status, self.code = status, code
        super().__init__(f'Backup request failed: HTTP {status}, application code {code}')


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RequestFailure(code)


def private_json(path):
    if path.stat().st_mode & 0o077:
        raise RuntimeError(f'{path.name} must have mode 0600')
    return json.loads(path.read_text())


def write_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def validate_capture(manifest, expected_options):
    capture = manifest.get('capture', {})
    if capture.get('mode') != 'online_interval' or capture.get('writes_paused') is not False:
        raise AssertionError('Recovery manifest does not describe an online capture')
    if timestamp(capture['finished_at']) < timestamp(capture['started_at']):
        raise AssertionError('Recovery capture interval is reversed')
    if manifest.get('requested_backup_options') != expected_options:
        raise AssertionError('Recovery requested options differ')
    effective = manifest.get('backup_options', {})
    if effective.get('include_embeddings') != expected_options['include_embeddings']:
        raise AssertionError('Recovery embedding selection differs')
    # A requested index may be omitted when no local workspace index exists.
    # The deployment fixture verifies a positive Search result before capture,
    # so this lane requires an actual retained cache for the included variant.
    if effective != expected_options:
        raise AssertionError('Recovery effective options differ from the indexed fixture')


class BackupSmoke:
    def __init__(self, runtime, base_url, verify, redeploy, observe=None, evidence=None, timeout=900):
        self.runtime, self.base_url = Path(runtime), base_url.rstrip('/')
        parsed = urllib.parse.urlsplit(self.base_url)
        if (parsed.scheme not in ('http', 'https') or parsed.hostname not in ('localhost', '127.0.0.1', '::1')
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path):
            raise RuntimeError('Backup acceptance requires a loopback deployment URL without credentials')
        if timeout <= 0:
            raise ValueError('Backup acceptance timeout must be positive')
        self.verify, self.redeploy, self.observe, self.evidence = verify, redeploy, observe, evidence
        self.timeout, self.token, self.events = timeout, None, []
        self.opener = urllib.request.build_opener(NoRedirects())
        credentials = private_json(self.runtime / 'credentials.json')
        self.admin = {'email': credentials['admin_email'], 'password': credentials['admin_password']}
        self.ordinary = private_json(self.runtime / 'ordinary-user.json')
        self.fixture = json.loads((self.runtime / 'api-state.json').read_text())
        self.row = json.loads((self.runtime / 'database-row-state.json').read_text())
        self.device = 'backup-ci-' + uuid.uuid4().hex
        self.ordinary_token = None

    def record(self, check, **details):
        event = {'check': check, **details}
        self.events.append(event)
        print(json.dumps(event), flush=True)
        write_private(self.runtime / 'backup-results.json', self.events)
        if self.evidence:
            self.evidence('backup-results.json', self.events)

    def request(self, method, path, payload=None, raw=None, token=DEFAULT_TOKEN,
                idempotency=None, binary=False, destination=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Only deployment-relative API paths are accepted')
        token = self.token if token is DEFAULT_TOKEN else token
        headers = {'x-platform': 'web', 'device-id': self.device,
                   'client-timestamp': str(int(time.time()))}
        version = os.environ.get('SWARM_TEST_CLIENT_VERSION')
        if version:
            headers['client-version'] = version
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if idempotency:
            headers['Idempotency-Key'] = idempotency
        if payload is not None:
            raw = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        elif raw is not None:
            headers['Content-Type'] = 'application/octet-stream'
        req = urllib.request.Request(self.base_url + path, data=raw, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=30) as response:
                if destination is not None:
                    length, digest = 0, hashlib.sha256()
                    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'wb') as stream:
                        while chunk := response.read(1024 * 1024):
                            length += len(chunk)
                            if length > MAX_ARCHIVE_BYTES:
                                raise RuntimeError('Export exceeded the small fixture archive limit')
                            digest.update(chunk)
                            stream.write(chunk)
                    return {'bytes': length, 'sha256': digest.hexdigest()}
                data = response.read(16 * 1024 * 1024 + 1)
                if len(data) > 16 * 1024 * 1024:
                    raise RuntimeError('API response exceeded the fixture limit')
        except urllib.error.HTTPError as exc:
            raise RequestFailure(exc.code) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise RequestFailure() from None
        if binary:
            return data
        value = json.loads(data) if data else None
        if isinstance(value, dict) and 'code' in value:
            if value['code'] != 0:
                raise RequestFailure(200, value['code'])
            return value.get('data')
        return value

    def login(self):
        self.token = self.request('POST', '/gotrue/token?grant_type=password', self.admin, token=None)['access_token']
        self.ordinary_token = self.request('POST', '/gotrue/token?grant_type=password', self.ordinary,
                                           token=None)['access_token']

    def poll(self, check, operation):
        deadline = time.monotonic() + self.timeout
        while True:
            result = operation()
            if result is not None:
                return result
            if time.monotonic() >= deadline:
                raise RuntimeError(f'{check} exceeded {self.timeout}s')
            time.sleep(1)

    def ready(self):
        last_pending = None
        def pending(**state):
            nonlocal last_pending
            if state != last_pending:
                self.record('backup_readiness', state='waiting', **state)
                last_pending = state

        def probe():
            try:
                caps = self.request('GET', API + '/capabilities')
            except RequestFailure as exc:
                if exc.status in (None, 502, 503, 504):
                    pending(http_status=exc.status)
                    return None
                if exc.status == 404:
                    self.record('backup_capabilities', passed=False, reason='missing_api', http_status=404)
                    raise RuntimeError(
                        'Cloud returned HTTP 404 for GET ' + API + '/capabilities; '
                        'select compatible Cloud, Worker, Search, GoTrue and Backup builds that include Backup support'
                    ) from None
                raise
            needed = {'recovery', 'export', 'restore'}
            flags = ('runner_ready', 'supports_online_backup', 'supports_archive_restore', 'supports_schedules')
            missing_flags = [flag for flag in flags if not caps.get(flag)]
            missing_operations = sorted(needed - set(caps.get('supported_operations', [])))
            blockers = len(caps.get('creation_blockers') or [])
            if not missing_flags and not missing_operations and not blockers:
                return caps
            # Report only known capability names and counts. Do not copy arbitrary
            # response fields or blocker text into logs containing private deployment data.
            pending(missing_capabilities=missing_flags, missing_operations=missing_operations,
                    creation_blocker_count=blockers)
        caps = self.poll('Backup capabilities', probe)
        self.record('backup_capabilities', passed=True, retention_hours=caps['retention_hours'],
                    recovery_retention_hours=caps['recovery_retention_hours'])

    def denied(self, path, token):
        try:
            data = self.request('GET', path, token=token, binary=True)
        except RequestFailure as exc:
            if exc.status in (401, 403):
                self.record('backup_access_denied', passed=True, http_status=exc.status,
                            authenticated=bool(token))
                return
            raise
        # Read the denial envelope even for download endpoints. HTTP 200 alone
        # is not authorization success, but unrelated errors or returned data
        # must never count as a successful access-control check.
        try:
            error = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            error = None
        if (isinstance(error, dict) and type(error.get('code')) is int
                and error['code'] in AUTH_DENIAL_CODES and error.get('data') is None
                and set(error).issubset({'code', 'message', 'data'})):
            self.record('backup_access_denied', passed=True, http_status=200,
                        application_code=error['code'], authenticated=bool(token))
            return
        raise AssertionError('Private backup endpoint admitted an unauthorized caller')

    def wait_job(self, snapshot_id, restore=False, status='completed'):
        previous = None
        def probe():
            nonlocal previous
            if restore and self.observe:
                self.observe('restore_poll', snapshot_id)
            try:
                job = self.request('GET', API + '/' + snapshot_id)
            except RequestFailure as exc:
                # The public gateway is unavailable while all writers are stopped.
                if restore and exc.status in (None, 502, 503, 504):
                    return None
                if restore and exc.status == 401:
                    try:
                        self.login()
                    except RequestFailure as login_error:
                        if login_error.status not in (None, 502, 503, 504):
                            raise
                    return None
                raise
            state = (job['status'], job['phase'])
            if state != previous:
                self.record('backup_job', snapshot_id=snapshot_id, status=state[0], phase=state[1])
                previous = state
            if state[0] == status:
                return job
            if state[0] in ('failed', 'cancelled', 'deleted', 'expired'):
                raise RuntimeError(f'Backup job {snapshot_id} ended as {state[0]} in {state[1]}')
            return None
        return self.poll('Backup job ' + snapshot_id, probe)

    def submit(self, operation, source=None, profile='full', include=False, content_mode=None):
        payload = {'name': 'Deployment ' + operation + ' ' + profile, 'operation': operation,
                   'profile': profile, 'source_snapshot_id': source,
                   'include_search_index': include, 'include_embeddings': include}
        if operation == 'recovery':
            payload['backup_type'] = 'full'
        if content_mode:
            payload['content_mode'] = content_mode
        key = str(uuid.uuid4())
        job = self.request('POST', API, payload, idempotency=key)
        repeated = self.request('POST', API, payload, idempotency=key)
        if repeated['snapshot_id'] != job['snapshot_id']:
            raise AssertionError('Repeated backup request created a second job')
        return self.wait_job(job['snapshot_id'])

    def recovery_manifest(self, job, include):
        manifest = json.loads(self.request('GET', API + '/' + job['snapshot_id'] + '/download', binary=True))
        validate_capture(manifest, {'include_search_index': include, 'include_embeddings': include})
        self.record('online_recovery_manifest', passed=True, snapshot_id=job['snapshot_id'],
                    backup_options=manifest['backup_options'], capture=manifest['capture']['mode'])

    def scheduled_recovery(self):
        payload = {'name': 'Deployment once', 'starts_at': (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
                   'timezone': 'UTC', 'repeat': 'once', 'enabled': True,
                   'retention_hours': 1, 'never_expire': False}
        key = str(uuid.uuid4())
        schedule = self.request('POST', API + '/schedules', payload, idempotency=key)
        repeated = self.request('POST', API + '/schedules', payload, idempotency=key)
        schedule_id = schedule['schedule_id']
        if repeated['schedule_id'] != schedule_id:
            raise AssertionError('Repeated schedule request created a second schedule')
        def dispatched():
            items = self.request('GET', API + '/schedules?limit=100')['items']
            current = next(item for item in items if item['schedule_id'] == schedule_id)
            return current.get('last_snapshot_id')
        job = self.wait_job(self.poll('Scheduled backup dispatch', dispatched))
        if job['schedule_id'] != schedule_id or job['retention_hours'] != 1 or job['never_expire']:
            raise AssertionError('Scheduled backup did not retain its selected policy')
        expiry = (timestamp(job['expires_at']) - timestamp(job['finished_at'])).total_seconds()
        if abs(expiry - 3600) > 5:
            raise AssertionError('Scheduled backup expiry does not match its retention')
        self.request('DELETE', API + '/schedules/' + schedule_id)
        items = self.request('GET', API + '/schedules?limit=100')['items']
        if any(item['schedule_id'] == schedule_id for item in items):
            raise AssertionError('Deleted schedule remains in active schedule listing')
        self.record('scheduled_recovery_retention', passed=True, snapshot_id=job['snapshot_id'],
                    retention_hours=1, expiry_seconds=expiry, schedule_deleted=True,
                    automatic_expiry_elapsed=False)
        return job

    def export_import(self, source, profile='full', content_mode=None):
        exported = self.submit('export', source, profile, content_mode=content_mode)
        export_id = exported['snapshot_id']
        download_path = API + '/' + export_id + '/download'
        self.denied(download_path, None)
        self.denied(download_path, self.ordinary_token)
        archive = self.runtime / ('backup-' + export_id + '.zip')
        receipt = self.request('GET', download_path, destination=archive)
        if receipt['bytes'] != exported['archive_size']:
            raise AssertionError('Export download length differs from its catalog entry')
        with zipfile.ZipFile(archive) as contents:
            if not {'manifest.json', 'files.ndjson', 'validation.json', 'restore-metadata.json'}.issubset(contents.namelist()):
                raise AssertionError('Export lacks portable archive metadata')
            # The worker independently validates checksums during import; no extraction
            # or unbounded decompression of the downloadable archive happens here.
        uploaded = self.request('POST', API + '/uploads', {'name': archive.name, 'bytes': receipt['bytes']},
                                idempotency=str(uuid.uuid4()))
        upload_id, part_bytes = uploaded['snapshot']['snapshot_id'], uploaded['part_bytes']
        if not isinstance(part_bytes, int) or not 1 <= part_bytes <= 64 * 1024 * 1024:
            raise AssertionError('Invalid upload part size')
        with archive.open('rb') as stream:
            part = 0
            while chunk := stream.read(part_bytes):
                part += 1
                self.request('PUT', f'{API}/uploads/{upload_id}/parts/{part}', raw=chunk)
        self.request('POST', API + '/uploads/' + upload_id + '/complete')
        imported = self.wait_job(upload_id)
        if imported['profile'] != profile or (content_mode and imported['content_mode'] != content_mode):
            raise AssertionError('Validated upload changed the export privacy profile')
        self.record('authenticated_export_upload', passed=True, export_id=export_id, upload_id=upload_id,
                    profile=profile, content_mode=content_mode, parts=part, **receipt)
        archive.unlink()
        return export_id, upload_id

    def database_path(self):
        return f"/api/workspace/{self.fixture['workspace_id']}/database/{self.fixture['database_id']}"

    def verify_fixture(self, phase):
        self.login()
        token, fixture = self.ordinary_token, self.fixture
        workspaces = self.request('GET', '/api/workspace', token=token)
        if fixture['workspace_id'] not in [workspace['workspace_id'] for workspace in workspaces]:
            raise AssertionError('Fixture account lost its workspace access')
        for page_id, name in [(fixture['document_id'], fixture['document_name']),
                              (fixture['database_view_id'], fixture['database_name'])]:
            page = self.request('GET', f"/api/workspace/{fixture['workspace_id']}/page-view/{page_id}", token=token)
            if page['view']['name'] != name or page['view']['view_id'] != page_id:
                raise AssertionError('Restored page identity/name differs')
            if page_id == fixture['document_id'] and fixture['marker'].encode() not in bytes(page['data']['encoded_collab']):
                raise AssertionError('Restored document payload lacks its fixture marker')
        rows = self.request('GET', self.database_path() + '/row/detail?ids=' + self.row['row_id'], token=token)
        if len(rows) != 1 or rows[0]['cells'][self.row['field_name']] != self.row['expected_text']:
            raise AssertionError('Restored database row differs from captured value')
        path = f"/api/file_storage/{fixture['workspace_id']}/v1/blob/{fixture['document_id']}/{urllib.parse.quote(fixture['attachment_id'], safe='')}"
        attachment = self.request('GET', path, token=token, binary=True)
        if attachment != fixture['attachment_text'].encode():
            raise AssertionError('Restored attachment bytes differ')
        self.denied(API + '/capabilities', token)
        self.record('backup_fixture_readback', passed=True, phase=phase, owner_access=True,
                    ordinary_user_admin_denied=True, document_payload_marker=True, database_row=True,
                    attachment_sha256=hashlib.sha256(attachment).hexdigest())
        self.verify_search(phase)
        if self.verify:
            self.verify()

    def verify_search(self, phase):
        # Both positive controls must pass before a backup can claim included LMDB.
        for kind, identity in [('document', self.fixture['document_id']), ('database_row', self.row['row_id'])]:
            query = urllib.parse.urlencode({'query': self.fixture['marker'], 'mode': 'keyword', 'limit': 50})
            path = f"/api/search/{self.fixture['workspace_id']}?{query}"
            def found():
                results = self.request('GET', path, token=self.ordinary_token)
                return True if identity in json.dumps(results) else None
            self.poll('Restored ' + kind + ' Search', found)
            self.record('backup_keyword_search', passed=True, phase=phase, kind=kind, object_id=identity)

    def mutate_after_capture(self):
        value = 'uncaptured-' + uuid.uuid4().hex
        self.request('PATCH', self.database_path() + '/row/' + self.row['row_id'],
                     {'cells': {self.row['field_id']: value}, 'document': None, 'parse_link_as_link_preview': False},
                     token=self.ordinary_token)
        rows = self.request('GET', self.database_path() + '/row/detail?ids=' + self.row['row_id'], token=self.ordinary_token)
        if rows[0]['cells'][self.row['field_name']] != value:
            raise AssertionError('Post-capture mutation was not visible before restore')
        self.record('post_capture_mutation', passed=True, row_id=self.row['row_id'])

    def restore(self, source, label):
        if self.observe:
            self.observe('before_restore', source)
        job = self.request('POST', API + '/' + source + '/restore',
                           {'confirmation': 'RESTORE', 'maintenance_acknowledged': True},
                           idempotency=str(uuid.uuid4()))
        self.wait_job(job['snapshot_id'], restore=True)
        if self.observe:
            self.observe('after_restore', job['snapshot_id'])
        self.ready()
        self.verify_fixture(label)
        self.record('backup_restore', passed=True, source_id=source, snapshot_id=job['snapshot_id'], phase=label)

    def delete_artifact(self, snapshot_id):
        self.request('DELETE', API + '/' + snapshot_id)
        job = self.wait_job(snapshot_id, status='deleted')
        if job['archive_available'] or job['recovery_available']:
            raise AssertionError('Deleted artifact remains available in the catalog')
        try:
            self.request('GET', API + '/' + snapshot_id + '/download', binary=True)
        except RequestFailure as exc:
            if exc.status not in (404, 410):
                raise
        else:
            raise AssertionError('Deleted artifact remains downloadable')
        self.record('backup_artifact_deletion', passed=True, snapshot_id=snapshot_id)

    def run(self):
        try:
            self.login()
            self.ready()
            self.verify_fixture('before_backup')
            recovery = self.scheduled_recovery()
            self.recovery_manifest(recovery, include=False)
            exported, imported = self.export_import(recovery['snapshot_id'])
            self.mutate_after_capture()
            self.restore(imported, 'portable_zip')
            self.redeploy()
            self.ready()
            self.verify_fixture('ordinary_compose_redeploy')
            included = self.submit('recovery', include=True)
            self.recovery_manifest(included, include=True)
            self.mutate_after_capture()
            self.restore(included['snapshot_id'], 'retained_recovery_with_indexes')
            # Export/import every privacy profile against the current migrated schema.
            # Original account/content readback above applies to full restores only.
            for profile, mode in [('identity_redacted', None), ('sanitized_debug', 'synthetic'), ('sanitized_debug', 'empty')]:
                redacted, redacted_upload = self.export_import(included['snapshot_id'], profile, mode)
                self.delete_artifact(redacted_upload)
                self.delete_artifact(redacted)
            self.delete_artifact(imported)
            self.delete_artifact(exported)
            self.record('backup_suite', passed=True, limitations=[
                'No concurrent HTTP/WebSocket edit is asserted inside the capture interval.',
                'Document readback checks marker bytes; it does not decode current CRDT text.',
                'Embedding selection is checked; external AI embedding generation is not exercised.',
                'Schedule expiry metadata and manual deletion are checked; one-hour automatic expiry is not elapsed.',
                'Redacted exports are validated by import; redacted activation/account privacy is not independently verified.',
                'Coordinator interruption and rollback require the separate server qualification lane.',
            ])
            return self.events[-1]
        except Exception as exc:
            # Assertion text comes from this module; network bodies and credentials
            # are intentionally not copied into shareable evidence.
            self.record('backup_suite', passed=False, error=type(exc).__name__)
            raise
