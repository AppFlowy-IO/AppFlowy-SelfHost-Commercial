"""The bundled Nginx limits how often one client address can make Cloud contact AppFlowy Billing.

The /api/commercial/billing relay needs no AppFlowy session, and Cloud opens a connection to
AppFlowy Billing for every request it relays."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
NGINX = (ROOT / 'docker/nginx/nginx.conf').read_text()
RELAY = 'location ^~ /api/commercial/billing/ {'


def block(text, opening):
    """Return the body of the block that `opening` starts, matching nested braces."""
    start = text.index(opening) + len(opening)
    depth = 1
    for index in range(start, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[start:index]
    raise ValueError('unterminated block: ' + opening)


class BillingRelayLimitTests(unittest.TestCase):
    def test_relay_is_limited_per_client_address(self):
        self.assertIn(RELAY, NGINX)
        relay = block(NGINX, RELAY)
        for directive in (
            'limit_req zone=appflowy_commercial_billing_per_ip burst=20 nodelay;',
            'limit_conn appflowy_commercial_billing_connections_per_ip 10;',
            'limit_req_status 429;',
            'limit_conn_status 429;',
            'proxy_pass $appflowy_cloud_backend;',
            # The limit keys on the socket address; a caller must not choose its own.
            'proxy_set_header X-Forwarded-For $remote_addr;',
        ):
            with self.subTest(directive=directive):
                self.assertIn(directive, relay)
        self.assertRegex(NGINX, r'limit_req_zone \$binary_remote_addr '
                                r'zone=appflowy_commercial_billing_per_ip:\w+ rate=2r/s;')
        self.assertRegex(NGINX, r'limit_conn_zone \$binary_remote_addr '
                                r'zone=appflowy_commercial_billing_connections_per_ip:\w+;')

    def test_limit_applies_to_the_relay_only(self):
        self.assertEqual(len(re.findall(r'zone=appflowy_commercial_billing_per_ip\b(?!:)', NGINX)), 1)
        self.assertEqual(NGINX.count('limit_conn appflowy_commercial_billing_connections_per_ip'), 1)
        self.assertNotIn('appflowy_commercial_billing', block(NGINX, 'location /api {'))


if __name__ == '__main__':
    unittest.main()
