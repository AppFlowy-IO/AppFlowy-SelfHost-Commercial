"""Render Compose and Swarm AI-app (MCP) settings without starting services (Helm: helm/appflowy-cloud/tests)."""
import json
import re
import subprocess
import unittest

from images import ROOT, clean_environment

COMPOSE_FILES = ('docker-compose.yml', 'docker-swarm/docker-stack.yml')
OAUTH_IP_LIMIT = 'APPFLOWY_MCP_OAUTH_IP_RATE_LIMIT_PER_MINUTE'


class McpConfigurationTests(unittest.TestCase):
    def render(self, *args, env=None):
        result = subprocess.run(args, capture_output=True, text=True,
                                env=env or clean_environment(), timeout=60, cwd=ROOT)
        # Rendered manifests can contain credentials. Keep both streams private on failure.
        self.assertEqual(result.returncode, 0, f'{args[0]} {args[1]} rendering failed')
        return result.stdout

    def compose_services(self, file, **values):
        """The rendered services from deploy.env, with `values` set in the shell."""
        config = json.loads(self.render(
            'docker', 'compose', '--env-file', str(ROOT / 'deploy.env'), '-p', 'appflowy-mcp-config',
            '-f', str(ROOT / file), 'config', '--format', 'json', env={**clean_environment(), **values}))
        return config['services']

    def compose_environments(self, file, **values):
        """Cloud's and MCP's environments from deploy.env, with `values` set in the shell."""
        services = self.compose_services(file, **values)
        return services['appflowy_cloud']['environment'], services['appflowy_mcp']['environment']

    def test_stop_grace_period_outlasts_mcp_shutdown_drain(self):
        # MCP drains requests in flight (60-second request timeout plus 5 s), then 5 s each for its
        # policy watchers and audit queue; Docker's 10-second default kills tool calls and drops
        # queued audit events.
        drain_seconds = 60 + 5 + 5 + 5
        for file in COMPOSE_FILES:
            with self.subTest(file=file):
                grace = self.compose_services(file)['appflowy_mcp'].get('stop_grace_period', '')
                match = re.fullmatch(r'(?:(\d+)m)?(?:(\d+)s)?', grace)
                self.assertTrue(grace and match, grace)
                self.assertGreater(int(match[1] or 0) * 60 + int(match[2] or 0), drain_seconds)

    def test_body_limit_and_outer_proxies_reach_mcp_only(self):
        # Every call in flight holds its parsed body, so the default stays at 1 MiB. The outer proxy
        # list is blank: the bundled Nginx replaces X-Forwarded-For, so there is nothing to step over.
        for file in COMPOSE_FILES:
            for values, body, outer in (
                ({}, '1048576', ''),
                ({'APPFLOWY_MCP_MAX_BODY_BYTES': '524288', 'APPFLOWY_MCP_OUTER_PROXY_CIDRS': '203.0.113.0/24'},
                 '524288', '203.0.113.0/24'),
            ):
                with self.subTest(file=file, values=values):
                    cloud, mcp = self.compose_environments(file, **values)
                    self.assertEqual(mcp.get('APPFLOWY_MCP_MAX_BODY_BYTES'), body)
                    self.assertEqual(mcp.get('APPFLOWY_MCP_OUTER_PROXY_CIDRS'), outer)
                    self.assertNotIn('APPFLOWY_MCP_MAX_BODY_BYTES', cloud)
                    self.assertNotIn('APPFLOWY_MCP_OUTER_PROXY_CIDRS', cloud)

    def test_oauth_ip_limit_is_left_to_the_server_default_unless_configured(self):
        # A deployment value, even one equal to the server default, makes Admin label the limit
        # "From deployment"; Cloud and MCP must also resolve the same limit.
        for file in COMPOSE_FILES:
            for configured in (None, '', '120'):
                with self.subTest(file=file, configured=configured):
                    values = {} if configured is None else {OAUTH_IP_LIMIT: configured}
                    for environment in self.compose_environments(file, **values):
                        self.assertEqual(environment.get(OAUTH_IP_LIMIT), configured)

    def test_audit_fallback_reaches_cloud_and_mcp_alike(self):
        # Until Admin saves the audit switch, Cloud and MCP each read it from their own
        # environment; a value only one of them gets leaves AI-app activity out of the audit log.
        for file in COMPOSE_FILES:
            for configured in (None, 'true'):
                with self.subTest(file=file, configured=configured):
                    values = {} if configured is None else {'APPFLOWY_AUDIT_ENABLE': configured}
                    for environment in self.compose_environments(file, **values):
                        self.assertEqual(environment.get('APPFLOWY_AUDIT_ENABLE'), configured)

    def test_cors_origins_are_configurable_for_mcp_only(self):
        # Helm exposes appflowy-mcp.config.corsAllowedOrigins; Compose and Swarm take it from .env.
        origins = 'https://tools.example.test,https://console.example.test'
        for file in COMPOSE_FILES:
            for configured, expected in ((None, ''), (origins, origins)):
                with self.subTest(file=file, configured=configured):
                    values = {} if configured is None else {'APPFLOWY_CORS_ALLOWED_ORIGINS': configured}
                    cloud, mcp = self.compose_environments(file, **values)
                    self.assertEqual(mcp.get('APPFLOWY_CORS_ALLOWED_ORIGINS'), expected)
                    self.assertNotIn('APPFLOWY_CORS_ALLOWED_ORIGINS', cloud)


if __name__ == '__main__':
    unittest.main()
