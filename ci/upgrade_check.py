"""Upgrade a self-hosted Compose installation to its checked-out deployment files, then check it.

Run it from an installation's checkout after updating that checkout, as a self-hoster upgrades:
`git pull --ff-only`, then `python3 ci/upgrade_check.py`. The Self-hosted upgrade check workflow
reaches the team's server with a key whose forced command does exactly that. The commit the run
was started for arrives in SSH_ORIGINAL_COMMAND, and the checkout must include it.

Its output is published in public CI logs. It names services, states, images and the derived
Compose settings, never other `.env` values or container logs.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DERIVED = ("COMPOSE_PROFILES", "COMPOSE_PATH_SEPARATOR", "COMPOSE_FILE")
SWITCH = re.compile(r"APPFLOWY_[A-Z0-9_]+_PROFILE")
COMMIT = re.compile(r"[0-9a-f]{40}")
WARNING = re.compile(r'level=warning msg="((?:[^"\\]|\\.)*)"')
ROUTES = ("/api/health", "/gotrue/health", "/console", "/app")
BASE_URL = "http://127.0.0.1"
WAIT_SECONDS = 900
PULL_SECONDS = 1800
SETTLE_SECONDS = 60
SUMMARY = "=== Summary ==="


class CheckFailed(Exception):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def requested_commit(value):
    """The commit a CI run asks for, or None. Anything else is refused, never interpreted."""
    value = (value or "").strip()
    if value and not COMMIT.fullmatch(value):
        raise CheckFailed(["refusing a request that is not a full commit hash"])
    return value or None


def read_env(text):
    """The last value of each `KEY=value` line, without surrounding quotes, as Compose reads it."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.removeprefix("export ").partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def stale_settings(template, env):
    """Derived Compose settings in `.env` that differ from `deploy.env`.

    An override file appended to COMPOSE_FILE is the documented exception.
    """
    problems = []
    for key in DERIVED:
        expected, actual = template.get(key), env.get(key)
        if expected is None or actual == expected:
            continue
        if key == "COMPOSE_FILE" and actual and actual.startswith(expected + ":"):
            continue
        found = "missing" if actual is None else f"`{actual}`"
        problems.append(f".env: {key} is {found}; deploy.env has `{expected}`")
    return problems


def unstarted_profiles(env, enabled, services_with):
    """Profile switches that are set although Compose would not start their services."""
    problems = []
    for key, value in sorted(env.items()):
        if not (SWITCH.fullmatch(key) and value):
            continue
        missing = services_with(value) - enabled
        if missing:
            problems.append(f".env: {key}={value} is set, but Compose would not start "
                            f"{', '.join(sorted(missing))}; set it above COMPOSE_PROFILES")
    return problems


def compose_warnings(stderr):
    """Warning messages in Compose's stderr, in its current and its older log format."""
    messages = []
    for line in stderr.splitlines():
        match = WARNING.search(line)
        if match:
            messages.append(match.group(1).replace('\\"', '"'))
        elif line.startswith("WARN["):
            messages.append(line.partition("]")[2].strip())
    return list(dict.fromkeys(messages))


def status(container):
    """`healthy`, `running` for a container without a health check, or the state it is in."""
    state = container["State"]
    if state["Status"] != "running":
        return state["Status"]
    return state.get("Health", {}).get("Status", "running")


def by_service(containers):
    grouped = {}
    for container in containers:
        service = container["Config"]["Labels"].get("com.docker.compose.service")
        grouped.setdefault(service, []).append(container)
    return grouped


def service_problems(services, containers):
    """Services without exactly one running container that passes its health check."""
    grouped = by_service(containers)
    problems = []
    for service in sorted(services):
        rows = grouped.get(service, [])
        if len(rows) != 1:
            problems.append(f"{service}: {len(rows)} containers")
        elif status(rows[0]) not in ("running", "healthy"):
            state, cause = rows[0]["State"], ""
            if state.get("OOMKilled"):
                cause = " (out of memory)"
            elif state["Status"] != "running":
                cause = f" (exit code {state.get('ExitCode')})"
            problems.append(f"{service}: {status(rows[0])}{cause}")
    return problems


def restarted(services, before, after):
    """Services whose container restarted or was replaced between two snapshots."""
    first, second = by_service(before), by_service(after)

    def identity(rows):
        return sorted((row["Id"], row["RestartCount"]) for row in rows)

    return [f"{service}: restarted during the {SETTLE_SECONDS}-second watch"
            for service in sorted(services)
            if identity(first.get(service, [])) != identity(second.get(service, []))]


def table(services, containers, before):
    """One line per service; `(updated)` marks a container this run created."""
    grouped = by_service(containers)
    lines = [f"{'SERVICE':24} {'STATUS':10} {'RESTARTS':9} IMAGE"]
    for service in sorted(services):
        rows = grouped.get(service, [])
        if len(rows) != 1:
            lines.append(f"{service:24} {len(rows)} containers")
            continue
        row = rows[0]
        image = row["Config"]["Image"].split("@")[0]
        updated = "" if row["Id"] in before else "  (updated)"
        lines.append(f"{service:24} {status(row):10} {row['RestartCount']:<9} {image}{updated}")
    return lines


def repositories(references):
    """Image repositories of Compose image references, without tag or digest."""
    names = set()
    for reference in references:
        head, _, last = reference.split("@")[0].rpartition("/")
        name = last.split(":")[0]
        names.add(f"{head}/{name}" if head else name)
    return names


def unused_images(images, deployment_repositories, used):
    """IDs of this deployment's images that no container on the host uses."""
    return sorted({image["ID"] for image in images
                   if image["Repository"] in deployment_repositories and image["ID"] not in used})


def run(*args, timeout=120):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def services(*flags):
    result = run("docker", "compose", *flags, "config", "--services")
    if result.returncode != 0:
        raise CheckFailed(["docker compose config failed; run it on the server to see why"])
    return set(result.stdout.split())


def snapshot():
    ids = run("docker", "compose", "ps", "--all", "--quiet").stdout.split()
    return json.loads(run("docker", "inspect", *ids).stdout or "[]") if ids else []


def describe_checkout(commit):
    head = run("git", "log", "-1", "--format=%h %s").stdout.strip()
    if commit and run("git", "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
        raise CheckFailed([f"the checkout ({head}) does not include {commit[:12]}"])
    version = run("docker", "compose", "version", "--short").stdout.strip()
    free = shutil.disk_usage("/").free / 2**30
    return [f"Checkout: {head}", f"Docker Compose {version}; {free:.1f} GiB free on /"]


def configuration():
    """The services Compose will start, once `.env` matches the deployment files."""
    if not (ROOT / ".env").is_file():
        raise CheckFailed(["no .env in the repository root"])
    template = read_env((ROOT / "deploy.env").read_text())
    env = read_env((ROOT / ".env").read_text())
    config = run("docker", "compose", "config", "--quiet")
    if config.returncode != 0:
        raise CheckFailed(["docker compose config failed; run it on the server to see why"])
    enabled = services()
    problems = stale_settings(template, env)
    problems += [f"Compose: {message}" for message in compose_warnings(config.stderr)]
    problems += unstarted_profiles(env, enabled, lambda profile: services("--profile", profile))
    if problems:
        raise CheckFailed(problems)
    return enabled


def upgrade():
    """Pull the pinned images and start every service, as a self-hoster upgrades."""
    steps = (("pull", "--quiet"), ("up", "--detach", "--wait", "--wait-timeout", str(WAIT_SECONDS)))
    for step in steps:
        print("$ docker compose " + " ".join(step))
        try:
            code = subprocess.run(["docker", "compose", *step], cwd=ROOT,
                                  timeout=PULL_SECONDS + WAIT_SECONDS).returncode
        except subprocess.TimeoutExpired:
            return [f"docker compose {step[0]} did not finish in time"]
        if code != 0:
            return [f"docker compose {step[0]} failed (exit code {code})"]
    return []


def watch(enabled):
    """The containers after the settle period, and the services that failed or restarted."""
    print(f"Watching {len(enabled)} services for {SETTLE_SECONDS} seconds")
    first = snapshot()
    time.sleep(SETTLE_SECONDS)
    second = snapshot()
    return second, service_problems(enabled, second) + restarted(enabled, first, second)


def route_problems():
    """Routes through the installation's Nginx that do not answer 200."""
    opener = urllib.request.build_opener(NoRedirect)
    problems = []
    for path in ROUTES:
        try:
            with opener.open(BASE_URL + path, timeout=15) as response:
                code = response.status
        except urllib.error.HTTPError as error:
            code = error.code
        except OSError as error:
            code = type(error).__name__
        if code != 200:
            problems.append(f"Nginx: {path} answered {code}")
    return problems


def remove_unused_images():
    """Remove older images of this deployment, so each release does not add to the disk."""
    references = run("docker", "compose", "config", "--images").stdout.split()
    listing = run("docker", "image", "ls", "--no-trunc", "--format", "json").stdout
    images = [json.loads(line) for line in listing.splitlines() if line.strip()]
    containers = run("docker", "ps", "--all", "--quiet").stdout.split()
    used = set()
    if containers:
        inspected = run("docker", "inspect", "--format", "{{.Image}}", *containers)
        used = set(inspected.stdout.split())
    stale = unused_images(images, repositories(references), used)
    removed = 0
    if stale:
        result = run("docker", "image", "rm", *stale, timeout=600)
        removed = len(stale) - result.stderr.count("Error response from daemon")
    free = shutil.disk_usage("/").free / 2**30
    images_word = "image" if removed == 1 else "images"
    return f"Cleanup: removed {removed} unused {images_word}; {free:.1f} GiB free"


def report(summary, problems):
    print(SUMMARY)
    print("\n".join(summary))
    if not problems:
        print("Result: every service is up")
        return 0
    print(f"Result: {len(problems)} problem{'' if len(problems) == 1 else 's'}")
    print("\n".join(f"- {problem}" for problem in problems))
    return 1


def main():
    sys.stdout.reconfigure(line_buffering=True)
    summary = []
    try:
        commit = requested_commit(os.environ.get("SSH_ORIGINAL_COMMAND"))
        summary += describe_checkout(commit)
        enabled = configuration()
    except CheckFailed as failure:
        unchanged = "No image was pulled and no service was restarted."
        return report(summary + [unchanged], failure.problems)
    before = {container["Id"] for container in snapshot()}
    problems = upgrade()
    containers, more = watch(enabled)
    problems += more + route_problems()
    summary += table(enabled, containers, before)
    if not problems:
        summary.append(remove_unused_images())
    return report(summary, problems)


if __name__ == "__main__":
    sys.exit(main())
