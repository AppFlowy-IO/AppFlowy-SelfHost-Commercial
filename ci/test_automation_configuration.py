"""Render the server and worker configuration a self-hosted operator actually installs."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

from configuration import ROOT, isolated_source
from images import clean_environment


FLAG = 'APPFLOWY_DATABASE_AUTOMATIONS_ENABLED'
BUDGET = 'APPFLOWY_WORKER_DATABASE_MAX_CONNECTIONS'
KEY = 'APPFLOWY_INTEGRATIONS_SECRET_KEY'
JWT = 'APPFLOWY_GOTRUE_JWT_SECRET'
CHART = Path('helm/appflowy-cloud')


class AutomationConfigurationTests(unittest.TestCase):
    def render(self, command, cwd, *, environment=None, expected_error=None):
        result = subprocess.run(command, cwd=cwd, env=environment if environment is not None else clean_environment(),
                                capture_output=True, text=True, timeout=60)
        # Both streams can contain credentials. Report only the expected condition.
        if expected_error:
            self.assertNotEqual(result.returncode, 0, 'Invalid configuration rendered')
            self.assertTrue(expected_error in result.stderr, 'Missing expected configuration error')
        else:
            self.assertEqual(result.returncode, 0, 'Deployment configuration did not render')
        return result.stdout

    def assert_setting(self, environment, name, expected):
        if expected is None:
            self.assertFalse(name in environment, f'Unexpected {name}')
        else:
            self.assertTrue(environment.get(name) == expected, f'Missing or incorrect {name}')

    def test_setting_failures_hide_credentials(self):
        environment = {KEY: 'actual-fixture-value', JWT: 'unrelated-fixture-value'}
        for expected in (None, 'expected-fixture-value'):
            with self.assertRaises(AssertionError) as failure:
                self.assert_setting(environment, KEY, expected)
            message = str(failure.exception)
            self.assertTrue(KEY in message, 'Missing setting name in failure')
            self.assertFalse('fixture-value' in message, 'Credential value in assertion failure')

    def test_compose_and_swarm_scope_worker_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            # Model a live checkout using a synthetic selection at the actual restore path.
            checkout = isolated_source(Path(directory) / 'checkout')
            restore = checkout / 'backup-ops/runtime'
            restore.mkdir(parents=True)
            marker = 'TEST_OPERATOR_RESTORE_SETTING'
            (restore / 'selection-appflowy_cloud.env').write_text(f'{marker}=fixture\n')
            compose = ['docker', 'compose', '-p', 'automation-test']
            control = self.render([*compose, '--env-file', 'deploy.env', 'config', '--format', 'json'], checkout)
            self.assert_setting(json.loads(control)['services']['appflowy_cloud']['environment'], marker, 'fixture')
            source = isolated_source(Path(directory) / 'render', checkout)
            current = [line for line in (source / 'deploy.env').read_text().splitlines()
                       if not line.startswith('GOTRUE_JWT_SECRET=')]
            # An older installation may predate all three settings.
            legacy = [line for line in current if not line.startswith((FLAG + '=', KEY + '=', BUDGET + '='))]
            jwt = 'fixture-jwt-for-config-render'
            key = 'A' * 43 + '='
            cases = [
                ('shipped defaults', current, {}, 'false', '16'),
                ('legacy defaults', legacy, {}, 'false', '16'),
                ('existing Cloud key', legacy, {KEY: key}, 'false', '16'),
                ('explicitly disabled', legacy, {FLAG: 'false', KEY: key}, 'false', '16'),
                ('enabled without key', legacy, {FLAG: 'true'}, 'true', '16'),
                ('enabled with key', legacy, {FLAG: 'true', KEY: key, BUDGET: '24'}, 'true', '24'),
            ]
            for case, defaults, settings, enabled, budget in cases:
                lines = [*defaults, 'GOTRUE_JWT_SECRET=' + jwt]
                lines.extend(f'{name}={value}' for name, value in settings.items())
                (source / '.env').write_text('\n'.join(lines) + '\n')
                for renderer in ('compose', 'swarm'):
                    with self.subTest(renderer=renderer, configuration=case):
                        if renderer == 'compose':
                            rendered = self.render([*compose, 'config', '--format', 'json'], source)
                            services = json.loads(rendered)['services']
                        else:
                            # Native Swarm expects the expanded installation variables in its environment.
                            expanded = self.render([*compose, 'config', '--environment'], source)
                            variables = dict(line.split('=', 1) for line in expanded.splitlines())
                            command = ['docker', 'stack', 'config', '-c', 'docker-swarm/docker-stack.yml']
                            services = yaml.safe_load(self.render(command, source, environment=variables))['services']
                        cloud = services['appflowy_cloud']['environment']
                        worker = services['appflowy_worker']['environment']
                        self.assert_setting(cloud, marker, None)
                        self.assert_setting(cloud, FLAG, enabled)
                        self.assert_setting(worker, FLAG, enabled)
                        self.assert_setting(worker, BUDGET, budget)
                        self.assert_setting(cloud, BUDGET, None)
                        self.assert_setting(cloud, JWT, jwt)
                        self.assert_setting(cloud, KEY, settings.get(KEY, ''))
                        self.assert_setting(worker, JWT, None)
                        self.assert_setting(worker, KEY, settings.get(KEY) if enabled == 'true' else None)
                        self.assertFalse(jwt in worker.values(), 'Worker received the signing credential')
                        if enabled == 'false':
                            self.assertFalse(key in worker.values(), 'Disabled Worker received the integration key')

    def helm_environments(self, *options, root=ROOT):
        command = ['helm', 'template', 'automation-test', str(CHART), '-f', 'ci/helm-values.yaml']
        for component in ('appflowy-cloud', 'appflowy-worker'):
            command.extend(['--show-only', f'templates/{component}/deployment.yaml'])
        environments = {}
        for deployment in yaml.safe_load_all(self.render(command + list(options), root)):
            component = deployment['metadata']['labels']['app.kubernetes.io/component']
            container, = deployment['spec']['template']['spec']['containers']
            environments[component] = {entry['name']: entry.get('value', entry.get('valueFrom'))
                                       for entry in container['env']}
        return environments['appflowy-cloud'], environments['appflowy-worker']

    def test_helm_uses_the_shared_key_reference_only_where_needed(self):
        for enabled, secret, budget in ((None, '', 16), (True, '', 16),
                                        (False, 'integration-key', 24), (True, 'integration-key', 24)):
            with self.subTest(enabled=enabled, dedicated=bool(secret), budget=budget):
                options = []
                if enabled is not None:
                    options = ['--set', 'global.databaseAutomationsEnabled=' + str(enabled).lower(),
                               '--set-string', 'global.integrationsSecret=' + secret,
                               '--set', f'appflowy-worker.config.databaseMaxConnections={budget}']
                cloud, worker = self.helm_environments(*options)
                self.assert_setting(cloud, FLAG, str(bool(enabled)).lower())
                self.assert_setting(worker, FLAG, str(bool(enabled)).lower())
                self.assert_setting(worker, BUDGET, str(budget))
                self.assert_setting(cloud, BUDGET, None)
                reference = {'secretKeyRef': {'name': secret, 'key': 'integrations-secret-key'}}
                jwt_reference = {'secretKeyRef': {'name': 'appflowy-ci-jwt-secret', 'key': 'jwt-secret'}}
                self.assert_setting(cloud, JWT, jwt_reference)
                self.assert_setting(cloud, KEY, reference if secret else None)
                self.assert_setting(worker, KEY, reference if enabled and secret else None)
                self.assert_setting(worker, JWT, jwt_reference if enabled and not secret else None)

    def test_helm_upgrade_reuses_pre_automation_values(self):
        with tempfile.TemporaryDirectory() as directory:
            source = isolated_source(Path(directory))
            chart = source / CHART
            shutil.copytree(ROOT / CHART / 'charts', chart / 'charts')
            # --reuse-values uses the previous chart's computed values as the new
            # defaults. Passing them with -f alone would merge the new defaults back in.
            values_file = chart / 'values.yaml'
            values = yaml.safe_load(values_file.read_text())
            del values['global']['databaseAutomationsEnabled'], values['global']['integrationsSecret']
            del values['appflowy-worker']['config']['databaseMaxConnections']
            values['appflowy-worker']['config']['rustLog'] = 'debug'
            values_file.write_text(yaml.safe_dump(values))
            for options, flag in (([], 'false'), (['--set', 'global.databaseAutomationsEnabled=true'], 'true')):
                with self.subTest(flag=flag):
                    cloud, worker = self.helm_environments('--is-upgrade', *options, root=source)
                    self.assert_setting(cloud, FLAG, flag)
                    self.assert_setting(worker, FLAG, flag)
                    self.assert_setting(worker, BUDGET, '16')
                    self.assert_setting(worker, 'RUST_LOG', 'debug')
                    if flag == 'false':
                        self.assert_setting(worker, KEY, None)
                        self.assert_setting(worker, JWT, None)

    def test_helm_rejects_an_invalid_automation_flag(self):
        for invalid in ('invalid', ''):
            with self.subTest(flag=invalid):
                self.render(['helm', 'template', 'automation-test', str(CHART), '-f', 'ci/helm-values.yaml',
                             '--set-string', 'global.databaseAutomationsEnabled=' + invalid], ROOT,
                            expected_error='global.databaseAutomationsEnabled must be true or false')


if __name__ == '__main__':
    unittest.main()
