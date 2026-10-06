#!/usr/bin/env python3
"""Disposable GitHub-hosted runtime tests; never operate on a developer's deployment.

Only render is usable outside GitHub Actions. Runtime credentials and rendered
manifests stay in RUNNER_TEMP; the artifact directory contains sanitized evidence.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import urllib.request

import yaml

from images import CORE, ROOT, clean_environment, repository

NAME = 'appflowy-ci'
NAMESPACE = NAME
STAGES = [['postgres', 'redis', 'minio'], ['gotrue'], ['appflowy_cloud'],
          ['appflowy_search', 'appflowy_worker', 'appflowy_web', 'admin_frontend', 'nginx']]
HELM_KEYS = {'appflowy_cloud': 'appflowy-cloud', 'appflowy_worker': 'appflowy-worker',
             'appflowy_search': 'appflowy-search', 'appflowy_web': 'appflowy-web',
             'admin_frontend': 'admin-frontend', 'gotrue': 'gotrue',
             'postgres': 'postgresql', 'redis': 'redis', 'minio': 'minio'}
HELM_WORKLOADS = {'appflowy_cloud': 'deployment/appflowy-ci-cloud',
                  'appflowy_worker': 'deployment/appflowy-ci-worker',
                  'appflowy_search': 'deployment/appflowy-ci-search',
                  'appflowy_web': 'deployment/appflowy-ci-web',
                  'admin_frontend': 'deployment/appflowy-ci-admin',
                  'gotrue': 'deployment/appflowy-ci-gotrue',
                  'postgres': 'statefulset/appflowy-ci-postgresql',
                  'redis': 'statefulset/appflowy-ci-redis-master',
                  'minio': 'deployment/appflowy-ci-minio'}


def normalized_image_reference(reference):
    """Normalize Docker Hub aliases without discarding a tag or digest."""
    name, separator, digest = reference.partition('@')
    if ':' not in name.rsplit('/', 1)[-1] and not separator:
        name += ':latest'
    parts = name.split('/')
    if len(parts) == 1 or not ('.' in parts[0] or ':' in parts[0] or parts[0] == 'localhost'):
        parts.insert(0, 'docker.io')
    if parts[0] == 'index.docker.io':
        parts[0] = 'docker.io'
    if parts[0] == 'docker.io' and len(parts) == 2:
        parts.insert(1, 'library')
    return '/'.join(parts) + separator + digest


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(value)


def sanitize(text, private):
    for file in ('credentials.json', 'ordinary-user.json'):
        path = private / file
        if path.exists():
            values = json.loads(path.read_text()).values()
            for value in sorted((str(v) for v in values if v), key=len, reverse=True):
                text = text.replace(value, '[redacted]')
                text = text.replace(base64.b64encode(value.encode()).decode(), '[redacted]')
    text = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[redacted-jwt]', text)
    text = re.sub(r'(/api/user/verify/)[^\s"\x27]+', r'\1[redacted]', text)
    text = re.sub(r'((?:postgres(?:ql)?|redis)://)[^@\s]+@', r'\1[redacted]@', text)
    text = re.sub(r'(https?://[^\s"\x27?]+)\?[^\s"\x27]+', r'\1?[redacted-query]', text)
    return text


class Deployment:
    def __init__(self, mode, runtime, artifacts, lock):
        self.mode, self.runtime, self.artifacts = mode, runtime.resolve(), artifacts.resolve()
        self.lock = json.loads(lock.read_text())
        self.images = self.lock['services']
        if set(self.images) != CORE:
            raise RuntimeError('Image lock does not cover exactly all ten core services')
        expected = hashlib.sha256((ROOT / 'docker-compose.yml').read_bytes()).hexdigest()
        if self.lock['compose_sha256'] != expected:
            raise RuntimeError('Image lock belongs to a different Compose source')
        self.helm_images = dict(self.images)
        if mode == 'helm':
            redis = self.lock.get('helm_services', {}).get('redis')
            if not redis:
                raise RuntimeError('Helm requires a separate image lock for its chart Redis image')
            self.helm_images['redis'] = redis
        self.artifacts.mkdir(parents=True, exist_ok=True)
        # Some Docker releases accept IPv6 connections to published Swarm
        # ports without forwarding them. Use IPv4 through the same public port.
        # https://github.com/moby/moby/issues/53091
        self.hostname = '127.0.0.1' if mode == 'swarm' else 'localhost'
        self.base_url = 'http://' + self.hostname
        self.env = dict(os.environ, SWARM_TEST_DIR=str(runtime), SWARM_TEST_BASE_URL=self.base_url,
                        SWARM_BROWSER_CHANNEL='chromium')
        self.compose = ['docker', 'compose', '--env-file', str(runtime / 'test.env'),
                        '-p', NAME, '-f', str(runtime / 'compose.yml')]

    def run(self, *args, timeout=600, check=True, env=None, combined=False):
        result = subprocess.run(args, capture_output=True, text=True, env=env or self.env, timeout=timeout)
        if result.returncode and check:
            output = sanitize(result.stdout + result.stderr, self.runtime)
            raise RuntimeError(f'{args[0]} {args[1]} failed ({result.returncode}):\n{output[-8000:]}')
        return result.stdout + result.stderr if combined else result.stdout

    def kubectl(self, *args, **kwargs):
        return self.run('kubectl', '--context', 'kind-' + NAME, '-n', NAMESPACE, *args, **kwargs)

    def evidence(self, name, value):
        text = value if isinstance(value, str) else json.dumps(value, indent=2) + '\n'
        (self.artifacts / name).write_text(sanitize(text, self.runtime))

    def guard(self):
        if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
            raise RuntimeError('Runtime operations require a disposable GitHub-hosted Actions runner')
        runner_temp = Path(os.environ['RUNNER_TEMP']).resolve()
        if runner_temp not in self.runtime.parents:
            raise RuntimeError('Runtime state must be a private subdirectory of RUNNER_TEMP')
        if self.mode != 'helm':
            context = json.loads(self.run('docker', 'context', 'inspect'))[0]
            context_endpoint = context['Endpoints']['docker']['Host']
            endpoint = (context_endpoint if os.environ.get('DOCKER_CONTEXT')
                        else os.environ.get('DOCKER_HOST') or context_endpoint)
            if not endpoint.startswith('unix://'):
                raise RuntimeError('Remote Docker endpoints are forbidden')

    def validate_helm_source_images(self):
        # Render the source chart before applying runtime image pins. Otherwise
        # a broken repository/tag in the chart would be silently repaired by CI.
        rendered = self.run('helm', 'template', NAME, str(ROOT / 'helm/appflowy-cloud'),
                            '--namespace', NAMESPACE, '-f', str(ROOT / 'ci/helm-values.yaml'),
                            env=clean_environment())
        documents = [document for document in yaml.safe_load_all(rendered) if document]
        for service, workload in HELM_WORKLOADS.items():
            kind, name = workload.split('/', 1)
            matches = [document for document in documents
                       if document.get('kind', '').lower() == kind
                       and document.get('metadata', {}).get('name') == name]
            if len(matches) != 1:
                raise RuntimeError(f'{service}: expected exactly one source Helm workload {workload}')
            containers = [container for container in matches[0]['spec']['template']['spec']['containers']
                          if container.get('name') == HELM_KEYS[service]]
            if len(containers) != 1:
                raise RuntimeError(f'{service}: expected exactly one main container in {workload}')
            actual = containers[0]['image']
            expected = self.helm_images[service]['source']
            if normalized_image_reference(actual) != normalized_image_reference(expected):
                raise RuntimeError(f'{service}: chart source image differs from image lock source: '
                                   f'{actual} != {expected}')

    def render(self):
        if self.mode == 'helm':
            self.validate_helm_source_images()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.runtime.chmod(0o700)
        credentials = {'admin_email': 'ci-' + secrets.token_hex(6) + '@example.com',
                       'admin_password': secrets.token_urlsafe(32),
                       'postgres_password': secrets.token_hex(24), 'jwt_secret': secrets.token_hex(32),
                       's3_access_key': 'ci' + secrets.token_hex(8), 's3_secret_key': secrets.token_hex(24)}
        private_write(self.runtime / 'credentials.json', json.dumps(credentials))
        values = {
            'FQDN': self.hostname, 'SCHEME': 'http', 'WS_SCHEME': 'ws',
            'APPFLOWY_BASE_URL': self.base_url, 'APPFLOWY_WEB_URL': self.base_url,
            'APPFLOWY_WEBSOCKET_BASE_URL': 'ws://' + self.hostname + '/ws/v2',
            'NGINX_PORT': '80', 'NGINX_TLS_PORT': '443',
            'POSTGRES_PASSWORD': credentials['postgres_password'],
            'GOTRUE_ADMIN_EMAIL': credentials['admin_email'], 'GOTRUE_ADMIN_PASSWORD': credentials['admin_password'],
            'GOTRUE_JWT_SECRET': credentials['jwt_secret'], 'GOTRUE_MAILER_AUTOCONFIRM': 'true',
            'GOTRUE_DISABLE_SIGNUP': 'false', 'AWS_ACCESS_KEY': credentials['s3_access_key'],
            'AWS_SECRET': credentials['s3_secret_key'], 'APPFLOWY_DATABASE_MAX_CONNECTIONS': '20',
            'AI_ENABLED': 'false', 'AI_OPENAI_API_KEY': '', 'ASSEMBLYAI_API_KEY': '',
            'AZURE_OPENAI_API_KEY': '', 'AZURE_OPENAI_ENDPOINT': '', 'AZURE_OPENAI_API_VERSION': '',
            'APPFLOWY_KEYWORD_SEARCH_ENABLED': 'true', 'APPFLOWY_INDEXER_DATABASE_ENABLED': 'false',
            'APPFLOWY_KEYWORD_INDEX_MAP_SIZE_BYTES': '268435456',
            'APPFLOWY_S3_PRESIGNED_URL_ENDPOINT': self.base_url + '/minio-api',
            'APPFLOWY_MAILER_SMTP_TLS_KIND': 'none',
        }
        for prefix in ('GOTRUE_SMTP', 'APPFLOWY_MAILER_SMTP'):
            values.update({prefix + '_HOST': '127.0.0.1', prefix + '_PORT': '2525'})
        values.update({'GOTRUE_SMTP_USER': '', 'GOTRUE_SMTP_PASS': '',
                       'GOTRUE_SMTP_ADMIN_EMAIL': credentials['admin_email'],
                       'APPFLOWY_MAILER_SMTP_USERNAME': '', 'APPFLOWY_MAILER_SMTP_PASSWORD': '',
                       'APPFLOWY_MAILER_SMTP_EMAIL': credentials['admin_email']})
        seen, lines = set(), []
        for line in (ROOT / 'deploy.env').read_text().splitlines():
            match = re.match(r'^([A-Z][A-Z0-9_]*)=', line)
            if match and match[1] in values:
                seen.add(match[1])
                line = match[1] + '=' + values[match[1]]
            lines.append(line)
        lines.extend(key + '=' + value for key, value in values.items() if key not in seen)
        env_file = self.runtime / 'test.env'
        private_write(env_file, '\n'.join(lines) + '\n')
        source = ROOT / ('docker-swarm/docker-stack.yml' if self.mode == 'swarm' else 'docker-compose.yml')
        rendered = json.loads(self.run('docker', 'compose', '--env-file', str(env_file), '-p', NAME,
                                      '-f', str(source), 'config', '--format', 'json', env=clean_environment()))
        rendered['services'].pop('ai')
        for name, service in rendered['services'].items():
            for key in ('command', 'entrypoint'):
                if service.get(key) is None:
                    service.pop(key, None)
            service['image'] = self.images[name]['image']
            service['logging'] = {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '2'}}
            if name in ('appflowy_cloud', 'appflowy_worker', 'appflowy_search'):
                service['environment'].update({'AI_ENABLED': 'false', 'APPFLOWY_INDEXER_ENABLED': 'false',
                                               'APPFLOWY_BACKGROUND_INDEXER_ENABLED': 'false',
                                               'APPFLOWY_INDEXER_DATABASE_ENABLED': 'false'})
            if name == 'appflowy_cloud':
                service['healthcheck']['start_period'] = '180s'
            if self.mode == 'swarm':
                service['deploy']['replicas'] = int(name in STAGES[0])
                # Compose serializes file modes as octal strings ("0400");
                # stack's legacy schema requires numeric permission bits.
                # Older Compose versions already return integers: retain them.
                for kind in ('configs', 'secrets'):
                    for reference in service.get(kind, []):
                        if isinstance(reference, dict) and isinstance(reference.get('mode'), str):
                            reference['mode'] = int(reference['mode'], 8)
                for port in service.get('ports', []):
                    if 'published' in port:
                        port['published'] = int(port['published'])
                for volume in service.get('volumes', []):
                    if 'bind' in volume:
                        volume['bind'].pop('create_host_path', None)
                        if not volume['bind']:
                            volume.pop('bind')
        if set(rendered['services']) != CORE:
            raise RuntimeError('Rendered deployment does not contain all ten core services')
        if self.mode == 'swarm':
            rendered.pop('name', None)
            rendered['version'] = '3.8'
        private_write(self.runtime / ('stack.yml' if self.mode == 'swarm' else 'compose.yml'),
                      yaml.safe_dump(rendered, sort_keys=False))
        private_write(self.runtime / 'metadata.json', json.dumps({'base_url': self.base_url, 'stack_name': NAME,
                      'mode': self.mode, 'images': {key: value['image'] for key, value in
                       (self.helm_images if self.mode == 'helm' else self.images).items()}}))
        if self.mode == 'helm':
            overrides = {'fullnameOverride': NAME, 'global': {'domain': 'localhost', 'scheme': 'http',
                         'wsScheme': 'ws', 'jwt': {'secret': credentials['jwt_secret']},
                         'postgresql': {'password': credentials['postgres_password']},
                         's3': {'presignedUrlEndpoint': self.base_url + '/minio-api'}},
                         'postgresql': {'auth': {'postgresPassword': credentials['postgres_password']}},
                         'minio': {'auth': {'rootUser': credentials['s3_access_key'], 'rootPassword': credentials['s3_secret_key']}},
                         'gotrue': {'config': {'adminEmail': credentials['admin_email'], 'adminPassword': credentials['admin_password']}}}
            for name, key in HELM_KEYS.items():
                image_values = {'digest': self.helm_images[name]['digest'], 'pullPolicy': 'IfNotPresent'}
                # Keep the Redis subchart's image family and startup contract.
                # Its digest is resolved separately from the rendered chart.
                if name != 'redis':
                    image_values['repository'] = repository(self.helm_images[name]['source'])
                overrides.setdefault(key, {})['image'] = image_values
            private_write(self.runtime / 'helm-overrides.yaml', yaml.safe_dump(overrides))
        self.evidence('image-lock.json', self.lock)

    def docker_containers(self, service):
        label = (f'com.docker.swarm.service.name={NAME}_{service}' if self.mode == 'swarm'
                 else f'com.docker.compose.service={service}')
        args = ['docker', 'ps', '-q', '--filter', 'label=' + label]
        if self.mode == 'compose':
            args += ['--filter', 'label=com.docker.compose.project=' + NAME]
        ids = self.run(*args).split()
        return json.loads(self.run('docker', 'inspect', *ids)) if ids else []

    def wait_services(self, services, before=None, timeout=600):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            status, ready = {}, True
            for service in services:
                containers = self.docker_containers(service)
                states = [row['State'].get('Health', {}).get('Status', row['State']['Status']) for row in containers]
                status[service] = states
                ready &= len(states) == 1 and states[0] in ('healthy', 'running')
                if before:
                    ready &= all(row['Id'] not in before for row in containers)
            if status != last:
                print(json.dumps({'readiness': status}), flush=True)
                last = status
            if ready:
                return
            time.sleep(3)
        raise RuntimeError('Service readiness timed out: ' + json.dumps(last))

    def wait_http(self):
        for path in ('/api/health', '/gotrue/health', '/', '/console'):
            deadline = time.monotonic() + 180
            last_error = 'no response'
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(self.base_url + path, timeout=10) as response:
                        if response.status == 200:
                            break
                        last_error = 'HTTP ' + str(response.status)
                except Exception as error:
                    last_error = type(error).__name__ + ': ' + str(error)
                time.sleep(3)
            else:
                raise RuntimeError('Public route failed: ' + self.base_url + path + '; '
                                   + sanitize(last_error, self.runtime))
        print('Public API, authentication, Web and Admin routes are ready', flush=True)

    def up(self):
        self.guard()
        if self.mode == 'compose':
            if self.run('docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + NAME).strip():
                raise RuntimeError('Refusing to use an existing Compose project')
        self.render()
        if self.mode == 'helm':
            self.run('helm', 'upgrade', '--install', NAME, str(ROOT / 'helm/appflowy-cloud'),
                     '--kube-context', 'kind-' + NAME, '--namespace', NAMESPACE, '--create-namespace',
                     '-f', str(ROOT / 'ci/helm-values.yaml'), '-f', str(self.runtime / 'helm-overrides.yaml'),
                     '--wait', '--timeout', '15m', timeout=960)
            self.kubectl('wait', '--for=condition=Ready', 'pod', '-l', 'app.kubernetes.io/instance=' + NAME,
                         '--timeout=300s', timeout=330)
        else:
            if self.mode == 'swarm':
                state = json.loads(self.run('docker', 'info', '--format', '{{json .Swarm}}'))
                if state['LocalNodeState'] != 'inactive':
                    raise RuntimeError('Refusing to use an existing Swarm')
                self.run('docker', 'swarm', 'init')
                private_write(self.runtime / 'created-swarm', 'true')
                node_id = self.run('docker', 'info', '--format', '{{.Swarm.NodeID}}').strip()
                self.run('docker', 'node', 'update', '--label-add', 'appflowy.data=true', node_id)
                # Validate with the actual stack parser, then deploy the same file once.
                self.run('docker', 'stack', 'config', '-c', str(self.runtime / 'stack.yml'))
                self.run('docker', 'stack', 'deploy', '--resolve-image', 'never',
                         '-c', str(self.runtime / 'stack.yml'), NAME)
            else:
                private_write(self.runtime / 'created-compose', 'true')
                self.run(*self.compose, 'pull', timeout=1200)
            for index, stage in enumerate(STAGES):
                if self.mode == 'compose':
                    self.run(*self.compose, 'up', '-d', '--no-deps', *stage)
                elif index:
                    self.run('docker', 'service', 'scale', '--detach', *[NAME + '_' + name + '=1' for name in stage])
                self.wait_services(stage)
        self.wait_http()
        self.check_images('initial-images.json')

    def helm_pods(self):
        return json.loads(self.kubectl('get', 'pods', '-l', 'app.kubernetes.io/instance=' + NAME, '-o', 'json'))['items']

    def check_images(self, filename):
        records = []
        if self.mode == 'helm':
            pods = self.helm_pods()
            for name, key in HELM_KEYS.items():
                expected = self.helm_images[name]
                matches = []
                for pod in pods:
                    if pod['metadata'].get('deletionTimestamp'):
                        continue
                    for container in pod.get('spec', {}).get('containers', []):
                        if container.get('name') != key:
                            continue
                        if normalized_image_reference(container['image']) != normalized_image_reference(expected['image']):
                            raise RuntimeError(name + ': requested Kubernetes image differs from shared image lock')
                        statuses = [status for status in pod.get('status', {}).get('containerStatuses', [])
                                    if status.get('name') == key]
                        if len(statuses) != 1:
                            raise RuntimeError(name + ': expected exactly one main container status')
                        status = statuses[0]
                        # Runtimes may report status.image as a tag, digest, or
                        # image ID. The requested spec and actual imageID are
                        # authoritative; status.image is only diagnostic data.
                        image_id = status.get('imageID', '')
                        digest = image_id.rsplit('@', 1)[-1].split('://', 1)[-1]
                        if digest not in (expected['digest'], expected['config_digest']):
                            raise RuntimeError(name + ': running Kubernetes image differs from shared image lock')
                        if not status.get('ready'):
                            raise RuntimeError(name + ': container is not Ready')
                        matches.append({'pod': pod['metadata']['name'], 'image': container['image'],
                                        'reported_image': status.get('image'), 'image_id': image_id})
                if len(matches) != 1:
                    raise RuntimeError(name + ': expected exactly one running container from the image lock')
                records.append({'service': name, **matches[0]})
            # Helm uses the ingress controller instead of the standalone nginx image.
            controller = json.loads(self.run('kubectl', '--context', 'kind-' + NAME, '-n', 'ingress-nginx',
                                            'get', 'pods', '-l', 'app.kubernetes.io/component=controller', '-o', 'json'))['items']
            if len(controller) != 1:
                raise RuntimeError('Expected exactly one real ingress-nginx controller')
            statuses = controller[0].get('status', {}).get('containerStatuses', [])
            if not statuses or not all(item.get('ready') for item in statuses):
                raise RuntimeError('Ingress controller is not Ready')
            records.append({'service': 'nginx', 'replacement': 'real ingress-nginx controller; chart ingress routes tested',
                            'containers': [{'image': row['image'], 'image_id': row['imageID']} for row in statuses]})
        else:
            for name in sorted(CORE):
                rows = self.docker_containers(name)
                if len(rows) != 1 or rows[0]['Image'] != self.images[name]['config_digest']:
                    raise RuntimeError(name + ': actual Docker image differs from shared image lock')
                records.append({'service': name, 'container_id': rows[0]['Id'],
                                'image': rows[0]['Config']['Image'], 'image_id': rows[0]['Image']})
        self.evidence(filename, records)

    def replace(self, service):
        started = time.monotonic()
        if self.mode == 'helm':
            workload = HELM_WORKLOADS[service]
            resource = json.loads(self.kubectl('get', workload, '-o', 'json'))
            selector = ','.join(key + '=' + value for key, value in resource['spec']['selector']['matchLabels'].items())
            before = json.loads(self.kubectl('get', 'pod', '-l', selector, '-o', 'json'))['items']
            if len(before) != 1:
                raise RuntimeError(service + ': expected one pod before replacement')
            old = before[0]['metadata']['uid']
            self.kubectl('delete', 'pod', before[0]['metadata']['name'], '--wait=true', '--timeout=120s', timeout=150)
            self.kubectl('rollout', 'status', workload, '--timeout=600s', timeout=630)
            self.kubectl('wait', '--for=condition=Ready', 'pod', '-l', selector, '--timeout=300s', timeout=330)
            after = json.loads(self.kubectl('get', 'pod', '-l', selector, '-o', 'json'))['items']
            if len(after) != 1 or after[0]['metadata']['uid'] == old:
                raise RuntimeError(service + ': pod was not replaced')
            changed = {'before': old, 'after': after[0]['metadata']['uid']}
        else:
            before = {row['Id'] for row in self.docker_containers(service)}
            if self.mode == 'compose':
                self.run(*self.compose, 'up', '-d', '--no-deps', '--force-recreate', service)
            else:
                self.run('docker', 'service', 'update', '--force', '--detach', NAME + '_' + service)
            self.wait_services([service], before=before)
            changed = {'before': sorted(before), 'after': [row['Id'] for row in self.docker_containers(service)]}
        record = {'service': service, **changed, 'seconds': round(time.monotonic() - started, 2)}
        self.evidence('replacement-' + service + '.json', record)
        print(json.dumps({'replaced': service, 'seconds': record['seconds']}), flush=True)

    def smoke(self, phase):
        for script in ('api_smoke.py', 'database_row_smoke.py'):
            output = self.run(sys.executable, str(ROOT / 'docker-swarm/tests' / script), phase, '--timeout', '300', timeout=900)
            print(sanitize(output, self.runtime), end='', flush=True)

    def browser(self):
        for file in ('ui-replacement-ready.json', 'ui-replacement-complete'):
            (self.runtime / file).unlink(missing_ok=True)
        log_path = self.runtime / 'browser.log'
        with log_path.open('w') as log:
            child = subprocess.Popen(['node', str(ROOT / 'docker-swarm/tests/ui_smoke.mjs')],
                                     env=self.env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 300
                while not (self.runtime / 'ui-replacement-ready.json').exists():
                    if child.poll() is not None:
                        raise RuntimeError('Browser exited before realtime/replacement readiness')
                    if time.monotonic() > deadline:
                        raise RuntimeError('Browser realtime setup timed out')
                    time.sleep(1)
                self.replace('appflowy_cloud')
                self.wait_http()
                (self.runtime / 'ui-replacement-complete').touch()
                if child.wait(timeout=300):
                    raise RuntimeError('Browser realtime/reconnect assertions failed')
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
        self.evidence('browser.log', log_path.read_text())

    def test(self):
        self.guard()
        self.smoke('create')
        self.browser()
        for service in ('postgres', 'minio', 'redis', 'appflowy_search', 'appflowy_worker'):
            self.replace(service)
        self.wait_http()
        self.smoke('verify')
        # Readback alone cannot prove a replaced Worker consumes jobs or Search
        # indexes new content. Use separate fixture state and require both again.
        output = self.run(sys.executable, str(ROOT / 'docker-swarm/tests/api_smoke.py'), 'create',
                          '--state', str(self.runtime / 'recovery-api-state.json'), '--timeout', '300', timeout=900)
        print(sanitize(output, self.runtime), end='', flush=True)
        self.check_images('recovered-images.json')
        self.evidence('acceptance.json', {'passed': True, 'mode': self.mode,
                      'coverage': ['auth', 'document', 'database row create/edit', 'attachment bytes', 'worker import',
                                   'keyword search', 'browser realtime', 'WebSocket reconnect', 'durable application state'],
                      'excluded': ['external AI providers', 'semantic search', 'SMTP', 'TLS', 'upgrades',
                                   'Redis queue persistence', 'multi-node networking', 'node loss', 'HA']})

    def diagnostics(self):
        self.guard()
        if self.mode == 'helm':
            for label, args in [('pods', ('get', 'pods', '-o', 'wide')),
                                ('events', ('get', 'events', '--sort-by=.metadata.creationTimestamp')),
                                ('volumes', ('get', 'pvc'))]:
                self.evidence(label + '.txt', self.kubectl(*args, check=False))
            try:
                pods = self.helm_pods()
            except Exception:
                pods = []
            for pod in pods:
                name = pod['metadata']['name']
                for container in pod['spec'].get('containers', []) + pod['spec'].get('initContainers', []):
                    self.evidence(name + '-' + container['name'] + '.log',
                                  self.kubectl('logs', name, '-c', container['name'], '--tail=160', check=False))
        else:
            for name in sorted(CORE):
                if self.mode == 'swarm':
                    log = self.run('docker', 'service', 'logs', '--tail=160', NAME + '_' + name, check=False, combined=True)
                else:
                    log = self.run(*self.compose, 'logs', '--no-color', '--tail=160', name, check=False, combined=True)
                self.evidence(name + '.log', log)
            if self.mode == 'swarm':
                self.evidence('stack-tasks.txt', self.run('docker', 'stack', 'ps', NAME, '--no-trunc', check=False))
                # Select only network fields: full service/container inspection
                # would include private environment variables and credentials.
                commands = {
                    'engine': ('docker', 'version', '--format', '{{json .Server}}'),
                    'node_address': ('docker', 'info', '--format', '{{.Swarm.NodeAddr}}'),
                    'published_endpoint': ('docker', 'service', 'inspect', NAME + '_nginx',
                                           '--format', '{{json .Endpoint}}'),
                    'ingress_subnet': ('docker', 'network', 'inspect', 'ingress',
                                       '--format', '{{json .IPAM.Config}}'),
                    'host_addresses': ('ip', '-brief', 'address'),
                    'host_routes': ('ip', 'route'),
                    'host_listeners': ('ss', '-lnt'),
                }
                for family in ('4', '6'):
                    commands['localhost_ipv' + family] = (
                        'curl', '-' + family, '--max-time', '5', '--silent', '--show-error',
                        '--output', '/dev/null', '--write-out', 'HTTP=%{http_code} remote=%{remote_ip}\n',
                        'http://localhost/api/health')
                self.evidence('swarm-network.json', {
                    name: self.run(*args, check=False, combined=True) for name, args in commands.items()})
        for path in self.runtime.glob('*.results.json'):
            self.evidence(path.name, path.read_text())
        for name in ('ui-results.json', 'browser.log'):
            path = self.runtime / name
            if path.exists():
                self.evidence(name, path.read_text())

    def cleanup(self):
        self.guard()
        if self.mode == 'helm':
            if (Path(os.environ['RUNNER_TEMP']) / 'appflowy-kind.created').exists():
                self.run('kind', 'delete', 'cluster', '--name', NAME, check=False)
        elif self.mode == 'compose':
            if (self.runtime / 'created-compose').exists():
                self.run(*self.compose, 'down', '--volumes', '--remove-orphans', check=False)
        elif (self.runtime / 'created-swarm').exists():
            self.run('docker', 'stack', 'rm', NAME, check=False)
            deadline = time.monotonic() + 90
            while self.run('docker', 'service', 'ls', '-q').strip() and time.monotonic() < deadline:
                time.sleep(2)
            if not self.run('docker', 'service', 'ls', '-q').strip():
                self.run('docker', 'swarm', 'leave', '--force', check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['render', 'up', 'test', 'diagnostics', 'cleanup'])
    parser.add_argument('--mode', choices=['compose', 'swarm', 'helm'], required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--images', type=Path, required=True)
    args = parser.parse_args()
    deployment = Deployment(args.mode, args.runtime.resolve(), args.artifacts.resolve(), args.images)
    try:
        getattr(deployment, args.action)()
    except Exception as exc:
        print(sanitize(str(exc), deployment.runtime), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
