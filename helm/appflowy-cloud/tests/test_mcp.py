"""Render the real chart to verify that nothing in the environment turns MCP on or off, and MCP's shared
settings, origin checks, shutdown, metrics and streaming Ingress."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]
# Removed: MCP is on by default and only the Admin console's MCP page turns it off.
REMOVED_SWITCH = 'APPFLOWY_MCP_ENABLED'
OAUTH_IP_LIMIT = 'APPFLOWY_MCP_OAUTH_IP_RATE_LIMIT_PER_MINUTE'


class McpChartTests(unittest.TestCase):
    def render(self, overrides=(), strings=(), success=True, files=()):
        command = ['helm', 'template', 'mcp-test', str(CHART), '-f', str(ROOT / 'ci/helm-values.yaml')]
        for value in overrides:
            command += ['--set', value]
        for value in strings:
            command += ['--set-string', value]
        command += list(files)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def deployment(self, documents, suffix):
        return next(item for item in documents if item['kind'] == 'Deployment'
                    and item['metadata']['name'] == 'appflowy-ci-' + suffix)

    def environment(self, documents, suffix):
        container = self.deployment(documents, suffix)['spec']['template']['spec']['containers'][0]
        return {entry['name']: entry.get('value') for entry in container['env']}

    def mcp_ingress(self, documents):
        return next(item for item in documents if item['kind'] == 'Ingress'
                    and item['metadata']['name'] == 'appflowy-ci-mcp')

    def test_no_container_receives_an_mcp_on_off_variable(self):
        # MCP is on by default and the setting saved in Admin always decides, so neither Cloud nor
        # MCP may receive APPFLOWY_MCP_ENABLED: not by default, not with an external or no MCP
        # service, and not from a values file that still sets the removed enabledOverride.
        external = 'appflowy-mcp.config.publicBaseUrl=https://ai.example.test'
        for overrides, strings, suffixes in (
            ((), (), ('cloud', 'mcp')),
            (('appflowy-mcp.config.enabledOverride=false',), (), ('cloud', 'mcp')),
            ((), ('appflowy-mcp.config.enabledOverride=true',), ('cloud', 'mcp')),
            (('appflowy-mcp.enabled=false', external), (), ('cloud',)),
            (('appflowy-mcp.enabled=false', 'appflowy-mcp.config.enabledOverride=false'), (), ('cloud',)),
        ):
            with self.subTest(overrides=overrides, strings=strings):
                documents = self.render(overrides=overrides, strings=strings)
                for suffix in suffixes:
                    self.assertNotIn(REMOVED_SWITCH, self.environment(documents, suffix), suffix)
                for item in documents:
                    pod = item.get('spec', {}).get('template', {}).get('spec', {})
                    for container in pod.get('initContainers', []) + pod.get('containers', []):
                        names = [entry['name'] for entry in container.get('env', [])]
                        self.assertNotIn(REMOVED_SWITCH, names, item['metadata']['name'])

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

    def test_mcp_reads_the_license_under_clouds_origin(self):
        # Cloud keys the installed license by the host of APPFLOWY_BASE_URL, and a self-hosted MCP
        # service serves only with a One, Team or Enterprise license, so it must read the same host,
        # also when it serves on a domain of its own.
        for overrides in ((), ('appflowy-mcp.config.publicBaseUrl=https://ai.example.test/',)):
            with self.subTest(overrides=overrides):
                documents = self.render(overrides=overrides)
                cloud = self.environment(documents, 'cloud')['APPFLOWY_BASE_URL']
                self.assertEqual(self.environment(documents, 'mcp').get('APPFLOWY_BASE_URL'), cloud)

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
        overrides = disabled + ('appflowy-mcp.config.allowedEmailDomains=example.test',
                                'appflowy-mcp.config.allowedEmails=a@example.test',
                                'appflowy-mcp.config.oauthIpRateLimitPerMinute=120')
        cloud = self.environment(self.render(overrides=overrides), 'cloud')
        self.assertEqual(cloud['APPFLOWY_MCP_ALLOWED_EMAIL_DOMAINS'], 'example.test')
        self.assertEqual(cloud['APPFLOWY_MCP_ALLOWED_EMAILS'], 'a@example.test')
        self.assertEqual(cloud[OAUTH_IP_LIMIT], '120')
        error = self.render(overrides=disabled[:1],
                            strings=('appflowy-mcp.config.publicBaseUrl=https://ai.example.test/mcp',),
                            success=False)
        self.assertIn('publicBaseUrl', error)

    def test_disabling_mcp_without_an_origin_leaves_cloud_on_its_own_origin(self):
        # No MCP origin is rendered, so Cloud advertises no MCP (it never falls back to
        # APPFLOWY_BASE_URL); the Admin console's MCP page, not the chart, turns MCP off.
        documents = self.render(overrides=('appflowy-mcp.enabled=false',))
        self.assertFalse(any(item['metadata']['name'] == 'appflowy-ci-mcp' for item in documents))
        cloud = self.environment(documents, 'cloud')
        self.assertTrue(cloud.get('APPFLOWY_BASE_URL'))
        for name in ('APPFLOWY_MCP_BASE_URL', REMOVED_SWITCH, OAUTH_IP_LIMIT):
            self.assertNotIn(name, cloud)
        self.assertNotIn('APPFLOWY_MCP_BASE_URL', self.environment(documents, 'web'))

    def test_unsafe_mcp_configurations_fail_rendering(self):
        for value, error in (
            ('appflowy-mcp.config.publicBaseUrl=https://appflowy.example.test/mcp', 'publicBaseUrl'),
            ('appflowy-mcp.config.publicBaseUrl=appflowy.example.test', 'publicBaseUrl'),
            ('ingress.mcp.proxyTimeoutSeconds=30', 'proxyTimeoutSeconds'),
            ('ingress.mcp.bodySize=0', 'bodySize'),
            ('appflowy-mcp.terminationGracePeriodSeconds=75', 'terminationGracePeriodSeconds'),
        ):
            with self.subTest(value=value):
                self.assertIn(error, self.render(strings=(value,), success=False))

    def test_streaming_annotations_win_over_inherited_and_extra_ones(self):
        documents = self.render(overrides=(
            'ingress.mcp.annotations.nginx\\.ingress\\.kubernetes\\.io/proxy-buffering=on',
            'ingress.mcp.annotations.nginx\\.ingress\\.kubernetes\\.io/proxy-read-timeout=30',
            'ingress.mcp.annotations.example\\.test/owner=ai-apps',
        ))
        annotations = self.mcp_ingress(documents)['metadata']['annotations']
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/use-regex'], 'true')
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-buffering'], 'off')
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-read-timeout'], '3600')
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-send-timeout'], '3600')
        # The primary Ingress's 100m upload limit does not reach the MCP routes.
        self.assertEqual(annotations['nginx.ingress.kubernetes.io/proxy-body-size'], '8m')
        self.assertEqual(annotations['example.test/owner'], 'ai-apps')

    def test_mcp_ingress_keeps_browser_affinity_and_per_ip_limits_off(self):
        # MCP keeps no session: affinity would put every user behind one NAT or AI vendor's egress
        # on one replica, and the primary per-IP limits would count each open GET /mcp stream.
        documents = self.render(overrides=(
            'ingress.annotations.nginx\\.ingress\\.kubernetes\\.io/limit-rps=100',
            'ingress.annotations.nginx\\.ingress\\.kubernetes\\.io/limit-connections=50',
            'ingress.annotations.nginx\\.ingress\\.kubernetes\\.io/upstream-hash-by-subset=true',
        ))
        primary = next(item for item in documents if item['kind'] == 'Ingress'
                       and item['metadata']['name'] == 'appflowy-ci')
        self.assertEqual(primary['metadata']['annotations']['nginx.ingress.kubernetes.io/upstream-hash-by'],
                         '$remote_addr')
        inherited = self.mcp_ingress(documents)['metadata']['annotations']
        self.assertFalse([key for key in inherited if key.startswith(('nginx.ingress.kubernetes.io/upstream-hash-by',
                                                                       'nginx.ingress.kubernetes.io/limit-'))])
        # Limits meant for MCP still apply from its own annotations.
        limited = self.render(strings=(
            'ingress.mcp.annotations.nginx\\.ingress\\.kubernetes\\.io/limit-connections=200',))
        self.assertEqual(self.mcp_ingress(limited)['metadata']['annotations']
                         ['nginx.ingress.kubernetes.io/limit-connections'], '200')

    def test_mcp_ingress_paths_are_anchored_regexes(self):
        # GoTrue's and MinIO's regex Ingresses make ingress-nginx match every path of the host as
        # `~* "^<path>"`, so an Exact or Prefix path would also send /mcpx or /mcp/x to MCP.
        paths = self.mcp_ingress(self.render())['spec']['rules'][0]['http']['paths']
        self.assertEqual([(path['path'], path['pathType']) for path in paths], [
            ('/mcp$', 'ImplementationSpecific'),
            ('/api/mcp(/|$)', 'ImplementationSpecific'),
            ('/.well-known/oauth-authorization-server$', 'ImplementationSpecific'),
            ('/.well-known/oauth-protected-resource(/|$)', 'ImplementationSpecific'),
            ('/.well-known/mcp.json$', 'ImplementationSpecific'),
            ('/.well-known/openai-apps-challenge$', 'ImplementationSpecific'),
        ])
        self.assertEqual({path['backend']['service']['port']['number'] for path in paths}, {8002})

    def test_plugin_directory_settings_reach_mcp_only_when_set(self):
        # Blank publishes nothing: MCP answers 404 for the challenge and omits op_policy_uri/op_tos_uri.
        settings = {'openaiAppsChallenge': 'APPFLOWY_MCP_OPENAI_APPS_CHALLENGE',
                    'privacyPolicyUrl': 'APPFLOWY_MCP_PRIVACY_POLICY_URL',
                    'termsOfServiceUrl': 'APPFLOWY_MCP_TERMS_OF_SERVICE_URL'}
        values = {'openaiAppsChallenge': 'ci-challenge-token',
                  'privacyPolicyUrl': 'https://appflowy.example.test/privacy',
                  'termsOfServiceUrl': 'https://appflowy.example.test/terms'}
        documents = self.render()
        for suffix in ('cloud', 'mcp'):
            for name in settings.values():
                self.assertNotIn(name, self.environment(documents, suffix), suffix)
        documents = self.render(strings=tuple(f'appflowy-mcp.config.{key}={value}' for key, value in values.items()))
        mcp = self.environment(documents, 'mcp')
        for key, name in settings.items():
            self.assertEqual(mcp.get(name), values[key])
            self.assertNotIn(name, self.environment(documents, 'cloud'))

    def test_mcp_listens_everywhere_bounds_bodies_and_outlasts_its_shutdown_drain(self):
        documents = self.render()
        mcp = self.environment(documents, 'mcp')
        # Dual-stack like Cloud: IPv6 single-stack clusters probe and proxy over IPv6.
        self.assertEqual(mcp['APPFLOWY_APPLICATION_HOST'], '[::]')
        self.assertEqual(mcp['APPFLOWY_MCP_MAX_BODY_BYTES'], '1048576')
        # SIGTERM ends GET /mcp streams at once; the grace period outlasts the request drain
        # (60-second timeout plus 5) and the policy watcher and audit queue drains (5 each).
        self.assertEqual(self.deployment(documents, 'mcp')['spec']['template']['spec']
                         ['terminationGracePeriodSeconds'], 90)
        longer = self.render(overrides=('appflowy-mcp.terminationGracePeriodSeconds=120',))
        self.assertEqual(self.deployment(longer, 'mcp')['spec']['template']['spec']
                         ['terminationGracePeriodSeconds'], 120)

    def test_metrics_overlays_scrape_mcp_like_the_other_services(self):
        for overlay in ('metrics', 'monitoring'):
            with self.subTest(overlay=overlay):
                documents = self.render(files=('-f', str(CHART / 'values/features' / f'{overlay}.yaml')))
                monitor = next(item for item in documents if item['kind'] == 'ServiceMonitor'
                               and item['metadata']['name'] == 'appflowy-ci-mcp')
                self.assertEqual(monitor['spec']['selector']['matchLabels']['app.kubernetes.io/component'],
                                 'appflowy-mcp')
                self.assertEqual(monitor['spec']['endpoints'], [
                    {'port': 'http', 'path': '/metrics', 'interval': '30s', 'scrapeTimeout': '10s'}])
        for overrides, files in (((), ()), (('appflowy-mcp.enabled=false',),
                                            ('-f', str(CHART / 'values/features/metrics.yaml')))):
            with self.subTest(overrides=overrides, files=files):
                documents = self.render(overrides=overrides, files=files)
                self.assertFalse(any(item['kind'] == 'ServiceMonitor' and item['metadata']['name'] == 'appflowy-ci-mcp'
                                     for item in documents))
        annotated = self.render(overrides=('appflowy-mcp.metrics.enabled=true',),
                                strings=('appflowy-mcp.metrics.serviceAnnotations.example\\.test/scrape=true',))
        service = next(item for item in annotated if item['kind'] == 'Service'
                       and item['metadata']['name'] == 'appflowy-ci-mcp')
        self.assertEqual(service['metadata']['annotations'], {'example.test/scrape': 'true'})


if __name__ == '__main__':
    unittest.main()
