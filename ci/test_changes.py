"""CI may skip runtime acceptance only for docs or consistent Web image pins."""
import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

import changes

ROOT = Path(__file__).resolve().parent.parent
NEW_PIN = 'appflowyinc/appflowy_web:99.0.0@sha256:' + 'a' * 64


class ChangeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.before = {path: yaml.safe_load((ROOT / path).read_text()) for path in changes.WEB_FILES}
        self.after = copy.deepcopy(self.before)
        for path, document in self.after.items():
            if path.endswith('values.yaml'):
                document['appflowy-web']['image'].update(tag='99.0.0', digest='sha256:' + 'a' * 64)
            else:
                document['services']['appflowy_web']['image'] = NEW_PIN

    def classify(self, paths=None):
        return changes.classify(list(changes.WEB_FILES) if paths is None else paths,
                                lambda path: yaml.safe_dump(self.before[path]),
                                lambda path: yaml.safe_dump(self.after[path]))

    def test_consistent_web_image_update_skips_integration_even_with_release_notes(self):
        self.assertEqual(self.classify(), 'web-images')
        self.assertEqual(self.classify([*changes.WEB_FILES, 'docs/release.md']), 'web-images')

    def test_mixed_cloud_backup_or_configuration_changes_still_need_integration(self):
        for service in ('appflowy_cloud', 'appflowy_worker', 'appflowy_backup'):
            with self.subTest(service=service):
                original = self.after['docker-compose.yml']['services'][service]['image']
                self.after['docker-compose.yml']['services'][service]['image'] = 'another:release'
                self.assertEqual(self.classify(), 'integration')
                self.after['docker-compose.yml']['services'][service]['image'] = original
        self.after['docker-compose.yml']['services']['appflowy_web']['restart'] = 'always'
        self.assertEqual(self.classify(), 'integration')
        self.assertEqual(self.classify([*changes.WEB_FILES, 'ci/backup_smoke.py']), 'integration')
        self.assertEqual(self.classify([*changes.WEB_FILES, '.github/workflows/backup-test.yml']), 'integration')

    def test_missing_target_or_unpinned_web_image_cannot_skip_acceptance(self):
        self.after['docker-swarm/docker-stack.yml'] = copy.deepcopy(self.before['docker-swarm/docker-stack.yml'])
        self.assertEqual(self.classify(['docker-compose.yml', 'helm/appflowy-cloud/values.yaml']), 'integration')
        self.after = copy.deepcopy(self.before)
        self.after['docker-compose.yml']['services']['appflowy_web']['image'] = 'appflowyinc/appflowy_web:latest'
        self.assertEqual(self.classify(['docker-compose.yml']), 'integration')

    def test_docs_are_skipped_but_empty_or_mixed_diffs_are_not(self):
        self.assertEqual(self.classify(['README.md', 'docs/nested/image.png']), 'docs')
        self.assertEqual(self.classify([]), 'integration')
        self.assertEqual(self.classify(['docs/README.md', 'deploy.env']), 'integration')
        self.assertEqual(self.classify(['docker-swarm/README.md']), 'integration')

    def test_manual_runs_and_new_branches_always_qualify_the_full_stack(self):
        self.assertIsNone(changes.event_range('workflow_dispatch', {}))
        self.assertIsNone(changes.event_range('push', {'before': '0' * 40, 'after': 'a' * 40}))

    def test_push_uses_before_and_after_but_pull_requests_use_the_merge_base(self):
        base, head, ancestor = 'a' * 40, 'b' * 40, 'c' * 40
        self.assertEqual(changes.event_range('push', {'before': base, 'after': head}), (base, head))
        with patch.object(changes, 'git', return_value=ancestor + '\n') as git:
            self.assertEqual(changes.event_range('pull_request', {
                'pull_request': {'base': {'sha': base}, 'head': {'sha': head}}}), (ancestor, head))
        git.assert_called_once_with('merge-base', base, head)

    def test_detection_runs_against_git_snapshots_and_writes_workflow_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', directory, *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('config', 'user.name', 'CI fixture')
            git('config', 'user.email', 'ci@example.invalid')
            for path in changes.WEB_FILES:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(yaml.safe_dump(self.before[path]))
            git('add', '.')
            git('commit', '-qm', 'initial images')
            base = git('rev-parse', 'HEAD')
            for path in changes.WEB_FILES:
                (root / path).write_text(yaml.safe_dump(self.after[path]))
            git('commit', '-qam', 'Web release')
            head = git('rev-parse', 'HEAD')
            output = root / 'output'
            result = subprocess.run(['python3', str(ROOT / 'ci/changes.py'), '--base', base, '--head', head],
                                    cwd=root, env={**os.environ, 'GITHUB_OUTPUT': str(output)},
                                    check=True, capture_output=True, text=True)
            self.assertIn('"kind": "web-images"', result.stdout)
            self.assertEqual(output.read_text(), 'kind=web-images\nrun_checks=true\nrun_integration=false\n')


class RequiredGateTests(unittest.TestCase):
    def run_gate(self, filename, **env):
        workflow = yaml.safe_load((ROOT / '.github/workflows' / filename).read_text())
        job = workflow['jobs']['deployment-tests' if filename == 'deployment-test.yml' else 'backup-tests']
        return subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', job['steps'][0]['run']],
                              env={**os.environ, **env}, capture_output=True).returncode

    def test_required_gates_accept_intentional_skips_and_reject_failed_detection_or_acceptance(self):
        for filename in ('deployment-test.yml', 'backup-test.yml'):
            env = dict(CHANGES_RESULT='success', RUN_CHECKS='true', RUN_INTEGRATION='false',
                       IMAGES_RESULT='success', RUNTIME_RESULT='skipped', BACKUP_RESULT='skipped')
            with self.subTest(filename=filename):
                self.assertEqual(self.run_gate(filename, **env), 0)
                self.assertNotEqual(self.run_gate(filename, **{**env, 'CHANGES_RESULT': 'failure'}), 0)
                if filename == 'deployment-test.yml':
                    for result in ('failure', 'cancelled', 'skipped'):
                        self.assertNotEqual(self.run_gate(filename, **{**env, 'IMAGES_RESULT': result}), 0)
                self.assertNotEqual(self.run_gate(filename, **{**env, 'RUN_INTEGRATION': ''}), 0)
                self.assertNotEqual(self.run_gate(filename, **{**env, 'RUN_INTEGRATION': 'true'}), 0)
                passing = {**env, 'RUN_INTEGRATION': 'true', 'RUNTIME_RESULT': 'success', 'BACKUP_RESULT': 'success'}
                self.assertEqual(self.run_gate(filename, **passing), 0)
                for result in ('failure', 'cancelled', 'skipped'):
                    self.assertNotEqual(self.run_gate(filename, **{
                        **passing, 'RUNTIME_RESULT': result, 'BACKUP_RESULT': result}), 0)
                self.assertEqual(self.run_gate(filename, **{
                    **env, 'RUN_CHECKS': 'false', 'IMAGES_RESULT': 'skipped'}), 0)


if __name__ == '__main__':
    unittest.main()
