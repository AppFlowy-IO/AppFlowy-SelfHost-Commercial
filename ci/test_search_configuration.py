"""Render Search configuration boundaries without starting deployment services."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from images import ROOT, clean_environment


class SearchConfigurationTests(unittest.TestCase):
    def render(self, *args, env=None):
        result = subprocess.run(args, capture_output=True, text=True,
                                env=env or clean_environment(), timeout=60, cwd=ROOT)
        # Rendered manifests can contain credentials. Keep both streams private on failure.
        self.assertEqual(result.returncode, 0, f'{args[0]} {args[1]} rendering failed')
        return result.stdout

    def test_compose_and_swarm_preserve_explicit_blank_search_url(self):
        source = (ROOT / 'deploy.env').read_text()
        source = '\n'.join(line for line in source.splitlines()
                           if not line.startswith('APPFLOWY_SEARCH_SERVICE_URL=')) + '\n'
        with tempfile.TemporaryDirectory(prefix='appflowy-search-config-') as directory:
            env_file = Path(directory) / 'test.env'
            env_file.write_text(source)
            for file in ('docker-compose.yml', 'docker-swarm/docker-stack.yml'):
                for configured in (None, '', '  \t ', 'https://search.example.test:4002'):
                    with self.subTest(file=file, configured=configured):
                        env = clean_environment()
                        # Retired user flags must not override the fixed legacy bootstrap value.
                        env['APPFLOWY_SEARCH_ENABLED'] = 'false'
                        env['APPFLOWY_INDEXER_ENABLED'] = 'false'
                        if configured is not None:
                            env['APPFLOWY_SEARCH_SERVICE_URL'] = configured
                        command = ('docker', 'compose', '--env-file', str(env_file),
                                   '-p', 'appflowy-search-config', '-f', str(ROOT / file), 'config')
                        self.render(*command, '--quiet', env=env)
                        config = json.loads(self.render(*command, '--format', 'json', env=env))
                        cloud = config['services']['appflowy_cloud']['environment']
                        expected = 'http://appflowy_search:4002' if configured is None else configured
                        self.assertEqual(cloud['APPFLOWY_SEARCH_SERVICE_URL'], expected)
                        self.assertEqual(cloud['APPFLOWY_SEARCH_ENABLED'], 'true')
                        self.assertNotIn('APPFLOWY_INDEXER_ENABLED', cloud)

    def test_helm_disabling_search_clears_cloud_endpoint(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                rendered = self.render('helm', 'template', 'appflowy-search-config',
                                       str(ROOT / 'helm/appflowy-cloud'),
                                       '--set', f'appflowy-search.enabled={str(enabled).lower()}')
                documents = [document for document in yaml.safe_load_all(rendered) if document]
                cloud = next(document for document in documents
                             if document.get('kind') == 'Deployment'
                             and document['metadata']['labels'].get('app.kubernetes.io/component')
                             == 'appflowy-cloud')
                container = cloud['spec']['template']['spec']['containers'][0]
                env = {item['name']: item.get('value') for item in container['env']}
                search = [document for document in documents
                          if document.get('kind') == 'Service'
                          and document['metadata']['labels'].get('app.kubernetes.io/component')
                          == 'appflowy-search']
                self.assertEqual(bool(search), enabled)
                expected = (f"http://{search[0]['metadata']['name']}:{search[0]['spec']['ports'][0]['port']}"
                            if enabled else '')
                self.assertEqual(env['APPFLOWY_SEARCH_SERVICE_URL'], expected)
                self.assertEqual(env['APPFLOWY_SEARCH_ENABLED'], str(enabled).lower())
                self.assertNotIn('APPFLOWY_INDEXER_ENABLED', env)


if __name__ == '__main__':
    unittest.main()
