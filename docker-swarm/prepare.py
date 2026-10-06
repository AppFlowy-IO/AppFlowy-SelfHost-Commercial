#!/usr/bin/env python3
"""Generate an isolated, staged single-node Swarm experiment; never read .env."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get('SWARM_TEST_DIR', str(REPO / 'docker-swarm/.local'))).expanduser().resolve()
PREVIOUS = json.loads((OUT / 'metadata.json').read_text()) if (OUT / 'metadata.json').exists() else {}
STACK = os.environ.get('SWARM_STACK_NAME', PREVIOUS.get('stack_name', 'af-swarm-local'))
HTTP_PORT = int(os.environ.get('SWARM_HTTP_PORT', urlparse(PREVIOUS.get('base_url', '')).port or 18080))
TLS_PORT = int(os.environ.get('SWARM_TLS_PORT', urlparse(PREVIOUS.get('optional_tls_url', '')).port or 18443))
BASE_URL = f'http://localhost:{HTTP_PORT}'
WS_URL = f'ws://localhost:{HTTP_PORT}/ws/v2'


def pin_local_images(services: dict, process_env: dict) -> dict:
    """Use the exact native-platform images already pulled by the operator."""
    engine = subprocess.run(
        ['docker', 'info', '--format', '{{.OSType}}/{{.Architecture}}'],
        env=process_env, text=True, capture_output=True,
    )
    if engine.returncode:
        raise SystemExit('Docker engine is unavailable. Start Docker, then rerun prepare.py.')
    platform = engine.stdout.strip().replace('aarch64', 'arm64').replace('x86_64', 'amd64')
    records = {}
    for name, service in services.items():
        source = service['image']
        if os.environ.get('SWARM_PULL_IMAGES') == '1':
            print(f'Pulling {source}', flush=True)
            subprocess.run(['docker', 'pull', '--platform', platform, source], env=process_env, check=True)
        inspected = subprocess.run(['docker', 'image', 'inspect', source], env=process_env, text=True, capture_output=True)
        if inspected.returncode:
            raise SystemExit(f'Missing local image {source}. Run: docker pull {source}; then rerun prepare.py.')
        value = json.loads(inspected.stdout)[0]
        actual_platform = f"{value['Os']}/{value['Architecture']}"
        if actual_platform != platform:
            raise SystemExit(f'Image {source} is {actual_platform}, but Docker is {platform}. '
                             f'Run: docker pull --platform {platform} {source}; then rerun prepare.py.')
        digests = value.get('RepoDigests', [])
        if not digests:
            raise SystemExit(f'Image {source} has no registry digest. Run: docker pull {source}; then rerun prepare.py.')
        repository = source.split('@')[0]
        if ':' in repository.rsplit('/', 1)[-1]:
            repository = repository.rsplit(':', 1)[0]
        normalize = lambda s: s.removeprefix('docker.io/').removeprefix('library/')
        digest = next((d for d in digests if normalize(d.split('@')[0]) == normalize(repository)), None)
        if digest is None:
            raise SystemExit(f'No matching repository digest for {source}. Run: docker pull {source}; then rerun prepare.py.')
        service['image'] = digest
        records[name] = {'source': source, 'digest': digest, 'id': value['Id'], 'architecture': value['Architecture']}
    return records


def private_write(path: Path, contents: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(contents)
    path.chmod(0o600)


def main() -> None:
    subprocess.run([sys.executable, str(REPO / 'docker-swarm/generate.py'), '--check'], check=True)
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', STACK):
        raise SystemExit('SWARM_STACK_NAME must contain only lowercase letters, digits, underscores, or hyphens.')
    if not (1 <= HTTP_PORT <= 65535 and 1 <= TLS_PORT <= 65535 and HTTP_PORT != TLS_PORT):
        raise SystemExit('SWARM_HTTP_PORT and SWARM_TLS_PORT must be distinct valid TCP ports.')
    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    credentials_file = OUT / 'credentials.json'
    if credentials_file.exists():
        credentials = json.loads(credentials_file.read_text())
    else:
        credentials = {
            'admin_email': f'swarm-smoke-{secrets.token_hex(4)}@example.com',
            'admin_password': secrets.token_urlsafe(30),
            'postgres_password': secrets.token_hex(24),
            'jwt_secret': secrets.token_hex(32),
            's3_access_key': 'swarm' + secrets.token_hex(8),
            's3_secret_key': secrets.token_hex(24),
        }
        private_write(credentials_file, json.dumps(credentials, indent=2) + '\n')
    credentials_file.chmod(0o600)

    overrides = {
        'FQDN': f'localhost:{HTTP_PORT}',
        'SCHEME': 'http', 'WS_SCHEME': 'ws',
        'APPFLOWY_BASE_URL': BASE_URL,
        'APPFLOWY_WEBSOCKET_BASE_URL': WS_URL,
        'APPFLOWY_WEB_URL': BASE_URL,
        'NGINX_PORT': str(HTTP_PORT), 'NGINX_TLS_PORT': str(TLS_PORT),
        'POSTGRES_PASSWORD': credentials['postgres_password'],
        'GOTRUE_ADMIN_EMAIL': credentials['admin_email'],
        'GOTRUE_ADMIN_PASSWORD': credentials['admin_password'],
        'GOTRUE_JWT_SECRET': credentials['jwt_secret'],
        'GOTRUE_MAILER_AUTOCONFIRM': 'true',
        'GOTRUE_DISABLE_SIGNUP': 'false',
        'AWS_ACCESS_KEY': credentials['s3_access_key'],
        'AWS_SECRET': credentials['s3_secret_key'],
        'GOTRUE_SMTP_HOST': '127.0.0.1', 'GOTRUE_SMTP_PORT': '2525',
        'GOTRUE_SMTP_USER': '', 'GOTRUE_SMTP_PASS': '',
        'GOTRUE_SMTP_ADMIN_EMAIL': credentials['admin_email'],
        'APPFLOWY_MAILER_SMTP_HOST': '127.0.0.1',
        'APPFLOWY_MAILER_SMTP_PORT': '2525',
        'APPFLOWY_MAILER_SMTP_USERNAME': '',
        'APPFLOWY_MAILER_SMTP_EMAIL': credentials['admin_email'],
        'APPFLOWY_MAILER_SMTP_PASSWORD': '',
        'APPFLOWY_MAILER_SMTP_TLS_KIND': 'none',
        'APPFLOWY_DATABASE_MAX_CONNECTIONS': '20',
        'AI_ENABLED': 'false', 'AI_TEST_ENABLED': 'false',
        'AI_OPENAI_API_KEY': '', 'AI_OPENAI_API_SUMMARY_MODEL': '',
        'AZURE_OPENAI_API_KEY': '', 'AZURE_OPENAI_ENDPOINT': '',
        'AZURE_OPENAI_API_VERSION': '',
        'AI_SERVER_HOST': '127.0.0.1',
        'ASSEMBLYAI_API_KEY': '',
        'ASSEMBLYAI_API_BASE': 'http://127.0.0.1:9',
        'ASSEMBLYAI_STREAMING_API_BASE': 'ws://127.0.0.1:9',
        'APPFLOWY_INDEXER_ENABLED': 'false',
        'APPFLOWY_BACKGROUND_INDEXER_ENABLED': 'false',
        'APPFLOWY_INDEXER_DATABASE_ENABLED': 'false',
        'APPFLOWY_KEYWORD_SEARCH_ENABLED': 'true',
        'APPFLOWY_KEYWORD_INDEX_MAP_SIZE_BYTES': '268435456',
        'SIGNUP_WHITELIST_ENABLED': 'false',
        'GUEST_INVITES_REQUIRE_ADMIN_APPROVAL': 'false',
        'CLOUDFLARE_TUNNEL_TOKEN': '',
    }
    # Replace in place: dependent URLs in deploy.env resolve the new credentials.
    # Explicit --env-file plus a sanitized process environment avoids real .env.
    env_source = (REPO / 'deploy.env').read_text()
    seen = set()
    lines = []
    for line in env_source.splitlines():
        match = re.match(r'^([A-Z][A-Z0-9_]*)=', line)
        if match and match[1] in overrides:
            key = match[1]
            line = f'{key}={overrides[key]}'
            seen.add(key)
        lines.append(line)
    lines.extend(f'{key}={value}' for key, value in overrides.items() if key not in seen)
    env_file = OUT / 'test.env'
    private_write(env_file, '\n'.join(lines) + '\n')
    process_env = {
        key: value for key, value in os.environ.items()
        if key in {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'DOCKER_HOST',
                   'DOCKER_CONTEXT', 'DOCKER_CONFIG', 'DOCKER_CERT_PATH',
                   'DOCKER_TLS_VERIFY', 'DOCKER_API_VERSION'}
    }
    result = subprocess.run(
        ['docker', 'compose', '--env-file', str(env_file),
         '--project-directory', str(REPO / 'docker-swarm'), '-p', STACK, '-f',
         str(REPO / 'docker-swarm/docker-stack.yml'), 'config', '--format', 'json'],
        env=process_env, text=True, capture_output=True,
    )
    if result.returncode:
        private_write(OUT / 'compose-config-error.txt', result.stderr)
        raise SystemExit('Compose expansion failed; private details: compose-config-error.txt')
    private_write(OUT / 'compose-config-warnings.txt', result.stderr)
    resolved = json.loads(result.stdout)
    services = resolved['services']
    services.pop('ai', None)
    pinned_images = pin_local_images(services, process_env)
    initial_services = {'postgres', 'redis', 'minio'}
    limits = {
        'postgres': '768M', 'redis': '256M', 'minio': '512M',
        'gotrue': '256M', 'appflowy_cloud': '1024M',
        'appflowy_search': '768M', 'appflowy_worker': '512M',
        'appflowy_web': '512M', 'admin_frontend': '128M', 'nginx': '128M',
    }
    for name, service in services.items():
        for key in ('depends_on', 'restart', 'container_name', 'name'):
            service.pop(key, None)
        for key in ('command', 'entrypoint'):
            if service.get(key) is None:
                service.pop(key, None)
        service['networks'] = ['default']
        service['deploy'] = {
            'replicas': int(name in initial_services),
            'restart_policy': {'condition': 'on-failure', 'delay': '5s'},
            'resources': {'limits': {'memory': limits[name]}},
            'update_config': {'parallelism': 1, 'order': 'stop-first'},
        }
        # A bounded local log size keeps the smoke test from consuming disk.
        service['logging'] = {
            'driver': 'json-file',
            'options': {'max-size': '10m', 'max-file': '2'},
        }
        for volume in service.get('volumes', []):
            if 'bind' in volume:
                volume['bind'].pop('create_host_path', None)
                if not volume['bind']:
                    volume.pop('bind')
        for port in service.get('ports', []):
            if 'published' in port:
                port['published'] = int(port['published'])
        if name in {'postgres', 'minio', 'appflowy_search'}:
            service['deploy']['placement'] = {
                'constraints': ['node.labels.appflowy-swarm-test == true'],
            }

    services['appflowy_cloud']['healthcheck']['start_period'] = '120s'
    # The upstream compose hard-codes the background indexer to true; override it.
    for name in ('appflowy_cloud', 'appflowy_search', 'appflowy_worker'):
        services[name]['environment'].update({
            'AI_ENABLED': 'false',
            'APPFLOWY_INDEXER_ENABLED': 'false',
            'APPFLOWY_BACKGROUND_INDEXER_ENABLED': 'false',
            'APPFLOWY_INDEXER_DATABASE_ENABLED': 'false',
        })
    # Preserve runtime shell variables. Compose config retains $$ escapes;
    # this generated YAML is parsed exactly once by docker stack deploy.
    search_test = services['appflowy_search']['healthcheck']['test']
    if '$${APPFLOWY_SEARCH_PORT' not in search_test[-1] or '$$status' not in search_test[-1]:
        raise SystemExit('Unexpected Compose dollar escaping in Search healthcheck; inspect privately')

    nginx_conf = OUT / 'nginx.conf'
    certificate = OUT / 'certificate.crt'
    private_key = OUT / 'private_key.key'
    for source, target in (
        (REPO / 'docker/nginx/nginx.conf', nginx_conf),
        (REPO / 'docker/nginx/ssl/certificate.crt', certificate),
        (REPO / 'docker/nginx/ssl/private_key.key', private_key),
    ):
        private_write(target, source.read_text())
    services['nginx'].pop('volumes', None)
    services['nginx']['configs'] = [
        {'source': 'nginx_config', 'target': '/etc/nginx/nginx.conf'},
        {'source': 'tls_certificate', 'target': '/etc/nginx/ssl/certificate.crt'},
    ]
    services['nginx']['secrets'] = [
        {'source': 'tls_private_key', 'target': '/etc/nginx/ssl/private_key.key', 'mode': 0o400},
    ]
    source_volumes = yaml.safe_load((REPO / 'docker-swarm/docker-stack.yml').read_text()).get('volumes', {})
    if any(value for value in source_volumes.values()):
        raise SystemExit('The source now customizes volume storage. Review isolation before using the local test profile.')
    stack = {
        'version': '3.8', 'services': services,
        'networks': {'default': {'driver': 'overlay', 'attachable': True}},
        'volumes': {name: {} for name in source_volumes},
        'configs': {
            'nginx_config': {'file': str(nginx_conf)},
            'tls_certificate': {'file': str(certificate)},
        },
        'secrets': {'tls_private_key': {'file': str(private_key)}},
    }
    stack_file = OUT / 'docker-stack.yml'
    private_write(stack_file, yaml.safe_dump(stack, sort_keys=False))
    # Validate the generated file without downloading a separate schema.
    # This is Compose parsing, not a claim of complete Swarm compatibility.
    parsed = subprocess.run(
        ['docker', 'compose', '--env-file', str(env_file), '-p', STACK,
         '-f', str(stack_file), 'config', '--quiet'],
        env=process_env, text=True, capture_output=True,
    )
    private_write(OUT / 'generated-config-warnings.txt', parsed.stderr)
    if parsed.returncode:
        raise SystemExit('Generated config failed Compose parsing; private details: generated-config-warnings.txt')
    help_result = subprocess.run(['docker', 'stack', '--help'], env=process_env, text=True, capture_output=True)
    native_validation = 'deferred to docker stack deploy (this CLI lacks docker stack config)'
    if re.search(r'^\s+config\s', help_result.stdout, re.MULTILINE):
        checked = subprocess.run(['docker', 'stack', 'config', '--compose-file', str(stack_file)],
                                 env=process_env, text=True, capture_output=True)
        private_write(OUT / 'stack-config-warnings.txt', checked.stderr)
        if checked.returncode:
            raise SystemExit('Generated config failed native stack parsing; private details: stack-config-warnings.txt')
        native_validation = 'docker stack config passed'
        # Discard rendered stdout: piping it into deploy would interpolate twice.
    private_write(OUT / 'images.json', json.dumps(pinned_images, indent=2) + '\n')
    metadata = {
        'stack_name': STACK, 'repository': str(REPO),
        'base_url': BASE_URL, 'websocket_url': WS_URL,
        'optional_tls_url': f'https://localhost:{TLS_PORT}',
        'stack_file': str(stack_file), 'credentials_file': str(credentials_file),
        'compose_sha256': hashlib.sha256((REPO / 'docker-compose.yml').read_bytes()).hexdigest(),
        'swarm_source_sha256': hashlib.sha256((REPO / 'docker-swarm/docker-stack.yml').read_bytes()).hexdigest(),
        'deploy_env_sha256': hashlib.sha256((REPO / 'deploy.env').read_bytes()).hexdigest(),
        'images': {name: service['image'] for name, service in services.items()},
        'environment_keys': {name: sorted(service.get('environment', {})) for name, service in services.items()},
        'initial_services': sorted(initial_services),
        'stages': [sorted(initial_services), ['gotrue'], ['appflowy_cloud'],
                   ['appflowy_search', 'appflowy_worker', 'appflowy_web', 'admin_frontend', 'nginx']],
        'stateful_node_constraint': 'node.labels.appflowy-swarm-test == true',
        'ai_enabled': False, 'semantic_indexing_enabled': False,
        'keyword_indexing_enabled': True, 'local_experiment_only': True,
        'configuration_validation': {'compose_parse_passed': True, 'native_stack_validation': native_validation},
    }
    private_write(OUT / 'metadata.json', json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'prepared': str(stack_file), 'services': len(services),
                      'initial_services': sorted(initial_services),
                      'base_url': BASE_URL, 'credentials': 'private credentials.json'}))


if __name__ == '__main__':
    main()
