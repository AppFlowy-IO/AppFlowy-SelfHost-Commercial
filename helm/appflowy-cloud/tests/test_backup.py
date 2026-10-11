"""Render the real chart to verify restore startup, storage and privilege boundaries."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]


class BackupChartTests(unittest.TestCase):
    def render(self, enabled=True, overrides=(), success=True):
        command = ['helm', 'template', 'backup-test', str(CHART), '-f', str(ROOT / 'ci/helm-values.yaml')]
        if enabled:
            for value in ('appflowy-backup.enabled=true', 'appflowy-backup.image.tag=adapter-test',
                          'appflowy-backup.nodeName=storage-node', 'appflowy-backup.apiServerCIDR=10.96.0.1/32'):
                command += ['--set', value]
        for value in overrides:
            command += ['--set', value]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def deployment(self, documents, suffix):
        return next(item for item in documents if item['kind'] == 'Deployment'
                    and item['metadata']['name'] == 'appflowy-ci-' + suffix)

    def test_default_has_no_backup_permissions_or_runtime_references(self):
        documents = self.render(enabled=False)
        self.assertFalse(any(item['metadata']['name'].startswith('appflowy-ci-backup') for item in documents))
        cloud = self.deployment(documents, 'cloud')['spec']['template']['spec']['containers'][0]
        environment = {entry['name']: entry for entry in cloud['env']}
        self.assertEqual(environment['APPFLOWY_S3_BUCKET']['value'], 'appflowy')
        self.assertNotIn('APPFLOWY_ACTIVE_REDIS_DATABASE', environment)
        self.assertEqual(cloud['readinessProbe']['httpGet']['path'], '/api/ready')
        self.assertEqual(cloud['startupProbe']['httpGet']['path'], '/api/startup')
        self.assertEqual(cloud['livenessProbe']['httpGet']['path'], '/api/health')

    def test_runtime_selection_survives_helm_render_and_every_writer_uses_it(self):
        documents = self.render(overrides=('appflowy-ai.enabled=true',))
        self.assertFalse(any(item['kind'] == 'ConfigMap' and item['metadata']['name'] ==
                             'appflowy-ci-backup-runtime' for item in documents))
        for service, redis in (('cloud', 'APPFLOWY_REDIS_URI'), ('worker', 'APPFLOWY_WORKER_REDIS_URL'),
                               ('search', 'APPFLOWY_SEARCH_REDIS_URL'), ('ai', 'AI_REDIS_URL')):
            pod = self.deployment(documents, service)['spec']['template']['spec']
            entries = pod['containers'][0]['env']
            environment = {entry['name']: entry for entry in entries}
            self.assertEqual(environment['APPFLOWY_S3_BUCKET']['valueFrom']['configMapKeyRef'],
                             {'name': 'appflowy-ci-backup-runtime', 'key': 'bucket'})
            self.assertEqual(environment['APPFLOWY_ACTIVE_REDIS_DATABASE']['valueFrom']['configMapKeyRef']['key'],
                             'redis-database')
            self.assertTrue(environment[redis]['value'].endswith('/$(APPFLOWY_ACTIVE_REDIS_DATABASE)'))
            self.assertLess([entry['name'] for entry in entries].index('APPFLOWY_ACTIVE_REDIS_DATABASE'),
                            [entry['name'] for entry in entries].index(redis))
        cloud = self.deployment(documents, 'cloud')['spec']['template']['spec']
        gate = cloud['initContainers'][0]
        self.assertIn('APPFLOWY_RESTORE_VERIFY_ONLY', gate['args'][0])
        self.assertEqual(gate['env'][0]['valueFrom']['configMapKeyRef']['key'], 'verify-only')

    def test_backup_and_search_share_pvc_uid_and_node_with_no_docker_socket(self):
        documents = self.render()
        backup = self.deployment(documents, 'backup')
        search = self.deployment(documents, 'search')
        for deployment in (backup, search):
            self.assertEqual(deployment['spec']['replicas'], 1)
            self.assertEqual(deployment['spec']['strategy']['type'], 'Recreate')
            pod = deployment['spec']['template']['spec']
            self.assertEqual(pod['securityContext']['runAsUser'], 999)
            self.assertEqual(pod['nodeSelector']['kubernetes.io/hostname'], 'storage-node')
            volume = next(volume for volume in pod['volumes'] if volume['name'] == 'keyword-index')
            self.assertEqual(volume['persistentVolumeClaim']['claimName'], 'appflowy-ci-search')
        pod = backup['spec']['template']['spec']
        self.assertFalse(any('hostPath' in volume for volume in pod['volumes']))
        self.assertNotIn('wait-for-cloud', [container['name'] for container in pod['initContainers']])
        pvc = next(item for item in documents if item['kind'] == 'PersistentVolumeClaim' and
                   item['metadata']['name'] == 'appflowy-ci-backup')
        self.assertEqual(pvc['metadata']['annotations']['helm.sh/resource-policy'], 'keep')

    def test_backup_permissions_are_namespace_scoped_without_secret_or_exec_access(self):
        documents = self.render()
        role = next(item for item in documents if item['kind'] == 'Role' and
                    item['metadata']['name'] == 'appflowy-ci-backup')
        self.assertFalse(any(item['kind'] in ('ClusterRole', 'ClusterRoleBinding') and
                             'backup' in item['metadata']['name'] for item in documents))
        for rule in role['rules']:
            self.assertFalse(set(rule['resources']) & {'secrets', 'pods/exec', '*'})
            self.assertNotIn('*', rule['verbs'])
        deployment_rule = next(rule for rule in role['rules'] if rule['resources'] == ['deployments'])
        self.assertNotIn('appflowy-ci-web', deployment_rule['resourceNames'])
        self.assertIn('appflowy-ci-gotrue', deployment_rule['resourceNames'])

    def test_unsafe_platform_configurations_fail_rendering(self):
        for value, error in (
            ('appflowy-backup.nodeName=', 'nodeName'),
            ('appflowy-backup.image.tag=', 'explicitly selected image'),
            ('appflowy-backup.apiServerCIDR=', 'API egress'),
            ('appflowy-cloud.autoscaling.enabled=true', 'autoscaling'),
            ('gotrue.replicaCount=2', 'replicaCount'),
            ('appflowy-search.persistence.enabled=false', 'persistent storage'),
            ('postgresql.enabled=false', 'PostgreSQL'),
        ):
            with self.subTest(value=value):
                self.assertIn(error, self.render(overrides=(value,), success=False))

    def test_artifact_location_is_fixed_and_shared_by_cloud_and_backup(self):
        documents = self.render(overrides=('appflowy-backup.artifacts.bucket=private-backups',
                                          'appflowy-backup.artifacts.prefix=archive/'))
        for suffix in ('cloud', 'backup'):
            pod = self.deployment(documents, suffix)['spec']['template']['spec']
            environment = {entry['name']: entry for entry in pod['containers'][0]['env']}
            self.assertEqual(environment['APPFLOWY_BACKUP_BUCKET']['value'], 'private-backups')
            self.assertEqual(environment['APPFLOWY_BACKUP_PREFIX']['value'], 'archive/')


if __name__ == '__main__':
    unittest.main()
