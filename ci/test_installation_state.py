"""Deployment recipes retain one private installation identity across Cloud replacement."""
import json
from pathlib import Path
import subprocess
import unittest

import yaml

from images import clean_environment

ROOT = Path(__file__).resolve().parents[1]
STATE_DIRECTORY = '/var/lib/appflowy/license'
STATE_ENVIRONMENT = {
    'APPFLOWY_INSTALLATION_IDENTITY_PATH': STATE_DIRECTORY + '/installation.json',
    'APPFLOWY_LICENSE_REPORT_STATE_PATH': STATE_DIRECTORY + '/report.json',
}


class InstallationStateConfigurationTests(unittest.TestCase):
    def test_compose_and_generated_swarm_mount_state_only_into_cloud(self):
        for filename in ('docker-compose.yml', 'docker-swarm/docker-stack.yml'):
            with self.subTest(filename=filename):
                command = ['docker', 'compose', '--env-file', str(ROOT / 'deploy.env'),
                           '-p', 'installation-state-test', '-f', str(ROOT / filename), 'config']
                result = subprocess.run(command + ['--quiet'], cwd=ROOT, env=clean_environment(),
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, 'Secret-safe Compose validation failed')
                result = subprocess.run(command + ['--format', 'json'], cwd=ROOT,
                                        env=clean_environment(), capture_output=True, text=True,
                                        timeout=30)
                self.assertEqual(result.returncode, 0, 'Private manifest rendering failed')
                config = json.loads(result.stdout)
                cloud = config['services']['appflowy_cloud']
                for key, expected in STATE_ENVIRONMENT.items():
                    self.assertEqual(cloud['environment'][key], expected)
                mount = next(mount for mount in cloud['volumes']
                             if mount['target'] == STATE_DIRECTORY)
                self.assertEqual(mount['type'], 'volume')
                self.assertEqual(mount['source'], 'appflowy_cloud_state')
                self.assertFalse(mount.get('read_only', False))
                self.assertIn('appflowy_cloud_state', config['volumes'])
                for name, service in config['services'].items():
                    if name == 'appflowy_cloud':
                        continue
                    self.assertFalse(any(item.get('source') == 'appflowy_cloud_state'
                                         for item in service.get('volumes', [])), name)

    def test_swarm_cloud_keeps_its_local_installation_volume_on_the_data_node(self):
        stack = yaml.safe_load((ROOT / 'docker-swarm/docker-stack.yml').read_text())
        cloud = stack['services']['appflowy_cloud']
        self.assertEqual(cloud['deploy']['placement']['constraints'],
                         ['node.labels.appflowy.data == true'])
        self.assertEqual(cloud['deploy']['update_config']['order'], 'stop-first')


if __name__ == '__main__':
    unittest.main()
