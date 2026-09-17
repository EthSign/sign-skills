import contextlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("delegator", ROOT / "scripts" / "invoke-codex.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
REAL_RUN, REAL_POPEN = subprocess.run, subprocess.Popen
HELP = "--ignore-user-config --ignore-rules --ephemeral --output-schema --json --strict-config --sandbox --output-last-message --skip-git-repo-check"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-codex-delegator-")
        self.root = Path(self.temp.name)
        self.prompt = self.root / "objective.txt"
        self.prompt.write_text("Review this small plan.", encoding="utf-8")
        self.children = []
        self.commands = []
        self.authenticated = True

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                runner.stop_child(child)
        self.temp.cleanup()

    def fake_run(self, command, **kwargs):
        if command[0] == sys.executable:
            if command[1:] == ["exec", "--help"]:
                return subprocess.CompletedProcess(command, 0, HELP.encode(), b"")
            if command[1:] == ["--version"]:
                return subprocess.CompletedProcess(command, 0, b"offline-codex", b"")
            if command[1:] == ["login", "status"]:
                return subprocess.CompletedProcess(command, 0 if self.authenticated else 1, b"", b"")
        return REAL_RUN(command, **kwargs)

    def fake_popen(self, command, **kwargs):
        if command[0] == sys.executable and command[1] == "exec":
            self.commands.append(command)
            child = REAL_POPEN([sys.executable, str(ROOT / "tests" / "fake_codex.py"), *command[2:]], **kwargs)
            self.children.append(child)
            return child
        return REAL_POPEN(command, **kwargs)

    def invoke(self, mode="success", extra=(), name="run"):
        run_dir = self.root / name
        args = runner.arguments(["--run-directory", str(run_dir), "--prompt-file", str(self.prompt), *extra])
        with patch.object(runner.shutil, "which", return_value=sys.executable), \
             patch.object(runner.subprocess, "run", side_effect=self.fake_run), \
             patch.object(runner.subprocess, "Popen", side_effect=self.fake_popen), \
             patch.dict(os.environ, {"DELEGATOR_TEST_MODE": mode}), contextlib.redirect_stdout(io.StringIO()):
            code = runner.run(args)
        return code, json.loads((run_dir / "metadata.json").read_text(encoding="utf-8")), run_dir

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
        with self.assertRaises(FileExistsError):
            self.invoke()
        self.assertEqual(len(self.children), 1)

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
            output = io.StringIO()
            with patch.object(runner, "write_json", side_effect=locked), contextlib.redirect_stderr(output):
                code, meta, directory = self.invoke(name="locked-" + target)
            self.assertEqual(code, 1)
            self.assertEqual(meta["status"], "artifact_error")
            self.assertTrue(meta["codex_started"])
            self.assertFalse(meta["complete"])
            self.assertIn(target, meta["artifact_errors"])
            self.assertIn("CODEX_DELEGATION_METADATA=", output.getvalue())
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


if __name__ == "__main__":
    unittest.main()
