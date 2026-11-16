"""Render GoTrue credentials to verify managed and existing Secret behavior."""
import base64
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]
OPTIONAL_CREDENTIALS = (
    ('smtp', 'gotrue.config.smtp', 'password', 'GOTRUE_SMTP_PASS', 'smtp-password'),
    ('google', 'gotrue.config.oauth.google', 'secret', 'GOTRUE_EXTERNAL_GOOGLE_SECRET', 'google-oauth-secret'),
    ('github', 'gotrue.config.oauth.github', 'secret', 'GOTRUE_EXTERNAL_GITHUB_SECRET', 'github-oauth-secret'),
    ('discord', 'gotrue.config.oauth.discord', 'secret', 'GOTRUE_EXTERNAL_DISCORD_SECRET', 'discord-oauth-secret'),
    ('saml', 'gotrue.config.saml', 'privateKey', 'GOTRUE_SAML_PRIVATE_KEY', 'saml-private-key'),
)


class GoTrueSecretChartTests(unittest.TestCase):
    def render(self, overrides=(), ci_profile=False, release='gotrue-secret-test'):
        command = ['helm', 'template', release, str(CHART)]
        if ci_profile:
            command += ['-f', str(ROOT / 'ci/helm-values.yaml')]
        for value in overrides:
            command += ['--set', value]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def deployment(self, documents):
        return next(item for item in documents if item['kind'] == 'Deployment'
                    and item['metadata']['labels'].get('app.kubernetes.io/component') == 'gotrue')

    def environment(self, documents):
        container = self.deployment(documents)['spec']['template']['spec']['containers'][0]
        return {entry['name']: entry for entry in container['env']}

    def assert_external_credentials(self, documents, credentials):
        secret_name = 'external-gotrue-credentials'
        environment = self.environment(documents)
        for variable, key in credentials.items():
            self.assertEqual(environment[variable]['valueFrom']['secretKeyRef'],
                             {'name': secret_name, 'key': key})
            self.assertNotIn('value', environment[variable])
        managed_name = self.deployment(documents)['metadata']['name'] + '-secret'
        self.assertFalse(any(item['kind'] == 'Secret'
                             and item['metadata']['name'] in (managed_name, secret_name)
                             for item in documents))
        for variable in ('POSTGRES_PASSWORD', 'GOTRUE_JWT_SECRET'):
            self.assertNotEqual(environment[variable]['valueFrom']['secretKeyRef']['name'], secret_name)

    def test_inline_credentials_remain_in_the_managed_secret(self):
        overrides = ['gotrue.config.adminPassword=test-admin-password']
        credentials = {'GOTRUE_ADMIN_PASSWORD': 'admin-password'}
        passwords = {'admin-password': 'test-admin-password'}
        for name, config, field, variable, key in OPTIONAL_CREDENTIALS:
            overrides += [config + '.enabled=true', config + '.' + field + '=test-' + name + '-password']
            credentials[variable] = key
            passwords[key] = 'test-' + name + '-password'
        for ci_profile in (False, True):
            with self.subTest(ci_profile=ci_profile):
                documents = self.render(overrides, ci_profile=ci_profile)
                secret_name = self.deployment(documents)['metadata']['name'] + '-secret'
                secret = next(item for item in documents if item['kind'] == 'Secret'
                              and item['metadata']['name'] == secret_name)
                self.assertEqual({key: base64.b64decode(value).decode() for key, value in secret['data'].items()},
                                 passwords)
                environment = self.environment(documents)
                for variable, key in credentials.items():
                    self.assertEqual(environment[variable]['valueFrom']['secretKeyRef'],
                                     {'name': secret_name, 'key': key})

    def test_existing_secret_supplies_admin_without_creating_a_secret(self):
        for ci_profile in (False, True):
            with self.subTest(ci_profile=ci_profile):
                documents = self.render(('gotrue.existingSecret=external-gotrue-credentials',
                                         'gotrue.config.adminPassword=ignored-inline-password'),
                                        ci_profile=ci_profile)
                self.assert_external_credentials(documents, {'GOTRUE_ADMIN_PASSWORD': 'admin-password'})
                environment = self.environment(documents)
                for _, _, _, variable, _ in OPTIONAL_CREDENTIALS:
                    self.assertNotIn(variable, environment)

    def test_existing_secret_supplies_each_enabled_provider(self):
        selections = [(credential[0], (credential,)) for credential in OPTIONAL_CREDENTIALS]
        selections.append(('all', OPTIONAL_CREDENTIALS))
        for name, selected in selections:
            with self.subTest(provider=name):
                overrides = ['gotrue.existingSecret=external-gotrue-credentials']
                credentials = {'GOTRUE_ADMIN_PASSWORD': 'admin-password'}
                for _, config, field, variable, key in selected:
                    overrides += [config + '.enabled=true', config + '.' + field + '=ignored-inline-password']
                    credentials[variable] = key
                documents = self.render(overrides, ci_profile=True)
                self.assert_external_credentials(documents, credentials)
                environment = self.environment(documents)
                for _, _, _, variable, _ in OPTIONAL_CREDENTIALS:
                    if variable not in credentials:
                        self.assertNotIn(variable, environment)

    def test_disabled_gotrue_has_no_deployment_or_secret(self):
        for secret_name in ('', 'external-gotrue-credentials'):
            with self.subTest(existing_secret=secret_name):
                documents = self.render(('gotrue.enabled=false', 'gotrue.existingSecret=' + secret_name))
                self.assertFalse(any(item['kind'] in ('Deployment', 'Secret')
                                     and item['metadata'].get('labels', {}).get('app.kubernetes.io/component')
                                     == 'gotrue' for item in documents))

    def test_managed_secret_tracks_release_and_fullname_overrides(self):
        for release, overrides, expected_name in (
            ('first-release', (), 'first-release-appflowy-cloud-gotrue-secret'),
            ('second-release', ('fullnameOverride=custom-appflowy',), 'custom-appflowy-gotrue-secret'),
        ):
            with self.subTest(release=release):
                documents = self.render(overrides, release=release)
                self.assertEqual(self.environment(documents)['GOTRUE_ADMIN_PASSWORD']['valueFrom']['secretKeyRef'],
                                 {'name': expected_name, 'key': 'admin-password'})
                self.assertTrue(any(item['kind'] == 'Secret' and item['metadata']['name'] == expected_name
                                    for item in documents))


if __name__ == '__main__':
    unittest.main()
