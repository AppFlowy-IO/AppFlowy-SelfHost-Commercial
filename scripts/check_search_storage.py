#!/usr/bin/env python3
"""Read-only Docker checks for Search's current index mount; never print service secrets."""

import argparse
import json
import posixpath
import re
import subprocess
import sys


DEFAULT_INDEX_DIR = "/tmp/appflowy_keyword_index"
INDEX_ENV = "APPFLOWY_KEYWORD_INDEX_DIR"
MEMORY_FILESYSTEMS = {"tmpfs", "ramfs"}
OVERLAY_FILESYSTEMS = {"overlay", "aufs", "fuse.overlayfs"}


class CheckUnavailable(Exception):
    """A safe diagnostic cannot be completed from the available evidence."""


def run(arguments):
    """Capture privately: Docker errors and config output can contain credentials."""
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckUnavailable("Docker check could not complete; check Docker access.") from error
    if result.returncode:
        raise CheckUnavailable("Docker check failed; check the running container and Compose setup.")
    return result.stdout


def covers(parent, child):
    parent = posixpath.normpath(parent)
    child = posixpath.normpath(child)
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def longest_mount(mounts, path, key):
    matches = [mount for mount in mounts if covers(mount[key], path)]
    return max(matches, key=lambda mount: len(mount[key]), default=None)


def unescape_mount(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)


def mountinfo_rows(content):
    rows = []
    for line in content.splitlines():
        before, separator, after = line.partition(" - ")
        fields, filesystem = before.split(), after.split()
        if not separator or len(fields) < 6 or len(filesystem) < 3:
            raise CheckUnavailable("The container mount table could not be read.")
        rows.append({
            "root": unescape_mount(fields[3]),
            "target": unescape_mount(fields[4]),
            "read_only": "ro" in fields[5].split(","),
            "filesystem": filesystem[0],
        })
    return rows


def index_directory(environment):
    if isinstance(environment, list):
        environment = dict(entry.split("=", 1) for entry in environment if "=" in entry)
    return environment.get(INDEX_ENV, DEFAULT_INDEX_DIR)


def compose_reuses_mount(config, mount, path, running_index_dir):
    service = config.get("services", {}).get("appflowy_search", {})
    if index_directory(service.get("environment", {})) != running_index_dir:
        return False
    configured = longest_mount(service.get("volumes", []), path, "target")
    if not configured or configured.get("type") != mount.get("Type"):
        return False
    if configured["target"] != mount["Destination"]:
        return False
    if configured.get("read_only", False):
        return False
    if configured.get("volume", {}).get("subpath"):
        return None  # The compact inspect view cannot verify Docker volume subpath selection.
    source = configured.get("source")
    if not source:  # Anonymous volumes do not establish a stable deployment mapping.
        return False
    if mount["Type"] == "volume":
        volume = config.get("volumes", {}).get(source, {})
        expected_name = volume.get("name")
        if not expected_name:
            return None
        return expected_name == mount.get("Name")
    return source == mount.get("Source")


def evaluate(container, canonical_path, mountinfo, compose_config=None):
    """Keep mount evidence separate from retaining the same mapping on replacement."""
    if not canonical_path.startswith("/"):
        raise CheckUnavailable("The configured index directory could not be resolved.")
    configured_path = index_directory(container.get("env", []))
    report = {
        "status": "unknown",
        "configured_index_directory": configured_path,
        "resolved_index_directory": canonical_path,
        "mount": None,
        "reused_by_current_compose": None,
        "reason": "Storage could not be verified.",
    }
    actual = longest_mount(container.get("mounts", []), canonical_path, "Destination")
    filesystem = longest_mount(mountinfo_rows(mountinfo), canonical_path, "target")
    if actual:
        report["mount"] = {
            "type": actual.get("Type"),
            "destination": actual["Destination"],
            "volume_name": actual.get("Name"),
            "read_only": not actual.get("RW", False) or bool(filesystem and filesystem["read_only"]),
            "filesystem": filesystem["filesystem"] if filesystem else None,
        }
    if not filesystem:
        report["reason"] = "No filesystem evidence covers the resolved index directory."
    elif filesystem["filesystem"] in MEMORY_FILESYSTEMS:
        report["status"] = "ephemeral"
        report["reason"] = "The checked directory is on memory storage."
    elif "kubernetes.io~empty-dir" in filesystem["root"]:
        report["status"] = "ephemeral"
        report["reason"] = "The index is in a Kubernetes emptyDir, which is removed with its pod."
    elif not actual:
        report["status"] = "ephemeral"
        report["reason"] = "No Docker volume or bind mount covers the resolved index directory."
    elif filesystem["filesystem"] in OVERLAY_FILESYSTEMS:
        report["reason"] = "An external overlay filesystem backs the directory; verify its storage lifetime."
    elif actual.get("Type") not in {"volume", "bind"}:
        report["reason"] = "The Docker mount is not a recognized external storage mount."
    elif not actual.get("RW", False) or filesystem["read_only"]:
        report["reason"] = "The index mount is read-only; Search requires writable storage."
    elif any(entry.startswith("KUBERNETES_SERVICE_HOST=") for entry in container.get("env", [])):
        report["reason"] = "Verify the Kubernetes volume and retention policy with the cluster administrator."
    elif any(covers(path, filesystem["root"]) for path in ("/tmp", "/var/tmp", "/run")):
        report["reason"] = "The mount comes from a temporary host directory; verify its retention."
    else:
        report["status"] = "external_mount"
        report["reason"] = (
            "The checked directory uses an external disk mount. This does not verify host durability, "
            "backups, free space, or index health."
        )
    if actual and compose_config is not None:
        report["reused_by_current_compose"] = compose_reuses_mount(
            compose_config, actual, canonical_path, configured_path
        )
        if report["reused_by_current_compose"] is False:
            report["reason"] += " The current Compose configuration does not reuse this index mapping."
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--container",
        help="Check one container; Compose mapping reuse remains unverified with this option.",
    )
    parser.add_argument("--env-file", help="Deployment environment file passed to Docker Compose.")
    parser.add_argument("--project-name", help="Existing Compose project name.")
    parser.add_argument("--compose-file", action="append", default=[], help="Compose file; repeat for overrides.")
    parser.add_argument(
        "--index-directory",
        help="Inspect this active index directory from the Search panel; default is the configured root.",
    )
    args = parser.parse_args()
    if args.container and (args.env_file or args.project_name or args.compose_file):
        parser.error("Use --container alone, or Compose options to verify the deployment mapping.")
    try:
        config = None
        container_id = args.container
        if not container_id:
            compose = ["docker", "compose"]
            if args.env_file:
                compose.extend(["--env-file", args.env_file])
            if args.project_name:
                compose.extend(["--project-name", args.project_name])
            for filename in args.compose_file:
                compose.extend(["--file", filename])
            containers = run(compose + ["ps", "--all", "--quiet", "appflowy_search"]).split()
            if len(containers) != 1:
                raise CheckUnavailable("Expected exactly one Search container in this Compose project.")
            container_id = containers[0]
            config = json.loads(run(compose + ["config", "--format", "json"]))
        # Never emit full inspect/config results, environment variables, or Docker stderr.
        template = ('{"running":{{json .State.Running}},"env":{{json .Config.Env}},'
                    '"mounts":{{json .Mounts}}}')
        container = json.loads(run(["docker", "inspect", "--type", "container", "--format", template, container_id]))
        if not container["running"]:
            raise CheckUnavailable("Search must be running to resolve its current index directory.")
        index_dir = index_directory(container["env"])
        selected_dir = args.index_directory or index_dir
        canonical = run(["docker", "exec", container_id, "readlink", "-e", "--", selected_dir]).rstrip("\n")
        mountinfo = run(["docker", "exec", container_id, "cat", "/proc/self/mountinfo"])
        report = evaluate(container, canonical, mountinfo, config)
        report["checked_index_directory"] = selected_dir
        report["check_scope"] = "selected_directory" if args.index_directory else "configured_root"
    except (CheckUnavailable, ValueError, KeyError, TypeError) as error:
        reason = str(error) if isinstance(error, CheckUnavailable) else "Docker returned incomplete check data."
        report = {"status": "unknown", "reason": reason}
    print(json.dumps(report, indent=2))
    if report["status"] == "ephemeral" or report.get("reused_by_current_compose") is False:
        return 1
    return 0 if report["status"] == "external_mount" and report.get("reused_by_current_compose") else 2


if __name__ == "__main__":
    sys.exit(main())
