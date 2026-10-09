"""Storage evidence regressions; no Docker daemon or deployment needed."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("storage", Path(__file__).parents[1] / "check_search_storage.py")
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)

INDEX = "/var/lib/appflowy/keyword_index"
ROOT = "21 1 0:12 / / rw - overlay overlay rw\n"
DISK = f"22 21 8:1 /var/lib/docker/volumes/project_keyword_index_data/_data {INDEX} rw - ext4 /dev/sda1 rw\n"


def container(**mount_changes):
    mount = {"Type": "volume", "Name": "project_keyword_index_data", "Destination": INDEX, "RW": True}
    mount.update(mount_changes)
    return {"env": [f"{storage.INDEX_ENV}={INDEX}", "SECRET=do-not-print"], "mounts": [mount]}


def compose():
    return {
        "services": {"appflowy_search": {
            "environment": {storage.INDEX_ENV: INDEX},
            "volumes": [{"type": "volume", "source": "keyword_index_data", "target": INDEX}],
        }},
        "volumes": {"keyword_index_data": {"name": "project_keyword_index_data"}},
    }


class StorageTests(unittest.TestCase):
    def test_named_volume_and_current_compose_agree(self):
        report = storage.evaluate(container(), INDEX + "/v2", ROOT + DISK, compose())
        self.assertEqual(report["status"], "external_mount")
        self.assertTrue(report["reused_by_current_compose"])
        self.assertNotIn("SECRET", str(report))
        self.assertNotIn("do-not-print", str(report))
        self.assertNotIn("/var/lib/docker/", str(report))

    def test_recreated_project_would_use_a_different_volume(self):
        config = compose()
        config["volumes"]["keyword_index_data"]["name"] = "newproject_keyword_index_data"
        report = storage.evaluate(container(), INDEX, ROOT + DISK, config)
        self.assertEqual(report["status"], "external_mount")
        self.assertFalse(report["reused_by_current_compose"])

    def test_missing_and_sibling_mounts_do_not_cover_index(self):
        for mounts in ([], [{"Destination": INDEX + "-old", "Type": "volume", "RW": True}]):
            data = container()
            data["mounts"] = mounts
            report = storage.evaluate(data, INDEX, ROOT)
            self.assertEqual(report["status"], "ephemeral")

    def test_symlink_resolves_outside_configured_volume(self):
        report = storage.evaluate(container(), "/tmp/index", ROOT + DISK, compose())
        self.assertEqual(report["status"], "ephemeral")

    def test_nested_tmpfs_overrides_outer_disk(self):
        info = ROOT + DISK + f"23 22 0:33 / {INDEX}/v2 rw - tmpfs tmpfs rw\n"
        report = storage.evaluate(container(), INDEX + "/v2", info)
        self.assertEqual(report["status"], "ephemeral")

    def test_external_overlay_lifetime_is_unknown_but_container_layer_is_ephemeral(self):
        info = ROOT + f"22 21 0:33 /srv/persisted {INDEX} rw - overlay overlay rw\n"
        report = storage.evaluate(container(Type="bind", Source="/srv/persisted"), INDEX, info)
        self.assertEqual(report["status"], "unknown")
        report = storage.evaluate({"env": [], "mounts": []}, "/tmp/index", ROOT)
        self.assertEqual(report["status"], "ephemeral")

    def test_empty_dir_on_disk_is_still_ephemeral(self):
        info = ROOT + f"22 21 8:1 /var/lib/kubelet/pods/id/volumes/kubernetes.io~empty-dir/index {INDEX} rw - ext4 /dev/sda1 rw\n"
        report = storage.evaluate(container(), INDEX, info)
        self.assertEqual(report["status"], "ephemeral")

    def test_kubernetes_mount_does_not_prove_pvc_retention(self):
        data = container()
        data["env"].append("KUBERNETES_SERVICE_HOST=10.0.0.1")
        report = storage.evaluate(data, INDEX, ROOT + DISK)
        self.assertEqual(report["status"], "unknown")

    def test_host_temporary_directory_requires_retention_check(self):
        info = ROOT + f"22 21 8:1 /tmp/search-data {INDEX} rw - ext4 /dev/sda1 rw\n"
        report = storage.evaluate(container(Type="bind", Source="/tmp/search-data"), INDEX, info)
        self.assertEqual(report["status"], "unknown")

    def test_read_only_filesystem_is_not_ready(self):
        report = storage.evaluate(container(), INDEX, ROOT + DISK.replace(" rw - ext4", " ro - ext4"))
        self.assertEqual(report["status"], "unknown")
        self.assertIn("read-only", report["reason"])

    def test_anonymous_volume_has_no_reusable_compose_mapping(self):
        config = compose()
        del config["services"]["appflowy_search"]["volumes"][0]["source"]
        report = storage.evaluate(container(), INDEX, ROOT + DISK, config)
        self.assertFalse(report["reused_by_current_compose"])

    def test_running_env_must_match_rendered_configuration(self):
        config = compose()
        config["services"]["appflowy_search"]["environment"][storage.INDEX_ENV] = INDEX + "/restore"
        report = storage.evaluate(container(), INDEX, ROOT + DISK, config)
        self.assertFalse(report["reused_by_current_compose"])

    def test_escaped_mount_path_and_nested_restore_directory(self):
        info = ROOT + DISK.replace(INDEX, INDEX.replace("keyword_index", "keyword\\040index"))
        path = INDEX.replace("keyword_index", "keyword index")
        report = storage.evaluate(container(Destination=path), path + "/restore/one", info)
        self.assertEqual(report["status"], "external_mount")

    def test_unavailable_mount_table_is_unknown(self):
        report = storage.evaluate(container(), INDEX, "")
        self.assertEqual(report["status"], "unknown")

    def test_bind_mount_must_match_actual_host_source(self):
        config = compose()
        config["services"]["appflowy_search"]["volumes"][0].update(type="bind", source="/srv/search")
        good = storage.evaluate(container(Type="bind", Source="/srv/search"), INDEX, ROOT + DISK, config)
        wrong = storage.evaluate(container(Type="bind", Source="/srv/other"), INDEX, ROOT + DISK, config)
        self.assertTrue(good["reused_by_current_compose"])
        self.assertFalse(wrong["reused_by_current_compose"])

    def test_same_volume_at_different_destination_is_not_the_same_mapping(self):
        config = compose()
        config["services"]["appflowy_search"]["volumes"][0]["target"] = INDEX + "/v2"
        report = storage.evaluate(container(), INDEX + "/v2", ROOT + DISK, config)
        self.assertFalse(report["reused_by_current_compose"])

    def test_volume_subpath_selection_is_unverified_not_a_claimed_mismatch(self):
        config = compose()
        config["services"]["appflowy_search"]["volumes"][0]["volume"] = {"subpath": "selected"}
        report = storage.evaluate(container(), INDEX, ROOT + DISK, config)
        self.assertIsNone(report["reused_by_current_compose"])
        self.assertNotIn("does not reuse", report["reason"])

    def test_command_failure_does_not_expose_stderr_or_environment(self):
        result = type("Result", (), {"returncode": 1, "stdout": "SECRET=one", "stderr": "password=two"})()
        with patch.object(storage.subprocess, "run", return_value=result):
            with self.assertRaises(storage.CheckUnavailable) as raised:
                storage.run(["docker", "compose", "config"])
        self.assertNotIn("SECRET", str(raised.exception))
        self.assertNotIn("password", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
