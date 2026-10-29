"""Offline coverage for a narrowly classified, no-observed-work task retry."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_runner

runner = test_runner.runner
FIXTURE = Path(__file__).with_name("routing-failure.jsonl")


class ConnectionRetryTests(unittest.TestCase):
    def setUp(self):
        test_runner.RunnerTests.setUp(self)
        self.wait_budgets = []
    tearDown = test_runner.RunnerTests.tearDown
    invoke = test_runner.RunnerTests.invoke
    repository = test_runner.RunnerTests.repository
    interrupt_first_wait = staticmethod(test_runner.RunnerTests.interrupt_first_wait)

    def fake_popen(self, command, **kwargs):
        if command[0] == test_runner.sys.executable and command[1:3] == ["exec", "--strict-config"]:
            if getattr(self, "succeed_second", False) and self.commands:
                kwargs["env"] = {**kwargs["env"], "DELEGATOR_TEST_MODE": "success"}
        child = test_runner.RunnerTests.fake_popen(self, command, **kwargs)
        if child in self.children:
            real_wait, calls = child.wait, []
            def wait(timeout=None):
                if not calls:
                    self.wait_budgets.append(timeout)
                    calls.append(timeout)
                return real_wait(timeout=timeout)
            child.wait = wait
        return child

    def task(self, mode="routing", extra=(), **kwargs):
        repo, _ = self.repository()
        with patch.object(runner, "CONNECTION_RETRY_DELAY", 0.01):
            return self.invoke(mode, ["--mode", "task", "--repo", str(repo), *extra], **kwargs)

    def test_second_attempt_succeeds_and_preserves_first_diagnostics(self):
        self.succeed_second = True
        code, meta, directory = self.task(extra=["--model", "fixture-model", "--effort", "high"])
        self.assertEqual(code, 0, meta)
        self.assertEqual(len(self.commands), 2)
        self.assertEqual(self.commands[0], self.commands[1])
        self.assertEqual(len(self.wait_budgets), 2)
        self.assertLess(self.wait_budgets[1], self.wait_budgets[0])
        self.assertEqual(self.environments[0], self.environments[1] | {"DELEGATOR_TEST_MODE": "routing"})
        self.assertEqual(meta["connection_retry_count"], 1)
        self.assertEqual(meta["connection_retry_reason"], "workspace routing discovery failed")
        first = directory / "attempts/attempt-1"
        self.assertEqual((first / "stream.jsonl").read_text(), FIXTURE.read_text())
        self.assertEqual((first / "stderr.log").read_text().strip(), "routing fixture stderr")
        archived = json.loads((first / "metadata.json").read_text())
        self.assertEqual(archived["status"], "incomplete")
        self.assertEqual(archived["exit_code"], 1)
        self.assertEqual(json.loads((first / "status.json").read_text())["status"], "incomplete")
        self.assertEqual(json.loads((first / "lifecycle-status.json").read_text())["status"], "running")
        self.assertTrue(archived["task_process_tree_terminated"])
        self.assertFalse(json.loads((first / "result.json").read_text())["complete"])
        self.assertEqual(json.loads((directory / "attempts/attempt-2/attempt.json").read_text())["status"], "complete")
        self.assertIn(b"turn.completed", (directory / "stream.jsonl").read_bytes())
        self.assertTrue(meta["cleanup_complete"])

    def test_repeated_failure_is_bounded_to_two_calls(self):
        code, meta, directory = self.task()
        self.assertEqual(code, 1, meta)
        self.assertEqual(len(self.commands), 2)
        self.assertEqual(meta["status"], "incomplete")
        self.assertEqual(meta["connection_retry_count"], 1)
        self.assertEqual(len(meta["attempts"]), 2)
        self.assertTrue((directory / "attempts/attempt-2/attempt.json").exists())

    def test_opt_out_never_retries(self):
        _, meta, _ = self.task(extra=["--connection-retries", "0"])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["connection_retry_count"], 0)

    def test_review_mode_never_retries(self):
        _, meta, _ = self.invoke("routing", extra=["--connection-retries", "1"])
        self.assertEqual(len(self.commands), 1)
        self.assertNotIn("connection_retry_count", meta)

    def test_classifier_rejects_any_work_unknown_or_usage_at_any_stage(self):
        original = FIXTURE.read_text()
        extras = [
            {"type": "item.started", "item": {"id": "tool", "type": "command_execution"}},
            {"type": "item.updated", "item": {"id": "tool", "type": "file_change"}},
            {"type": "item.completed", "item": {"id": "model", "type": "agent_message", "text": "partial"}},
            {"type": "item.completed", "item": {"id": "model", "type": "reasoning", "text": "thinking"}},
            {"type": "future.event"}, {"type": "usage", "usage": {"output_tokens": 0}},
            {"type": "turn.completed", "usage": {}},
            {"type": "error", "message": "timeout: workspace routing discovery failed"},
            {"type": "error", "message": "Reconnecting... 6/5 (workspace routing discovery failed)"},
            {"type": "thread.started", "thread_id": "again"},
            {"type": "turn.started"},
        ]
        candidate = self.root / "candidate.jsonl"
        self.assertEqual(runner.connection_failure(FIXTURE), "workspace routing discovery failed")
        for event in extras:
            with self.subTest(event=event):
                lines = original.splitlines()
                lines.insert(-1, json.dumps(event))
                candidate.write_text("\n".join(lines) + "\n")
                self.assertIsNone(runner.connection_failure(candidate))
        for text in (original.rstrip(), original + '{"type":', original + "\n", original.replace(
                '"type":"turn.started"', '"type":"turn.started","usage":{}'),
                original.replace('"type":"turn.started"', '"type":"turn.started","type":"turn.started"')):
            candidate.write_text(text)
            self.assertIsNone(runner.connection_failure(candidate))

    def test_tool_started_and_malformed_stream_do_not_retry(self):
        repo, _ = self.repository()
        for mode, extra_event in (("routing", '{"type":"item.started","item":{"type":"command_execution"}}'),
                                  ("routing_malformed", "")):
            with self.subTest(mode=mode):
                previous = len(self.commands)
                _, meta, _ = self.invoke(mode, ["--mode", "task", "--repo", str(repo)], name=mode,
                                        env={"DELEGATOR_TEST_ROUTING_EXTRA": extra_event})
                self.assertEqual(len(self.commands), previous + 1)
                self.assertEqual(meta["connection_retry_count"], 0)

    def test_worktree_index_ignored_scratch_and_final_output_block_retry(self):
        repo, _ = self.repository()
        (repo / ".gitignore").write_text("ignored.tmp\n")
        runner.git(repo, "add", ".gitignore")
        runner.git(repo, "commit", "-m", "ignore test output")
        for mode in ("routing_changed", "routing_index", "routing_ignored", "routing_scratch", "routing_final"):
            with self.subTest(mode=mode):
                previous = len(self.commands)
                _, meta, _ = self.invoke(mode, ["--mode", "task", "--repo", str(repo)], name=mode)
                self.assertEqual(len(self.commands), previous + 1)
                self.assertEqual(meta["connection_retry_count"], 0)
                if mode != "routing_final":
                    self.assertIn("No-work verification failed", meta["connection_retry_disabled_reason"])

    def test_guard_uncertainty_does_not_block_initial_call(self):
        with patch.object(runner, "retry_task_state", side_effect=OSError("inventory unavailable")):
            _, meta, _ = self.task()
        self.assertEqual(len(self.commands), 1)
        self.assertIn("Baseline unavailable", meta["connection_retry_disabled_reason"])

    def test_inventory_requires_existing_readable_real_root(self):
        scratch = self.root / "scratch"
        scratch.mkdir()
        self.assertTrue(runner.retry_tree_state(scratch))
        scratch.rmdir()
        with self.assertRaises(FileNotFoundError):
            runner.retry_tree_state(scratch)
        scratch.write_text("replaced by file")
        with self.assertRaises(ValueError):
            runner.retry_tree_state(scratch)
        scratch.unlink()
        scratch.mkdir()
        info = scratch.lstat()
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)):
            with self.assertRaises(ValueError):
                runner.retry_tree_state(scratch)
        def unreadable_walk(root, *, followlinks, onerror):
            onerror(PermissionError("unreadable subtree"))
            return iter(())
        with patch.object(runner.os, "walk", side_effect=unreadable_walk):
            with self.assertRaises(PermissionError):
                runner.retry_tree_state(scratch)

    def test_missing_scratch_after_initial_failure_blocks_retry(self):
        original = runner.retry_task_state
        calls = []
        def missing(worktree, scratch):
            calls.append(scratch)
            if len(calls) == 2:
                scratch.rmdir()
            return original(worktree, scratch)
        with patch.object(runner, "retry_task_state", side_effect=missing):
            _, meta, _ = self.task()
        self.assertEqual(len(self.commands), 1)
        self.assertIn("No-work verification failed", meta["connection_retry_disabled_reason"])

    def test_cleanup_uncertainty_prevents_retry(self):
        original = runner.stop_task_tree
        def uncertain(child, job):
            original(child, job)
            if child in self.children:
                raise runner.ProcessCleanupError("termination uncertain")
        with patch.object(runner, "stop_task_tree", side_effect=uncertain):
            _, meta, _ = self.task()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "cleanup_failed")
        self.assertFalse(meta["task_process_tree_terminated"])

    def test_artifact_collision_blocks_retry_without_overwrite(self):
        original = runner.archive_connection_attempt
        def collision(directory, *args):
            destination = directory / "attempts/attempt-1"
            destination.mkdir(parents=True)
            (destination / "stream.jsonl").write_bytes(b"sentinel")
            return original(directory, *args)
        with patch.object(runner, "archive_connection_attempt", side_effect=collision):
            _, meta, directory = self.task()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual((directory / "attempts/attempt-1/stream.jsonl").read_bytes(), b"sentinel")
        self.assertEqual(meta["status"], "artifact_error")

    def test_delay_is_interruptible_and_retains_first_call(self):
        original = runner.time.sleep
        def interrupt_delay(seconds):
            if seconds == 5:
                self.assertEqual(self.status(self.root / "run"), "retry_wait")
                raise KeyboardInterrupt("Signal 15")
            original(seconds)
        repo, _ = self.repository()
        with patch.object(runner.time, "sleep", side_effect=interrupt_delay):
            _, meta, directory = self.invoke("routing", ["--mode", "task", "--repo", str(repo)])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "interrupted")
        self.assertEqual(meta["connection_retry_count"], 0)
        self.assertTrue((directory / "attempts/attempt-1/stream.jsonl").exists())

    def test_budget_expiry_during_delay_does_not_launch_second_call(self):
        original = runner.time.monotonic
        offset = [0]
        def expire_delay(seconds):
            if seconds == 5:
                offset[0] = 1801
        repo, _ = self.repository()
        with patch.object(runner.time, "monotonic", side_effect=lambda: original() + offset[0]), \
             patch.object(runner.time, "sleep", side_effect=expire_delay):
            _, meta, _ = self.invoke("routing", ["--mode", "task", "--repo", str(repo)])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "timeout")
        self.assertEqual(meta["connection_retry_count"], 0)

    def test_second_starting_status_delay_cannot_launch_after_deadline(self):
        original_clock, original_write = runner.time.monotonic, runner.write_json
        original_stop = runner.stop_task_tree
        offset, empty_job_cleanup = [0], []
        def delayed_status(path, value):
            original_write(path, value)
            if path.name == "status.json" and value["status"] == "starting" and value["attempt_number"] == 2:
                offset[0] = 1801
        def stopped(child, job):
            if child is None:
                empty_job_cleanup.append(job)
            return original_stop(child, job)
        with patch.object(runner.time, "monotonic", side_effect=lambda: original_clock() + offset[0]), \
             patch.object(runner, "write_json", side_effect=delayed_status), \
             patch.object(runner, "stop_task_tree", side_effect=stopped):
            code, meta, directory = self.task()
        self.assertEqual(code, 1)
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "timeout")
        self.assertEqual(meta["connection_retry_count"], 0)
        self.assertFalse(meta["attempts"][-1]["codex_started"])
        self.assertTrue(meta["task_process_tree_terminated"])
        self.assertEqual(len(empty_job_cleanup), 1)
        if os.name == "nt":
            self.assertIsNotNone(empty_job_cleanup[0])
            self.assertIsNone(empty_job_cleanup[0].handle)
            self.assertTrue(empty_job_cleanup[0].termination_confirmed)
        self.assertTrue((directory / "attempts/attempt-1/stream.jsonl").exists())

    def test_state_change_during_delay_prevents_second_call(self):
        def changed_delay(seconds):
            if seconds == 5:
                (self.root / "run/task-tmp/changed").write_text("external change")
        repo, _ = self.repository()
        with patch.object(runner.time, "sleep", side_effect=changed_delay):
            _, meta, _ = self.invoke("routing", ["--mode", "task", "--repo", str(repo)])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "incomplete")
        self.assertIn("changed during retry delay", meta["connection_retry_disabled_reason"])

    status = staticmethod(test_runner.RunnerTests.status)

    def test_insufficient_timeout_does_not_schedule_retry(self):
        repo, _ = self.repository()
        _, meta, _ = self.invoke("routing", ["--mode", "task", "--repo", str(repo), "--timeout-seconds", "1"])
        self.assertEqual(len(self.commands), 1)
        self.assertIn("Insufficient remaining timeout", meta["connection_retry_disabled_reason"])

    def test_timeout_and_interrupt_never_retry(self):
        _, meta, _ = self.task("routing_timeout", extra=["--timeout-seconds", "1"])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "timeout")
        self.interrupt = True
        repo = self.root / "repo"
        _, meta, _ = self.invoke("routing", ["--mode", "task", "--repo", str(repo)], name="interrupt")
        self.assertEqual(len(self.commands), 2)
        self.assertEqual(meta["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
