"""Render the real chart to verify the AI-app (MCP) lock, origin checks and streaming Ingress."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]
LOCK = 'APPFLOWY_MCP_ENABLED'


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
