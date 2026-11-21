"""Render the server and worker configuration a self-hosted operator actually installs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from images import ROOT, clean_environment


FLAG = 'APPFLOWY_DATABASE_AUTOMATIONS_ENABLED'
BUDGET = 'APPFLOWY_WORKER_DATABASE_MAX_CONNECTIONS'
KEY = 'APPFLOWY_INTEGRATIONS_SECRET_KEY'
JWT = 'APPFLOWY_GOTRUE_JWT_SECRET'


class AutomationConfigurationTests(unittest.TestCase):
    def render(self, command, variables=None):
        result = subprocess.run(command, cwd=ROOT, env={**clean_environment(), **(variables or {})},
                                capture_output=True, text=True, timeout=60)
        # The output of either renderer may include credentials.
        self.assertEqual(result.returncode, 0, 'Deployment configuration did not render')
        return result.stdout

    def test_compose_and_swarm_forward_both_key_modes_and_the_worker_budget(self):
        defaults = (ROOT / 'deploy.env').read_text().splitlines()
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / 'install.env'
            # Existing installations can upgrade without copying the new entries into .env.
            env_file.write_text('\n'.join(line for line in defaults
                                          if not line.startswith((FLAG + '=', BUDGET + '=', KEY + '='))) + '\n')
            for manifest in ('docker-compose.yml', 'docker-swarm/docker-stack.yml'):
                command = ['docker', 'compose', '--env-file', str(env_file), '-f', manifest,
                           '-p', 'automation-config-test', 'config']
                for overrides, enabled, budget in (({}, 'false', '16'),
                                                   ({FLAG: 'true'}, 'true', '16'),
                                                   ({FLAG: 'true', BUDGET: '24',
                                                     KEY: 'A' * 43 + '='}, 'true', '24')):
                    with self.subTest(manifest=manifest, enabled=enabled, budget=budget):
                        values = {'GOTRUE_JWT_SECRET': 'local-automation-fixture', **overrides}
                        self.render([*command, '--quiet'], values)
                        services = json.loads(self.render([*command, '--format', 'json'], values))['services']
                        cloud = services['appflowy_cloud']['environment']
                        worker = services['appflowy_worker']['environment']
                        self.assertEqual((cloud[FLAG], worker[FLAG]), (enabled, enabled))
                        self.assertEqual(worker[BUDGET], budget)
                        self.assertNotIn(BUDGET, cloud)
                        for service in (cloud, worker):
                            self.assertEqual(service[KEY], overrides.get(KEY, ''))
                            self.assertEqual(service[JWT], values['GOTRUE_JWT_SECRET'])

    @staticmethod
    def helm_service_env(documents, component):
        document, = (d for d in documents
                     if d['metadata']['labels'].get('app.kubernetes.io/component') == component)
        container, = document['spec']['template']['spec']['containers']
        return {entry['name']: entry for entry in container['env']}

    def test_helm_uses_the_shared_key_reference_only_where_needed(self):
        for enabled, secret, budget in ((None, '', 16), (True, '', 16),
                                        (False, 'integration-key', 24), (True, 'integration-key', 24)):
            with self.subTest(enabled=enabled, dedicated=bool(secret), budget=budget):
                cmd = ['helm', 'template', 'automation-config-test', 'helm/appflowy-cloud',
                       '-f', 'ci/helm-values.yaml']
                if enabled is not None:
                    cmd.extend(['--set', 'global.databaseAutomationsEnabled=' + str(enabled).lower(),
                                '--set-string', 'global.integrationsSecret=' + secret,
                                '--set', f'appflowy-worker.config.databaseMaxConnections={budget}'])
                docs = [d for d in yaml.safe_load_all(self.render(cmd)) if d and d['kind'] == 'Deployment']
                cloud = self.helm_service_env(docs, 'appflowy-cloud')
                worker = self.helm_service_env(docs, 'appflowy-worker')
                self.assertEqual((cloud[FLAG]['value'], worker[FLAG]['value']), (str(bool(enabled)).lower(),) * 2)
                self.assertEqual(worker[BUDGET]['value'], str(budget))
                self.assertNotIn(BUDGET, cloud)
                if secret:
                    self.assertEqual(cloud[KEY]['valueFrom']['secretKeyRef'],
                                     {'name': secret, 'key': 'integrations-secret-key'})
                if enabled:
                    selected = KEY if secret else JWT
                    self.assertEqual(worker[selected]['valueFrom'], cloud[selected]['valueFrom'])
                    self.assertNotIn(JWT if secret else KEY, worker)
                else:
                    self.assertNotIn(KEY, worker)
                    self.assertNotIn(JWT, worker)


    def test_helm_rejects_an_invalid_automation_flag(self):
        result = subprocess.run(
            ['helm', 'template', 'automation-config-test', 'helm/appflowy-cloud',
             '-f', 'ci/helm-values.yaml', '--set-string', 'global.databaseAutomationsEnabled=invalid'],
            cwd=ROOT, env=clean_environment(), capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('global.databaseAutomationsEnabled must be true or false', result.stderr)


if __name__ == '__main__':
    unittest.main()
