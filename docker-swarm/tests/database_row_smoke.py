#!/usr/bin/env python3
"""Create/edit or verify one isolated Swarm test database row. No secrets printed."""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

root = Path(os.environ.get('SWARM_TEST_DIR', Path(__file__).resolve().parents[1] / '.local')).expanduser().resolve()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('phase', choices=['create', 'verify'])
parser.add_argument('--timeout', type=int, default=150, help='Seconds to wait for a temporary recovery fence')
args = parser.parse_args()
state = json.loads((root / 'api-state.json').read_text())
credential_path = root / 'ordinary-user.json'
if credential_path.stat().st_mode & 0o077:
    raise SystemExit('ordinary-user.json must have mode 0600')
creds = json.loads(credential_path.read_text())
metadata = json.loads((root / 'metadata.json').read_text())
base = os.environ.get('SWARM_TEST_BASE_URL', metadata['base_url']).rstrip('/')
if urllib.parse.urlsplit(base).hostname not in ('localhost', '127.0.0.1', '::1'):
    raise SystemExit('This script only accepts a loopback test URL')
phase = args.phase
token = None
events = []

def call(method, path, body=None):
    headers = {'Content-Type':'application/json', 'x-platform':'web'}
    if os.environ.get('SWARM_TEST_CLIENT_VERSION'):
        headers['client-version'] = os.environ['SWARM_TEST_CLIENT_VERSION']
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    deadline = time.monotonic() + args.timeout
    retries = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{method} {path}: HTTP {exc.code}') from None
        except Exception as exc:
            raise RuntimeError(f'{method} {path}: {type(exc).__name__}') from None
        # A restarted dependency may briefly fence database access while the
        # server recovers. Retry only this explicit read-only temporary error.
        if (method == 'GET' and result.get('code') == -5
                and 'database restore finalization is in progress' in result.get('message', '')
                and time.monotonic() < deadline):
            retries += 1
            time.sleep(2)
            continue
        if 'code' in result:
            assert result['code'] == 0, f"Application error {result['code']}: {result.get('message')}"
            if retries:
                record('recovery_fence_retry', passed=True, attempts=retries)
            return result.get('data')
        return result

def record(name, **details):
    events.append({'check':name, **details})
    print(json.dumps(events[-1]), flush=True)

try:
    token = call('POST', '/gotrue/token?grant_type=password', creds)['access_token']
    dbpath = f"/api/workspace/{state['workspace_id']}/database/{state['database_id']}"
    rowstate = root / 'database-row-state.json'
    if phase == 'create':
        fields = call('GET', dbpath + '/fields')
        primary = next(f for f in fields if f.get('is_primary'))
        initial = 'initial ' + state['marker']
        updated = 'updated ' + state['marker']
        rowid = call('POST', dbpath + '/row', {'cells':{primary['id']:initial},'document':None,'parse_link_as_link_preview':False})
        rows = call('GET', dbpath + '/row/detail?ids=' + rowid)
        assert len(rows) == 1 and rows[0]['id'] == rowid, 'Created row ID differs'
        assert rows[0]['cells'][primary['name']] == initial, 'Initial row cell text differs'
        record('create_read_database_row', passed=True, row_id=rowid)
        call('PATCH', dbpath + '/row/' + rowid, {'cells':{primary['id']:updated},'document':None,'parse_link_as_link_preview':False})
        rowstate.write_text(json.dumps({'row_id':rowid,'field_id':primary['id'],
                                      'field_name':primary['name'],'expected_text':updated}, indent=2)+'\n')
    row = json.loads(rowstate.read_text())
    field_name = row.get('field_name')
    if field_name is None:
        fields = call('GET', dbpath + '/fields')
        field_name = next(f['name'] for f in fields if f['id'] == row['field_id'])
    rows = call('GET', dbpath + '/row/detail?ids=' + row['row_id'])
    assert len(rows) == 1 and rows[0]['id'] == row['row_id'], 'Persisted row ID differs'
    assert rows[0]['cells'][field_name] == row['expected_text'], 'Updated row cell text differs'
    record('edit_read_database_row' if phase == 'create' else 'persisted_database_row', passed=True, row_id=row['row_id'])
except Exception as exc:
    message = str(exc)
    for value in (creds['email'], creds['password'], token):
        if value:
            message = message.replace(value, '[redacted]')
    record('database_row_suite', passed=False, phase=phase, error=message)
    raise SystemExit(1)
finally:
    (root / ('database-row.'+phase+'.results.json')).write_text(json.dumps(events,indent=2)+'\n')
