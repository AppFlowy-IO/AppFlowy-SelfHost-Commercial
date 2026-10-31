"""Render retained Cloud state and reject replica configurations without shared writable storage."""
from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1]
ROOT = CHART.parents[1]


class InstallationStateChartTests(unittest.TestCase):
    def render(self, overrides=(), success=True):
        command = ['helm', 'template', 'installation-state', str(CHART),
                   '-f', str(ROOT / 'ci/helm-values.yaml')]
        for value in overrides:
            command += ['--set', value]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, 'Helm state contract did not render')
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def cloud(self, documents):
        return next(item for item in documents if item['kind'] == 'Deployment'
                    and item['metadata']['name'] == 'appflowy-ci-cloud')

    def test_default_retains_one_service_owned_claim_and_recreates_the_rwo_writer(self):
        documents = self.render()
        cloud = self.cloud(documents)
        self.assertEqual(cloud['spec']['strategy']['type'], 'Recreate')
        pod = cloud['spec']['template']['spec']
        container = pod['containers'][0]
        env = {entry['name']: entry.get('value') for entry in container['env']}
        self.assertEqual(env['APPFLOWY_INSTALLATION_IDENTITY_PATH'],
                         '/var/lib/appflowy/license/installation.json')
        self.assertEqual(env['APPFLOWY_LICENSE_REPORT_STATE_PATH'],
                         '/var/lib/appflowy/license/report.json')
        self.assertIn({'name': 'cloud-state', 'mountPath': '/var/lib/appflowy/license'},
                      container['volumeMounts'])
        self.assertIn({'name': 'cloud-state', 'persistentVolumeClaim':
                       {'claimName': 'appflowy-ci-cloud-state'}}, pod['volumes'])
        claim = next(item for item in documents if item['kind'] == 'PersistentVolumeClaim'
                     and item['metadata']['name'] == 'appflowy-ci-cloud-state')
        self.assertEqual(claim['metadata']['annotations']['helm.sh/resource-policy'], 'keep')
        self.assertEqual(claim['spec']['accessModes'], ['ReadWriteOnce'])
        self.assertEqual(claim['spec']['resources']['requests']['storage'], '1Gi')
        for workload in documents:
            if workload['kind'] not in ('Deployment', 'StatefulSet') or workload == cloud:
                continue
            for volume in workload['spec']['template']['spec'].get('volumes', []):
                self.assertNotEqual(volume.get('persistentVolumeClaim', {}).get('claimName'),
                                    'appflowy-ci-cloud-state')

    def test_existing_claim_is_reused_without_creating_or_mutating_it(self):
        documents = self.render(('appflowy-cloud.persistence.existingClaim=private-installation',))
        pod = self.cloud(documents)['spec']['template']['spec']
        self.assertEqual(pod['volumes'][0]['persistentVolumeClaim']['claimName'],
                         'private-installation')
        self.assertFalse(any(item['kind'] == 'PersistentVolumeClaim'
                             and item['metadata']['name'] in
                             ('private-installation', 'appflowy-ci-cloud-state')
                             for item in documents))

    def test_missing_persistence_and_multi_replica_rwo_fail_closed(self):
        for overrides, reason in (
            (('appflowy-cloud.persistence.enabled=false',), 'persistent storage'),
            (('appflowy-cloud.replicaCount=2',), 'ReadWriteMany'),
            (('appflowy-cloud.autoscaling.enabled=true',), 'ReadWriteMany'),
            (('appflowy-cloud.persistence.existingClaim=private-installation',
              'appflowy-cloud.replicaCount=2'), 'ReadWriteMany'),
            (('appflowy-cloud.persistence.accessModes[0]=ReadOnlyMany',), 'accessModes'),
        ):
            with self.subTest(overrides=overrides):
                self.assertIn(reason, self.render(overrides, success=False))

    def test_multiple_replicas_and_autoscaling_share_one_rwx_claim(self):
        documents = self.render(('appflowy-cloud.replicaCount=2',
                                 'appflowy-cloud.persistence.accessModes[0]=ReadWriteMany',
                                 'appflowy-cloud.persistence.storageClass=shared-filesystem',
                                 'appflowy-cloud.autoscaling.enabled=true'))
        cloud = self.cloud(documents)
        self.assertEqual(cloud['spec']['replicas'], 2)
        self.assertNotIn('strategy', cloud['spec'])
        claim = next(item for item in documents if item['kind'] == 'PersistentVolumeClaim'
                     and item['metadata']['name'] == 'appflowy-ci-cloud-state')
        self.assertEqual(claim['spec']['accessModes'], ['ReadWriteMany'])
        self.assertEqual(claim['spec']['storageClassName'], 'shared-filesystem')
        self.assertEqual(cloud['spec']['template']['spec']['volumes'][0]
                         ['persistentVolumeClaim']['claimName'], claim['metadata']['name'])

    def test_single_replica_autoscaling_and_disabled_cloud_do_not_need_rwx(self):
        self.render(('appflowy-cloud.autoscaling.enabled=true',
                     'appflowy-cloud.autoscaling.maxReplicas=1'))
        documents = self.render(('appflowy-cloud.enabled=false',
                                 'appflowy-cloud.persistence.enabled=false'))
        self.assertFalse(any(item['metadata']['name'] == 'appflowy-ci-cloud-state'
                             for item in documents))


if __name__ == '__main__':
    unittest.main()
