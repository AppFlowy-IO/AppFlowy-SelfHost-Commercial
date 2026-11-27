"""Render the real chart to verify how delegated row access reaches GoTrue and AppFlowy Cloud."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]
AUDIENCE = '33333333-3333-4333-8333-333333333333'
CLIENTS = {'11111111-1111-4111-8111-111111111111': {
    'entra_client_id': '22222222-2222-4222-8222-222222222222', 'audience': AUDIENCE,
    'scopes': ['data.read', 'data.write']}}
# A placeholder with the shape of the real value. It is not a usable private key.
SIGNING_KEYS = json.dumps([{'kty': 'EC', 'crv': 'P-256', 'alg': 'ES256', 'kid': 'contract',
                            'key_ops': ['sign'], 'x': 'contract-x', 'y': 'contract-y', 'd': 'contract-d'}])


class DelegatedAccessChartTests(unittest.TestCase):
    def render(self, values=None, success=True):
        command = ['helm', 'template', 'delegated-access-test', str(CHART), '-f', str(ROOT / 'ci/helm-values.yaml')]
        with tempfile.TemporaryDirectory(prefix='delegated-access-values-') as directory:
            if values is not None:
                overlay = Path(directory) / 'values.yaml'
                overlay.write_text(yaml.safe_dump(values))
                command += ['-f', str(overlay)]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        # A rendered chart contains secrets. Keep both streams out of a failure message.
        self.assertEqual(result.returncode, 0, 'helm template failed')
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def container(self, documents, suffix):
        deployment = next(item for item in documents if item['kind'] == 'Deployment'
                          and item['metadata']['name'] == 'appflowy-ci-' + suffix)
        return deployment['spec']['template']['spec']['containers'][0]

    def environment(self, documents, suffix):
        return {entry['name']: entry for entry in self.container(documents, suffix)['env']}

    def exchange_names(self, documents, suffix):
        return sorted(name for name in self.environment(documents, suffix) if 'TOKEN_EXCHANGE' in name)

    def test_the_default_chart_leaves_delegated_access_off(self):
        documents = self.render()
        self.assertEqual(self.exchange_names(documents, 'gotrue'), [])
        self.assertEqual(self.exchange_names(documents, 'cloud'), [])
        secret = next(item for item in documents if item['kind'] == 'Secret'
                      and item['metadata']['name'] == 'appflowy-ci-gotrue-secret')
        self.assertNotIn('token-exchange-signing-keys', secret['data'])

    def test_settings_alone_turn_it_on_and_a_partial_set_is_refused(self):
        # GoTrue has no switch for exchange, so the chart has none either. Any setting turns it
        # on, and one given without the tenant and provider must not render as silently off.
        exchange = lambda **values: {'gotrue': {'config': {'tokenExchange': values}}}
        for partial, missing in (
            ({'tenantId': '44444444-4444-4444-8444-444444444444'}, 'tokenExchange.provider'),
            ({'provider': 'custom:entra'}, 'tokenExchange.tenantId'),
            ({'signingKeys': SIGNING_KEYS}, 'tokenExchange.tenantId'),
            ({'clients': CLIENTS}, 'tokenExchange.tenantId'),
        ):
            with self.subTest(partial=sorted(partial)):
                self.assertIn(missing, self.render(exchange(**partial), success=False))
        documents = self.render(exchange(tenantId='44444444-4444-4444-8444-444444444444',
                                         provider='custom:entra'))
        # Enough to start GoTrue with no backends yet; an upgrade keeps the stored key.
        self.assertEqual(self.exchange_names(documents, 'gotrue'), [
            'GOTRUE_TOKEN_EXCHANGE_' + name for name in
            ('CLIENTS', 'MAX_CONCURRENT', 'PROVIDER', 'RATE_LIMIT', 'SIGNING_KEYS', 'TENANT_ID')])
        self.assertEqual(self.environment(documents, 'gotrue')['GOTRUE_TOKEN_EXCHANGE_CLIENTS']['value'], '{}')

    def test_configured_values_reach_gotrue_and_keep_the_key_in_its_secret(self):
        documents = self.render({'gotrue': {'config': {'tokenExchange': {
            'tenantId': '44444444-4444-4444-8444-444444444444',
            'provider': 'custom:entra', 'clients': CLIENTS, 'signingKeys': SIGNING_KEYS,
            'rateLimit': 600, 'maxConcurrent': 16}}}})
        gotrue = self.environment(documents, 'gotrue')
        value = lambda name: gotrue['GOTRUE_TOKEN_EXCHANGE_' + name].get('value')
        self.assertNotIn('GOTRUE_TOKEN_EXCHANGE_ENABLED', gotrue)
        self.assertEqual(value('TENANT_ID'), '44444444-4444-4444-8444-444444444444')
        self.assertEqual(value('PROVIDER'), 'custom:entra')
        self.assertEqual(json.loads(value('CLIENTS')), CLIENTS)
        # GoTrue parses the limits as integers, so 600 must not arrive as 6e+02.
        self.assertEqual((value('RATE_LIMIT'), value('MAX_CONCURRENT')), ('600', '16'))
        keys = gotrue['GOTRUE_TOKEN_EXCHANGE_SIGNING_KEYS']
        self.assertNotIn('value', keys, 'the private key is never written into the Deployment')
        self.assertEqual(keys['valueFrom']['secretKeyRef'],
                         {'name': 'appflowy-ci-gotrue-secret', 'key': 'token-exchange-signing-keys'})
        secret = next(item for item in documents if item['kind'] == 'Secret'
                      and item['metadata']['name'] == 'appflowy-ci-gotrue-secret')
        stored = base64.b64decode(secret['data']['token-exchange-signing-keys']).decode()
        self.assertEqual(json.loads(stored), json.loads(SIGNING_KEYS))
        for suffix in ('cloud', 'worker', 'mcp', 'search'):
            self.assertNotIn('contract-d', json.dumps(self.container(documents, suffix)), suffix)
        # GoTrue issuing tokens does not by itself make Cloud accept them.
        self.assertEqual(self.exchange_names(documents, 'cloud'), [])

    def test_cloud_accepts_the_audience_from_the_issuer_gotrue_uses(self):
        documents = self.render({'appflowy-cloud': {'config': {'tokenExchangeAudience': AUDIENCE}}})
        cloud = self.environment(documents, 'cloud')
        self.assertEqual(cloud['APPFLOWY_TOKEN_EXCHANGE_AUDIENCE']['value'], AUDIENCE)
        # Cloud compares the token's issuer with this value exactly, so both come from one helper.
        self.assertEqual(cloud['APPFLOWY_TOKEN_EXCHANGE_ISSUER']['value'],
                         self.environment(documents, 'gotrue')['API_EXTERNAL_URL']['value'])
        for suffix in ('worker', 'mcp', 'search'):
            self.assertEqual(self.exchange_names(documents, suffix), [], suffix)


if __name__ == '__main__':
    unittest.main()
