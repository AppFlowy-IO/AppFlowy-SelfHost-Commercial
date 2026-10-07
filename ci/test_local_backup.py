"""Local qualification must not adopt an operator's containers, networks or data."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from configuration import source_fingerprint
from deployment import private_write
from images import CORE, ROOT, resolve_local_image
from local_backup import LocalBackupDeployment, OWNER_LABEL


class LocalBackupSafetyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='appflowy-local-contract-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = self.root / 'ci/.local/unique-run'
        self.lock = self.root / 'images.json'
        digest = 'sha256:' + 'a' * 64
        record = {'source': 'local:latest', 'image': digest, 'config_digest': digest, 'platform': 'linux/arm64'}
        self.lock.write_text(json.dumps({'local': True, 'services': {name: record for name in CORE},
            'backup_services': {'appflowy_backup': record}, 'source_sha256': source_fingerprint(),
            'compose_sha256': hashlib.sha256((ROOT / 'docker-compose.yml').read_bytes()).hexdigest()}))
        self.root_patch = patch('local_backup.ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def deployment(self, **environment):
        with patch.dict(os.environ, environment, clear=True), patch('local_backup.ports', return_value=(21080, 21443)):
            return LocalBackupDeployment(self.runtime, self.root / 'artifacts', self.lock)

    def own(self, instance):
        instance.owner = {'project': instance.name, 'runtime': str(instance.runtime), 'endpoint': 'unix:///docker.sock',
                          'token': 'local-ownership-token', 'http_port': 21080, 'tls_port': 21443}

    def docker(self, instance, endpoint='unix:///docker.sock', container=None, volume=None, network=None):
        def run(*args, **kwargs):
            if args[1:3] == ('context', 'inspect'):
                return json.dumps([{'Endpoints': {'docker': {'Host': endpoint}}}])
            if args[1] == 'ps':
                return 'container' if container else ''
            if args[1] == 'inspect':
                return json.dumps([container])
            if args[1:3] == ('volume', 'ls'):
                return volume['Name'] if volume else ''
            if args[1:3] == ('volume', 'inspect'):
                return json.dumps([volume])
            if args[1:3] == ('network', 'ls'):
                return network['Id'] if network else ''
            if args[1:3] == ('network', 'inspect'):
                return json.dumps([network])
            raise AssertionError('Unexpected Docker action ' + str(args[:3]))
        instance.run = Mock(side_effect=run)

    def test_local_entrypoint_requires_owned_private_runtime_and_local_image_lock(self):
        instance = self.deployment()
        self.assertEqual(instance.base_url, 'http://127.0.0.1:21080')
        self.assertFalse(instance.pull_images)
        self.runtime.mkdir(parents=True)
        (self.runtime / 'operator-file').write_text('do not touch')
        with self.assertRaisesRegex(RuntimeError, 'nonempty'):
            self.deployment()
        (self.runtime / 'operator-file').unlink()
        self.own(instance)
        private_write(self.runtime / 'local-owner.json', json.dumps(instance.owner))
        self.assertEqual(self.deployment().owner, instance.owner)
        (self.runtime / 'local-owner.json').chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'private'):
            self.deployment()

    def test_unowned_existing_container_blocks_mutation(self):
        instance = self.deployment()
        instance.creating = True
        self.docker(instance, container={'Config': {'Labels': {}}})
        with self.assertRaisesRegex(RuntimeError, 'containers not owned'):
            instance.guard()
        self.assertFalse(any(call.args[1] in ('compose', 'rm') for call in instance.run.call_args_list))

    def test_unowned_volume_or_network_without_containers_cannot_be_reused_or_deleted(self):
        for kind in ('volume', 'network'):
            instance = self.deployment()
            self.own(instance)
            resource = {'Id': 'network-id', 'Name': instance.name + '_data', 'Labels': {}}
            self.docker(instance, **{kind: resource})
            instance.smoke = Mock()
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, kind + ' resources not owned'):
                instance.backup_test()
            instance.smoke.assert_not_called()
            with self.assertRaises(RuntimeError):
                instance.cleanup()
            self.assertFalse(any('down' in call.args for call in instance.run.call_args_list))

    def test_matching_resource_labels_allow_only_recorded_project(self):
        instance = self.deployment()
        self.own(instance)
        label = {OWNER_LABEL: instance.owner['token']}
        self.docker(instance, container={'Config': {'Labels': label}},
                    volume={'Name': instance.name + '_postgres_data', 'Labels': label},
                    network={'Id': 'network-id', 'Name': instance.name + '_default', 'Labels': label})
        self.assertEqual(instance.guard(), 'unix:///docker.sock')

    def test_remote_context_cannot_be_hidden_by_another_local_endpoint(self):
        cases = [({'DOCKER_HOST': 'unix:///docker.sock'}, 'ssh://remote'),
                 ({'DOCKER_HOST': 'tcp://remote:2375'}, 'unix:///docker.sock'),
                 ({'DOCKER_CONTEXT': 'remote', 'DOCKER_HOST': 'unix:///docker.sock'}, 'ssh://remote')]
        for env, endpoint in cases:
            instance = self.deployment(**env)
            self.own(instance)
            self.docker(instance, endpoint=endpoint)
            with self.subTest(env=env), self.assertRaisesRegex(RuntimeError, 'local Unix'):
                instance.guard()
        instance = self.deployment()
        self.own(instance)
        self.docker(instance, endpoint='unix:///another.sock')
        with self.assertRaisesRegex(RuntimeError, 'endpoint changed'):
            instance.guard()

    def test_operator_application_variables_cannot_override_isolated_runtime(self):
        instance = self.deployment(APPFLOWY_DATABASE_URL='postgres://operator', APPFLOWY_REDIS_URI='redis://operator',
            APPFLOWY_S3_MINIO_URL='http://operator', COMPOSE_PROJECT_NAME='operator', COMPOSE_FILE='/operator.yml')
        for key in ('APPFLOWY_DATABASE_URL', 'APPFLOWY_REDIS_URI', 'APPFLOWY_S3_MINIO_URL',
                    'COMPOSE_PROJECT_NAME', 'COMPOSE_FILE'):
            self.assertNotIn(key, instance.env)
        self.assertEqual(instance.env['SWARM_TEST_DIR'], str(self.runtime.resolve()))

    def test_up_cannot_regenerate_credentials_or_overwrite_restored_state_in_an_old_run(self):
        instance = self.deployment()
        self.own(instance)
        instance.run = Mock()
        with self.assertRaisesRegex(RuntimeError, 'new runtime directory'):
            instance.up()
        instance.run.assert_not_called()

    def rendered(self):
        instance = self.deployment()
        self.own(instance)
        private_write(instance.owner_path, json.dumps(instance.owner))
        services = {name: {'image': 'local:latest', 'environment': {}, 'healthcheck': {}}
                    for name in instance.services | {'ai'}}
        rendered = {'services': services, 'volumes': {'postgres_data': {}, 'backup_work': {}},
                    'networks': {'default': {}}}
        instance.run = Mock(side_effect=lambda *args, **kwargs: json.dumps(rendered) if '--format' in args else '')
        with patch('deployment.check_compose', return_value='2.30.0'):
            instance.render()
        return instance

    def test_render_labels_data_and_networks_preserves_source_and_binds_loopback(self):
        instance = self.rendered()
        override = yaml.safe_load((instance.source / 'ci.override.yml').read_text())
        for service in override['services'].values():
            self.assertEqual(service['labels'][OWNER_LABEL], instance.owner['token'])
            self.assertEqual(service['pull_policy'], 'never')
        for kind in ('volumes', 'networks'):
            for resource in override[kind].values():
                self.assertEqual(resource['labels'][OWNER_LABEL], instance.owner['token'])
        env = (instance.source / '.env').read_text()
        self.assertIn('NGINX_PORT=127.0.0.1:21080\n', env)
        self.assertIn('NGINX_TLS_PORT=127.0.0.1:21443\n', env)
        self.assertEqual((instance.source / 'docker-compose.yml').read_bytes(), (ROOT / 'docker-compose.yml').read_bytes())
        self.assertIn(str(instance.source / '.env'), instance.compose)
        self.assertNotIn(str(instance.runtime / 'compose.yml'), instance.compose)

    def test_cleanup_uses_original_installed_sources_when_checkout_or_external_lock_changes(self):
        instance = self.rendered()
        self.lock.unlink()
        with patch('deployment.ROOT', self.root / 'changed-checkout'):
            installed = LocalBackupDeployment(self.runtime, self.root / 'artifacts', self.lock, installed_source=True)
            with self.assertRaises(FileNotFoundError):
                self.deployment()
        self.assertEqual(installed.images, instance.images)
        self.docker(installed)
        self.assertEqual(installed.guard(), 'unix:///docker.sock')
        for action in ('backup_test', 'test', 'render', 'up'):
            with self.subTest(action=action), self.assertRaises(RuntimeError):
                getattr(installed, action)()

    def test_installed_cleanup_cannot_expand_manifest_paths_or_ignore_changed_inputs(self):
        instance = self.rendered()
        original = json.loads(instance.installed_lock.read_text())
        for bad in ('../credentials.json', '/etc/passwd', 'docker/../../private', 'docker\\private'):
            changed = {**original, 'source_files': [bad]}
            private_write(instance.installed_lock, json.dumps(changed))
            with self.subTest(path=bad), self.assertRaisesRegex(RuntimeError, 'relative file names'):
                LocalBackupDeployment(self.runtime, self.root / 'artifacts', self.lock, installed_source=True)
        private_write(instance.installed_lock, json.dumps(original))
        installed = LocalBackupDeployment(self.runtime, self.root / 'artifacts', self.lock, installed_source=True)
        (installed.source / 'ci.override.yml').write_text('services: {}\n')
        self.docker(installed)
        with self.assertRaisesRegex(RuntimeError, 'environment or overrides changed'):
            installed.guard()

    def test_generated_restore_selections_remain_dynamic_under_installed_integrity_checks(self):
        instance = self.rendered()
        selected = instance.source / 'backup-ops/runtime'
        selected.mkdir(parents=True)
        (selected / 'selection-appflowy_cloud.env').write_text('APPFLOWY_S3_BUCKET=restored\n')
        self.docker(instance)
        self.assertEqual(instance.guard(), 'unix:///docker.sock')
        (selected / 'selection-appflowy_cloud.env').write_text('APPFLOWY_S3_BUCKET=second-restore\n')
        self.assertEqual(instance.guard(), 'unix:///docker.sock')

    def test_local_images_use_installed_native_ids_without_registry_pull(self):
        digest = 'sha256:' + 'a' * 64
        record = [{'Os': 'linux', 'Architecture': 'arm64', 'Id': digest}]
        with patch('images.command', side_effect=[json.dumps(record), 'linux/aarch64']) as command:
            result = resolve_local_image('backup', 'local-build')
        self.assertEqual(result['image'], digest)
        self.assertEqual(result['config_digest'], digest)
        self.assertEqual(result['platform'], 'linux/arm64')
        self.assertEqual(command.call_args_list[0].args, ('docker', 'image', 'inspect', 'local-build'))
        self.assertFalse(any('pull' in call.args or 'buildx' in call.args for call in command.call_args_list))
        with patch('images.command', side_effect=[json.dumps(record), 'linux/x86_64']):
            with self.assertRaisesRegex(RuntimeError, 'platform'):
                resolve_local_image('backup', 'local-build')

    def test_registry_lock_is_not_accepted_as_a_local_build_qualification(self):
        lock = json.loads(self.lock.read_text())
        lock.pop('local')
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(RuntimeError, '--local --backup'):
            self.deployment()

    def test_shareable_evidence_removes_generated_credentials_and_connection_secrets(self):
        instance = self.deployment()
        instance.runtime.mkdir(parents=True)
        private_write(instance.runtime / 'credentials.json', json.dumps({'admin_password': 'local-private-password'}))
        instance.evidence('diagnostic.txt', 'password=local-private-password postgres://user:other-secret@postgres/db')
        text = (instance.artifacts / 'diagnostic.txt').read_text()
        self.assertNotIn('local-private-password', text)
        self.assertNotIn('other-secret', text)
        self.assertIn('[redacted]', text)


if __name__ == '__main__':
    unittest.main()
