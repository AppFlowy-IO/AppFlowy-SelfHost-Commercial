"""Render deployment-wide AI-app (MCP) settings without starting deployment services."""
import json
import subprocess
import unittest

import yaml

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

    def compose_environments(self, file, **values):
        """Cloud's and MCP's environments from deploy.env, with `values` set in the shell."""
        config = json.loads(self.render(
            'docker', 'compose', '--env-file', str(ROOT / 'deploy.env'), '-p', 'appflowy-mcp-config',
            '-f', str(ROOT / file), 'config', '--format', 'json', env={**clean_environment(), **values}))
        return config['services']['appflowy_cloud']['environment'], config['services']['appflowy_mcp']['environment']

    def helm_environments(self, *values):
        """Cloud's and MCP's container environments from the chart, with `values` passed to --set."""
        command = ['helm', 'template', 'appflowy-mcp-config', str(ROOT / 'helm/appflowy-cloud')]
        for value in values:
            command += ['--set', value]
        documents = [document for document in yaml.safe_load_all(self.render(*command)) if document]
        environments = []
        for component in ('appflowy-cloud', 'appflowy-mcp'):
            deployment = next(document for document in documents if document.get('kind') == 'Deployment'
                              and document['metadata']['labels'].get('app.kubernetes.io/component') == component)
            container = deployment['spec']['template']['spec']['containers'][0]
            environments.append({item['name']: item.get('value') for item in container['env']})
        return tuple(environments)

    def test_oauth_ip_limit_is_left_to_the_server_default_unless_configured(self):
        # A deployment value, even one equal to the server default, makes Admin label the limit
        # "From deployment"; Cloud and MCP must also resolve the same limit.
        for file in COMPOSE_FILES:
            for configured in (None, '', '120'):
                with self.subTest(file=file, configured=configured):
                    values = {} if configured is None else {OAUTH_IP_LIMIT: configured}
                    for environment in self.compose_environments(file, **values):
                        self.assertEqual(environment.get(OAUTH_IP_LIMIT), configured)
        for configured in (None, '0', '120'):
            with self.subTest(helm=configured):
                values = () if configured is None else (
                    'appflowy-mcp.config.oauthIpRateLimitPerMinute=' + configured,)
                for environment in self.helm_environments(*values):
                    # MCP refuses 0 at startup instead of the chart replacing it.
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
        for configured in (None, 'true'):
            with self.subTest(helm=configured):
                values = () if configured is None else ('appflowy-cloud.config.auditEnable=' + configured,)
                for environment in self.helm_environments(*values):
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
