"""Render the real chart to verify the AI-app (MCP) lock, shared settings, origin checks and streaming Ingress."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]
LOCK = 'APPFLOWY_MCP_ENABLED'
OAUTH_IP_LIMIT = 'APPFLOWY_MCP_OAUTH_IP_RATE_LIMIT_PER_MINUTE'


class McpChartTests(unittest.TestCase):
    def render(self, overrides=(), strings=(), success=True):
        command = ['helm', 'template', 'mcp-test', str(CHART), '-f', str(ROOT / 'ci/helm-values.yaml')]
        for value in overrides:
            command += ['--set', value]
        for value in strings:
            command += ['--set-string', value]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def environment(self, documents, suffix):
        deployment = next(item for item in documents if item['kind'] == 'Deployment'
                          and item['metadata']['name'] == 'appflowy-ci-' + suffix)
        container = deployment['spec']['template']['spec']['containers'][0]
        return {entry['name']: entry.get('value') for entry in container['env']}

    def test_enabled_override_locks_cloud_and_mcp_alike(self):
        # Cloud reports the lock in Admin and MCP enforces it, so they must never disagree. An
        # unquoted YAML false must still lock AI apps off rather than be skipped as empty.
        for overrides, strings, expected in (
            ((), (), None),
            ((), ('appflowy-mcp.config.enabledOverride=',), None),
            (('appflowy-mcp.config.enabledOverride=false',), (), 'false'),
            ((), ('appflowy-mcp.config.enabledOverride=false',), 'false'),
            (('appflowy-mcp.config.enabledOverride=true',), (), 'true'),
        ):
            with self.subTest(overrides=overrides, strings=strings):
                documents = self.render(overrides=overrides, strings=strings)
                for suffix in ('cloud', 'mcp'):
                    self.assertEqual(self.environment(documents, suffix).get(LOCK), expected, suffix)

    def test_oauth_ip_limit_is_left_to_the_server_default_unless_configured(self):
        # A deployment value, even one equal to the server default, makes Admin label the limit
        # "From deployment"; Cloud and MCP must also resolve the same limit.
        for configured in (None, '0', '120'):
            with self.subTest(configured=configured):
                overrides = () if configured is None else (
                    'appflowy-mcp.config.oauthIpRateLimitPerMinute=' + configured,)
                documents = self.render(overrides=overrides)
                for suffix in ('cloud', 'mcp'):
                    # MCP refuses 0 at startup instead of the chart replacing it.
                    self.assertEqual(self.environment(documents, suffix).get(OAUTH_IP_LIMIT), configured, suffix)

    def test_audit_fallback_reaches_cloud_and_mcp_alike(self):
        # Until Admin saves the audit switch, Cloud and MCP each read it from their own
        # environment; a value only one of them gets leaves AI-app activity out of the audit log.
        for configured in (None, 'true'):
            with self.subTest(configured=configured):
                overrides = () if configured is None else ('appflowy-cloud.config.auditEnable=' + configured,)
                documents = self.render(overrides=overrides)
                for suffix in ('cloud', 'mcp'):
                    self.assertEqual(self.environment(documents, suffix).get('APPFLOWY_AUDIT_ENABLE'), configured,
                                     suffix)

    def test_one_origin_reaches_mcp_cloud_and_web_but_not_admin(self):
        external = 'appflowy-mcp.config.publicBaseUrl=https://ai.example.test/'
        for overrides, origin, readers in (
            ((), 'http://localhost', ('mcp', 'cloud', 'web')),
            ((external,), 'https://ai.example.test', ('mcp', 'cloud', 'web')),
            (('appflowy-mcp.enabled=false', external), 'https://ai.example.test', ('cloud', 'web')),
        ):
            with self.subTest(overrides=overrides):
                documents = self.render(overrides=overrides)
                for suffix in readers:
                    self.assertEqual(self.environment(documents, suffix)['APPFLOWY_MCP_BASE_URL'], origin, suffix)
                # Admin reads the origin from Cloud; it has no setting of its own.
                self.assertNotIn('APPFLOWY_MCP_BASE_URL', self.environment(documents, 'admin'))

    def test_external_mcp_origin_keeps_the_policy_env_on_cloud(self):
        disabled = ('appflowy-mcp.enabled=false', 'appflowy-mcp.config.publicBaseUrl=https://ai.example.test')
        for override, expected in ((None, None), ('true', 'true'), ('false', 'false')):
            with self.subTest(enabledOverride=override):
                overrides = disabled + ('appflowy-mcp.config.allowedEmailDomains=example.test',)
                if override is not None:
                    overrides += ('appflowy-mcp.config.enabledOverride=' + override,)
                cloud = self.environment(self.render(overrides=overrides), 'cloud')
                self.assertEqual(cloud.get(LOCK), expected)
                self.assertEqual(cloud['APPFLOWY_MCP_ALLOWED_EMAIL_DOMAINS'], 'example.test')
        error = self.render(overrides=disabled[:1],
                            strings=('appflowy-mcp.config.publicBaseUrl=https://ai.example.test/mcp',),
                            success=False)
        self.assertIn('publicBaseUrl', error)

    def test_disabling_mcp_without_an_origin_locks_ai_apps_off_in_cloud(self):
        # Unlocked, Cloud would fall back to APPFLOWY_BASE_URL and advertise /mcp to every client
        # once Admin turns AI apps on, although nothing serves it.
        for overrides in ((), ('appflowy-mcp.config.enabledOverride=true',)):
            with self.subTest(overrides=overrides):
                documents = self.render(overrides=('appflowy-mcp.enabled=false',) + overrides)
                self.assertFalse(any(item['metadata']['name'] == 'appflowy-ci-mcp' for item in documents))
                cloud = self.environment(documents, 'cloud')
                self.assertEqual(cloud[LOCK], 'false')
                self.assertNotIn('APPFLOWY_MCP_BASE_URL', cloud)
                self.assertNotIn('APPFLOWY_MCP_BASE_URL', self.environment(documents, 'web'))

    def test_unsafe_mcp_configurations_fail_rendering(self):
        for value, error in (
            ('appflowy-mcp.config.publicBaseUrl=https://appflowy.example.test/mcp', 'publicBaseUrl'),
            ('appflowy-mcp.config.publicBaseUrl=appflowy.example.test', 'publicBaseUrl'),
            ('ingress.mcp.proxyTimeoutSeconds=30', 'proxyTimeoutSeconds'),
            ('ingress.mcp.bodySize=0', 'bodySize'),
        ):
            with self.subTest(value=value):
                self.assertIn(error, self.render(strings=(value,), success=False))

    def test_streaming_annotations_win_over_inherited_and_extra_ones(self):
        documents = self.render(overrides=(
            'ingress.mcp.annotations.nginx\\.ingress\\.kubernetes\\.io/proxy-buffering=on',
            'ingress.mcp.annotations.nginx\\.ingress\\.kubernetes\\.io/proxy-read-timeout=30',
            'ingress.mcp.annotations.example\\.test/owner=ai-apps',
        ))
        ingress = next(item for item in documents if item['kind'] == 'Ingress'
                       and item['metadata']['name'] == 'appflowy-ci-mcp')
        annotations = ingress['metadata']['annotations']
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-buffering'], 'off')
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-read-timeout'], '3600')
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-send-timeout'], '3600')
        # The primary Ingress's 100m upload limit does not reach the MCP routes.
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-body-size'], '8m')
        self.assertEqual(annotations['example.test/owner'], 'ai-apps')
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/upstream-hash-by'], '$remote_addr')


if __name__ == '__main__':
    unittest.main()
