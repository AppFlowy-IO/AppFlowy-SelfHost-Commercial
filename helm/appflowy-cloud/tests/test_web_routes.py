"""Render the real chart to verify that AI Meeting's YouTube import reaches AppFlowy Web, not Cloud."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]
ROUTE = '/api/youtube-audio'


class WebRouteChartTests(unittest.TestCase):
    def render_paths(self, overrides=()):
        command = ['helm', 'template', 'web-test', str(CHART), '-f', str(ROOT / 'ci/helm-values.yaml')]
        for value in overrides:
            command += ['--set', value]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [(path['path'], path['pathType'], path['backend']['service']['name'])
                for item in yaml.safe_load_all(result.stdout)
                if item and item['kind'] == 'Ingress'
                for rule in item['spec']['rules']
                for path in rule['http']['paths']]

    def test_youtube_import_goes_to_web(self):
        paths = self.render_paths()
        web = next(service for path, _, service in paths if path == '/')
        self.assertIn((ROUTE, 'Exact', web), paths)
        # The longer, exact path wins over the /api prefix that Cloud serves.
        self.assertIn('/api', [path for path, kind, _ in paths if kind == 'Prefix'])

    def test_route_is_absent_without_web(self):
        paths = self.render_paths(('appflowy-web.enabled=false',))
        self.assertNotIn(ROUTE, [path for path, _, _ in paths])


if __name__ == '__main__':
    unittest.main()
