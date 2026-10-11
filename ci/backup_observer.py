"""Independent, read-only Docker/PostgreSQL observations around Compose restore."""
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit


RESOURCE_SERVICES = ('appflowy_cloud', 'appflowy_worker', 'appflowy_search')
REDIS_KEYS = {'appflowy_cloud': 'APPFLOWY_REDIS_URI', 'appflowy_worker': 'APPFLOWY_WORKER_REDIS_URL',
              'appflowy_search': 'APPFLOWY_SEARCH_REDIS_URL'}


def environment(container):
    return dict(value.split('=', 1) for value in container['Config']['Env'] if '=' in value)


def redis_namespace(value):
    parsed = urlsplit(value)
    database = parsed.path.lstrip('/') or '0'
    if parsed.scheme not in ('redis', 'rediss') or not parsed.hostname or not database.isdecimal():
        raise RuntimeError('Writer has an invalid Redis namespace')
    return parsed.scheme, parsed.hostname, parsed.port or 6379, int(database)


def writer_stop_evidence(events, before, started_ns):
    """Require a Docker die event for every old writer before any writer starts.

    Docker retains recent lifecycle events independently of the HTTP polling loop.
    If the bounded daemon history no longer contains the evidence, fail rather than
    claiming that observing a final stopped/replaced process proves coordinated drain.
    """
    deaths, starts = {}, []
    for event in events:
        when = event.get('timeNano', int(event.get('time', 0)) * 1_000_000_000)
        if when < started_ns:
            continue
        actor = event.get('Actor', {})
        identity = actor.get('ID', event.get('id'))
        action = event.get('Action', event.get('status'))
        service = actor.get('Attributes', {}).get('com.docker.compose.service')
        if action == 'die' and identity in before.values():
            deaths[identity] = min(deaths.get(identity, when), when)
        if action == 'start' and service in before:
            starts.append(when)
    if set(deaths) != set(before.values()):
        raise RuntimeError('Docker lifecycle history does not prove every previous writer stopped')
    if not starts or min(starts) < max(deaths.values()):
        raise RuntimeError('Docker lifecycle history does not prove writers drained before restart')
    return {'writer_stop_events': len(deaths), 'all_stopped_before_first_restart': True}


class ComposeRestoreObserver:
    def __init__(self, runtime, run, containers, evidence):
        self.runtime, self.run, self.containers, self.evidence = Path(runtime), run, containers, evidence
        self.before = None

    def one(self, service):
        rows = self.containers(service)
        if len(rows) != 1 or not rows[0]['State']['Running']:
            raise RuntimeError('Restore observation requires one running ' + service)
        return rows[0]

    def postgres_oid(self):
        postgres = self.one('postgres')
        # Credentials remain in the existing container environment; only a SELECT
        # is executed over the managed PostgreSQL Unix socket.
        result = self.run('docker', 'exec', postgres['Id'], 'sh', '-ec',
            'exec psql --no-psqlrc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At '
            '-c "SELECT oid FROM pg_database WHERE datname=current_database()"', timeout=30).strip()
        if not result.isdecimal():
            raise RuntimeError('Managed PostgreSQL returned no database identity')
        return int(result)

    def snapshot(self):
        return {name: self.one(name) for name in self.writers}

    def __call__(self, event, snapshot_id):
        if event == 'before_restore':
            self.started_ns = time.time_ns()
            backup = self.one('appflowy_backup')
            configured = environment(backup).get('APPFLOWY_BACKUP_COMPOSE_WRITERS')
            self.writers = json.loads(configured) if configured else []
            if (not isinstance(self.writers, list) or not all(isinstance(name, str) for name in self.writers)
                    or len(set(self.writers)) != len(self.writers)
                    or not set(RESOURCE_SERVICES + ('gotrue',)).issubset(self.writers)):
                raise RuntimeError('Backup observer requires an explicit complete writer inventory')
            self.before = self.snapshot()
            projects = {row['Config']['Labels']['com.docker.compose.project'] for row in self.before.values()}
            if len(projects) != 1:
                raise RuntimeError('Restore writers do not belong to the same isolated project')
            self.project = projects.pop()
            self.old_oid = self.postgres_oid()
            self.observed_all_stopped = False
            return
        if self.before is None:
            raise RuntimeError('Restore observation was not initialized')
        if event == 'restore_poll':
            active = [name for name in self.writers
                      if any(row['State']['Running'] for row in self.containers(name))]
            self.observed_all_stopped |= not active
            return
        if event != 'after_restore':
            raise ValueError('Unknown restore observation event')
        after, new_oid = self.snapshot(), self.postgres_oid()
        if new_oid == self.old_oid:
            raise RuntimeError('Restore did not switch the PostgreSQL database identity')
        for name, old in self.before.items():
            # ComposeOwner captures GoTrue and restarts its same container after
            # the database rename; resource-selection writers are recreated.
            if name != 'gotrue' and old['Id'] == after[name]['Id']:
                raise RuntimeError('Restore did not replace writer ' + name)
            if environment(after[name]).get('APPFLOWY_RESTORE_VERIFY_ONLY', 'false') != 'false':
                raise RuntimeError('Restore left a writer in verification-only mode')
        old_ids = {name: row['Id'] for name, row in self.before.items()}
        start = f'{self.started_ns // 1_000_000_000}.{self.started_ns % 1_000_000_000:09d}'
        ended_ns = time.time_ns()
        end = f'{ended_ns // 1_000_000_000}.{ended_ns % 1_000_000_000:09d}'
        raw = self.run('docker', 'events', '--since', start, '--until', end,
            '--filter', 'type=container', '--filter', 'label=com.docker.compose.project=' + self.project,
            '--format', '{{json .}}', timeout=30)
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        drain = writer_stop_evidence(events, old_ids, self.started_ns)
        selections = self.validate_selections(after)
        self.evidence('backup-restore-' + snapshot_id + '.json', {
            'passed': True, 'snapshot_id': snapshot_id, 'old_database_oid': self.old_oid,
            'new_database_oid': new_oid, 'observed_all_stopped_during_poll': self.observed_all_stopped,
            **drain, 'selection_sha256': selections,
            'writers': {name: {'before': old_ids[name], 'after': after[name]['Id']} for name in self.writers}})
        self.before = None

    def validate_selections(self, after):
        bucket, redis, generation, result = None, None, None, {}
        directory = self.runtime / 'deployment/backup-ops/runtime'
        for name in self.writers:
            current, original = environment(after[name]), environment(self.before[name])
            if name == 'gotrue':
                continue
            path = directory / ('selection-' + name + '.env')
            if path.is_symlink() or not path.is_file():
                raise RuntimeError('Restore did not persist a writer selection file')
            persisted = dict(line.split('=', 1) for line in path.read_text().splitlines()
                             if line and not line.startswith('#') and '=' in line)
            if 'APPFLOWY_RESTORE_VERIFY_ONLY' in persisted:
                raise RuntimeError('Temporary verification mode escaped into persistent deployment state')
            if not persisted or any(current.get(key) != value for key, value in persisted.items()):
                raise RuntimeError('Persisted selection differs from running writer ' + name)
            if name not in RESOURCE_SERVICES:
                continue
            selected_bucket = current['APPFLOWY_S3_BUCKET']
            selected_redis = redis_namespace(current[REDIS_KEYS[name]])
            if selected_bucket == original['APPFLOWY_S3_BUCKET'] or selected_redis == redis_namespace(original[REDIS_KEYS[name]]):
                raise RuntimeError('Restore reused a previous active storage namespace')
            if selected_redis[-1] == 0:
                raise RuntimeError('Restore did not select a reserved nonzero Redis database')
            if bucket is not None and (bucket != selected_bucket or redis != selected_redis):
                raise RuntimeError('Application writers selected different restored resources')
            bucket, redis = selected_bucket, selected_redis
            keys = ['APPFLOWY_S3_BUCKET', REDIS_KEYS[name]]
            if name in ('appflowy_cloud', 'appflowy_search'):
                key = 'APPFLOWY_KEYWORD_INDEX_DIR'
                if not current.get(key) or current[key] == original.get(key):
                    raise RuntimeError('Restore did not select a fresh Search directory')
                selected_generation = Path(current[key]).name
                if (not selected_generation.startswith('restore-')
                        or generation is not None and selected_generation != generation):
                    raise RuntimeError('Cloud and Search selected different index generations')
                generation = selected_generation
                keys.append(key)
            if not set(keys).issubset(persisted):
                raise RuntimeError('Restored selections are missing from persistent deployment state')
            result[name] = {key: hashlib.sha256(current[key].encode()).hexdigest() for key in keys}
        return result
