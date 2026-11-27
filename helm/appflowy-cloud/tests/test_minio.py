"""Render the real chart to verify that the bundled MinIO never asks dl.min.io for a newer release."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]


class MinioChartTests(unittest.TestCase):
    def test_update_check_is_off(self):
        result = subprocess.run(
            ['helm', 'template', 'minio-test', str(CHART), '-f', str(ROOT / 'ci/helm-values.yaml')],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        containers = [container
                      for item in yaml.safe_load_all(result.stdout)
                      if item and item['kind'] == 'Deployment'
                      for container in item['spec']['template']['spec']['containers']
                      if container['name'] == 'minio']
        self.assertEqual(len(containers), 1)
        environment = {entry['name']: entry.get('value') for entry in containers[0].get('env', [])}
        self.assertEqual(environment.get('MINIO_UPDATE'), 'off')


if __name__ == '__main__':
    unittest.main()
