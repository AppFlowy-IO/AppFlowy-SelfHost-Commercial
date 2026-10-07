#!/usr/bin/env python3
"""Resolve the root Compose images once for every deployment job in this run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import tempfile

import yaml
from configuration import check_compose, isolated_source, source_fingerprint

ROOT = Path(__file__).resolve().parents[1]
CORE = {'nginx', 'postgres', 'redis', 'minio', 'gotrue', 'appflowy_cloud',
        'appflowy_worker', 'appflowy_search', 'appflowy_web', 'admin_frontend'}
SERVER = {'appflowy_cloud', 'appflowy_worker', 'appflowy_search', 'appflowy_backup'}


def clean_environment():
    # Compose must never inherit application credentials or automatically read .env.
    allowed = {'PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR', 'LANG', 'LC_ALL', 'DOCKER_HOST',
               'DOCKER_CONTEXT', 'DOCKER_CONFIG', 'DOCKER_CERT_PATH', 'DOCKER_TLS_VERIFY',
               'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
               'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
               'SSL_CERT_FILE', 'SSL_CERT_DIR'}
    return {key: value for key, value in os.environ.items() if key in allowed}


def command(*args):
    registry_read = len(args) > 2 and args[1] == 'buildx'
    for attempt in range(3 if registry_read else 1):
        result = subprocess.run(args, text=True, capture_output=True, env=clean_environment(), timeout=180)
        if not result.returncode:
            return result.stdout
        if registry_read and attempt < 2:
            time.sleep(3)
    # Compose output can contain credentials; only registry-read errors are safe
    # to show, after removing any URL userinfo from proxy/network diagnostics.
    detail = re.sub(r'(https?://)[^/@\s]+@', r'\1[redacted]@', result.stderr[-2000:]) if registry_read else ''
    raise RuntimeError(f'{args[0]} {args[1]} failed with exit {result.returncode}: {detail}')


def repository(image):
    name = image.split('@')[0]
    return name.rsplit(':', 1)[0] if ':' in name.rsplit('/', 1)[-1] else name


def resolve_image(name, source):
    descriptor = json.loads(command('docker', 'buildx', 'imagetools', 'inspect', source,
                                    '--format', '{{json .Manifest}}'))
    if descriptor.get('manifests'):
        candidates = [row for row in descriptor['manifests']
                      if row.get('platform', {}).get('os') == 'linux'
                      and row.get('platform', {}).get('architecture') == 'amd64']
        if len(candidates) != 1:
            raise RuntimeError(f'{name}: expected one linux/amd64 manifest')
        digest = candidates[0]['digest']
    else:
        digest = descriptor['digest']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise RuntimeError(f'{name}: invalid registry digest')
    pinned = repository(source) + '@' + digest
    if not descriptor.get('manifests'):
        image_config = json.loads(command('docker', 'buildx', 'imagetools', 'inspect', pinned,
                                          '--format', '{{json .Image}}'))
        if image_config.get('os') != 'linux' or image_config.get('architecture') != 'amd64':
            raise RuntimeError(f'{name}: the single manifest is not linux/amd64')
    manifest = json.loads(command('docker', 'buildx', 'imagetools', 'inspect', pinned, '--raw'))
    print(f'{name}: {pinned}', flush=True)
    return {'source': source, 'image': pinned, 'digest': digest,
            'config_digest': manifest['config']['digest'], 'platform': 'linux/amd64'}


def resolve_local_image(name, source):
    """Pin an already built native image by immutable configuration ID; never pull implicitly."""
    records = json.loads(command('docker', 'image', 'inspect', source))
    if len(records) != 1:
        raise RuntimeError(name + ': expected one local image')
    value = records[0]
    platform = command('docker', 'info', '--format', '{{.OSType}}/{{.Architecture}}').strip()
    platform = platform.replace('aarch64', 'arm64').replace('x86_64', 'amd64')
    if value['Os'] + '/' + value['Architecture'] != platform:
        raise RuntimeError(name + ': local image does not match the Docker engine platform')
    digest = value['Id']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise RuntimeError(name + ': invalid local image identity')
    print(name + ': ' + digest, flush=True)
    return {'source': source, 'image': digest, 'config_digest': digest, 'platform': platform}


def chart_redis_image():
    rendered = command('helm', 'template', 'appflowy-ci', str(ROOT / 'helm/appflowy-cloud'),
                       '--namespace', 'appflowy-ci', '-f', str(ROOT / 'ci/helm-values.yaml'))
    images = [container['image'] for document in yaml.safe_load_all(rendered)
              if document and document.get('kind') == 'StatefulSet'
              and document['metadata']['name'] == 'appflowy-ci-redis-master'
              for container in document['spec']['template']['spec']['containers']
              if container['name'] == 'redis']
    if len(images) != 1:
        raise RuntimeError('Expected exactly one Redis container from the normal Helm templates')
    return images[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--server-tag', help='CI-only tag for Cloud, Worker, Search and optional Backup')
    parser.add_argument('--backup', action='store_true', help='Resolve the optional Backup image too')
    parser.add_argument('--backup-image', help='Explicit Backup build to qualify; recorded in the image lock')
    parser.add_argument('--local', action='store_true', help='Pin already installed native images for isolated local qualification')
    parser.add_argument('--helm-redis', action='store_true',
                        help="Append the chart's Redis image lock in the Helm job; never replace it with Compose Redis")
    args = parser.parse_args()
    if args.server_tag and not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', args.server_tag):
        parser.error('--server-tag must be a valid Docker image tag')
    if args.helm_redis:
        lock = json.loads(args.output.read_text())
        lock['helm_services'] = {'redis': resolve_image('helm Redis', chart_redis_image())}
        args.output.write_text(json.dumps(lock, indent=2) + '\n')
        return
    check_compose(clean_environment())
    with tempfile.TemporaryDirectory(prefix='appflowy-image-source-') as directory:
        source = isolated_source(Path(directory))
        config = json.loads(command('docker', 'compose', '--env-file', str(source / 'deploy.env'),
                                    '-f', str(source / 'docker-compose.yml'), 'config', '--format', 'json'))
        backup_config = json.loads(command('docker', 'compose', '--env-file', str(source / 'deploy.env'),
                                    '-f', str(source / 'docker-compose.yml'),
                                    '-f', str(source / 'docker-compose.backup.yml'), '--profile', 'backup',
                                    'config', '--format', 'json')) if args.backup else None
    if set(config['services']) - {'ai'} != CORE:
        raise RuntimeError('Core services changed; update the runtime acceptance coverage explicitly')
    records = {}
    resolver = resolve_local_image if args.local else resolve_image

    def resolve_selected(name, configured_source, explicit_source=None):
        selected = explicit_source or (repository(configured_source) + ':' + args.server_tag
            if args.server_tag and name in SERVER else configured_source)
        record = resolver(name, selected)
        if selected != configured_source:
            record['configured_source'] = configured_source
        return record

    for name in sorted(CORE):
        records[name] = resolve_selected(name, config['services'][name]['image'])
    lock = {'platform': 'linux/amd64', 'services': records,
            'compose_sha256': hashlib.sha256((ROOT / 'docker-compose.yml').read_bytes()).hexdigest(),
            'source_sha256': source_fingerprint(),
            'scope': 'Core deployment; paid external AI providers, SMTP, TLS, Redis queue persistence, upgrades and HA are not tested'}
    if args.backup:
        lock['backup_services'] = {'appflowy_backup': resolve_selected('appflowy_backup',
            backup_config['services']['appflowy_backup']['image'], args.backup_image)}
    elif args.backup_image:
        raise RuntimeError('--backup-image requires --backup')
    if args.local:
        lock['platform'] = next(iter(records.values()))['platform']
        lock['local'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(lock, indent=2) + '\n')


if __name__ == '__main__':
    main()
