#!/usr/bin/env python3
"""Qualify Backup in an owned disposable Compose project on the local Docker engine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys

import yaml

from deployment import Deployment, private_write, sanitize
from configuration import SOURCE_FILES, source_fingerprint
from images import ROOT, clean_environment

OWNER_LABEL = 'io.appflowy.backup-qualification'


def ports():
    with socket.socket() as http, socket.socket() as tls:
        http.bind(('127.0.0.1', 0))
        tls.bind(('127.0.0.1', 0))
        return http.getsockname()[1], tls.getsockname()[1]


class LocalBackupDeployment(Deployment):
    def __init__(self, runtime, artifacts, lock, installed_source=False):
        runtime = runtime.resolve()
        allowed = (ROOT / 'ci/.local').resolve()
        if allowed not in runtime.parents:
            raise RuntimeError('Local Backup qualification must use a private child of ci/.local')
        self.owner_path = runtime / 'local-owner.json'
        if self.owner_path.is_symlink() or (self.owner_path.exists() and self.owner_path.stat().st_mode & 0o077):
            raise RuntimeError('Local qualification ownership must be a private regular file')
        owner = json.loads(self.owner_path.read_text()) if self.owner_path.exists() else None
        if owner is None and runtime.exists() and any(runtime.iterdir()):
            raise RuntimeError('Refusing to claim a nonempty runtime directory without ownership')
        if runtime in artifacts.resolve().parents or artifacts.resolve() == runtime:
            raise RuntimeError('Keep sanitized evidence outside the private runtime directory')
        name = 'appflowy-backup-check-' + hashlib.sha256(str(runtime).encode()).hexdigest()[:12]
        if owner and (owner.get('project') != name or owner.get('runtime') != str(runtime)):
            raise RuntimeError('Local qualification ownership does not match this directory')
        self.installed_lock = runtime / 'local-image-lock.json'
        if installed_source:
            if not owner or self.installed_lock.is_symlink() or not self.installed_lock.is_file():
                raise RuntimeError('Cleanup and diagnostics require the owned installed image/source lock')
            if self.installed_lock.stat().st_mode & 0o077:
                raise RuntimeError('Installed image/source lock must be private')
            lock = self.installed_lock
        http, tls = (owner['http_port'], owner['tls_port']) if owner else ports()
        super().__init__('compose', runtime, artifacts, lock, backup=True,
                         name=name, hostname='127.0.0.1:' + str(http), installed_source=installed_source)
        self.tls_port = tls
        self.pull_images = False
        self.owner = owner
        self.creating = False
        self.installed_source_only = installed_source
        # Never let the operator's application variables override the disposable
        # .env at startup after the clean render has already passed validation.
        self.env = {**clean_environment(), **{key: value for key, value in self.env.items()
                    if key.startswith('SWARM_TEST_') or key == 'SWARM_BROWSER_CHANNEL'}}
        if self.lock.get('local') is not True:
            raise RuntimeError('Local qualification requires images.py --local --backup')

    def owned_resources(self, kind):
        prefix = self.name + '_'
        all_ids = self.run('docker', kind, 'ls', '-q').split()
        labeled = self.run('docker', kind, 'ls', '-q', '--filter',
                           'label=com.docker.compose.project=' + self.name).split()
        if kind == 'volume':
            candidates = set(labeled) | {name for name in all_ids if name.startswith(prefix) or name == self.name}
            rows = json.loads(self.run('docker', 'volume', 'inspect', *sorted(candidates))) if candidates else []
        else:
            # Network ls returns IDs; inspect names as well so an unlabeled name
            # collision cannot be adopted by Compose.
            rows = json.loads(self.run('docker', 'network', 'inspect', *all_ids)) if all_ids else []
            rows = [row for row in rows if row['Id'] in labeled or row['Name'].startswith(prefix)
                    or row['Name'] == self.name]
        for row in rows:
            if not self.owner or (row.get('Labels') or {}).get(OWNER_LABEL) != self.owner['token']:
                raise RuntimeError('Refusing to modify ' + kind + ' resources not owned by this qualification')

    def guard(self):
        # Validate the effective endpoint as well as an explicit context. A remote context
        # cannot be hidden by setting a second local DOCKER_HOST value.
        context = json.loads(self.run('docker', 'context', 'inspect'))[0]
        context_endpoint = context['Endpoints']['docker']['Host']
        endpoint = (context_endpoint if self.env.get('DOCKER_CONTEXT')
                    else self.env.get('DOCKER_HOST') or context_endpoint)
        if not endpoint.startswith('unix://') or not context_endpoint.startswith('unix://'):
            raise RuntimeError('Local Backup qualification requires a local Unix Docker endpoint')
        if not self.owner and not self.creating:
            raise RuntimeError('This directory does not own a local Backup deployment; run up first')
        if self.owner and self.owner.get('endpoint') != endpoint:
            raise RuntimeError('The local qualification Docker endpoint changed')
        if self.installed_lock.exists():
            self.validate_installed_runtime()
        ids = self.run('docker', 'ps', '-aq', '--filter',
                       'label=com.docker.compose.project=' + self.name).split()
        if ids:
            records = json.loads(self.run('docker', 'inspect', *ids))
            if not self.owner or any((row.get('Config', {}).get('Labels') or {}).get(OWNER_LABEL)
                                     != self.owner['token'] for row in records):
                raise RuntimeError('Refusing to modify containers not owned by this qualification')
        self.owned_resources('volume')
        self.owned_resources('network')
        return endpoint

    def validate_installed_runtime(self):
        if self.installed_lock.is_symlink() or self.installed_lock.stat().st_mode & 0o077:
            raise RuntimeError('Installed image/source lock must be a private regular file')
        lock = json.loads(self.installed_lock.read_text())
        if source_fingerprint(self.source, lock.get('source_files')) != lock.get('source_sha256'):
            raise RuntimeError('Installed qualification source changed; refusing runtime operations')
        generated = lock.get('installed_files', {})
        if set(generated) != {'.env', 'ci.override.yml'}:
            raise RuntimeError('Installed qualification inputs are not recorded')
        for name, expected in generated.items():
            path = self.source / name
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError('Installed qualification environment or overrides changed')

    def render(self):
        if self.installed_source_only:
            raise RuntimeError('Installed source mode is restricted to cleanup and diagnostics')
        if not self.owner:
            raise RuntimeError('Create local qualification ownership before rendering')
        super().render()
        path = self.source / 'ci.override.yml'
        override = yaml.safe_load(path.read_text())
        for service in override['services'].values():
            service.setdefault('labels', {})[OWNER_LABEL] = self.owner['token']
            service['pull_policy'] = 'never'
        resolved = yaml.safe_load((self.runtime / 'compose.yml').read_text())
        for kind in ('volumes', 'networks'):
            names = set(resolved.get(kind, {}))
            if kind == 'networks':
                names.add('default')
            override[kind] = {name: {'labels': {OWNER_LABEL: self.owner['token']}} for name in names}
        self.write_backup_override(override)
        # Source port interpolation avoids Compose's list merge appending a
        # second public binding when a loopback binding is added via an override.
        env_path = self.source / '.env'
        lines = []
        for line in env_path.read_text().splitlines():
            if line.startswith(('NGINX_PORT=', 'NGINX_TLS_PORT=')):
                key, value = line.split('=', 1)
                line = key + '=127.0.0.1:' + value
            lines.append(line)
        private_write(env_path, '\n'.join(lines) + '\n')
        self.run(*self.compose, 'config', '--quiet', env=clean_environment())
        if source_fingerprint(self.source) != self.lock['source_sha256']:
            raise RuntimeError('Deployment source changed while preparing qualification')
        private_write(self.installed_lock, json.dumps({**self.lock, 'source_files': list(SOURCE_FILES),
            'installed_files': {name: hashlib.sha256((self.source / name).read_bytes()).hexdigest()
                                for name in ('.env', 'ci.override.yml')}}))

    def up(self):
        if self.owner:
            raise RuntimeError('Use a new runtime directory for each qualification; existing runs support test, diagnostics and cleanup')
        self.creating = True
        try:
            endpoint = self.guard()
            if not self.owner:
                self.runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
                self.runtime.chmod(0o700)
                self.owner = {'project': self.name, 'runtime': str(self.runtime),
                              'http_port': int(self.hostname.rpartition(':')[2]),
                              'tls_port': self.tls_port, 'endpoint': endpoint,
                              'token': secrets.token_hex(32)}
                private_write(self.owner_path, json.dumps(self.owner))
            super().up()
        finally:
            self.creating = False

    def backup_test(self):
        if self.installed_source_only:
            raise RuntimeError('Installed source mode is restricted to cleanup and diagnostics')
        self.guard()
        (self.artifacts / 'backup-acceptance.json').unlink(missing_ok=True)
        self.smoke('create')
        from backup_smoke import BackupSmoke
        from backup_observer import ComposeRestoreObserver
        result = BackupSmoke(self.runtime, self.base_url, verify=None,
                             redeploy=self.backup_redeploy, evidence=self.evidence,
                             observe=ComposeRestoreObserver(self.runtime, self.run, self.docker_containers, self.evidence),
                             timeout=1800).run()
        self.check_images('backup-images.json')
        self.evidence('backup-acceptance.json', result)

    def test(self):
        if self.installed_source_only:
            raise RuntimeError('Installed source mode is restricted to cleanup and diagnostics')
        return super().test()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['up', 'test', 'backup-test', 'diagnostics', 'cleanup'])
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--images', type=Path, required=True)
    args = parser.parse_args()
    deployment = LocalBackupDeployment(args.runtime, args.artifacts, args.images,
                                      installed_source=args.action in ('cleanup', 'diagnostics'))
    try:
        getattr(deployment, args.action.replace('-', '_'))()
    except Exception as exc:
        print(sanitize(str(exc), deployment.runtime), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
