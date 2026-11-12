"""Read-only Compose contracts for the optional server-log reader."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from images import ROOT, clean_environment


class ServerLogsConfigurationTests(unittest.TestCase):
    def render(self, backup=False, logs=False, *, token="", project="server-logs-contract",
               socket="/var/run/docker.sock", ambient_url=None):
        # Never read a developer's .env or inherit application credentials.
        with tempfile.TemporaryDirectory(prefix="server-logs-compose-") as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text((ROOT / "deploy.env").read_text())
            os.chmod(env_file, 0o600)
            env = {
                **clean_environment(),
                "APPFLOWY_BACKUP_PROFILE": "backup" if backup else "",
                "APPFLOWY_SERVER_LOGS_PROFILE": "server-logs" if logs else "",
                "APPFLOWY_SERVER_LOGS_IMAGE": "appflowyinc/appflowy_log_collector:contract-check",
                "APPFLOWY_SERVER_LOGS_DOCKER_SOCKET": socket,
            }
            if token is not None:
                env["APPFLOWY_SERVER_LOGS_TOKEN"] = token
            if ambient_url is not None:
                env["APPFLOWY_SERVER_LOGS_URL"] = ambient_url
            command = ["docker", "compose", "--env-file", str(env_file)]
            if project:
                command += ["--project-name", project]
            result = subprocess.run(command + ["config", "--format", "json"], cwd=ROOT,
                                    env=env, capture_output=True, text=True, timeout=30)
            # Compose diagnostics can contain rendered credentials; don't include them in failures.
            self.assertEqual(result.returncode, 0, "Read-only Compose configuration failed")
            return json.loads(result.stdout)

    def test_profiles_are_independent_and_preserve_existing_storage(self):
        configurations = {}
        for backup, logs in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(backup=backup, logs=logs):
                result = self.render(backup, logs)
                configurations[backup, logs] = result
                self.assertEqual("appflowy_backup" in result["services"], backup)
                self.assertEqual("appflowy_log_collector" in result["services"], logs)
                cloud = result["services"]["appflowy_cloud"]
                self.assertEqual(cloud["environment"]["APPFLOWY_SERVER_LOGS_URL"],
                                 "http://appflowy_log_collector:8088" if logs else "")
                self.assertNotIn("appflowy_log_collector", cloud.get("depends_on", {}))
        for backup in (False, True):
            self.assertEqual(configurations[backup, False].get("volumes"),
                             configurations[backup, True].get("volumes"))
            self.assertEqual(configurations[backup, False].get("name"),
                             configurations[backup, True].get("name"))

    def test_reader_is_internal_and_keeps_docker_access_out_of_cloud_and_admin(self):
        token = "test-only-collector-token-" + "0" * 40
        result = self.render(logs=True, token=token)
        collector = result["services"]["appflowy_log_collector"]
        self.assertFalse(collector.get("ports"))
        self.assertTrue(collector["read_only"])
        self.assertEqual(collector["user"], "0:0")
        self.assertEqual(collector["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", collector["security_opt"])
        self.assertGreater(collector["pids_limit"], 0)
        self.assertLessEqual(collector["pids_limit"], 64)
        self.assertGreater(int(collector["mem_limit"]), 0)
        self.assertLessEqual(int(collector["mem_limit"]), 256 * 1024 * 1024)
        self.assertGreater(float(collector["cpus"]), 0)
        self.assertLessEqual(float(collector["cpus"]), 0.5)
        self.assertEqual(collector["environment"]["APPFLOWY_SERVER_LOGS_PROJECT"], result["name"])
        self.assertEqual(collector["environment"]["APPFLOWY_SERVER_LOGS_TOKEN"], token)
        self.assertEqual(result["services"]["appflowy_cloud"]["environment"]
                         ["APPFLOWY_SERVER_LOGS_TOKEN"], token)
        self.assertEqual(len(collector["volumes"]), 1)
        mount = collector["volumes"][0]
        self.assertEqual(mount["target"], "/var/run/docker.sock")
        self.assertTrue(mount["read_only"])
        self.assertFalse(mount.get("bind", {}).get("create_host_path", False))
        for service in ("appflowy_cloud", "admin_frontend"):
            self.assertFalse(any(volume.get("target") == "/var/run/docker.sock"
                                 for volume in result["services"][service].get("volumes", [])))

    def test_disabled_reader_needs_no_token_and_does_not_forward_one(self):
        tokens = {
            "unset": None,
            "empty": "",
            "malformed": "test-only-invalid-token\r\n",
            "leftover_valid": "test-only-unused-token-" + "1" * 40,
        }
        for token_state, token in tokens.items():
            with self.subTest(token_state=token_state):
                result = self.render(token=token,
                                     ambient_url="http://unused-privacy-canary.invalid/private")
                cloud = result["services"]["appflowy_cloud"]["environment"]
                self.assertEqual(cloud["APPFLOWY_SERVER_LOGS_URL"], "")
                self.assertEqual(cloud["APPFLOWY_SERVER_LOGS_TOKEN"], "")
                self.assertNotIn("appflowy_log_collector", result["services"])
                self.assertFalse(any(volume.get("target") == "/var/run/docker.sock"
                                     for service in result["services"].values()
                                     for volume in service.get("volumes", [])))

    def test_project_scope_and_rootless_socket_follow_the_operator_configuration(self):
        for project in (None, "existing-production-project"):
            with self.subTest(project=project):
                result = self.render(logs=True, project=project,
                                     socket="/run/user/1000/docker.sock")
                collector = result["services"]["appflowy_log_collector"]
                self.assertEqual(collector["environment"]["APPFLOWY_SERVER_LOGS_PROJECT"],
                                 result["name"])
                self.assertEqual(collector["volumes"][0]["source"], "/run/user/1000/docker.sock")
                self.assertEqual(collector["environment"]["APPFLOWY_SERVER_LOGS_DOCKER_SOCKET"],
                                 "/var/run/docker.sock")


if __name__ == "__main__":
    unittest.main()
