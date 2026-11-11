"""Release notifications must never promote test, partial, or stale image sets."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

import images
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
        for source in ('cloud', 'web', 'admin'):
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
        services = ['gotrue', 'appflowy_cloud', 'appflowy_worker', 'appflowy_search', 'appflowy_mcp',
                    'appflowy_backup', 'ai']
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

    def test_mcp_image_updates_ask_the_reviewer_to_compare_the_copied_mcp_routes(self):
        def body(services):
            changes, _ = self.update('cloud', services=services)
            return release.pull_request_body('cloud', '0.20.0', '', changes)

        without_mcp = body(['appflowy_cloud', 'appflowy_worker', 'appflowy_search'])
        with_mcp = body(['appflowy_mcp'])
        self.assertIn('| appflowy_mcp |', with_mcp)
        self.assertIn('server commit the publisher run built', with_mcp)
        self.assertNotIn('MCP', without_mcp)
        self.assertIn('- [ ] `docker/nginx/nginx.conf`: the MCP locations (server: `nginx/nginx.conf`)', with_mcp)
        self.assertIn('- [ ] `docker-compose.yml`: the `appflowy_mcp` environment\n', with_mcp)
        for path, _, _ in release.MCP_COPIES:
            with self.subTest(path=path):
                self.assertIn(f'- [ ] `{path}`', with_mcp)
                # A moved or renamed copy must not leave the checklist pointing nowhere.
                self.assertIn('mcp', (release.ROOT / path).read_text().lower())

    def test_mcp_copies_include_the_settings_and_guides_and_match_the_release_guide(self):
        paths = [path for path, _, _ in release.MCP_COPIES]
        self.assertEqual(len(paths), len(set(paths)))
        # The deploy.env settings and the Compose and chart guides describe MCP's routes and settings.
        for path in ('deploy.env', 'docs/docker-compose.md', 'helm/appflowy-cloud/README.md'):
            self.assertIn(path, paths)
        guide = (release.ROOT / 'docs/RELEASE_IMAGES.md').read_text()
        section = guide.partition('\n## MCP copies\n')[2].partition('\n### ')[0]
        listed = re.findall(r'^- `([^`]+)`: ', section, re.M)
        self.assertEqual(listed, paths)

    def test_mcp_updates_link_the_deliberate_differences_and_ask_for_a_separate_port(self):
        changes, _ = self.update('cloud', services=['appflowy_mcp'])
        body = release.pull_request_body('cloud', '0.20.0', '', changes)
        self.assertIn(f'({release.MCP_DIFFERENCES_URL})', body)
        # GitHub's anchor for the guide's heading.
        guide = (release.ROOT / 'docs/RELEASE_IMAGES.md').read_text()
        self.assertTrue(release.MCP_DIFFERENCES_URL.endswith(
            '/blob/main/docs/RELEASE_IMAGES.md#deliberate-differences-from-the-server'))
        self.assertIn('\n### Deliberate differences from the server\n', guide)
        # Commits pushed to the automation branch are lost when a repeated notification rebuilds it.
        for text in (body, guide):
            self.assertIn('separate PR', text)
            self.assertIn('rebuilds', text)

    def test_mcp_updates_name_the_recorded_copy_baseline_until_mcp_is_pinned(self):
        self.assertRegex(release.MCP_COPIES_BASELINE, r'^[0-9a-f]{40}$')
        changes, _ = self.update('cloud', services=['appflowy_mcp'])
        self.assertIn(release.MCP_COPIES_BASELINE, release.pull_request_body('cloud', '0.20.0', '', changes))
        # Once MCP is pinned, the build of the pinned image is the baseline.
        changes, _ = self.update('cloud', tag='0.20.1', services=['appflowy_mcp'])
        self.assertIn('@sha256:', changes[0][1])
        pinned = release.pull_request_body('cloud', '0.20.1', '', changes)
        self.assertIn('server commit the publisher run built', pinned)
        self.assertNotIn(release.MCP_COPIES_BASELINE, pinned)
        # The release guide records the same baseline while the shipped MCP image is unpinned.
        image = yaml.safe_load((release.ROOT / 'docker-compose.yml').read_text())['services']['appflowy_mcp']['image']
        if not release.DIGEST.search(image):
            self.assertIn(release.MCP_COPIES_BASELINE, (release.ROOT / 'docs/RELEASE_IMAGES.md').read_text())

    def test_mcp_image_updates_are_left_for_review_instead_of_auto_merging(self):
        # Auto-merge would land a new MCP image before its copied routes and settings are ported.
        for source, services, merges in (('web', None, True),
                                         ('cloud', ['appflowy_cloud', 'appflowy_worker', 'appflowy_search'], True),
                                         ('cloud', release.DEFAULT_SERVICES['cloud'], False)):
            with self.subTest(source=source, services=services):
                changes, _ = self.update(source, services=services)
                self.assertTrue(changes)
                self.assertEqual(release.auto_merge(changes), merges)
                body = release.pull_request_body(source, '0.20.0', '', changes)
                self.assertEqual('Auto-merge waits for the required CI checks.' in body, merges)
                self.assertEqual('Auto-merge is off because the MCP image changed' in body, not merges)
        changes = [('appflowy_mcp', 'appflowyinc/appflowy_mcp:latest', 'appflowyinc/appflowy_mcp:0.20.0@' + self.digest)]
        with tempfile.TemporaryDirectory() as directory:
            event, body, output = (Path(directory) / name for name in ('event.json', 'body.md', 'output'))
            event.write_text('{}')
            environment = {'GITHUB_EVENT_NAME': 'repository_dispatch', 'GITHUB_OUTPUT': str(output)}
            with patch.dict(os.environ, environment), \
                 patch('sys.argv', ['update_release_images.py', '--event', str(event), '--body', str(body)]), \
                 patch.object(release, 'notification', return_value=('cloud', '0.20.0', ['appflowy_mcp'], '')), \
                 patch.object(release, 'prepare_update', return_value=(changes, 'Prepared exact image pins')), \
                 contextlib.redirect_stdout(io.StringIO()):
                release.main()
            self.assertIn('auto_merge=false\n', output.read_text())

    def test_admin_update_pins_only_the_public_admin_image_in_compose_and_helm(self):
        original = self.compose()
        original_chart = yaml.safe_load((self.root / self.paths[1]).read_text())
        (self.root / '.env').write_text('APPFLOWY_ADMIN_FRONTEND_VERSION=should-not-be-read\n')
        changes, _ = self.update('admin', tag='v1.2.3')
        self.assertEqual([row[0] for row in changes], ['admin_frontend'])
        expected = 'appflowyinc/admin_frontend:v1.2.3@' + self.digest
        original['services']['admin_frontend']['image'] = expected
        self.assertEqual(self.compose(), original)
        original_chart['admin-frontend']['image'].update(tag='v1.2.3', digest=self.digest)
        self.assertEqual(yaml.safe_load((self.root / self.paths[1]).read_text()), original_chart)
        self.resolve.assert_called_once_with('appflowyinc/admin_frontend:v1.2.3')
        self.assertEqual((self.root / '.env').read_text(),
                         'APPFLOWY_ADMIN_FRONTEND_VERSION=should-not-be-read\n')

    def test_admin_notifications_cannot_select_images_owned_by_other_publishers(self):
        selections = [
            ('admin', ['appflowy_web']),
            ('admin', ['appflowy_cloud', 'appflowy_worker']),
            ('cloud', ['admin_frontend']),
            ('web', ['admin_frontend']),
        ]
        for source, services in selections:
            with self.subTest(source=source, services=services), self.assertRaisesRegex(ValueError, 'source'):
                self.update(source, services=services)
        self.resolve.assert_not_called()
        self.assertEqual(self.contents(), self.original)

    def test_admin_retries_and_stale_events_preserve_pinned_releases(self):
        self.update('admin', tag='1.2.3')
        pinned = self.contents()
        changes, _ = self.update('admin', tag='1.2.3')
        self.assertEqual(changes, [])
        self.resolve.reset_mock()
        changes, reason = self.update('admin', tag='1.2.2')
        self.assertEqual(changes, [])
        self.assertIn('stale', reason)
        self.resolve.assert_not_called()
        self.resolve.return_value = 'sha256:' + 'b' * 64
        with self.assertRaisesRegex(ValueError, 'republished'):
            self.update('admin', tag='1.2.3')
        self.assertEqual(self.contents(), pinned)

    def test_duplicate_events_and_release_retries_are_idempotent(self):
        self.update()
        pinned = self.contents()
        changes, _ = self.update()
        self.assertEqual(changes, [])
        self.assertEqual(self.contents(), pinned)
        self.assertEqual(pinned[self.paths[1]].count('    digest: ' + self.digest), 1)

    def test_separate_cloud_publications_do_not_replace_another_open_image_selection(self):
        services = ['appflowy_cloud', 'appflowy_worker', 'appflowy_search']
        branch = release.update_branch('cloud', '0.20.0', services)
        self.assertEqual(branch, release.update_branch('cloud', '0.20.0', services[::-1]))
        self.assertNotEqual(branch, release.update_branch('cloud', '0.20.0', ['gotrue']))
        self.assertEqual(release.update_branch('web', '0.19.30', ['appflowy_web']),
                         'automation/image-updates/web-0.19.30')

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
        for source in ('cloud', 'web', 'admin'):
            with self.subTest(source=source):
                event = {'action': 'selfhost-images-published', 'client_payload': {
                    'source': source, 'tag': '0.20.0', 'services': release.DEFAULT_SERVICES[source],
                    'source_repository': release.SOURCES[source],
                    'source_url': 'https://github.com/' + release.SOURCES[source] + '/actions/runs/123'}}
                self.assertEqual(release.notification('repository_dispatch', event)[:3],
                                 (source, '0.20.0', release.DEFAULT_SERVICES[source]))
                event['client_payload']['source_repository'] = 'someone/else'
                with self.assertRaisesRegex(ValueError, 'publisher'):
                    release.notification('repository_dispatch', event)
                manual = {'inputs': {'source': source, 'tag': '0.20.0'}}
                self.assertEqual(release.notification('workflow_dispatch', manual)[2],
                                 release.DEFAULT_SERVICES[source])

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
    def test_update_prs_enable_auto_merge_only_when_the_updater_allows_it(self):
        workflow = yaml.safe_load((release.ROOT / '.github/workflows/update-release-images.yml').read_text())
        steps = workflow['jobs']['update']['steps']
        merge = next(step for step in steps if 'gh pr merge' in step.get('run', ''))
        self.assertIn("steps.update.outputs.auto_merge == 'true'", merge['if'])
        self.assertIn('update', [step.get('id') for step in steps])

    def test_release_pr_checks_do_not_substitute_the_qualification_baseline(self):
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
                                       SERVER_IMAGE_TAG='0.20.0', WEB_IMAGE_TAG='0.19.30',
                                       BACKUP_IMAGE='appflowyinc/appflowy_backup:0.20.0')
                    subprocess.run(['bash', '-e', '-o', 'pipefail', '-c',
                                    'python() { printf "%s\\n" "$@" > "$CAPTURED_ARGS"; }\n' + step['run']],
                                   env=environment, check=True, capture_output=True)
                    arguments = capture.read_text().splitlines()
                    self.assertEqual('--server-tag' in arguments, use_pins == 'false')
                    self.assertEqual('--web-tag' in arguments, use_pins == 'false')
                    if filename == 'backup-test.yml':
                        self.assertIn('--backup', arguments)
                        self.assertEqual('--backup-image' in arguments, use_pins == 'false')


class QualificationImageTests(unittest.TestCase):
    def test_server_and_web_baseline_is_explicit_and_release_pins_are_preserved(self):
        digest = 'sha256:' + 'a' * 64
        configured = {name: {'image': name + ':configured-release'} for name in images.CORE}
        backup = 'appflowy_backup:configured-release'
        for use_baseline in (False, True):
            with self.subTest(use_baseline=use_baseline), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'docker-compose.yml').write_text('source fingerprint input')
                output = root / 'image-lock.json'
                argv = ['images.py', '--backup', '--output', str(output)]
                if use_baseline:
                    argv += ['--server-tag', '0.20.0', '--web-tag', '0.19.30',
                             '--backup-image', 'appflowy_backup:0.20.0']
                configs = [json.dumps({'services': configured}),
                           json.dumps({'services': {**configured, 'appflowy_backup': {'image': backup}}})]

                def resolved(_name, reference):
                    return {'source': reference, 'image': images.repository(reference) + '@' + digest,
                            'digest': digest, 'config_digest': digest, 'platform': 'linux/amd64'}

                with patch('sys.argv', argv), patch.object(images, 'ROOT', root), \
                     patch.object(images, 'check_compose'), patch.object(images, 'isolated_source', return_value=root), \
                     patch.object(images, 'command', side_effect=configs), \
                     patch.object(images, 'source_fingerprint', return_value='source fingerprint'), \
                     patch.object(images, 'resolve_image', side_effect=resolved):
                    images.main()
                lock = json.loads(output.read_text())
                self.assertEqual(lock['services']['appflowy_mcp']['source'],
                                 configured['appflowy_mcp']['image'])
                for service, config in configured.items():
                    record = lock['services'][service]
                    expected = (service + ':0.20.0' if service in images.SERVER else
                                'appflowy_web:0.19.30' if service == 'appflowy_web' else config['image'])
                    self.assertEqual(record['source'], expected if use_baseline else config['image'])
                    if use_baseline and (service in images.SERVER or service == 'appflowy_web'):
                        self.assertEqual(record['configured_source'], config['image'])
                    else:
                        self.assertNotIn('configured_source', record)
                record = lock['backup_services']['appflowy_backup']
                self.assertEqual(record['source'], 'appflowy_backup:0.20.0' if use_baseline else backup)
