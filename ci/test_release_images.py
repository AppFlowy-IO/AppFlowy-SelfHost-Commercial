"""Release notifications must never promote test, partial, or stale image sets."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

from deployment import normalized_image_reference
import update_release_images as release


class ReleaseImageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.paths = ['docker-compose.yml', 'helm/appflowy-cloud/values.yaml']
        for name in self.paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            value = yaml.safe_load((release.ROOT / name).read_text())
            # Layout follows the real sources; fixture versions must not track future releases.
            for service, (repository, helm_key) in release.SERVICES.items():
                if name == 'docker-compose.yml':
                    tag = '${APPFLOWY_WEB_VERSION:-latest}' if service == 'appflowy_web' else 'latest'
                    value['services'][service]['image'] = 'appflowyinc/' + repository + ':' + tag
                else:
                    value[helm_key]['image']['tag'] = 'latest'
                    value[helm_key]['image'].pop('digest', None)
            target.write_text(yaml.safe_dump(value, sort_keys=False))
        self.original = self.contents()
        self.digest = 'sha256:' + 'a' * 64
        self.resolve = Mock(return_value=self.digest)

    def contents(self):
        return {name: (self.root / name).read_text() for name in self.paths}

    def update(self, source='web', tag='0.20.0', services=None):
        return release.prepare_update(self.root, source, tag,
                                      services if services is not None else release.DEFAULT_SERVICES[source],
                                      resolve=self.resolve)

    def compose(self):
        return yaml.safe_load((self.root / self.paths[0]).read_text())

    def test_test_notifications_are_no_ops_before_any_registry_access(self):
        for source in ('cloud', 'web'):
            for tag in ('0.20.0_test', 'v0.20.0_test', 'arbitrary_test'):
                with self.subTest(source=source, tag=tag):
                    changes, reason = self.update(source, tag)
                    self.assertEqual(changes, [])
                    self.assertIn('ignored', reason)
        self.resolve.assert_not_called()
        self.assertEqual(self.contents(), self.original)

    def test_web_update_pins_the_index_and_changes_only_web(self):
        original = self.compose()
        (self.root / '.env').write_text('APPFLOWY_WEB_VERSION=should-not-be-read\n')
        changes, _ = self.update()
        self.assertEqual([row[0] for row in changes], ['appflowy_web'])
        expected = 'appflowyinc/appflowy_web:0.20.0@' + self.digest
        updated = self.compose()
        self.assertEqual(updated['services']['appflowy_web']['image'], expected)
        original['services']['appflowy_web']['image'] = expected
        self.assertEqual(updated, original)
        image = yaml.safe_load((self.root / self.paths[1]).read_text())['appflowy-web']['image']
        self.assertEqual(image['tag'], '0.20.0')
        self.assertEqual(image['digest'], self.digest)
        self.assertEqual(normalized_image_reference(expected),
                         normalized_image_reference(image['repository'] + '@' + image['digest']))
        self.assertEqual((self.root / '.env').read_text(), 'APPFLOWY_WEB_VERSION=should-not-be-read\n')

    def test_cloud_updates_only_successfully_published_services_including_optional_ones(self):
        original = self.compose()
        services = ['gotrue', 'appflowy_cloud', 'appflowy_worker', 'appflowy_search', 'appflowy_backup', 'ai']
        changes, _ = self.update('cloud', services=services)
        self.assertEqual({row[0] for row in changes}, set(services))
        updated = self.compose()
        for service in updated['services']:
            if service in services:
                repository, helm_key = release.SERVICES[service]
                expected = f'appflowyinc/{repository}:0.20.0@{self.digest}'
                self.assertEqual(updated['services'][service]['image'], expected)
                image = yaml.safe_load((self.root / self.paths[1]).read_text())[helm_key]['image']
                self.assertEqual(image['digest'], self.digest)
            else:
                self.assertEqual(updated['services'][service], original['services'][service])

    def test_duplicate_events_and_release_retries_are_idempotent(self):
        self.update()
        pinned = self.contents()
        changes, _ = self.update()
        self.assertEqual(changes, [])
        self.assertEqual(self.contents(), pinned)
        self.assertEqual(pinned[self.paths[1]].count('    digest: ' + self.digest), 1)

    def test_one_missing_image_prevents_the_entire_set_from_being_written(self):
        self.resolve.side_effect = [self.digest, RuntimeError('image not published')]
        with self.assertRaisesRegex(RuntimeError, 'not published'):
            self.update('cloud')
        self.assertEqual(self.contents(), self.original)

    def test_cloud_and_worker_cannot_be_updated_independently(self):
        for services in (['appflowy_cloud'], ['appflowy_worker']):
            with self.subTest(services=services), self.assertRaisesRegex(ValueError, 'together'):
                self.update('cloud', services=services)
        self.resolve.assert_not_called()
        self.assertEqual(self.contents(), self.original)

    def test_late_notifications_cannot_downgrade_the_deployment(self):
        self.update(tag='v0.20.0')
        pinned = self.contents()
        self.resolve.reset_mock()
        for tag in ('0.19.99', '0.20.0-rc.1'):
            changes, reason = self.update(tag=tag)
            self.assertEqual(changes, [])
            self.assertIn('stale', reason)
        self.resolve.assert_not_called()
        self.assertEqual(self.contents(), pinned)
        self.assertLess(release.version_key('0.20.0-rc.2'), release.version_key('0.20.0-rc.10'))

    def test_republished_version_does_not_silently_replace_the_original_digest(self):
        self.update()
        pinned = self.contents()
        self.resolve.return_value = 'sha256:' + 'b' * 64
        with self.assertRaisesRegex(ValueError, 'republished'):
            self.update()
        self.assertEqual(self.contents(), pinned)

    def test_malformed_versions_and_foreign_service_selections_cannot_change_files(self):
        for tag in ('latest', 'stable', '0.20.0\nextra=value', '0.20.0;true', '../0.20.0'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                self.update(tag=tag)
        for services in ([], ['appflowy_cloud'], ['appflowy_web', 'appflowy_web'], ['nginx'], 'appflowy_web'):
            with self.subTest(services=services), self.assertRaises(ValueError):
                self.update(services=services)
        self.resolve.assert_not_called()
        self.assertEqual(self.contents(), self.original)

    def test_publisher_identity_and_manual_defaults(self):
        event = {'action': 'selfhost-images-published', 'client_payload': {
            'source': 'web', 'tag': '0.20.0', 'services': ['appflowy_web'],
            'source_repository': release.SOURCES['web'],
            'source_url': 'https://github.com/AppFlowy-IO/AppFlowy-Web/releases/tag/0.20.0'}}
        self.assertEqual(release.notification('repository_dispatch', event)[:3],
                         ('web', '0.20.0', ['appflowy_web']))
        event['client_payload']['source_repository'] = 'someone/else'
        with self.assertRaisesRegex(ValueError, 'publisher'):
            release.notification('repository_dispatch', event)
        manual = {'inputs': {'source': 'cloud', 'tag': '0.20.0'}}
        self.assertEqual(release.notification('workflow_dispatch', manual)[2], release.DEFAULT_SERVICES['cloud'])

    def test_missing_target_image_line_cannot_rewrite_the_next_service(self):
        path = self.root / self.paths[0]
        text = path.read_text().replace('    image: appflowyinc/appflowy_web:${APPFLOWY_WEB_VERSION:-latest}\n', '')
        path.write_text(text)
        with self.assertRaises(KeyError):
            self.update()
        self.assertEqual(path.read_text(), text)


class RegistryIndexTests(unittest.TestCase):
    def test_parent_index_is_pinned_instead_of_the_amd64_child(self):
        manifest = {'digest': 'sha256:' + 'a' * 64, 'manifests': [
            {'digest': 'sha256:' + 'b' * 64, 'platform': {'os': 'linux', 'architecture': 'amd64'}},
            {'digest': 'sha256:' + 'c' * 64, 'platform': {'os': 'linux', 'architecture': 'arm64'}}]}
        with patch.object(release, 'command', return_value=json.dumps(manifest)):
            self.assertEqual(release.release_digest('appflowyinc/appflowy_web:0.20.0'), manifest['digest'])
        manifest['manifests'].pop()
        with patch.object(release, 'command', return_value=json.dumps(manifest)):
            with self.assertRaisesRegex(ValueError, 'linux/arm64'):
                release.release_digest('appflowyinc/appflowy_web:0.20.0')

    def test_digest_comparison_still_distinguishes_different_content(self):
        a, b = 'sha256:' + 'a' * 64, 'sha256:' + 'b' * 64
        self.assertNotEqual(normalized_image_reference('appflowyinc/appflowy_web:0.20.0@' + a),
                            normalized_image_reference('appflowyinc/appflowy_web@' + b))


class WorkflowImageSelectionTests(unittest.TestCase):
    def test_release_pr_checks_do_not_substitute_the_temporary_test_images(self):
        for filename, step_name in (
                ('deployment-test.yml', 'Resolve exact linux/amd64 image digests once'),
                ('backup-test.yml', 'Resolve exact core and Backup image digests')):
            workflow = yaml.safe_load((release.ROOT / '.github/workflows' / filename).read_text())
            step = next(step for job in workflow['jobs'].values() for step in job.get('steps', [])
                        if step.get('name') == step_name)
            for use_pins in ('true', 'false'):
                with self.subTest(workflow=filename, use_pins=use_pins), tempfile.TemporaryDirectory() as directory:
                    capture = Path(directory) / 'arguments'
                    environment = dict(os.environ, USE_RELEASE_PINS=use_pins, CAPTURED_ARGS=str(capture),
                                       SERVER_IMAGE_TAG='0.19.4_test', BACKUP_IMAGE='appflowyinc/appflowy_backup:0.19.4_test')
                    subprocess.run(['bash', '-e', '-o', 'pipefail', '-c',
                                    'python() { printf "%s\\n" "$@" > "$CAPTURED_ARGS"; }\n' + step['run']],
                                   env=environment, check=True, capture_output=True)
                    arguments = capture.read_text().splitlines()
                    self.assertEqual('--server-tag' in arguments, use_pins == 'false')
                    if filename == 'backup-test.yml':
                        self.assertIn('--backup', arguments)
                        self.assertEqual('--backup-image' in arguments, use_pins == 'false')
