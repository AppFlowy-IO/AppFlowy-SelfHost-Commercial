"""The bundled MinIO must not ask dl.min.io for a newer release when Compose or Swarm starts it."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_FILES = ('docker-compose.yml', 'docker-swarm/docker-stack.yml')


def minio_environment(path):
    entries = yaml.safe_load((ROOT / path).read_text())['services']['minio'].get('environment', [])
    if isinstance(entries, dict):
        return {key: str(value) for key, value in entries.items()}
    return dict(entry.split('=', 1) for entry in entries)


class MinioConfigurationTests(unittest.TestCase):
    def test_update_check_is_off(self):
        for path in DEPLOYMENT_FILES:
            with self.subTest(path=path):
                self.assertEqual(minio_environment(path).get('MINIO_UPDATE'), 'off')


if __name__ == '__main__':
    unittest.main()
