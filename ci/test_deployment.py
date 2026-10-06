"""Safety and rendering contracts for the runtime harness (never start services)."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deployment import Deployment, HELM_KEYS, HELM_WORKLOADS, normalized_image_reference, sanitize
from images import CORE, ROOT, clean_environment


class RuntimeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='appflowy-ci-contract-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        digest = 'sha256:' + 'a' * 64
        self.lock = self.root / 'images.json'
        self.payload = {'services': {name: {'source': name + ':latest', 'image': name + '@' + digest,
                                          'digest': digest, 'config_digest': digest} for name in CORE},
                        'compose_sha256': hashlib.sha256((ROOT / 'docker-compose.yml').read_bytes()).hexdigest()}
        self.lock.write_text(json.dumps(self.payload))

    def deployment(self, mode='compose'):
        return Deployment(mode, self.root / mode, self.root / 'artifacts' / mode, self.lock)

    def helm_source_documents(self):
        documents = []
        for service, workload in HELM_WORKLOADS.items():
            kind, name = workload.split('/', 1)
            record = (self.payload['helm_services']['redis'] if service == 'redis'
                      else self.payload['services'][service])
            documents.append({'kind': {'deployment': 'Deployment', 'statefulset': 'StatefulSet'}[kind],
                              'metadata': {'name': name}, 'spec': {'template': {'spec': {'containers': [
                                  {'name': HELM_KEYS[service], 'image': normalized_image_reference(record['source'])}
                              ]}}}})
        return documents

    def test_requires_every_core_service_and_matching_source(self):
        self.payload['services'].pop('appflowy_search')
        self.lock.write_text(json.dumps(self.payload))
        with self.assertRaisesRegex(RuntimeError, 'ten core services'):
            self.deployment()
        self.payload['services']['appflowy_search'] = {}
        self.payload['compose_sha256'] = 'different'
        self.lock.write_text(json.dumps(self.payload))
        with self.assertRaisesRegex(RuntimeError, 'different Compose source'):
            self.deployment()

    def test_runtime_refuses_local_and_self_hosted_runners(self):
        for environment in ({}, {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'self-hosted'}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'GitHub-hosted'):
                    self.deployment().guard()

    def test_helm_requires_its_own_redis_image_without_startup_or_storage_overrides(self):
        with self.assertRaisesRegex(RuntimeError, 'chart Redis image'):
            self.deployment('helm')
        digest = 'sha256:' + 'b' * 64
        redis = {'source': 'docker.io/bitnami/redis:latest',
                 'image': 'docker.io/bitnami/redis@' + digest, 'digest': digest, 'config_digest': digest}
        self.payload['helm_services'] = {'redis': redis}
        self.lock.write_text(json.dumps(self.payload))
        instance = self.deployment('helm')
        source = yaml.safe_dump_all(self.helm_source_documents())
        original_run = instance.run
        def run(*args, **kwargs):
            if args[:2] == ('helm', 'template'):
                return source
            return original_run(*args, **kwargs)
        with patch.object(instance, 'run', side_effect=run):
            instance.render()
        overrides = yaml.safe_load((instance.runtime / 'helm-overrides.yaml').read_text())
        self.assertEqual(overrides['redis'], {'image': {'digest': digest, 'pullPolicy': 'IfNotPresent'}})
        self.assertEqual(instance.helm_images['redis'], redis)
        self.assertNotEqual(instance.helm_images['redis']['image'], instance.images['redis']['image'])
        self.assertEqual(instance.base_url, 'http://localhost')
        self.assertEqual(overrides['global']['domain'], 'localhost')
        self.assertEqual(overrides['global']['s3']['presignedUrlEndpoint'], 'http://localhost/minio-api')

    def test_helm_pins_cannot_hide_a_changed_source_repository_or_tag(self):
        self.payload['helm_services'] = {'redis': self.payload['services']['redis']}
        self.lock.write_text(json.dumps(self.payload))
        for service, bad_image in [('appflowy_web', 'wrong.example/broken-web:latest'),
                                   ('appflowy_web', 'appflowy_web:wrong-version'),
                                   ('redis', 'redis:wrong-version')]:
            with self.subTest(service=service, image=bad_image):
                instance = self.deployment('helm')
                documents = self.helm_source_documents()
                name = HELM_WORKLOADS[service].split('/', 1)[1]
                document = next(item for item in documents if item['metadata']['name'] == name)
                document['spec']['template']['spec']['containers'][0]['image'] = bad_image
                with patch.object(instance, 'run', return_value=yaml.safe_dump_all(documents)):
                    with self.assertRaisesRegex(RuntimeError, 'chart source image differs'):
                        instance.render()
                self.assertFalse((instance.runtime / 'helm-overrides.yaml').exists())
                self.assertFalse((instance.runtime / 'credentials.json').exists())

    def test_image_reference_normalization_preserves_versions(self):
        self.assertEqual(normalized_image_reference('redis'), 'docker.io/library/redis:latest')
        self.assertEqual(normalized_image_reference('docker.io/redis:latest'),
                         normalized_image_reference('index.docker.io/library/redis:latest'))
        self.assertEqual(normalized_image_reference('pgvector/pgvector:pg16'),
                         'docker.io/pgvector/pgvector:pg16')
        self.assertNotEqual(normalized_image_reference('redis:7'), normalized_image_reference('redis:8'))
        digest = 'sha256:' + 'a' * 64
        self.assertEqual(normalized_image_reference('redis@' + digest), 'docker.io/library/redis@' + digest)

    def helm_running_pods(self):
        self.payload['helm_services'] = {'redis': self.payload['services']['redis']}
        self.payload['services']['admin_frontend']['config_digest'] = 'sha256:' + 'c' * 64
        self.lock.write_text(json.dumps(self.payload))
        instance = self.deployment('helm')
        pods = []
        for service, container_name in HELM_KEYS.items():
            image = instance.helm_images[service]
            pods.append({'metadata': {'name': service + '-pod'},
                         'spec': {'containers': [{'name': container_name,
                                                   'image': normalized_image_reference(image['image'])}]},
                         'status': {'containerStatuses': [{'name': container_name,
                                   'image': image['config_digest'],
                                   'imageID': 'containerd://' + image['config_digest'], 'ready': True}]}})
        return instance, pods

    def test_helm_image_check_uses_requested_reference_and_runtime_image_id(self):
        instance, pods = self.helm_running_pods()
        # Reproduces containerd returning a bare config digest in status.image
        # while the spec contains the correct repository@manifest digest.
        controller = {'items': [{'status': {'containerStatuses': [
            {'image': 'controller:locked', 'imageID': 'controller@sha256:controller', 'ready': True}
        ]}}]}
        with patch.object(instance, 'helm_pods', return_value=pods), \
                patch.object(instance, 'run', return_value=json.dumps(controller)):
            instance.check_images('running-images.json')
        evidence = json.loads((instance.artifacts / 'running-images.json').read_text())
        self.assertEqual(len(evidence), 10)
        admin = next(row for row in evidence if row['service'] == 'admin_frontend')
        expected = instance.helm_images['admin_frontend']
        self.assertEqual(admin['image'], normalized_image_reference(expected['image']))
        self.assertEqual(admin['reported_image'], expected['config_digest'])
        self.assertEqual(admin['image_id'], 'containerd://' + expected['config_digest'])

    def test_helm_image_check_still_rejects_wrong_or_unready_main_containers(self):
        cases = {'wrong_repository': 'requested Kubernetes image differs',
                 'wrong_spec_digest': 'requested Kubernetes image differs',
                 'wrong_runtime_digest': 'running Kubernetes image differs',
                 'unready': 'container is not Ready',
                 'missing_main_status': 'exactly one main container status',
                 'duplicate_pod': 'exactly one running container'}
        for case, error in cases.items():
            with self.subTest(case=case):
                instance, pods = self.helm_running_pods()
                admin = next(pod for pod in pods if pod['metadata']['name'] == 'admin_frontend-pod')
                container = admin['spec']['containers'][0]
                status = admin['status']['containerStatuses'][0]
                if case == 'wrong_repository':
                    container['image'] = 'wrong.example/admin@' + instance.helm_images['admin_frontend']['digest']
                elif case == 'wrong_spec_digest':
                    container['image'] = 'admin_frontend@sha256:' + 'd' * 64
                elif case == 'wrong_runtime_digest':
                    status['imageID'] = 'containerd://sha256:' + 'd' * 64
                elif case == 'unready':
                    status['ready'] = False
                elif case == 'missing_main_status':
                    status['name'] = 'different-container'
                else:
                    duplicate = json.loads(json.dumps(admin))
                    duplicate['metadata']['name'] = 'duplicate-admin-pod'
                    pods.append(duplicate)
                with patch.object(instance, 'helm_pods', return_value=pods):
                    with self.assertRaisesRegex(RuntimeError, error):
                        instance.check_images('rejected-images.json')

    def test_remote_context_cannot_be_hidden_by_local_docker_host(self):
        environment = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                       'RUNNER_TEMP': str(self.root), 'DOCKER_CONTEXT': 'remote',
                       'DOCKER_HOST': 'unix:///var/run/docker.sock'}
        instance = self.deployment()
        with patch.dict(os.environ, environment, clear=True), patch.object(instance, 'run', return_value=json.dumps(
                [{'Endpoints': {'docker': {'Host': 'ssh://remote.example'}}}])):
            with self.assertRaisesRegex(RuntimeError, 'Remote Docker'):
                instance.guard()

    def test_runtime_state_must_be_under_runner_temp(self):
        environment = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                       'RUNNER_TEMP': str(self.root / 'different')}
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'subdirectory'):
                self.deployment().guard()

    def test_compose_environment_filters_application_secrets_but_keeps_docker_identity(self):
        environment = {'PATH': '/bin', 'HOME': '/tmp/test-home', 'USER': 'runner', 'LOGNAME': 'runner',
                       'APPFLOWY_DATABASE_URL': 'postgres://private', 'GOTRUE_JWT_SECRET': 'private',
                       'HTTPS_PROXY': 'http://proxy.example'}
        with patch.dict(os.environ, environment, clear=True):
            result = clean_environment()
        self.assertEqual(result['USER'], 'runner')
        self.assertEqual(result['LOGNAME'], 'runner')
        self.assertIn('HTTPS_PROXY', result)
        self.assertNotIn('APPFLOWY_DATABASE_URL', result)
        self.assertNotIn('GOTRUE_JWT_SECRET', result)

    def test_artifact_redaction_removes_credentials_jwt_and_signed_queries(self):
        private = self.root / 'private'
        private.mkdir()
        password = 'unique-test-password-123456789'
        (private / 'credentials.json').write_text(json.dumps({'password': password}))
        jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzZWNyZXQifQ.signature'
        result = sanitize(password + ' ' + base64.b64encode(password.encode()).decode()
                          + ' ' + jwt + ' /api/user/verify/opaque-token'
                          + ' http://localhost/minio-api/object?X-Amz-Signature=secret'
                          + ' postgres://user:another-password@postgres/db', private)
        for secret in (password, jwt, 'opaque-token', 'X-Amz-Signature', 'another-password'):
            self.assertNotIn(secret, result)

    def test_swarm_preserves_file_permission_bits_from_compose_json(self):
        # Compose's FileMode.MarshalJSON emits an octal string. Earlier
        # versions emitted numeric bits; stack requires those numeric bits.
        cases = [('modern_octal_strings', '0400', '0444', 0o400, 0o444),
                 ('legacy_integer_bits', 256, 292, 0o400, 0o444),
                 ('decimal_integer_bits', 400, 420, 0o620, 0o644),
                 ('equivalent_octal_strings', '0620', '0644', 400, 420)]
        for label, secret_mode, config_mode, expected_secret, expected_config in cases:
            with self.subTest(format=label):
                instance = self.deployment('swarm')
                original_run = instance.run
                def run(*args, **kwargs):
                    output = original_run(*args, **kwargs)
                    if args[:2] == ('docker', 'compose') and '--format' in args:
                        rendered = json.loads(output)
                        nginx = rendered['services']['nginx']
                        nginx['secrets'][0]['mode'] = secret_mode
                        nginx['configs'][0]['mode'] = config_mode
                        return json.dumps(rendered)
                    return output
                with patch.object(instance, 'run', side_effect=run):
                    instance.render()
                nginx = yaml.safe_load((instance.runtime / 'stack.yml').read_text())['services']['nginx']
                self.assertIs(type(nginx['secrets'][0]['mode']), int)
                self.assertIs(type(nginx['configs'][0]['mode']), int)
                self.assertEqual(nginx['secrets'][0]['mode'], expected_secret)
                self.assertEqual(nginx['configs'][0]['mode'], expected_config)

    def test_real_source_render_preserves_storage_and_shell_escaping(self):
        # Docker Compose parsing is read-only; no Docker daemon or images needed.
        source = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
        normalized_source = json.loads(self.deployment().run(
            'docker', 'compose', '--env-file', str(ROOT / 'deploy.env'), '-p', 'appflowy-ci',
            '-f', str(ROOT / 'docker-compose.yml'), 'config', '--format', 'json', env=clean_environment()))
        for mode in ('compose', 'swarm'):
            with self.subTest(mode=mode):
                instance = self.deployment(mode)
                instance.render()
                file = instance.runtime / ('compose.yml' if mode == 'compose' else 'stack.yml')
                rendered = yaml.safe_load(file.read_text())
                self.assertEqual(set(rendered['services']), CORE)
                hostname = '127.0.0.1' if mode == 'swarm' else 'localhost'
                base_url = 'http://' + hostname
                self.assertEqual(instance.env['SWARM_TEST_BASE_URL'], base_url)
                metadata = json.loads((instance.runtime / 'metadata.json').read_text())
                self.assertEqual(metadata['base_url'], base_url)
                cloud = rendered['services']['appflowy_cloud']['environment']
                self.assertEqual(cloud['APPFLOWY_BASE_URL'], base_url)
                self.assertEqual(cloud['APPFLOWY_WEB_URL'], base_url)
                self.assertEqual(cloud['APPFLOWY_S3_PRESIGNED_URL_ENDPOINT'], base_url + '/minio-api')
                web = rendered['services']['appflowy_web']['environment']
                self.assertEqual(web['APPFLOWY_BASE_URL'], base_url)
                self.assertEqual(web['APPFLOWY_GOTRUE_BASE_URL'], base_url + '/gotrue')
                self.assertEqual(web['APPFLOWY_WS_BASE_URL'], 'ws://' + hostname + '/ws/v2')
                self.assertEqual(rendered['services']['gotrue']['environment']['API_EXTERNAL_URL'],
                                 base_url + '/gotrue')
                ports = rendered['services']['nginx']['ports']
                self.assertEqual({(int(port['published']), port['target']) for port in ports},
                                 {(80, 80), (443, 443)})
                self.assertTrue(all(port.get('mode', 'ingress') == 'ingress' for port in ports))
                redis = rendered['services']['redis']
                expected_redis = normalized_source['services']['redis']
                for key in ('command', 'volumes', 'healthcheck'):
                    self.assertEqual(redis.get(key), expected_redis.get(key),
                                     'CI must preserve the source Redis configuration: ' + key)
                self.assertEqual(set(rendered.get('volumes', {})), set(source.get('volumes', {})))
                search = rendered['services']['appflowy_search']['healthcheck']['test'][-1]
                self.assertIn('$$status', search)
                self.assertIn('$${APPFLOWY_SEARCH_PORT', search)
                for service in rendered['services'].values():
                    self.assertNotIn(None, [value for key, value in service.items() if key in ('command', 'entrypoint')])
                if mode == 'swarm':
                    self.assertEqual(rendered['services']['appflowy_cloud']['deploy']['replicas'], 0)
                    self.assertEqual(rendered['services']['postgres']['deploy']['replicas'], 1)
                    self.assertFalse(redis['deploy'].get('placement'))
                else:
                    instance.run(*instance.compose, 'config', '--quiet')

    def test_swarm_public_readiness_uses_ipv4_and_reports_last_error(self):
        instance = self.deployment('swarm')
        with patch('deployment.urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value.status = 200
            instance.wait_http()
            self.assertEqual([call.args[0] for call in request.call_args_list],
                             ['http://127.0.0.1' + path for path in
                              ('/api/health', '/gotrue/health', '/', '/console')])
        with patch('deployment.urllib.request.urlopen', side_effect=TimeoutError('timed out')), \
             patch('deployment.time.monotonic', side_effect=[0, 0, 181]), \
             patch('deployment.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, r'http://127\.0\.0\.1/api/health; TimeoutError: timed out'):
                instance.wait_http()


if __name__ == '__main__':
    unittest.main()
