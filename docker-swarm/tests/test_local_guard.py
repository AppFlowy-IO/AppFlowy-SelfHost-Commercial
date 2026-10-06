"""Guard regressions: no Docker daemon is contacted by these tests."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('swarm_local', Path(__file__).resolve().parents[1] / 'local.py')
LOCAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCAL)


class LocalGuardTests(unittest.TestCase):
    def test_explicit_remote_context_cannot_be_hidden_by_local_host(self):
        def docker(*args):
            if args == ('context', 'show'):
                return 'remote'
            if args == ('context', 'inspect', 'remote'):
                return json.dumps([{'Endpoints': {'docker': {'Host': 'ssh://remote'}}}])
            self.fail('A daemon call escaped the endpoint guard')

        with patch.dict(os.environ, {'DOCKER_CONTEXT': 'remote', 'DOCKER_HOST': 'unix:///local.sock'}), \
                patch.object(LOCAL, 'docker', side_effect=docker):
            with self.assertRaisesRegex(SystemExit, 'local Docker socket'):
                LOCAL.local_engine()

    def test_unowned_service_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(LOCAL, 'OUT', Path(folder)), \
                patch.object(LOCAL, 'service_ids', return_value={'unrelated-service'}):
            with self.assertRaisesRegex(SystemExit, 'Refusing to modify another stack'):
                LOCAL.owned('af-swarm-local')

    def test_partial_deployment_retains_ownership_for_cleanup(self):
        created = set()

        def deploy(*args, **kwargs):
            if args[:3] == ('docker', 'stack', 'deploy'):
                created.add('created-before-error')
                raise subprocess.CalledProcessError(1, args)
            self.fail(f'Unexpected command: {args}')

        state = {'LocalNodeState': 'active', 'ControlAvailable': True, 'NodeID': 'test-node'}
        with tempfile.TemporaryDirectory() as folder, patch.object(LOCAL, 'OUT', Path(folder)), \
                patch.object(LOCAL, 'local_engine', return_value=state), \
                patch.object(LOCAL, 'stack_name', return_value='af-swarm-local'), \
                patch.object(LOCAL, 'owned', return_value=set()), \
                patch.object(LOCAL, 'service_ids', side_effect=lambda _: created.copy()), \
                patch.object(LOCAL, 'docker', return_value='test-node'), \
                patch.object(LOCAL.subprocess, 'run'), patch.object(LOCAL, 'run', side_effect=deploy):
            with self.assertRaises(subprocess.CalledProcessError):
                LOCAL.up(no_pull=True)
            owner = json.loads((Path(folder) / 'ownership.json').read_text())
            self.assertEqual(owner['service_ids'], ['created-before-error'])
            self.assertEqual(owner['stack_name'], 'af-swarm-local')


if __name__ == '__main__':
    unittest.main()
