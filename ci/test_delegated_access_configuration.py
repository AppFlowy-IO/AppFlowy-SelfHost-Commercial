"""Render Compose and Swarm delegated-access settings without starting services
(Helm: helm/appflowy-cloud/tests)."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from images import ROOT, clean_environment

COMPOSE_FILES = ('docker-compose.yml', 'docker-swarm/docker-stack.yml')
GOTRUE_PREFIX = 'GOTRUE_TOKEN_EXCHANGE_'
CLOUD_SETTINGS = ('APPFLOWY_TOKEN_EXCHANGE_ISSUER', 'APPFLOWY_TOKEN_EXCHANGE_AUDIENCE')
# Placeholders with the shape of real values. The key is not a usable private key.
CLIENTS = ('{"11111111-1111-4111-8111-111111111111":{"entra_client_id":'
           '"22222222-2222-4222-8222-222222222222","audience":'
           '"33333333-3333-4333-8333-333333333333","scopes":["data.read","data.write"]}}')
SIGNING_KEYS = ('[{"kty":"EC","crv":"P-256","alg":"ES256","kid":"contract","key_ops":["sign"],'
                '"x":"contract-x","y":"contract-y","d":"contract-d"}]')


class DelegatedAccessConfigurationTests(unittest.TestCase):
    def services(self, file, **values):
        """The rendered services from deploy.env, with `values` set in the shell."""
        result = subprocess.run(
            ['docker', 'compose', '--env-file', str(ROOT / 'deploy.env'), '-p', 'appflowy-delegated-access',
             '-f', str(ROOT / file), 'config', '--format', 'json'],
            capture_output=True, text=True, env={**clean_environment(), **values}, timeout=60, cwd=ROOT)
        # Rendered manifests can contain credentials. Keep both streams private on failure.
        self.assertEqual(result.returncode, 0, 'docker compose rendering failed')
        return json.loads(result.stdout)['services']

    def test_a_new_installation_has_delegated_access_off(self):
        active = [line for line in (ROOT / 'deploy.env').read_text().splitlines()
                  if line.startswith((GOTRUE_PREFIX,) + CLOUD_SETTINGS)]
        self.assertEqual(active, [], 'deploy.env documents the settings without setting them')
        for file in COMPOSE_FILES:
            with self.subTest(file=file):
                services = self.services(file)
                gotrue = {name: value for name, value in services['gotrue']['environment'].items()
                          if name.startswith(GOTRUE_PREFIX)}
                # GoTrue reads the remaining settings only once the first is true, and rejects a
                # numeric limit that is present but empty.
                self.assertEqual(gotrue, {
                    GOTRUE_PREFIX + 'ENABLED': 'false', GOTRUE_PREFIX + 'TENANT_ID': '',
                    GOTRUE_PREFIX + 'PROVIDER': '', GOTRUE_PREFIX + 'CLIENTS': '',
                    GOTRUE_PREFIX + 'SIGNING_KEYS': '', GOTRUE_PREFIX + 'RATE_LIMIT': '150',
                    GOTRUE_PREFIX + 'MAX_CONCURRENT': '8'})
                cloud = services['appflowy_cloud']['environment']
                # Cloud treats two empty settings as off and refuses to start with only one.
                self.assertEqual([cloud[name] for name in CLOUD_SETTINGS], ['', ''])

    def test_operator_settings_reach_gotrue_and_cloud_unchanged(self):
        configured = {
            GOTRUE_PREFIX + 'ENABLED': 'true',
            GOTRUE_PREFIX + 'TENANT_ID': '44444444-4444-4444-8444-444444444444',
            GOTRUE_PREFIX + 'PROVIDER': 'custom:entra',
            GOTRUE_PREFIX + 'CLIENTS': CLIENTS,
            GOTRUE_PREFIX + 'SIGNING_KEYS': SIGNING_KEYS,
            GOTRUE_PREFIX + 'RATE_LIMIT': '600',
            GOTRUE_PREFIX + 'MAX_CONCURRENT': '16',
            'APPFLOWY_TOKEN_EXCHANGE_ISSUER': 'https://appflowy.example.test/gotrue',
            'APPFLOWY_TOKEN_EXCHANGE_AUDIENCE': '33333333-3333-4333-8333-333333333333',
        }
        for file in COMPOSE_FILES:
            with self.subTest(file=file):
                services = self.services(file, **configured)
                gotrue = services['gotrue']['environment']
                cloud = services['appflowy_cloud']['environment']
                for name, value in configured.items():
                    target = gotrue if name.startswith(GOTRUE_PREFIX) else cloud
                    # JSON survives interpolation byte for byte; GoTrue parses these two itself.
                    self.assertEqual(target[name], value, name)
                self.assertEqual(json.loads(gotrue[GOTRUE_PREFIX + 'CLIENTS']), json.loads(CLIENTS))

    def test_the_documented_env_file_lines_keep_their_json_and_follow_the_public_url(self):
        # docs/DELEGATED_ACCESS.md has operators single-quote JSON in .env and reuse API_EXTERNAL_URL.
        with tempfile.TemporaryDirectory(prefix='delegated-access-env-') as directory:
            env_file = Path(directory) / '.env'
            env_file.write_text((ROOT / 'deploy.env').read_text() + '\n'.join((
                GOTRUE_PREFIX + 'ENABLED=true',
                GOTRUE_PREFIX + "CLIENTS='" + CLIENTS + "'",
                GOTRUE_PREFIX + "SIGNING_KEYS='" + SIGNING_KEYS + "'",
                'APPFLOWY_TOKEN_EXCHANGE_ISSUER=${API_EXTERNAL_URL}',
                'APPFLOWY_TOKEN_EXCHANGE_AUDIENCE=33333333-3333-4333-8333-333333333333', '')))
            env_file.chmod(0o600)
            result = subprocess.run(
                ['docker', 'compose', '--env-file', str(env_file), '-p', 'appflowy-delegated-access',
                 '-f', str(ROOT / 'docker-compose.yml'), 'config', '--format', 'json'],
                capture_output=True, text=True, env=clean_environment(), timeout=60, cwd=ROOT)
        self.assertEqual(result.returncode, 0, 'docker compose rendering failed')
        services = json.loads(result.stdout)['services']
        gotrue = services['gotrue']['environment']
        self.assertEqual(gotrue[GOTRUE_PREFIX + 'CLIENTS'], CLIENTS)
        self.assertEqual(gotrue[GOTRUE_PREFIX + 'SIGNING_KEYS'], SIGNING_KEYS)
        # Cloud compares the token's issuer with GoTrue's public URL exactly.
        self.assertEqual(services['appflowy_cloud']['environment']['APPFLOWY_TOKEN_EXCHANGE_ISSUER'],
                         gotrue['API_EXTERNAL_URL'])

    def test_only_gotrue_holds_the_signing_key_and_only_cloud_accepts_the_tokens(self):
        configured = {GOTRUE_PREFIX + 'ENABLED': 'true', GOTRUE_PREFIX + 'SIGNING_KEYS': SIGNING_KEYS,
                      'APPFLOWY_TOKEN_EXCHANGE_ISSUER': 'https://appflowy.example.test/gotrue',
                      'APPFLOWY_TOKEN_EXCHANGE_AUDIENCE': '33333333-3333-4333-8333-333333333333'}
        for file in COMPOSE_FILES:
            with self.subTest(file=file):
                for name, service in self.services(file, **configured).items():
                    environment = service.get('environment') or {}
                    exchange = {key for key in environment if key.startswith(GOTRUE_PREFIX)}
                    accepted = {key for key in environment if key in CLOUD_SETTINGS}
                    self.assertEqual(bool(exchange), name == 'gotrue', name)
                    # Other services keep rejecting these tokens: only the row API opted in.
                    self.assertEqual(bool(accepted), name == 'appflowy_cloud', name)
                    if name != 'gotrue':
                        self.assertNotIn('contract-d', json.dumps(environment), name)


if __name__ == '__main__':
    unittest.main()
