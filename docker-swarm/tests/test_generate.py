"""Swarm must retain deployable defaults without activating unsupported Compose profiles."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import yaml

SPEC = importlib.util.spec_from_file_location('swarm_generate', Path(__file__).resolve().parents[1] / 'generate.py')
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.source = yaml.safe_load(GENERATOR.SOURCE.read_text())

    def test_current_source_retains_application_defaults_without_backup_or_runtime_files(self):
        before = copy.deepcopy(self.source)
        stack = GENERATOR.derive(self.source)
        self.assertEqual(self.source, before)
        self.assertEqual(set(stack['services']),
                         set(self.source['services']) - {'appflowy_backup', 'appflowy_log_collector'})
        for name, service in stack['services'].items():
            self.assertNotIn('profiles', service)
            self.assertNotIn('env_file', service)
        cloud = stack['services']['appflowy_cloud']['environment']
        self.assertIn('APPFLOWY_S3_BUCKET=${APPFLOWY_S3_BUCKET}', cloud)
        self.assertIn('APPFLOWY_REDIS_URI=${APPFLOWY_REDIS_URI}', cloud)
        search = stack['services']['appflowy_search']['environment']
        self.assertIn('APPFLOWY_KEYWORD_INDEX_DIR=${APPFLOWY_KEYWORD_INDEX_DIR:-/var/lib/appflowy/keyword_index}', search)
        GENERATOR.check_parity(self.source, stack)

    def test_compose_log_collection_is_excluded_without_changing_other_cloud_settings(self):
        cloud = self.source['services']['appflowy_cloud']
        original = GENERATOR.environment_map(cloud['environment'])
        for environment in (cloud['environment'], original):
            with self.subTest(environment_type=type(environment).__name__):
                source = copy.deepcopy(self.source)
                source['services']['appflowy_cloud']['environment'] = copy.deepcopy(environment)
                stack = GENERATOR.derive(source)
                actual = GENERATOR.environment_map(stack['services']['appflowy_cloud']['environment'])
                self.assertFalse(any(key.startswith('APPFLOWY_SERVER_LOGS_') for key in actual))
                self.assertEqual({key: actual[key] for key in original if key not in
                                  GENERATOR.COMPOSE_LOG_ENVIRONMENT},
                                 {key: value for key, value in original.items() if key not in
                                  GENERATOR.COMPOSE_LOG_ENVIRONMENT})
                GENERATOR.check_parity(source, stack)
        backup = GENERATOR.derive_backup(
            self.source, yaml.safe_load(GENERATOR.BACKUP_SOURCE.read_text()))
        self.assertFalse(any(key.startswith('APPFLOWY_SERVER_LOGS_') for key in
                             backup['services']['appflowy_cloud']['environment']))

    def test_collector_without_exact_opt_in_profile_requires_review(self):
        for profile in (None, [], ['other'], ['server-logs', 'other']):
            with self.subTest(profile=profile):
                source = copy.deepcopy(self.source)
                collector = source['services']['appflowy_log_collector']
                if profile is None:
                    collector.pop('profiles')
                else:
                    collector['profiles'] = profile
                with self.assertRaisesRegex(ValueError, 'explicit Swarm adapter'):
                    GENERATOR.derive(source)

    def test_changed_or_ambiguous_cloud_log_settings_require_review(self):
        original = self.source['services']['appflowy_cloud']['environment']
        mutations = [
            original + ['APPFLOWY_SERVER_LOGS_UNREVIEWED=true'],
        ]
        for key in GENERATOR.COMPOSE_LOG_ENVIRONMENT:
            remaining = [item for item in original if not item.startswith(key + '=')]
            mutations.extend([remaining, remaining + [key], remaining + [key + '=changed'],
                              {**GENERATOR.environment_map(original), key: None}])
        # Duplicate a log setting specifically, independent of its source ordering.
        mutations.append(original + [next(item for item in original
                                         if item.startswith('APPFLOWY_SERVER_LOGS_TOKEN='))])
        for index, environment in enumerate(mutations):
            with self.subTest(mutation=index):
                source = copy.deepcopy(self.source)
                source['services']['appflowy_cloud']['environment'] = environment
                with self.assertRaisesRegex(ValueError, 'server-log settings changed'):
                    GENERATOR.derive(source)

    def test_parity_rejects_reintroduced_cloud_collector_endpoint_or_token(self):
        for key, value in GENERATOR.COMPOSE_LOG_ENVIRONMENT.items():
            with self.subTest(setting=key):
                stack = GENERATOR.derive(self.source)
                stack['services']['appflowy_cloud']['environment'].append(f'{key}={value}')
                with self.assertRaisesRegex(ValueError, 'configuration drift: appflowy_cloud'):
                    GENERATOR.check_parity(self.source, stack)

    def test_source_environment_defaults_cannot_reintroduce_cloud_log_settings(self):
        original_defaults = GENERATOR.source_defaults

        def defaults(name):
            result = original_defaults(name)
            if name == 'appflowy_cloud':
                result['APPFLOWY_SERVER_LOGS_UNREVIEWED'] = '${APPFLOWY_SERVER_LOGS_UNREVIEWED}'
            return result

        with patch.object(GENERATOR, 'source_defaults', side_effect=defaults):
            with self.assertRaisesRegex(ValueError, 'server-log settings changed'):
                GENERATOR.derive(self.source)

    def test_unknown_profile_requires_review_instead_of_implicit_startup(self):
        self.source['services']['ai']['profiles'] = ['ai']
        with self.assertRaisesRegex(ValueError, 'explicit Swarm adapter'):
            GENERATOR.derive(self.source)

    def test_backup_without_profile_cannot_be_accidentally_enabled(self):
        self.source['services']['appflowy_backup'].pop('profiles')
        with self.assertRaisesRegex(ValueError, 'explicit Swarm adapter'):
            GENERATOR.derive(self.source)

    def test_unknown_optional_raw_environment_file_cannot_be_silently_ignored(self):
        self.source['services']['appflowy_cloud']['env_file'].append(
            {'path': './new-runtime.env', 'required': False, 'format': 'raw'})
        with self.assertRaisesRegex(ValueError, 'explicit Swarm conversion'):
            GENERATOR.derive(self.source)

    def test_required_relative_environment_files_rebase_to_the_source_directory(self):
        service = {'env_file': ['./shared.env', {'path': './docker/service.env', 'required': True}, '/etc/service.env']}
        GENERATOR.convert_environment('service', service)
        self.assertEqual(service['env_file'], ['../shared.env', '../docker/service.env', '/etc/service.env'])

    def test_explicit_environment_values_and_unset_keys_override_source_defaults(self):
        for environment, expected in [
            ({'KEY': 'explicit'}, {'KEY': 'explicit', 'OTHER': '${OTHER}'}),
            (['KEY'], ['OTHER=${OTHER}', 'KEY']),
        ]:
            service = {'env_file': [{'path': './docker/backup/source-service.env'}], 'environment': environment}
            with patch.object(GENERATOR, 'source_defaults', return_value={'KEY': '${KEY}', 'OTHER': '${OTHER}'}):
                GENERATOR.convert_environment('service', service)
            self.assertEqual(service['environment'], expected)

    def test_parity_rejects_accidental_environment_drift(self):
        stack = GENERATOR.derive(self.source)
        stack['services']['appflowy_cloud']['environment'].append('ACCIDENTAL_SETTING=true')
        with self.assertRaisesRegex(ValueError, 'configuration drift: appflowy_cloud'):
            GENERATOR.check_parity(self.source, stack)

    def test_backup_overlay_selects_swarm_and_starts_only_after_application_readiness(self):
        source = yaml.safe_load(GENERATOR.BACKUP_SOURCE.read_text())
        overlay = GENERATOR.derive_backup(self.source, source)
        self.assertEqual(overlay['services']['appflowy_search'], source['services']['appflowy_search'])
        backup = overlay['services']['appflowy_backup']
        self.assertEqual(backup['environment']['APPFLOWY_BACKUP_DEPLOYMENT'], 'swarm')
        self.assertEqual(backup['command'], ['bootstrap'])
        self.assertEqual(backup['deploy']['replicas'], 0)
        self.assertIn('node.role == manager', backup['deploy']['placement']['constraints'])
        self.assertNotIn('profiles', backup)
        self.assertNotIn('env_file', backup)
        self.assertNotIn('depends_on', backup)
        self.assertNotIn('.:/appflowy-deployment:ro', backup['volumes'])
        self.assertIn('/api/ready', overlay['services']['appflowy_cloud']['healthcheck']['test'])
        self.assertIn('backup_work:/var/lib/appflowy-backup', backup['volumes'])
        self.assertIn('keyword_index_data:/var/lib/appflowy/keyword_index', backup['volumes'])

    def test_committed_stack_matches_current_source(self):
        result = subprocess.run(['python3', str(GENERATOR.__file__), '--check'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
