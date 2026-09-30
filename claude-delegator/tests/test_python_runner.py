import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("claude_runner", ROOT / "scripts" / "invoke-claude.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
REAL_POPEN = subprocess.Popen


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claude-python-tests-")
        self.root = Path(self.temp.name).resolve()
        self.children, self.commands = [], []
        self.auth = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "pro",
                     "email": "do-not-persist@example.invalid"}

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                runner.stop_child(child)
        self.temp.cleanup()

    def preflight(self, command):
        if command[1:] == ["--help"]:
            return " ".join(runner.REQUIRED_FLAGS)
        if command[1:] == ["--version"]:
            return "2.1.263 (offline fixture)"
        if command[1:] == ["auth", "status", "--json"]:
            return json.dumps(self.auth)
        raise AssertionError(command)

    def popen(self, command, **kwargs):
        if command[0] == sys.executable and "--print" in command:
            self.commands.append(command)
            child = REAL_POPEN([sys.executable, str(ROOT / "tests" / "fake_claude.py"), *command[1:]], **kwargs)
            self.children.append(child)
            return child
        return REAL_POPEN(command, **kwargs)

    def invoke(self, mode="success", extra=(), name="run"):
        directory = self.root / name
        args = runner.arguments(["--prompt", "Review the bounded test objective", "--working-directory", str(self.root),
                                 "--run-directory", str(directory), *extra])
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(runner, "resolve_claude", return_value=sys.executable), \
             patch.object(runner, "capture", side_effect=self.preflight), \
             patch.object(runner.subprocess, "Popen", side_effect=self.popen), \
             patch.dict(os.environ, {"CLAUDE_PY_TEST_MODE": mode}), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = runner.run(args)
        meta = json.loads((directory / "metadata.json").read_text())
        result = json.loads((directory / "result.json").read_text())
        return code, meta, result, stdout.getvalue()

    def git(self, root, *args):
        result = subprocess.run(["git", "-c", f"core.hooksPath={os.devnull}", "-C", str(root), *args], capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", "replace"))
        return result.stdout

    def repository(self, name="repo"):
        repo = self.root / name
        repo.mkdir()
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Offline Test")
        self.git(repo, "config", "core.autocrlf", "false")
        (repo / "a.txt").write_bytes(b"base\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "base")
        return repo, self.git(repo, "rev-parse", "HEAD").decode().strip()

    def test_bounded_defaults_and_safety(self):
        code, meta, result, out = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(result["review_complete"])
        self.assertEqual(meta["model"], "fable")
        self.assertEqual(meta["effort"], "high")
        self.assertTrue(meta["sandbox_cleanup_succeeded"])
        cmd = self.commands[0]
        for flag in ("--tools=", "--disable-slash-commands", "--setting-sources=", "--strict-mcp-config", "--no-chrome", "--no-session-persistence"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "dontAsk")
        self.assertNotIn("--max-budget-usd", cmd)
        self.assertNotIn("--max-turns", cmd)
        self.assertNotIn("do-not-persist", out)
        self.assertIn("CLAUDE_DELEGATION_METADATA=", out)

    def test_collab_uses_neutral_prompt_and_existing_safety(self):
        code, meta, result, out = self.invoke("collab_success", ["--collab"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["wrapper_version"], "8.1.0")
        self.assertEqual(meta["model"], "fable")
        self.assertEqual(meta["effort"], "high")
        self.assertEqual(meta["review_scope"], "bounded-collab")
        self.assertEqual(meta["response_protocol"], "collab-turn-v1")
        self.assertEqual(meta["input_transport"], "prompt-only-no-tools")
        self.assertEqual(meta["status"], "success_collab")
        self.assertEqual(meta["completion_marker"], "COLLAB_TURN_COMPLETE")
        self.assertTrue(result["review_complete"])
        self.assertIn("Codex should execute the next step", out)
        command = self.commands[0]
        for flag in ("--tools=", "--disable-slash-commands", "--setting-sources=", "--strict-mcp-config", "--no-chrome", "--no-session-persistence"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
        self.assertNotIn("--max-budget-usd", command)

    def test_collab_incomplete_responses_fail(self):
        expected = {"collab_incomplete": "collab_incomplete", "collab_missing": "collab_incomplete",
                    "collab_wrong_marker": "collab_incomplete", "collab_trailer": "collab_incomplete",
                    "collab_marker_only": "collab_empty", "collab_zero_usage": "collab_no_model_usage"}
        for mode, status in expected.items():
            with self.subTest(mode=mode):
                code, meta, result, out = self.invoke(mode, ["--collab"], name=mode)
                self.assertEqual(code, 1)
                self.assertEqual(meta["status"], status)
                self.assertFalse(result["review_complete"])
                self.assertIn("<incomplete_claude_collab>", out)
                self.assertNotIn("<incomplete_claude_review>", out)

    def test_collab_rejects_repository_switches_before_claude(self):
        for index, switches in enumerate((("--base-revision", "HEAD", "--head-revision", "HEAD"),
                                          ("--review-working-tree",), ("--base-revision", ""))):
            with self.subTest(switches=switches):
                code, meta, result, _ = self.invoke(extra=["--collab", *switches], name=f"invalid-collab-{index}")
                self.assertEqual(code, 1)
                self.assertEqual(meta["status"], "preflight_error")
                self.assertFalse(meta["claude_start_attempted"])
                self.assertFalse(result["review_complete"])
        self.assertFalse(self.commands)

    def test_budget_override_switches(self):
        subscription = {"authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "pro"}
        self.assertFalse(runner.budget_info(subscription, .5, {})["budget_cap_applied"])
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_FOUNDRY"):
            self.assertTrue(runner.budget_info(subscription, .5, {key: "secret-or-enabled"})["budget_cap_applied"])
        for value in ("0", "false", "NO", "off"):
            self.assertFalse(runner.budget_info(subscription, .5, {"CLAUDE_CODE_USE_VERTEX": value})["budget_cap_applied"])

    def test_api_budget_model_and_raw_json(self):
        self.auth.update(authMethod="api_key", apiProvider="custom")
        code, meta, result, out = self.invoke(extra=["--raw-json", "--model", "opus", "--effort", "max", "--max-budget-usd", "1.25"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["delegation_metadata"]["model"], "opus")
        cmd = self.commands[0]
        self.assertEqual(cmd[cmd.index("--max-budget-usd") + 1], "1.2500")

    def test_failures_and_partial_output(self):
        for mode in ("failure", "malformed", "nonzero", "unexpected"):
            code, meta, result, _ = self.invoke(mode, name=mode)
            self.assertEqual(code, 1, meta)
            self.assertFalse(result["review_complete"])
            self.assertTrue(result["review"])
            self.assertTrue(meta["claude_start_attempted"])
        self.assertEqual(len(self.children), 4)

    def test_overflow_is_not_complete(self):
        code, meta, result, _ = self.invoke("overflow")
        self.assertEqual(code, 0)
        self.assertEqual(meta["status"], "success_with_overflow")
        self.assertFalse(result["review_complete"])

    def test_timeout_and_truncation(self):
        code, meta, result, _ = self.invoke("timeout", ["--max-runtime-minutes", ".05"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "error_timeout")
        self.assertTrue(meta["timed_out"])
        self.assertFalse(result["review_complete"])
        self.assertIsNotNone(self.children[0].poll())

    def test_preflight_error_is_durable(self):
        code, meta, result, _ = self.invoke(extra=["--base-revision", "HEAD"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "preflight_error")
        self.assertFalse(meta["claude_start_attempted"])
        self.assertTrue(result["terminal"])

    def test_login_failure_and_dry_run(self):
        self.auth["loggedIn"] = False
        code, meta, _, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(meta["claude_start_attempted"])
        self.auth["loggedIn"] = True
        code, meta, result, _ = self.invoke(extra=["--dry-run"], name="dry")
        self.assertEqual(code, 0)
        self.assertFalse(result["review_complete"])
        self.assertFalse(self.children)

    def test_reused_directory_refused(self):
        self.invoke()
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(len(self.children), 1)

    def test_working_snapshot_exact_bytes_and_names(self):
        repo, head = self.repository()
        files = {"a.txt": b"changed\r\n", "new staged.bin": b"\x00\xff\n", "untracked 测试 [x].txt": b"raw\x00data"}
        for name, data in files.items():
            (repo / name).write_bytes(data)
        self.git(repo, "add", "new staged.bin")
        before = self.git(repo, "status", "--porcelain")
        with patch.dict(os.environ, {"CLAUDE_PY_TEST_FILES": json.dumps({key: value.hex() for key, value in files.items()})}):
            code, meta, _, _ = self.invoke("inspect_snapshot", ["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["repository_head"], head)
        self.assertEqual(meta["diff_sha256"], meta["evidence_patch_sha256"])
        self.assertEqual(before, self.git(repo, "status", "--porcelain"))
        self.assertEqual(meta["status"], "success_native_review")
        cmd = self.commands[0]
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "Read,Glob,Grep")
        self.assertEqual(cmd[cmd.index("--disallowedTools") + 1], ",".join(runner.DENIED_TOOLS))
        self.assertFalse(Path(meta["snapshot_root"]).exists())
        self.assertEqual(self.git(repo, "worktree", "list", "--porcelain").count(b"worktree "), 1)

    def test_native_unexpected_tool_is_diagnostic(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_bytes(b"changed")
        code, meta, result, _ = self.invoke("unexpected", ["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 0)
        self.assertTrue(result["review_complete"])
        self.assertIn("Bash", meta["unexpected_tool_calls"])

    def test_native_zero_usage_rejected(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_bytes(b"changed")
        code, meta, result, _ = self.invoke("zero_usage", ["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "native_review_no_model_usage")

    def test_deleted_staged_addition_refused(self):
        repo, _ = self.repository()
        (repo / "added").write_bytes(b"staged")
        self.git(repo, "add", "added")
        (repo / "added").unlink()
        code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 1)
        self.assertFalse(meta["claude_start_attempted"])

    def test_deleted_tracked_and_untracked_replacement(self):
        repo, _ = self.repository()
        self.git(repo, "rm", "a.txt")
        (repo / "a.txt").write_bytes(b"untracked replacement")
        code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["untracked_file_count"], 1)

    def test_empty_scope_does_not_start(self):
        repo, head = self.repository()
        code, meta, result, out = self.invoke(extra=["--working-directory", str(repo), "--base-revision", head, "--head-revision", head, "--raw-json"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(json.loads(out)["delegation_metadata"]["status"], "no_changes")
        self.assertFalse(self.children)

    def test_committed_uses_three_dot_range(self):
        repo, ancestor = self.repository()
        (repo / "base-only").write_bytes(b"base branch")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "base branch")
        base = self.git(repo, "rev-parse", "HEAD").decode().strip()
        self.git(repo, "checkout", "--detach", ancestor)
        (repo / "head-only").write_bytes(b"head branch")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "head branch")
        head = self.git(repo, "rev-parse", "HEAD").decode().strip()
        code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--base-revision", base, "--head-revision", head])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["native_review_target"], f"{base}...{head}")
        self.assertEqual(meta["changed_file_count"], 1)

    def test_diff_config_and_aliased_temp(self):
        repo, _ = self.repository()
        self.git(repo, "config", "diff.noprefix", "true")
        (repo / "a.txt").write_bytes(b"changed")
        (repo / "new").write_bytes(b"untracked")
        real_temp = tempfile.mkdtemp
        def alias(*args, **kwargs):
            path = Path(real_temp(*args, **kwargs))
            return str(path / ".." / path.name)
        with patch.object(tempfile, "mkdtemp", side_effect=alias):
            code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 0, meta)

    def test_untracked_count_limit(self):
        repo, _ = self.repository()
        (repo / "new").write_bytes(b"new")
        code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree", "--max-untracked-files", "0"])
        self.assertEqual(code, 1)
        self.assertFalse(meta["claude_start_attempted"])

    def test_source_race_stops_before_model(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_bytes(b"first version")
        real_copy = shutil.copy2
        def changing(source, destination, *args, **kwargs):
            result = real_copy(source, destination, *args, **kwargs)
            if Path(source) == repo / "a.txt":
                Path(source).write_bytes(b"changed after copy")
            return result
        with patch.object(shutil, "copy2", side_effect=changing):
            code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 1)
        self.assertFalse(meta["claude_start_attempted"])
        self.assertIn("changed during snapshot", meta["error"])
        self.assertTrue(meta["sandbox_cleanup_succeeded"])

    def test_submodule_clean_pointer_and_dirty_refusal(self):
        dependency, _ = self.repository("dependency")
        repo, _ = self.repository()
        self.git(repo, "-c", "protocol.file.allow=always", "submodule", "add", str(dependency), "sub")
        self.git(repo, "commit", "-am", "add gitlink")
        child = repo / "sub"
        self.git(child, "config", "user.email", "test@example.invalid")
        self.git(child, "config", "user.name", "Offline Test")
        (child / "a.txt").write_bytes(b"next commit")
        self.git(child, "commit", "-am", "next")
        code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"], name="clean-link")
        self.assertEqual(code, 0, meta)
        (child / "a.txt").write_bytes(b"dirty child")
        code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"], name="dirty-link")
        self.assertEqual(code, 1)
        self.assertIn("Dirty submodule", meta["error"])
        self.assertFalse(meta["claude_start_attempted"])

    def test_worktree_add_ambiguous_failure_cleans_registration(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_bytes(b"change")
        original = runner.Snapshot.git
        def fail_after_add(instance, root, *args):
            result = original(instance, root, *args)
            if args[:2] == ("worktree", "add"):
                raise RuntimeError("simulated interruption after registration")
            return result
        with patch.object(runner.Snapshot, "git", fail_after_add):
            code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 1)
        self.assertTrue(meta["sandbox_cleanup_succeeded"])
        self.assertFalse(meta["claude_start_attempted"])
        self.assertEqual(self.git(repo, "worktree", "list", "--porcelain").count(b"worktree "), 1)

    def test_registered_worktree_cleanup_failure_is_retained(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_bytes(b"change")
        original = runner.Snapshot.git
        def fail_remove(instance, root, *args):
            if args[:2] == ("worktree", "remove"):
                raise RuntimeError("fixture registration lock")
            return original(instance, root, *args)
        with patch.object(runner.Snapshot, "git", fail_remove):
            code, meta, result, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"])
        retained = Path(meta["retained_snapshot_root"])
        try:
            self.assertEqual(code, 1)
            self.assertEqual(meta["status"], "sandbox_cleanup_failed")
            self.assertFalse(result["review_complete"])
            self.assertTrue(retained.is_dir())
            self.assertEqual(self.git(repo, "worktree", "list", "--porcelain").count(b"worktree "), 2)
        finally:
            cleanup = runner.Snapshot(runner.arguments(["--prompt", "cleanup fixture"]))
            cleanup.repo, cleanup.root, cleanup.path = repo, retained, retained / "repository"
            cleanup.worktree_attempted = True
            cleanup.cleanup()

    def test_live_status_write_failure_reaps_child(self):
        original = runner.write_json
        def failed_running(path, value):
            if path.name == "status.json" and value["status"] == "running":
                raise PermissionError("fixture live status lock")
            return original(path, value)
        with patch.object(runner, "write_json", side_effect=failed_running):
            code, meta, result, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertTrue(meta["claude_started"])
        self.assertFalse(result["review_complete"])
        self.assertIsNotNone(self.children[0].poll())

    def test_cleanup_and_publication_shield_repeated_signals(self):
        import signal
        original = runner.publish
        def guarded_publish(*args):
            self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_IGN)
            self.assertEqual(signal.getsignal(signal.SIGINT), signal.SIG_IGN)
            return original(*args)
        with patch.object(runner, "publish", side_effect=guarded_publish):
            code, _, _, _ = self.invoke()
        self.assertEqual(code, 0)

    def test_utf8_prompt_file(self):
        prompt = self.root / "prompt.txt"
        objective = 'Review "quoted" 测试\r\nsecond line\\'
        prompt.write_bytes(objective.encode("utf-8"))
        args = runner.arguments(["--prompt-file", str(prompt), "--working-directory", str(self.root), "--run-directory", str(self.root / "run"), "--dry-run"])
        with patch.object(runner, "resolve_claude", return_value=sys.executable), patch.object(runner, "capture", side_effect=self.preflight), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.run(args), 0)
        meta = json.loads((self.root / "run/metadata.json").read_text())
        self.assertEqual(meta["prompt_sha256"], runner.sha256(objective.encode()))

    def test_maximum_native_prompt_uses_cleaned_guidance_file(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_bytes(b"changed")
        code, meta, _, _ = self.invoke(mode="verify_guidance", extra=[
            "--working-directory", str(repo), "--review-working-tree", "--prompt", "x" * (256 * 1024)])
        self.assertEqual(code, 0, meta)
        command = self.commands[-1]
        self.assertLess(len(subprocess.list2cmdline(command)), 32000)
        self.assertNotIn("--append-system-prompt", command)
        self.assertFalse(Path(command[command.index("--append-system-prompt-file") + 1]).exists())

    def test_large_bounded_input_timeout_without_stdin_reader(self):
        began = time.monotonic()
        code, meta, _, _ = self.invoke(mode="no_stdin", extra=[
            "--prompt", "x" * (256 * 1024), "--max-runtime-minutes", "0.05"])
        self.assertLess(time.monotonic() - began, 15)
        self.assertEqual(code, 1)
        self.assertTrue(meta["timed_out"])
        self.assertTrue(meta["sandbox_cleanup_succeeded"])
        self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_auth_requires_explicit_boolean_true(self):
        for index, auth in enumerate(({}, {"error": "not logged in"}, {"loggedIn": None},
                                      {"loggedIn": 1}, {"loggedIn": "true"}, [])):
            with self.subTest(auth=auth):
                self.auth = auth
                code, meta, _, _ = self.invoke(name=f"invalid-auth-{index}")
                self.assertEqual(code, 1)
                self.assertEqual(meta["status"], "preflight_error")
                self.assertFalse(meta["claude_start_attempted"])
        self.assertEqual(self.commands, [])

    def test_submodule_ignored_by_config_is_still_frozen(self):
        dependency, _ = self.repository("dependency")
        repo, _ = self.repository()
        self.git(repo, "-c", "protocol.file.allow=always", "submodule", "add", str(dependency), "sub")
        self.git(repo, "commit", "-am", "add gitlink")
        base = self.git(repo, "rev-parse", "HEAD").decode().strip()
        child = repo / "sub"
        self.git(child, "config", "user.email", "test@example.invalid")
        self.git(child, "config", "user.name", "Offline Test")
        (child / "a.txt").write_bytes(b"next commit")
        self.git(child, "commit", "-am", "next")
        self.git(repo, "config", "diff.ignoreSubmodules", "all")
        for staged in (False, True):
            if staged:
                self.git(repo, "add", "sub")
            code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"], name=f"link-{staged}")
            self.assertEqual(code, 0, meta)
            self.assertEqual(meta["changed_file_count"], 1)
        self.git(repo, "commit", "-m", "update pointer")
        head = self.git(repo, "rev-parse", "HEAD").decode().strip()
        code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--base-revision", base,
                                             "--head-revision", head], name="link-range")
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["changed_file_count"], 1)

    def test_repository_location_is_reused_and_head_race_check_remains(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_bytes(b"changed")
        calls = []
        original = runner.Snapshot.git
        def recorded(snapshot, root, *args):
            calls.append(args)
            return original(snapshot, root, *args)
        with patch.object(runner.Snapshot, "git", recorded):
            code, meta, _, _ = self.invoke(extra=["--working-directory", str(repo), "--review-working-tree"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(sum(args == ("rev-parse", "--show-toplevel") for args in calls), 1)
        self.assertEqual(sum(args == ("rev-parse", "--verify", "--end-of-options", "HEAD^{commit}") for args in calls), 2)

    def test_artifact_failure_retains_start_flags(self):
        real_write = runner.write_json
        def locked(path, value):
            if path.name == "result.json":
                raise PermissionError("locked")
            return real_write(path, value)
        with patch.object(runner, "write_json", side_effect=locked):
            with self.assertRaises(FileNotFoundError):  # invoke helper cannot read the deliberately failed file
                self.invoke()
        meta = json.loads((self.root / "run/metadata.json").read_text())
        status = json.loads((self.root / "run/status.json").read_text())
        self.assertTrue(meta["claude_started"])
        self.assertFalse(meta["review_complete"])
        self.assertEqual(status["status"], "durable_artifact_error")


if __name__ == "__main__":
    unittest.main()
