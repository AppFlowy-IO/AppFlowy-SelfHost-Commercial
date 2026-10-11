"""Safety and rendering contracts for the runtime harness (never start services)."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deployment import Deployment, HELM_KEYS, HELM_WORKLOADS, normalized_image_reference, private_write, sanitize
from images import CORE, ROOT, clean_environment
from configuration import source_fingerprint


class RuntimeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='appflowy-ci-contract-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        digest = 'sha256:' + 'a' * 64
        self.lock = self.root / 'images.json'
        self.payload = {'services': {name: {'source': name + ':latest', 'image': name + '@' + digest,
                                          'digest': digest, 'config_digest': digest} for name in CORE},
                        'compose_sha256': hashlib.sha256((ROOT / 'docker-compose.yml').read_bytes()).hexdigest(),
                        'source_sha256': source_fingerprint()}
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

    def test_ci_server_tag_preserves_helm_source_validation(self):
        self.payload['helm_services'] = {'redis': self.payload['services']['redis']}
        documents = self.helm_source_documents()
        cloud = self.payload['services']['appflowy_cloud']
        cloud['configured_source'] = cloud['source']
        cloud['source'] = 'appflowy_cloud:0.19.4_test'
        self.lock.write_text(json.dumps(self.payload))
        instance = self.deployment('helm')
        with patch.object(instance, 'run', return_value=yaml.safe_dump_all(documents)):
            instance.validate_helm_source_images()

        name = HELM_WORKLOADS['appflowy_cloud'].split('/', 1)[1]
        document = next(item for item in documents if item['metadata']['name'] == name)
        for bad_image in ('wrong.example/appflowy_cloud:latest', 'appflowy_cloud:wrong-version'):
            with self.subTest(image=bad_image):
                document['spec']['template']['spec']['containers'][0]['image'] = bad_image
                with patch.object(instance, 'run', return_value=yaml.safe_dump_all(documents)):
                    with self.assertRaisesRegex(RuntimeError, 'chart source image differs'):
                        instance.validate_helm_source_images()

    def test_helm_and_kubectl_receive_the_runner_kubeconfig(self):
        self.payload['helm_services'] = {'redis': self.payload['services']['redis']}
        self.lock.write_text(json.dumps(self.payload))
        kubeconfig = str(self.root / 'appflowy-ci.kubeconfig')
        with patch.dict(os.environ, {'KUBECONFIG': kubeconfig,
                                     'APPFLOWY_DATABASE_URL': 'postgres://private'}):
            instance = self.deployment('helm')
        result = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        with patch.object(instance, 'guard'), patch.object(instance, 'render'), \
                patch.object(instance, 'wait_http'), patch.object(instance, 'check_images'), \
                patch('deployment.subprocess.run', return_value=result) as run:
            instance.up()
            self.assertEqual([call.args[0][0] for call in run.call_args_list], ['helm', 'kubectl'])
            for call in run.call_args_list:
                self.assertEqual(call.kwargs['env']['KUBECONFIG'], kubeconfig)
                self.assertNotIn('APPFLOWY_DATABASE_URL', call.kwargs['env'])

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

    def test_diagnostics_preserve_results_before_a_log_timeout_and_continue(self):
        instance = self.deployment()
        instance.runtime.mkdir()
        secret = 'private-diagnostic-password-123456'
        (instance.runtime / 'credentials.json').write_text(json.dumps({'password': secret}))
        for name in ('api.results.json', 'registration-results.json', 'browser.log', 'registration.log'):
            (instance.runtime / name).write_text(json.dumps({'passed': True, 'detail': secret}))
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs['timeout'], 30)
            for name in ('api.results.json', 'registration-results.json', 'browser.log', 'registration.log'):
                evidence = (instance.artifacts / name).read_text()
                self.assertIn('[redacted]', evidence)
                self.assertNotIn(secret, evidence)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(args, kwargs['timeout'],
                    output=('partial stdout ' + secret).encode(),
                    stderr=('partial stderr ' + base64.b64encode(secret.encode()).decode()).encode())
            return subprocess.CompletedProcess(args, 0, 'later service log', '')

        warning = io.StringIO()
        with patch.object(instance, 'guard'), patch('deployment.subprocess.run', side_effect=run), \
             patch('sys.stdout', warning):
            instance.diagnostics()
        self.assertEqual(len(calls), len(CORE))
        first = (instance.artifacts / (sorted(CORE)[0] + '.log')).read_text()
        self.assertIn('partial stdout [redacted]', first)
        self.assertIn('partial stderr [redacted]', first)
        self.assertEqual((instance.artifacts / (sorted(CORE)[-1] + '.log')).read_text(), 'later service log')
        failures = json.loads((instance.artifacts / 'diagnostic-failures.json').read_text())
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]['reason'], 'timeout')
        self.assertEqual(failures[0]['timeout_seconds'], 30)
        self.assertIn('::warning::Diagnostic', warning.getvalue())
        self.assertNotIn(secret, warning.getvalue())

    def test_diagnostic_nonzero_and_missing_commands_record_sanitized_failures(self):
        instance = self.deployment()
        private_write(instance.runtime / 'credentials.json', json.dumps({'password': 'secret-diagnostic-password'}))
        with patch('deployment.subprocess.run', side_effect=[
                subprocess.CompletedProcess(('missing',), 23, 'partial stdout ', 'secret-diagnostic-password'),
                FileNotFoundError('missing secret-diagnostic-password')]), patch('sys.stdout', io.StringIO()):
            failed = instance.diagnostic_command('first', 'missing')
            missing = instance.diagnostic_command('second', 'missing')
        self.assertEqual(failed.returncode, 23)
        self.assertIn('partial stdout [redacted]', failed.stdout)
        self.assertIsNone(missing.returncode)
        self.assertIn('[redacted]', missing.stdout)
        failures_text = (instance.artifacts / 'diagnostic-failures.json').read_text()
        self.assertNotIn('secret-diagnostic-password', failures_text)
        failures = json.loads(failures_text)
        self.assertEqual([item['reason'] for item in failures], ['nonzero exit', 'command unavailable'])
        self.assertEqual(failures[0]['returncode'], 23)

    def test_swarm_diagnostics_use_exact_service_labels_and_local_retained_tasks(self):
        instance = self.deployment('swarm')
        identifiers = ['a' * 12, 'b' * 12]
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs['timeout'], 30)
            self.assertNotEqual(args[:3], ('docker', 'service', 'logs'))
            output = '\n'.join(identifiers) if args[:3] == ('docker', 'ps', '-aq') else 'diagnostic output'
            return subprocess.CompletedProcess(args, 0, output, 'CLI warning on stderr')

        with patch.object(instance, 'guard'), patch('deployment.subprocess.run', side_effect=run):
            instance.diagnostics()
        inventories = [args for args in calls if args[:3] == ('docker', 'ps', '-aq')]
        self.assertEqual(inventories, [
            ('docker', 'ps', '-aq', '--filter', 'label=com.docker.swarm.service.name=appflowy-ci_' + name)
            for name in sorted(CORE)])
        logs = [args for args in calls if args[:2] == ('docker', 'logs')]
        self.assertEqual(logs, [('docker', 'logs', '--tail=160', identifier)
                               for _ in sorted(CORE) for identifier in identifiers])
        for name in CORE:
            output = (instance.artifacts / (name + '.log')).read_text()
            for identifier in identifiers:
                self.assertIn('Container ' + identifier, output)
        self.assertEqual(json.loads((instance.artifacts / 'diagnostic-failures.json').read_text()), [])

    def test_helm_diagnostics_keep_collecting_after_errors_and_parse_only_inventory_stdout(self):
        self.payload['helm_services'] = {'redis': self.payload['services']['redis']}
        self.lock.write_text(json.dumps(self.payload))
        instance = self.deployment('helm')
        calls = []
        pod = {'metadata': {'name': 'appflowy-ci-cloud-pod'},
               'spec': {'containers': [{'name': 'appflowy-cloud'}], 'initContainers': [{'name': 'init'}]}}

        def run(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs['timeout'], 30)
            if args[-1] == 'wide':
                raise FileNotFoundError('kubectl temporarily unavailable')
            output = json.dumps({'items': [pod]}) if args[-1] == 'json' else 'collected output'
            return subprocess.CompletedProcess(args, 0, output, 'CLI warning on stderr')

        with patch.object(instance, 'guard'), patch('deployment.subprocess.run', side_effect=run), \
             patch('sys.stdout', io.StringIO()):
            instance.diagnostics()
        self.assertIn(('kubectl', '--context', 'kind-appflowy-ci', '-n', 'appflowy-ci', 'get', 'pods',
                       '-l', 'app.kubernetes.io/instance=appflowy-ci', '-o', 'json'), calls)
        for container in ('appflowy-cloud', 'init'):
            self.assertIn('collected output',
                (instance.artifacts / ('appflowy-ci-cloud-pod-' + container + '.log')).read_text())
        failures = json.loads((instance.artifacts / 'diagnostic-failures.json').read_text())
        self.assertEqual([item['name'] for item in failures], ['pods'])

    def test_diagnostic_timeout_is_enforced_on_a_real_child_and_keeps_partial_output(self):
        instance = self.deployment()
        started = time.monotonic()
        with patch('sys.stdout', io.StringIO()):
            result = instance.diagnostic_command('short child', sys.executable, '-u', '-c',
                'import time; print("before timeout", flush=True); time.sleep(10)', timeout=0.5)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsNone(result.returncode)
        self.assertIn('before timeout', result.stdout)
        failure = json.loads((instance.artifacts / 'diagnostic-failures.json').read_text())[0]
        self.assertEqual(failure['reason'], 'timeout')
        self.assertEqual(failure['timeout_seconds'], 0.5)

    def test_registration_requires_fresh_success_and_preserves_sanitized_failure_evidence(self):
        for outcome in ('success', 'exit_failure', 'timeout', 'false_result', 'missing_result'):
            with self.subTest(outcome=outcome):
                instance = self.deployment()
                instance.runtime.mkdir(exist_ok=True)
                secret = 'private-registration-password-' + outcome
                (instance.runtime / 'registration-user.json').write_text(json.dumps({'password': secret}))
                result_path = instance.runtime / 'registration-results.json'
                # A previous success must not satisfy a run that emits no result.
                result_path.write_text(json.dumps({'passed': True}))

                def run(*args, **kwargs):
                    kwargs['stdout'].write('registration diagnostic ' + secret)
                    if outcome != 'missing_result':
                        result_path.write_text(json.dumps({'passed': outcome == 'success', 'detail': secret}))
                    if outcome == 'timeout':
                        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
                    return subprocess.CompletedProcess(args[0], int(outcome == 'exit_failure'))

                with patch('deployment.subprocess.run', side_effect=run):
                    if outcome == 'success':
                        instance.registration()
                    else:
                        with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                            instance.registration()
                log = (instance.artifacts / 'registration.log').read_text()
                self.assertIn('[redacted]', log)
                self.assertNotIn(secret, log)
                if outcome != 'missing_result':
                    result = (instance.artifacts / 'registration-results.json').read_text()
                    self.assertNotIn(secret, result)
                    self.assertEqual(json.loads(result)['passed'], outcome == 'success')
                else:
                    self.assertFalse((instance.artifacts / 'registration-results.json').exists())

    def test_acceptance_is_not_written_when_final_registration_fails(self):
        instance = self.deployment()
        instance.evidence('core-acceptance.json', {'passed': True, 'mode': instance.mode, 'coverage': []})
        # A repeated failing attempt must not leave a prior final success.
        instance.evidence('acceptance.json', {'passed': True})
        with patch.object(instance, 'guard'), patch.object(instance, 'cleanup_fixture'), \
             patch.object(instance, 'registration', side_effect=RuntimeError('registration failed')):
            with self.assertRaisesRegex(RuntimeError, 'registration failed'):
                instance.register()
        self.assertFalse((instance.artifacts / 'acceptance.json').exists())

    def test_final_registration_requires_matching_core_success_and_fixture_cleanup(self):
        for case in ('missing', 'failed', 'wrong_mode', 'cleanup_failed', 'success'):
            with self.subTest(case=case):
                instance = self.deployment()
                core = {'passed': case != 'failed', 'mode': 'swarm' if case == 'wrong_mode' else instance.mode,
                        'coverage': ['durable application state'], 'excluded': ['SMTP']}
                if case == 'missing':
                    (instance.artifacts / 'core-acceptance.json').unlink(missing_ok=True)
                else:
                    instance.evidence('core-acceptance.json', core)
                with patch.object(instance, 'guard'), patch.object(instance, 'cleanup_fixture') as cleanup, \
                     patch.object(instance, 'registration') as registration:
                    if case == 'cleanup_failed':
                        cleanup.side_effect = RuntimeError('cleanup failed')
                    if case == 'success':
                        instance.register()
                        cleanup.assert_called_once()
                        registration.assert_called_once()
                        result = json.loads((instance.artifacts / 'acceptance.json').read_text())
                        self.assertEqual(result['coverage'], ['durable application state', 'browser registration'])
                        self.assertEqual(result['excluded'], ['SMTP'])
                    else:
                        with self.assertRaises(RuntimeError):
                            instance.register()
                        registration.assert_not_called()
                        if case != 'cleanup_failed':
                            cleanup.assert_not_called()
                        self.assertFalse((instance.artifacts / 'acceptance.json').exists())

    def cleanup_fixture_case(self):
        instance = self.deployment()
        user_id = '11111111-1111-4111-8111-111111111111'
        workspace_id = '22222222-2222-4222-8222-222222222222'
        admin_id = '33333333-3333-4333-8333-333333333333'
        email = 'ci-012345abcdef+user@example.com'
        files = {
            'credentials.json': {'admin_email': 'ci-012345abcdef@example.com', 'admin_password': 'test-password'},
            'ordinary-user.json': {'email': email, 'password': 'test-password'},
            'ordinary-user-ownership.json': {'user_id': user_id, 'email': email},
            'api-state.json': {'workspace_id': workspace_id},
            'recovery-api-state.json': {'workspace_id': workspace_id},
            'ui-target.json': {'workspace_id': workspace_id},
        }
        for name, value in files.items():
            private_write(instance.runtime / name, json.dumps(value))
        responses = [
            {'user': {'id': user_id, 'email': email}, 'access_token': 'ordinary-token'},
            {'user': {'id': admin_id, 'email': files['credentials.json']['admin_email']}, 'access_token': 'admin-token'},
            [{'workspace_id': workspace_id}],
            [{'workspace_id': workspace_id, 'member_count': 1}],
            {'seats_taken': 1, 'total_seats': 1},
            True,
            {'seats_taken': 0, 'total_seats': 1},
        ]
        return instance, files, responses

    def test_fixture_cleanup_refuses_local_execution_before_any_api_call(self):
        instance = self.deployment()
        with patch.dict(os.environ, {}, clear=True), patch.object(instance, 'fixture_request') as request:
            with self.assertRaisesRegex(RuntimeError, 'GitHub-hosted'):
                instance.cleanup_fixture()
            request.assert_not_called()

    def test_fixture_cleanup_deletes_only_the_verified_created_user(self):
        instance, files, responses = self.cleanup_fixture_case()
        with patch.object(instance, 'guard'), patch.object(instance, 'fixture_request', side_effect=responses) as request:
            instance.cleanup_fixture()
        deletes = [call for call in request.call_args_list if call.args[0] == 'DELETE']
        user_id = files['ordinary-user-ownership.json']['user_id']
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0].args, ('DELETE', f'/api/admin/users/{user_id}?soft_delete=false'))
        self.assertEqual(deletes[0].kwargs, {'token': 'admin-token'})
        evidence = json.loads((instance.artifacts / 'fixture-cleanup.json').read_text())
        self.assertTrue(evidence['passed'])
        self.assertEqual(evidence['seats_before'], {'seats_taken': 1, 'total_seats': 1})
        self.assertEqual(evidence['seats_after'], {'seats_taken': 0, 'total_seats': 1})

    def test_fixture_cleanup_fails_closed_before_deleting_unowned_data(self):
        cases = ('missing_ownership', 'wrong_email', 'wrong_login', 'admin_identity',
                 'disagreeing_fixture', 'extra_membership', 'wrong_owned_workspace',
                 'extra_owned_workspace', 'other_member', 'other_occupied_seat')
        for case in cases:
            with self.subTest(case=case):
                instance, files, responses = self.cleanup_fixture_case()
                if case == 'missing_ownership':
                    (instance.runtime / 'ordinary-user-ownership.json').unlink()
                elif case == 'wrong_email':
                    files['ordinary-user.json']['email'] = 'unrelated@example.com'
                    private_write(instance.runtime / 'ordinary-user.json', json.dumps(files['ordinary-user.json']))
                elif case == 'wrong_login':
                    responses[0]['user']['id'] = responses[1]['user']['id']
                elif case == 'admin_identity':
                    responses[1]['user']['id'] = responses[0]['user']['id']
                elif case == 'disagreeing_fixture':
                    private_write(instance.runtime / 'ui-target.json', json.dumps({'workspace_id': 'different'}))
                elif case == 'extra_membership':
                    responses[2].append({'workspace_id': 'unrelated'})
                elif case == 'wrong_owned_workspace':
                    responses[3][0]['workspace_id'] = 'unrelated'
                elif case == 'extra_owned_workspace':
                    responses[3].append({'workspace_id': 'unrelated', 'member_count': 1})
                elif case == 'other_member':
                    responses[3][0]['member_count'] = 2
                elif case == 'other_occupied_seat':
                    responses[4]['seats_taken'] = 2
                with patch.object(instance, 'guard'), patch.object(instance, 'fixture_request', side_effect=responses) as request:
                    with self.assertRaises((RuntimeError, FileNotFoundError)):
                        instance.cleanup_fixture()
                self.assertFalse(any(call.args[0] == 'DELETE' for call in request.call_args_list))
                self.assertFalse(json.loads((instance.artifacts / 'fixture-cleanup.json').read_text())['passed'])

    def test_fixture_cleanup_requires_confirmed_deletion_and_unchanged_license(self):
        for case in ('delete_rejected', 'seat_not_released', 'license_changed'):
            with self.subTest(case=case):
                instance, files, responses = self.cleanup_fixture_case()
                if case == 'delete_rejected':
                    responses[5] = False
                elif case == 'seat_not_released':
                    responses[6]['seats_taken'] = 1
                else:
                    responses[6]['total_seats'] = 2
                with patch.object(instance, 'guard'), patch.object(instance, 'fixture_request', side_effect=responses):
                    with self.assertRaisesRegex(RuntimeError, 'Fixture cleanup'):
                        instance.cleanup_fixture()
                self.assertFalse(json.loads((instance.artifacts / 'fixture-cleanup.json').read_text())['passed'])

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
