import contextlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fake_codex.py"
spec = importlib.util.spec_from_file_location("delegator", ROOT / "scripts" / "invoke-codex.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
REAL_POPEN = subprocess.Popen


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-codex-delegator-")
        self.root = Path(self.temp.name).resolve()
        self.prompt = self.root / "objective.txt"
        self.prompt.write_text("Review this small plan.", encoding="utf-8")
        self.children, self.commands, self.stdin, self.environments = [], [], [], []
        self.permission_preflights = []
        self.execution_preflights = []
        self.authenticated = True
        self.interrupt = False
        self.stderr = ""

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                runner.stop_child(child)
        self.temp.cleanup()

    def fake_popen(self, command, **kwargs):
        # The resolved "codex" is sys.executable; route preflight and exec calls to the offline fixture.
        if command[0] == sys.executable and command[1] in ("exec", "--version", "login", "app-server", "sandbox"):
            if command[1] == "app-server":
                self.permission_preflights.append((command, kwargs.get("cwd"), kwargs.get("env")))
            if command[1] == "sandbox":
                self.execution_preflights.append((command, kwargs.get("cwd"), kwargs.get("env")))
            child = REAL_POPEN([sys.executable, str(FAKE), *command[1:]], **kwargs)
            if command[1] == "exec" and command[2] != "--help":
                self.commands.append(command)
                self.stdin.append(kwargs.get("stdin"))
                self.environments.append(kwargs.get("env"))
                self.children.append(child)
                if self.interrupt:
                    self.interrupt_first_wait(child)
            return child
        return REAL_POPEN(command, **kwargs)

    @staticmethod
    def interrupt_first_wait(child):
        # Deterministic stand-in for SIGINT/SIGTERM arriving while the wrapper waits on Codex.
        real_wait, calls = child.wait, []
        def wait(timeout=None):
            if not calls:
                calls.append(timeout)
                raise KeyboardInterrupt("Signal 15")
            return real_wait(timeout=timeout)
        child.wait = wait

    def invoke(self, mode="success", extra=(), name="run", prompt=True, run_directory=True, env=None):
        argv = ["--run-directory", str(self.root / name)] if run_directory else []
        if prompt:
            argv += ["--prompt-file", str(self.prompt)]
        args = runner.arguments([*argv, *extra])
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with patch.object(runner, "resolve_codex", return_value=sys.executable), \
                 patch.object(runner.subprocess, "Popen", side_effect=self.fake_popen), \
                 patch.dict(os.environ, {"DELEGATOR_TEST_MODE": mode,
                                         "DELEGATOR_TEST_AUTH": "1" if self.authenticated else "0", **(env or {})}), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = runner.run(args)
        finally:
            self.stderr = stderr.getvalue()
        run_dir = Path(json.loads(stdout.getvalue())["run_directory"])
        return code, json.loads((run_dir / "metadata.json").read_text(encoding="utf-8")), run_dir

    @staticmethod
    def status(directory):
        try:
            return json.loads((directory / "status.json").read_text(encoding="utf-8"))["status"]
        except (OSError, ValueError):
            return None

    def repository(self):
        repo = self.root / "repo"
        repo.mkdir()
        runner.git(repo, "init")
        runner.git(repo, "config", "user.email", "offline@example.invalid")
        runner.git(repo, "config", "user.name", "Offline Test")
        runner.git(repo, "config", "core.autocrlf", "false")
        (repo / "a.txt").write_text("before\n", encoding="utf-8")
        runner.git(repo, "add", ".")
        runner.git(repo, "commit", "-m", "base")
        return repo, runner.revision(repo, "HEAD")

    def test_success_and_safety_arguments(self):
        code, meta, directory = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(meta["complete"])
        self.assertTrue(meta["cleanup_complete"])
        self.assertEqual(meta["usage"][0]["output_tokens"], 50)
        command = self.commands[0]
        self.assertIn("--strict-config", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn('approval_policy="never"', command)
        self.assertIn('web_search="disabled"', command)
        self.assertFalse(any("dangerously" in value for value in command))
        self.assertNotIn(self.stdin[0], (None, subprocess.PIPE))
        self.assertTrue((directory / "stream.jsonl").exists())
        self.assertEqual(json.loads((directory / "status.json").read_text())["status"], "complete")

    def test_failures_never_clean(self):
        for mode in ("malformed", "failed", "unexpected", "missing_turn", "zero_usage", "missing_final", "invalid_final", "partial", "nonzero"):
            with self.subTest(mode=mode):
                code, meta, directory = self.invoke(mode, name=mode)
                self.assertEqual(code, 1)
                self.assertFalse(meta["complete"])
                self.assertTrue(meta["codex_start_attempted"])
                self.assertFalse(json.loads((directory / "result.json").read_text())["complete"])
        self.assertEqual(len(self.children), 9)  # one attempt each, no retries

    def test_more_than_eight_findings(self):
        code, meta, directory = self.invoke("many_findings")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads((directory / "result.json").read_text())["review"]["findings"]), 12)

    def test_timeout_reaps_child(self):
        code, meta, _ = self.invoke("timeout", ["--timeout-seconds", "1"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "timeout")
        self.assertIsNotNone(self.children[0].poll())

    def test_preflight_and_dry_run(self):
        self.authenticated = False
        code, meta, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(meta["codex_start_attempted"])
        code, meta, _ = self.invoke(extra=["--dry-run"], name="dry")
        self.assertEqual(code, 0)
        self.assertEqual(meta["status"], "dry_run")
        self.assertFalse(meta["complete"])
        self.assertEqual(self.children, [])

    def test_existing_run_directory_is_not_overwritten(self):
        self.invoke()
        with self.assertRaisesRegex(ValueError, "new or empty"):
            self.invoke()
        self.assertEqual(len(self.children), 1)
        self.assertEqual(self.status(self.root / "run"), "complete")

    def test_model_selection(self):
        self.invoke(extra=["--model", "explicit-model", "--effort", "high"])
        command = self.commands[0]
        self.assertEqual(command[command.index("--model") + 1], "explicit-model")
        self.assertIn('model_reasoning_effort="high"', command)

    def test_committed_exact_range_cleanup(self):
        repo, base = self.repository()
        (repo / "a.txt").write_text("after\n", encoding="utf-8")
        runner.git(repo, "commit", "-am", "head")
        head = runner.revision(repo, "HEAD")
        (repo / "a.txt").write_text("unrelated dirty content\n", encoding="utf-8")
        before = runner.git(repo, "status", "--porcelain")
        code, meta, directory = self.invoke(extra=["--repo", str(repo), "--base", base, "--head", head])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["base"], base)
        self.assertEqual(meta["head"], head)
        self.assertNotIn(b"unrelated", (directory / "diff.patch").read_bytes())
        self.assertEqual(before, runner.git(repo, "status", "--porcelain"))
        self.assertFalse(Path(meta["snapshot"]).exists())
        self.assertEqual(runner.git(repo, "worktree", "list", "--porcelain").count(b"worktree "), 1)

    def test_working_tree_unicode_binary_and_untracked(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_text("after\n", encoding="utf-8")
        (repo / "new staged.txt").write_bytes(b"\x00\xff\x00")
        runner.git(repo, "add", "new staged.txt")
        (repo / "untracked 测试.txt").write_text("untracked", encoding="utf-8")
        before = runner.git(repo, "status", "--porcelain")
        code, meta, _ = self.invoke(extra=["--repo", str(repo), "--working-tree"])
        self.assertEqual(code, 0, meta)
        self.assertTrue(meta["source_unchanged"])
        self.assertEqual(before, runner.git(repo, "status", "--porcelain"))

    def test_deleted_staged_addition_fails_before_call(self):
        repo, _ = self.repository()
        added = repo / "added.txt"
        added.write_text("staged", encoding="utf-8")
        runner.git(repo, "add", "added.txt")
        added.unlink()
        code, meta, _ = self.invoke(extra=["--repo", str(repo), "--working-tree"])
        self.assertEqual(code, 1)
        self.assertFalse(meta["codex_start_attempted"])
        self.assertIn("staged addition", meta["error"])

    def test_staged_deletion_with_untracked_replacement(self):
        repo, _ = self.repository()
        runner.git(repo, "rm", "a.txt")
        (repo / "a.txt").write_text("replacement", encoding="utf-8")
        before = runner.git(repo, "status", "--porcelain")
        code, meta, _ = self.invoke(extra=["--repo", str(repo), "--working-tree"])
        self.assertEqual(code, 0, meta)
        self.assertIn("a.txt", meta["untracked_files"])
        self.assertEqual(before, runner.git(repo, "status", "--porcelain"))

    def test_run_inside_repo_refused(self):
        repo, base = self.repository()
        with self.assertRaisesRegex(ValueError, "outside"):
            self.invoke(extra=["--repo", str(repo), "--base", base], name="repo/run")
        self.assertFalse((repo / "run").exists())

    def test_log_failure_does_not_start(self):
        real_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if path.name == "stream.jsonl":
                raise OSError("fixture log failure")
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", guarded_open):
            code, meta, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(self.children, [])

    def test_uncertain_process_cleanup_retains_temp(self):
        real_stop = runner.stop_child
        def uncertain(child):
            if child.poll() is None:
                real_stop(child)
                raise runner.ProcessCleanupError("fixture uncertainty")
        with patch.object(runner, "stop_child", side_effect=uncertain):
            code, meta, _ = self.invoke("timeout", ["--timeout-seconds", "1"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "cleanup_failed")
        retained = Path(meta["retained_temp_directory"])
        self.assertTrue(retained.exists())
        shutil.rmtree(retained)

    def test_skill_flat_frontmatter_and_metadata(self):
        # This skill deliberately uses two plain scalar YAML fields only.
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        front = content.split("---", 2)[1].strip().splitlines()
        self.assertEqual(len(front), 2)
        self.assertEqual(front[0], "name: codex-delegator")
        self.assertTrue(front[1].startswith("description: "))
        description = front[1].removeprefix("description: ")
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn(": ", description)
        self.assertNotIn(" #", description)
        self.assertIsNone(re.search(r"[<>\[\]{}]", description))
        self.assertNotIn("[TODO:", content)
        metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$codex-delegator", metadata)

    def test_no_changes_no_call(self):
        repo, base = self.repository()
        code, meta, _ = self.invoke(extra=["--repo", str(repo), "--base", base])
        self.assertEqual(code, 0)
        self.assertEqual(meta["status"], "no_changes")
        self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(self.children, [])

    def test_source_drift_invalidates_result(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_text("uncommitted", encoding="utf-8")
        with patch.dict(os.environ, {"DELEGATOR_TEST_SOURCE": str(repo / "a.txt")}):
            code, meta, _ = self.invoke("source_changed", ["--repo", str(repo), "--working-tree"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "source_changed")
        self.assertFalse(meta["complete"])

    def test_cleanup_failure_nonzero(self):
        with patch.object(runner.shutil, "rmtree", side_effect=OSError("fixture cleanup failure")):
            code, meta, _ = self.invoke(extra=["--dry-run"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "cleanup_failed")
        shutil.rmtree(meta["retained_temp_directory"])

    def test_repository_location_validation(self):
        value = {"complete": True, "summary": "", "limitations": [], "findings": [
            {"priority": "P2", "file": "", "line": 0, "title": "plan", "body": "text"}]}
        runner.validate_review(value)
        with self.assertRaises(ValueError):
            runner.validate_review(value, repository=True)

    def test_git_diff_prefix_overrides(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_text("changed\n", encoding="utf-8")
        for index, (key, setting) in enumerate((("diff.noprefix", "true"), ("diff.srcPrefix", "old/"), ("diff.dstPrefix", "new/"))):
            runner.git(repo, "config", key, setting)
            code, meta, directory = self.invoke(extra=["--repo", str(repo), "--working-tree"], name=f"prefix-{index}")
            self.assertEqual(code, 0, meta)
            self.assertIn(b"--- a/a.txt", (directory / "diff.patch").read_bytes())
            self.assertIn(b"+++ b/a.txt", (directory / "diff.patch").read_bytes())
            self.assertTrue(meta["source_unchanged"])

    def test_noncanonical_temp_path(self):
        repo, _ = self.repository()
        (repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        real_mkdtemp = tempfile.mkdtemp
        def alias(*args, **kwargs):
            actual = Path(real_mkdtemp(*args, **kwargs))
            return str(actual / ".." / actual.name)
        with patch.object(runner.tempfile, "mkdtemp", side_effect=alias):
            code, meta, _ = self.invoke(extra=["--repo", str(repo), "--working-tree"])
        self.assertEqual(code, 0, meta)
        self.assertNotIn("..", Path(meta["snapshot"]).parts)
        self.assertFalse(Path(meta["snapshot"]).exists())

    def test_rooted_finding_paths_rejected_on_every_platform(self):
        value = {"complete": True, "summary": "", "limitations": [], "findings": [
            {"priority": "P2", "file": "src/a.py", "line": 1, "title": "fixture", "body": "text"}]}
        runner.validate_review(value, repository=True)
        for name in ("/outside.py", "\\outside.py", "C:\\outside.py", "C:outside.py",
                     "\\\\server\\share\\a.py", "../a.py", "..\\a.py"):
            value["findings"][0]["file"] = name
            with self.subTest(path=name), self.assertRaises(ValueError):
                runner.validate_review(value, repository=True)

    def test_truncated_timeout_keeps_status_and_partial_review(self):
        code, meta, directory = self.invoke("timeout_partial", ["--timeout-seconds", "1"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "timeout")
        self.assertTrue(meta["event_errors"])
        result = json.loads((directory / "result.json").read_text())
        self.assertFalse(result["complete"])
        self.assertEqual(result["review"]["summary"], "Partial evidence")

    def test_null_item_is_recorded_without_discarding_review(self):
        code, meta, directory = self.invoke("null_item")
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "incomplete")
        self.assertTrue(meta["event_errors"])
        self.assertIsNotNone(json.loads((directory / "result.json").read_text())["review"])

    def test_atomic_write_retries_transient_reader_lock(self):
        destination = self.root / "locked.json"
        destination.write_text("{}", encoding="utf-8")
        real_replace = os.replace
        attempts = []
        def locked(source, target):
            attempts.append(target)
            if len(attempts) < 3:
                raise PermissionError("reader lock")
            return real_replace(source, target)
        with patch.object(runner.os, "replace", side_effect=locked), patch.object(runner.time, "sleep"):
            runner.write_json(destination, {"finished": True})
        self.assertEqual(len(attempts), 3)
        self.assertEqual(json.loads(destination.read_text()), {"finished": True})

    def test_terminal_write_failures_attempt_other_artifacts(self):
        real_write = runner.write_json
        for target in ("result.json", "status.json"):
            def locked(path, value):
                if path.name == target and (target != "status.json" or value["status"] in ("complete", "artifact_error")):
                    raise PermissionError("permanent terminal lock")
                return real_write(path, value)
            with patch.object(runner, "write_json", side_effect=locked):
                code, meta, directory = self.invoke(name="locked-" + target)
            self.assertEqual(code, 1)
            self.assertEqual(meta["status"], "artifact_error")
            self.assertTrue(meta["codex_started"])
            self.assertFalse(meta["complete"])
            self.assertIn(target, meta["artifact_errors"])
            self.assertIn("CODEX_DELEGATION_METADATA=", self.stderr)
            if target == "result.json":
                self.assertEqual(json.loads((directory / "status.json").read_text())["status"], "artifact_error")
            else:
                self.assertFalse(json.loads((directory / "result.json").read_text())["complete"])

    def test_total_terminal_storage_failure_emits_fallback(self):
        meta = {"status": "complete", "complete": True, "codex_started": True, "codex_start_attempted": True}
        output = io.StringIO()
        with patch.object(runner, "write_json", side_effect=OSError("disk full")) as writer, contextlib.redirect_stderr(output):
            runner.publish_terminal(self.root, meta, {"complete": True})
        self.assertEqual(writer.call_count, 6)
        recovered = json.loads(output.getvalue().split("=", 1)[1])
        self.assertEqual(recovered["status"], "artifact_error")
        self.assertTrue(recovered["codex_started"])
        self.assertFalse(recovered["complete"])
        self.assertEqual(len(recovered["artifact_errors"]), 3)


    def test_generated_run_directory_is_reported_and_kept(self):
        code, meta, directory = self.invoke(run_directory=False)
        self.addCleanup(shutil.rmtree, directory, True)
        self.assertEqual(code, 0, meta)
        self.assertTrue(meta["run_directory_generated"])
        self.assertTrue(directory.name.startswith("codex-delegator-run-"))
        self.assertTrue(directory.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertIn("CODEX_DELEGATION_RUN_DIRECTORY=" + str(directory), self.stderr)
        self.assertEqual(self.status(directory), "complete")

    def test_existing_empty_run_directory_is_accepted(self):
        (self.root / "empty").mkdir()
        code, meta, directory = self.invoke(name="empty")
        self.assertEqual(code, 0, meta)
        self.assertFalse(meta["run_directory_generated"])
        self.assertEqual((directory / ".run-claim").read_text(encoding="ascii"), str(os.getpid()))

    def test_symlinked_run_directory_refused(self):
        target = self.root / "target"
        target.mkdir()
        try:
            (self.root / "link").symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks are unavailable")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.invoke(name="link")
        self.assertEqual(list(target.iterdir()), [])

    def test_inline_prompt_and_objective_validation(self):
        copy = self.root / "prompt-copy.txt"
        objective = 'Inline "quoted" objective 测试'
        code, meta, _ = self.invoke(prompt=False, extra=["--prompt", objective],
                                    env={"DELEGATOR_TEST_PROMPT_COPY": str(copy)})
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["mode"], "standalone")
        self.assertTrue(copy.read_text(encoding="utf-8").endswith(objective))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            runner.arguments(["--prompt", "x", "--prompt-file", str(self.prompt)])
        for name, extra, message in (("blank", ["--prompt", "  "], "nonempty"),
                                     ("missing", [], "--prompt or --prompt-file")):
            with self.subTest(name=name):
                code, meta, _ = self.invoke(prompt=False, extra=extra, name=name)
                self.assertEqual(code, 1)
                self.assertIn(message, meta["error"])
                self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(len(self.children), 1)

    def test_prompt_is_fed_from_a_file_so_large_input_cannot_block(self):
        began = time.monotonic()
        code, meta, _ = self.invoke("no_stdin", prompt=False,
                                    extra=["--prompt", "x" * (1024 * 1024), "--timeout-seconds", "1"])
        self.assertLess(time.monotonic() - began, 15)
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "timeout")
        self.assertTrue(meta["cleanup_complete"])
        self.assertIsNotNone(self.children[0].poll())
        self.assertNotIn(self.stdin[0], (None, subprocess.PIPE))
        self.assertTrue(callable(getattr(self.stdin[0], "fileno", None)))

    def test_preflight_is_bounded_with_inheriting_grandchild(self):
        began = time.monotonic()
        with patch.object(runner, "PREFLIGHT_TIMEOUT", 1):
            code, meta, _ = self.invoke("preflight_hang")
        self.assertLess(time.monotonic() - began, 15)
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "error")
        self.assertIn("TimeoutExpired", meta["error"])
        self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(self.children, [])

    def test_bounded_capture_with_inheriting_grandchild(self):
        code = ("import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "print('started',flush=True); time.sleep(30)")
        began = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.run_capture([sys.executable, "-c", code], timeout=.5)
        self.assertLess(time.monotonic() - began, 10)

    def test_capture_preserves_bytes_return_code_and_stdin(self):
        echo = "import sys; sys.stdout.buffer.write(b'raw\\x00' + sys.stdin.buffer.read()); sys.exit(3)"
        result = runner.run_capture([sys.executable, "-c", echo], timeout=10, data=b"\xffinput")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"raw\x00\xffinput")
        self.assertEqual(runner.run_capture([sys.executable, "-c", echo], timeout=10).stdout, b"raw\x00")

    def test_resolver_ignores_implicit_cwd_and_relative_path_entries(self):
        original = Path.cwd()
        actual = runner.resolve_on_path("git")
        fake = self.root / ("git.exe" if os.name == "nt" else "git")
        fake.write_bytes(b"not the Git executable")
        fake.chmod(0o755)
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, {"PATH": "." + os.pathsep + str(Path(actual).parent)}):
                self.assertEqual(runner.resolve_on_path("git"), actual)
        finally:
            os.chdir(original)

    def test_codex_resolution_refuses_cwd_lookup_and_shell_shims(self):
        original = Path.cwd()
        name = "codex.exe" if os.name == "nt" else "codex"
        (self.root / name).write_bytes(b"planted")
        (self.root / name).chmod(0o755)
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, {"PATH": "."}), self.assertRaisesRegex(ValueError, "not found"):
                runner.resolve_codex("codex")
        finally:
            os.chdir(original)
        for suffix in (".cmd", ".bat", ".ps1"):
            shim = self.root / ("codex" + suffix)
            shim.write_bytes(b"@echo off")
            shim.chmod(0o755)
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "shell shim"):
                runner.resolve_codex(str(shim))
        native = self.root / "bin" / name
        native.parent.mkdir()
        native.write_bytes(b"native fixture")
        native.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(native.parent)}):
            self.assertEqual(runner.resolve_codex("codex"), str(native.resolve()))
        self.assertEqual(runner.resolve_codex(str(native)), str(native.resolve()))

    @unittest.skipUnless(os.name == "nt", "Windows taskkill policy")
    def test_taskkill_failure_does_not_claim_descendants_are_dead(self):
        child = Mock(pid=12345)
        child.poll.side_effect = [None, 0]
        with patch.object(runner.subprocess, "run", return_value=Mock(returncode=128, stderr=b"")):
            with self.assertRaises(runner.ProcessCleanupError):
                runner.stop_child(child)
        child.kill.assert_not_called()
        child.wait.assert_called_once()

    def test_repeated_signals_are_ignored_during_cleanup_then_restored(self):
        before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        with runner.cleanup_signals():
            for number in before:
                self.assertEqual(signal.getsignal(number), signal.SIG_IGN)
                signal.raise_signal(number)
        for number, previous in before.items():
            self.assertEqual(signal.getsignal(number), previous)

    def test_cleanup_and_publication_shield_repeated_signals(self):
        original, seen = runner.publish_terminal, []
        def guarded(*args):
            seen.append({number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)})
            return original(*args)
        with patch.object(runner, "publish_terminal", side_effect=guarded):
            code, _, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(seen, [{signal.SIGINT: signal.SIG_IGN, signal.SIGTERM: signal.SIG_IGN}])

    def test_interrupt_publishes_terminal_interrupted_status(self):
        repo, _ = self.repository()
        (repo / "a.txt").write_text("changed\n", encoding="utf-8")
        self.interrupt = True
        code, meta, directory = self.invoke("timeout", ["--repo", str(repo), "--working-tree"])
        self.assertEqual(code, 1)
        self.assertEqual(meta["status"], "interrupted")
        self.assertIn("do not automatically retry", meta["error"])
        self.assertTrue(meta["codex_started"])
        self.assertFalse(meta["complete"])
        self.assertTrue(meta["cleanup_complete"])
        self.assertIsNotNone(self.children[0].poll())
        self.assertFalse(Path(meta["snapshot"]).exists())
        self.assertEqual(self.status(directory), "interrupted")
        self.assertFalse(json.loads((directory / "result.json").read_text())["complete"])

    @unittest.skipIf(os.name == "nt", "POSIX signal delivery to a separate wrapper process")
    def test_wrapper_process_sigterm_is_interrupted_and_repeats_are_ignored(self):
        shims = self.root / "bin"
        shims.mkdir()
        codex = shims / "codex"
        codex.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} "$@"\n', encoding="utf-8")
        codex.chmod(0o755)
        directory = self.root / "signalled"
        env = {**os.environ, "PATH": str(shims) + os.pathsep + os.environ.get("PATH", ""), "DELEGATOR_TEST_MODE": "timeout"}
        wrapper = REAL_POPEN([sys.executable, str(ROOT / "scripts" / "invoke-codex.py"), "--prompt", "Review the plan.",
                              "--run-directory", str(directory), "--timeout-seconds", "120"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        try:
            deadline = time.monotonic() + 30
            while self.status(directory) != "running":
                if wrapper.poll() is not None:
                    self.fail("Wrapper exited before running: " + wrapper.communicate()[1].decode("utf-8", "replace"))
                if time.monotonic() > deadline:
                    self.fail("Wrapper did not reach the running state")
                time.sleep(0.05)
            for _ in range(3):
                wrapper.send_signal(signal.SIGTERM)
                time.sleep(0.02)
            out, err = wrapper.communicate(timeout=60)
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
        meta = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(wrapper.returncode, 1, err)
        self.assertEqual(json.loads(out)["status"], "interrupted")
        self.assertEqual(self.status(directory), "interrupted")
        self.assertIn("do not automatically retry", meta["error"])
        self.assertTrue(meta["codex_started"])
        self.assertTrue(meta["cleanup_complete"])
        self.assertIn(b"CODEX_DELEGATION_RUN_DIRECTORY=", err)
        with self.assertRaises(ProcessLookupError):
            os.kill(meta["pid"], 0)

    def test_code_grounded_reads_exact_commit_without_diff(self):
        repo, base = self.repository()
        (repo / "a.txt").write_text("after\n", encoding="utf-8")
        runner.git(repo, "commit", "-am", "later")
        (repo / "a.txt").write_text("dirty checkout\n", encoding="utf-8")
        (repo / "untracked.txt").write_text("not evidence\n", encoding="utf-8")
        before = runner.git(repo, "status", "--porcelain")
        copy = self.root / "prompt-copy.txt"
        code, meta, directory = self.invoke("read_snapshot", ["--repo", str(repo), "--head", base],
                                            env={"DELEGATOR_TEST_PROMPT_COPY": str(copy)})
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["mode"], "code-grounded")
        self.assertEqual(meta["head"], base)
        self.assertIsNone(meta["base"])
        self.assertIsNone(meta["diff_sha256"])
        self.assertEqual(meta["untracked_files"], {})
        self.assertFalse((directory / "diff.patch").exists())
        self.assertEqual(json.loads((directory / "result.json").read_text())["review"]["summary"], "before\n")
        prompt = copy.read_text(encoding="utf-8")
        self.assertLess(prompt.index("Review this small plan."), prompt.index("Snapshot: "))
        self.assertIn("Exact commit: " + base, prompt)
        self.assertIn(runner.READ_ONLY_SHELL, prompt)
        command = self.commands[0]
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        for flag in ("--strict-config", "--ignore-user-config", "--ignore-rules", "--ephemeral",
                     'approval_policy="never"', 'web_search="disabled"', "project_doc_max_bytes=0",
                     "features.hooks=false", "features.plugins=false", "features.multi_agent=false"):
            self.assertIn(flag, command)
        self.assertEqual(before, runner.git(repo, "status", "--porcelain"))
        self.assertFalse(Path(meta["snapshot"]).exists())
        self.assertEqual(runner.git(repo, "worktree", "list", "--porcelain").count(b"worktree "), 1)

    def test_code_grounded_mode_selection_and_document_findings(self):
        repo, head = self.repository()
        code, meta, directory = self.invoke("document_finding", ["--repo", str(repo), "--head", "HEAD"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["head"], head)  # A clean checkout still runs: this mode has no NoChanges path.
        self.assertEqual(len(json.loads((directory / "result.json").read_text())["review"]["findings"]), 2)
        for name, extra, prompt in (("no-head", ["--repo", str(repo)], True),
                                    ("no-objective", ["--repo", str(repo), "--head", head], False),
                                    ("tree-head", ["--repo", str(repo), "--working-tree", "--head", "HEAD"], True)):
            with self.subTest(name=name):
                code, meta, _ = self.invoke(extra=extra, name=name, prompt=prompt)
                self.assertEqual(code, 1)
                self.assertEqual(meta["status"], "error")
                self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(len(self.children), 1)

    def test_working_tree_without_changes_does_not_start(self):
        repo, _ = self.repository()
        code, meta, _ = self.invoke(extra=["--repo", str(repo), "--working-tree"])
        self.assertEqual(code, 0)
        self.assertEqual(meta["status"], "no_changes")
        self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(self.children, [])

    def test_task_edits_retained_worktree_and_preserves_source(self):
        repo, head = self.repository()
        (repo / "a.txt").write_text("unrelated dirty source\n", encoding="utf-8")
        (repo / "private.txt").write_text("untracked source", encoding="utf-8")
        before = runner.capture_working(repo)[3]
        code, meta, directory = self.invoke(extra=["--mode", "task", "--repo", str(repo), "--head", head])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["mode"], "task")
        self.assertTrue(meta["complete"])
        self.assertTrue(meta["worktree_retained"])
        workspace = Path(meta["task_worktree"])
        self.assertEqual((workspace / "a.txt").read_text(), "implemented\n")
        self.assertEqual((workspace / "new 测试.bin").read_bytes(), b"\x00\xffnew\n")
        self.assertFalse((workspace / "private.txt").exists())
        self.assertEqual(before, runner.capture_working(repo)[3])
        self.assertEqual(runner.revision(workspace, "HEAD"), head)
        self.assertIn(b"+implemented", (directory / "task-diff.patch").read_bytes())
        self.assertEqual((directory / "task-untracked" / "new 测试.bin").read_bytes(), b"\x00\xffnew\n")
        self.assertTrue((directory / "task-evidence.json").is_file())
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        self.assertTrue(result["task"]["complete"])
        self.assertNotIn("review", result)
        command = self.commands[0]
        self.assertEqual(command[command.index("-C") + 1], str(workspace))
        self.assertNotIn("--sandbox", command)
        self.assertTrue(meta["task_permission_verified"])
        self.assertNotIn("project_doc_max_bytes=0", command)
        self.assertIn('approval_policy="never"', command)
        self.assertIn("features.multi_agent=false", command)
        self.assertEqual(meta["event_errors"], [])

    def test_task_requires_repo_objective_and_commit_start(self):
        repo, head = self.repository()
        cases = [(["--mode", "task"], True),
                 (["--mode", "task", "--repo", str(repo)], False),
                 (["--mode", "task", "--repo", str(repo), "--base", head], True),
                 (["--mode", "task", "--repo", str(repo), "--working-tree"], True)]
        for i, (extra, prompt) in enumerate(cases):
            with self.subTest(extra=extra):
                code, meta, _ = self.invoke(extra=extra, prompt=prompt, name=f"invalid-task-{i}")
                self.assertEqual(code, 1, meta)
                self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(self.children, [])

    def test_task_background_writer_stops_before_evidence_publication(self):
        repo, _ = self.repository()
        code, meta, directory = self.invoke("task_background", ["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 0, meta)
        evidence = (directory / "task-diff.patch").read_bytes()
        self.assertIn(b"+implemented", evidence)
        time.sleep(4)
        self.assertEqual((Path(meta["task_worktree"]) / "a.txt").read_text(), "implemented\n")
        self.assertEqual((directory / "task-diff.patch").read_bytes(), evidence)

    def test_task_failures_preserve_edits_and_never_report_complete(self):
        repo, _ = self.repository()
        for mode in ("task_timeout", "partial", "malformed", "unexpected", "missing_final", "nonzero"):
            with self.subTest(mode=mode):
                code, meta, directory = self.invoke(mode, ["--mode", "task", "--repo", str(repo),
                                                          "--timeout-seconds", "2"], name=mode)
                self.assertEqual(code, 1, meta)
                self.assertFalse(meta["complete"])
                self.assertTrue(meta["worktree_retained"])
                self.assertEqual((Path(meta["task_worktree"]) / "a.txt").read_text(), "implemented\n")
                self.assertTrue((directory / "task-diff.patch").exists())
                if mode == "task_timeout":
                    self.assertEqual(meta["status"], "timeout")
        self.assertEqual(len(self.children), 6)

    def test_task_interrupt_retains_workspace(self):
        repo, _ = self.repository()
        self.interrupt = True
        code, meta, directory = self.invoke("timeout", ["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertEqual(meta["status"], "interrupted")
        self.assertTrue(meta["worktree_retained"])
        self.assertTrue(Path(meta["task_worktree"]).is_dir())
        self.assertTrue((directory / "task-evidence.json").exists())

    def test_task_dry_run_keeps_workspace_without_model_call(self):
        repo, head = self.repository()
        code, meta, _ = self.invoke(extra=["--mode", "task", "--repo", str(repo), "--dry-run"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(meta["status"], "dry_run")
        self.assertFalse(meta["complete"])
        self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(self.children, [])
        self.assertEqual(runner.revision(Path(meta["task_worktree"]), "HEAD"), head)

    @unittest.skipUnless(os.name == "nt", "Windows suspended task launch")
    def test_task_job_assignment_failure_never_executes_task(self):
        repo, _ = self.repository()
        original_resume = runner.WindowsTaskJob.assign_and_resume
        def fail_model(job, child):
            if child in self.children:
                raise OSError("fixture job denied")
            return original_resume(job, child)
        with patch.object(runner.WindowsTaskJob, "assign_and_resume", fail_model):
            code, meta, _ = self.invoke(extra=["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertFalse(meta["complete"])
        self.assertTrue(meta["codex_start_attempted"])
        self.assertIn("fixture job denied", meta["error"])
        self.assertTrue(meta["task_process_tree_terminated"])
        self.assertEqual((Path(meta["task_worktree"]) / "a.txt").read_text(), "before\n")
        self.assertIsNotNone(self.children[0].poll())

    def test_task_unconfirmed_termination_does_not_publish_evidence(self):
        repo, _ = self.repository()
        real_stop = runner.stop_task_tree
        def uncertain(child, job):
            real_stop(child, job)
            if child in self.children:
                raise runner.ProcessCleanupError("fixture unconfirmed task termination")
        with patch.object(runner, "stop_task_tree", side_effect=uncertain):
            code, meta, directory = self.invoke(extra=["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertFalse(meta["complete"])
        self.assertIn("unconfirmed", meta["process_cleanup_error"])
        self.assertTrue(Path(meta["task_worktree"]).is_dir())
        self.assertFalse((directory / "task-evidence.json").exists())
        # The fixture already terminated its child; remove its deliberately retained runner temp.
        shutil.rmtree(meta["retained_temp_directory"])

    def test_task_collection_failure_retains_work_and_invalidates_success(self):
        repo, _ = self.repository()
        real_write = runner.write_json
        def fail_evidence(path, value):
            if path.name == "task-evidence.json":
                raise OSError("fixture disk full")
            return real_write(path, value)
        with patch.object(runner, "write_json", side_effect=fail_evidence):
            code, meta, _ = self.invoke(extra=["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertFalse(meta["complete"])
        self.assertTrue(meta["worktree_retained"])
        self.assertIn("task_collection_error", meta)
        self.assertEqual((Path(meta["task_worktree"]) / "a.txt").read_text(), "implemented\n")

    def test_task_terminal_failure_keeps_worktree(self):
        repo, _ = self.repository()
        real_write = runner.write_json
        def locked(path, value):
            if path.name == "result.json":
                raise PermissionError("fixture terminal lock")
            return real_write(path, value)
        with patch.object(runner, "write_json", side_effect=locked):
            code, meta, _ = self.invoke(extra=["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertEqual(meta["status"], "artifact_error")
        self.assertTrue(Path(meta["task_worktree"]).is_dir())
        self.assertTrue(meta["worktree_retained"])
        self.assertIn("CODEX_DELEGATION_METADATA=", self.stderr)

    def test_review_still_rejects_file_changes(self):
        code, meta, _ = self.invoke("review_file_change")
        self.assertEqual(code, 1)
        self.assertIn({"unexpected_item": "file_change"}, meta["event_errors"])

    def test_task_result_schema_and_path_validation(self):
        value = {"complete": True, "summary": "Done", "changed_files": ["src/a.py"],
                 "tests": [{"command": "python -m unittest", "outcome": "passed", "details": "1 passed"}],
                 "limitations": []}
        runner.validate_task(value)
        for name in ("", "/outside", "C:outside", "../outside", "..\\outside", "\\outside"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runner.validate_task({**value, "changed_files": [name]})
        for change in ({"tests": [{"command": "test", "outcome": "maybe", "details": ""}]},
                       {"complete": 1}, {"limitations": "none"}, {"findings": []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.validate_task({**value, **change})

    @unittest.skipUnless(os.name == "nt", "Windows Job Object confirmation")
    def test_task_failed_job_confirmation_never_becomes_confirmed(self):
        repo, _ = self.repository()
        original_job = runner.WindowsTaskJob
        fixture = self
        class QueryFailureJob(original_job):
            def assign_and_resume(self, child):
                super().assign_and_resume(child)
                if child in fixture.children:
                    self.api.QueryInformationJobObject = Mock(side_effect=OSError("fixture accounting unavailable"))
        with patch.object(runner, "WindowsTaskJob", QueryFailureJob):
            code, meta, directory = self.invoke(extra=["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertFalse(meta["complete"])
        self.assertIsNot(meta.get("task_process_tree_terminated"), True)
        self.assertIn("process_cleanup_error", meta)
        self.assertFalse((directory / "task-evidence.json").exists())
        self.assertTrue(Path(meta["task_worktree"]).is_dir())
        shutil.rmtree(meta["retained_temp_directory"])

    @unittest.skipUnless(os.name == "nt", "Windows suspended launch")
    def test_task_launch_failure_with_successful_cleanup_is_not_cleanup_failure(self):
        repo, _ = self.repository()
        original_resume = runner.WindowsTaskJob.assign_and_resume
        def fail_model(job, child):
            if child in self.children:
                raise runner.TaskLaunchError("fixture thread identification failed")
            return original_resume(job, child)
        with patch.object(runner.WindowsTaskJob, "assign_and_resume", fail_model):
            code, meta, directory = self.invoke(extra=["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertEqual(meta["status"], "error")
        self.assertIn("thread identification failed", meta["error"])
        self.assertNotIn("process_cleanup_error", meta)
        self.assertTrue(meta["task_process_tree_terminated"])
        self.assertTrue(meta["cleanup_complete"])
        self.assertTrue((directory / "task-evidence.json").exists())

    def test_task_setup_interrupt_survives_secondary_collection_failure(self):
        repo, _ = self.repository()
        real_git = runner.git
        def interrupted_git(repo, *args, **kwargs):
            if args[:2] == ("worktree", "add"):
                raise KeyboardInterrupt("fixture setup interrupt")
            return real_git(repo, *args, **kwargs)
        with patch.object(runner, "git", side_effect=interrupted_git):
            code, meta, directory = self.invoke(extra=["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 1, meta)
        self.assertEqual(meta["status"], "interrupted")
        self.assertEqual(self.status(directory), "interrupted")
        self.assertFalse(meta["codex_start_attempted"])
        self.assertIn("task_collection_error", meta)
        self.assertTrue(meta["secondary_errors"])

    def test_task_timeout_survives_secondary_evidence_write_failure(self):
        repo, _ = self.repository()
        real_write = runner.write_json
        def broken_evidence(path, value):
            if path.name == "task-evidence.json":
                raise OSError("fixture evidence disk full")
            return real_write(path, value)
        with patch.object(runner, "write_json", side_effect=broken_evidence):
            code, meta, directory = self.invoke("task_timeout", ["--mode", "task", "--repo", str(repo),
                                                               "--timeout-seconds", "2"])
        self.assertEqual(code, 1, meta)
        self.assertEqual(meta["status"], "timeout")
        self.assertEqual(self.status(directory), "timeout")
        self.assertIn("task_collection_error", meta)
        self.assertTrue(meta["worktree_retained"])

    def test_linux_disappearing_threads_are_tolerated_but_unreadable_threads_fail_closed(self):
        # Exercise Linux error handling without requiring a Linux host or killing real processes.
        class ProcEntry:
            name = "1234"
            def __truediv__(self, _):
                return self
            def iterdir(self):
                return iter([self])
            def read_text(self):
                raise error("fixture proc race")
        for error in (FileNotFoundError, ProcessLookupError, PermissionError):
            with self.subTest(error=error.__name__), \
                 patch.object(runner.os, "name", "posix"), patch.object(runner.sys, "platform", "linux"), \
                 patch.object(runner.os, "killpg", create=True), \
                 patch.object(runner.signal, "SIGKILL", 9, create=True), \
                 patch.object(runner, "Path", return_value=ProcEntry()):
                child = Mock(pid=456)
                if error is PermissionError:
                    with self.assertRaises(PermissionError):
                        runner.stop_task_tree(child, None)
                else:
                    runner.stop_task_tree(child, None)
                child.wait.assert_called_once()

    def test_task_temp_scope_excludes_wrapper_artifacts(self):
        repo, _ = self.repository()
        code, meta, directory = self.invoke("task_temp_probe", ["--mode", "task", "--repo", str(repo)])
        self.assertEqual(code, 0, meta)
        scratch = Path(meta["task_tmp_directory"])
        self.assertEqual(scratch, directory / "task-tmp")
        self.assertTrue(meta["task_tmp_retained"])
        self.assertEqual((scratch / "probe.txt").read_text(), "scratch works")
        command = self.commands[0]
        overrides = dict(value.split("=", 1) for i, value in enumerate(command) if i and command[i - 1] == "-c")
        self.assertEqual(json.loads(overrides["default_permissions"]), meta["task_permission_profile"])
        prefix = "permissions." + meta["task_permission_profile"] + "."
        self.assertEqual(overrides[prefix + "extends"], '":workspace"')
        self.assertEqual(overrides[prefix + "network.enabled"], "false")
        filesystem = overrides[prefix + "filesystem"]
        for rule in ('":workspace_roots"={"."="read"}', '":tmpdir"="read"', '":slash_tmp"="read"',
                     json.dumps(str(directory)) + '="read"',
                     json.dumps(meta["task_worktree"]) + '="write"', json.dumps(str(scratch)) + '="write"'):
            self.assertIn(rule, filesystem)
        self.assertTrue(meta["task_permission_verified"])
        self.assertNotIn("--sandbox", command)
        self.assertFalse(any(key.startswith("sandbox_workspace_write.") for key in overrides))
        self.assertEqual(len(self.permission_preflights), 2)
        for _, cwd, environment in self.permission_preflights:
            self.assertEqual(cwd, Path(meta["task_worktree"]))
            self.assertEqual(environment["TMPDIR"], str(scratch))
        checked = self.permission_preflights[-1][0]
        self.assertEqual([value for i, value in enumerate(checked) if i and checked[i - 1] == "-c"],
                         [value for i, value in enumerate(command) if i and command[i - 1] == "-c"])
        shell_temp = {name: json.loads(value) for name, value in re.findall(
            r'(TEMP|TMP|TMPDIR)=("(?:\\.|[^"\\])*")', overrides["shell_environment_policy.set"])}
        for name in ("TMP", "TEMP", "TMPDIR"):
            self.assertEqual(self.environments[0][name], str(scratch))
            self.assertEqual(shell_temp[name], str(scratch))
        # Review mode has neither task-specific sandbox overrides nor a replacement environment.
        self.invoke(name="review")
        self.assertIsNone(self.environments[-1])
        self.assertFalse(any(value.startswith("sandbox_workspace_write.") for value in self.commands[-1]))

    def test_task_permission_fallback_or_unverified_config_never_starts_model(self):
        repo, _ = self.repository()
        for mode in ("task_permission_fallback", "task_permission_unrelated_error",
                     "task_permission_malformed", "task_permission_rejected"):
            with self.subTest(mode=mode):
                code, meta, _ = self.invoke(mode, ["--mode", "task", "--repo", str(repo)], name=mode)
                self.assertEqual(code, 1, meta)
                self.assertEqual(meta["status"], "error")
                self.assertFalse(meta["codex_start_attempted"])
                self.assertIsNot(meta.get("task_permission_verified"), True)
                self.assertTrue(Path(meta["task_worktree"]).is_dir())
        self.assertEqual(self.commands, [])

    @unittest.skipUnless(os.name == "nt", "Windows native execution preflight")
    def test_task_execution_probe_requires_working_enforced_sandbox(self):
        repo, _ = self.repository()
        for mode in ("task_sandbox_blocked", "task_sandbox_missing_marker"):
            with self.subTest(mode=mode):
                code, meta, _ = self.invoke(mode, ["--mode", "task", "--repo", str(repo)], name=mode)
                self.assertEqual(code, 1, meta)
                self.assertFalse(meta["task_execution_verified"])
                self.assertFalse(meta["codex_start_attempted"])
                self.assertTrue(meta["task_permission_verified"])
                self.assertTrue(meta["worktree_retained"])
        self.assertEqual(self.commands, [])

    @unittest.skipUnless(os.name == "nt", "Windows native execution preflight")
    def test_task_dry_run_explicitly_selects_mxc_and_checks_execution(self):
        repo, _ = self.repository()
        code, meta, _ = self.invoke(extra=["--mode", "task", "--repo", str(repo), "--dry-run"])
        self.assertEqual(code, 0, meta)
        self.assertTrue(meta["task_execution_verified"])
        self.assertFalse(meta["codex_start_attempted"])
        self.assertEqual(len(self.execution_preflights), 1)
        command, cwd, environment = self.execution_preflights[0]
        self.assertIn('windows.sandbox="mxc"', command)
        self.assertIn("--include-managed-config", command)
        self.assertEqual(command[command.index("--permission-profile") + 1], meta["task_permission_profile"])
        self.assertEqual(cwd, Path(meta["task_worktree"]))
        self.assertEqual(environment["TMPDIR"], meta["task_tmp_directory"])
        self.assertIn("-I", command)
        self.assertIn("-S", command)
        self.assertEqual(self.commands, [])

    def test_task_evidence_refuses_preexisting_output_directory_or_file(self):
        repo, head = self.repository()
        (repo / "new.txt").write_text("task output", encoding="utf-8")
        for kind in ("directory", "file"):
            with self.subTest(kind=kind):
                directory = self.root / kind
                directory.mkdir()
                evidence = directory / "task-untracked"
                if kind == "directory":
                    evidence.mkdir()
                    sentinel = evidence / "new.txt"
                else:
                    sentinel = evidence
                sentinel.write_text("must survive", encoding="utf-8")
                with self.assertRaises((FileExistsError, ValueError)):
                    runner.collect_task_evidence(repo, head, directory)
                self.assertEqual(sentinel.read_text(), "must survive")
                self.assertFalse((directory / "task-evidence.json").exists())

    def test_code_grounded_unlocated_findings(self):
        value = {"complete": True, "summary": "", "limitations": [], "findings": [
            {"priority": "P2", "file": "", "line": 0, "title": "document", "body": "text"}]}
        runner.validate_review(value, repository=True, allow_unlocated=True)
        for name, line in (("", 1), ("a.txt", 0), ("/outside.py", 1), ("../a.py", 1)):
            value["findings"][0].update(file=name, line=line)
            with self.subTest(file=name, line=line), self.assertRaises(ValueError):
                runner.validate_review(value, repository=True, allow_unlocated=True)


if __name__ == "__main__":
    unittest.main()
