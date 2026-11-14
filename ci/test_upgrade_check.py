"""The self-hosted upgrade check reports an outdated `.env` and services that do not come up."""
import unittest

import upgrade_check as check

TEMPLATE = check.read_env((check.ROOT / "deploy.env").read_text())
OLD_PROFILES = "${APPFLOWY_BACKUP_PROFILE}"


def container(service, state="running", health=None, restarts=0, ident=None, **details):
    state = {"Status": state, "ExitCode": 0, "OOMKilled": False, **details}
    if health:
        state["Health"] = {"Status": health}
    return {"Id": ident or service, "RestartCount": restarts, "State": state,
            "Config": {"Image": f"appflowyinc/{service}:1.0@sha256:{'a' * 64}",
                       "Labels": {"com.docker.compose.service": service}}}


class UpgradeCheckTest(unittest.TestCase):
    def test_only_a_full_commit_hash_is_accepted(self):
        commit = "0123456789abcdef0123456789abcdef01234567"
        self.assertEqual(check.requested_commit(f" {commit}\n"), commit)
        self.assertIsNone(check.requested_commit(None))
        self.assertIsNone(check.requested_commit(""))
        for refused in ("HEAD", commit[:12], commit.upper(), f"{commit}; rm -rf ~", "bash"):
            with self.subTest(refused=refused), self.assertRaises(check.CheckFailed):
                check.requested_commit(refused)

    def test_env_values_are_read_as_compose_reads_them(self):
        env = check.read_env("# comment\n\nA=1\nexport B='two'\nC=\"three\"\nA=4\nnot a setting\n")
        self.assertEqual(env, {"A": "4", "B": "two", "C": "three"})

    def test_an_env_copied_from_the_current_template_passes(self):
        env = dict(TEMPLATE, APPFLOWY_BACKUP_PROFILE="backup")
        env["COMPOSE_FILE"] = TEMPLATE["COMPOSE_FILE"] + ":docker-compose.local.yml"
        self.assertEqual(check.stale_settings(TEMPLATE, env), [])

    def test_an_env_older_than_the_template_is_reported(self):
        env = dict(TEMPLATE, COMPOSE_PROFILES=OLD_PROFILES)
        del env["COMPOSE_FILE"]
        problems = check.stale_settings(TEMPLATE, env)
        self.assertEqual(len(problems), 2)
        self.assertIn(f"COMPOSE_PROFILES is `{OLD_PROFILES}`", problems[0])
        self.assertIn("COMPOSE_FILE is missing", problems[1])

    def test_a_profile_switch_compose_ignores_is_reported(self):
        env = {"APPFLOWY_BACKUP_PROFILE": "", "APPFLOWY_SERVER_LOGS_PROFILE": "server-logs"}
        with_profile = {"server-logs": {"appflowy_cloud", "appflowy_log_collector"}}
        problems = check.unstarted_profiles(env, {"appflowy_cloud"}, with_profile.__getitem__)
        self.assertEqual(len(problems), 1)
        self.assertIn("would not start appflowy_log_collector", problems[0])
        enabled = {"appflowy_cloud", "appflowy_log_collector"}
        self.assertEqual(check.unstarted_profiles(env, enabled, with_profile.__getitem__), [])

    def test_compose_warnings_are_read_in_both_log_formats(self):
        unset = ('time="2026-11-14T01:15:19Z" level=warning msg="The \\"SMTP_PORT\\" variable is '
                 'not set. Defaulting to a blank string."\n')
        stderr = unset + unset + "WARN[0000] Found orphan containers\nPulling images\n"
        self.assertEqual(check.compose_warnings(stderr), [
            'The "SMTP_PORT" variable is not set. Defaulting to a blank string.',
            "Found orphan containers",
        ])

    def test_each_service_needs_one_running_container_that_passes_its_health_check(self):
        containers = [
            container("appflowy_cloud", health="healthy"),
            container("redis"),
            container("ai", health="starting"),
            container("appflowy_worker", state="exited", ExitCode=137, OOMKilled=True),
            container("appflowy_search", state="restarting", ExitCode=1),
            container("nginx", ident="nginx-1"),
            container("nginx", ident="nginx-2"),
        ]
        services = {"appflowy_cloud", "redis", "ai", "appflowy_worker", "appflowy_search",
                    "nginx", "gotrue"}
        self.assertEqual(check.service_problems(services, containers), [
            "ai: starting",
            "appflowy_search: restarting (exit code 1)",
            "appflowy_worker: exited (out of memory)",
            "gotrue: 0 containers",
            "nginx: 2 containers",
        ])

    def test_a_restart_or_replacement_during_the_watch_is_reported(self):
        before = [container("redis"), container("nginx"), container("gotrue")]
        after = [container("redis"), container("nginx", restarts=1),
                 container("gotrue", ident="replacement")]
        self.assertEqual(check.restarted({"redis", "nginx", "gotrue"}, before, after), [
            "gotrue: restarted during the 60-second watch",
            "nginx: restarted during the 60-second watch",
        ])

    def test_the_table_marks_containers_this_run_created(self):
        containers = [container("appflowy_cloud", health="healthy", ident="new"),
                      container("redis", ident="old")]
        lines = check.table({"appflowy_cloud", "redis"}, containers, before={"old"})
        self.assertTrue(lines[1].startswith("appflowy_cloud"))
        self.assertTrue(lines[1].endswith("appflowyinc/appflowy_cloud:1.0  (updated)"))
        self.assertTrue(lines[2].endswith("appflowyinc/redis:1.0"))


if __name__ == "__main__":
    unittest.main()
