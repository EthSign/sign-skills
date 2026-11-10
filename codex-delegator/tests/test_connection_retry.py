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
TRANSPORT_CAUSES = (
    ("failed to lookup address information: Temporary failure in name resolution", "dns resolution failed"),
    ("failed to lookup address information: Name or service not known", "dns resolution failed"),
    ("No such host is known. (os error 11001)", "dns resolution failed"),
    ("This is usually a temporary error during hostname resolution and means that the local server did not "
     "receive a response from an authoritative server. (os error 11002)", "dns resolution failed"),
    ("Connection refused (os error 111)", "connection refused"),
    ("No connection could be made because the target machine actively refused it. (os error 10061)", "connection refused"),
    ("Connection reset by peer (os error 104)", "connection reset"),
    ("An existing connection was forcibly closed by the remote host. (os error 10054)", "connection reset"),
    ("Connection timed out (os error 110)", "connection timed out"),
    ("A connection attempt failed because the connected party did not properly respond after a period of time, "
     "or established connection failed because connected host has failed to respond. (os error 10060)", "connection timed out"),
    ("failed to lookup address information: Name does not resolve", "dns resolution failed"),
    ("failed to lookup address information: Try again", "dns resolution failed"),
    ("failed to lookup address information: No address associated with hostname", "dns resolution failed"),
    ("Operation timed out (os error 110)", "connection timed out"),
)


def transport_events(message, counter="2/5"):
    return [
        {"type": "thread.started", "thread_id": "offline-transport"},
        {"type": "turn.started"},
        {"type": "error", "message": f"Reconnecting... {counter} ({message})"},
        {"type": "item.completed", "item": {"id": "fallback", "type": "error",
         "message": "Falling back from WebSockets to HTTPS transport. " + message}},
        {"type": "error", "message": message},
        {"type": "turn.failed", "error": {"message": message}},
    ]


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

    def test_native_transport_causes_and_envelopes(self):
        candidate = self.root / "transport.jsonl"
        for cause, expected in TRANSPORT_CAUSES:
            for io_prefix in ("", "IO error: "):
                for counter in ("2/5", "4/4", "10/10"):
                    with self.subTest(cause=cause, io_prefix=io_prefix, counter=counter):
                        message = "stream disconnected before completion: " + io_prefix + cause
                        candidate.write_text("".join(json.dumps(e) + "\n" for e in transport_events(message, counter)))
                        self.assertEqual(runner.connection_failure(candidate), expected)

    def test_ambiguous_and_nonconnection_errors_never_qualify(self):
        messages = (
            "request timed out", "Connection failed: error sending request",
            'Connection failed: error sending request for url ("https://example.invalid")',
            "stream disconnected before completion: error sending request",
            "stream disconnected before completion: idle timeout waiting for SSE",
            "stream disconnected before completion: IO error: invalid peer certificate: UnknownIssuer",
            "stream disconnected before completion: IO error: Permission denied (os error 13)",
            "stream disconnected before completion: IO error: Connection refused (os error 13)",
            "stream disconnected before completion: HTTP error 401: Connection reset by peer (os error 104)",
            "stream disconnected before completion: unexpected status 503 Service Unavailable",
            "stream disconnected before completion: rate limit exceeded: request timed out",
            "stream disconnected before completion: invalid model: Connection refused (os error 111)",
            "stream disconnected before completion: Connection refused (os error 111); authentication failed",
            "Connection refused (os error 111)",
        )
        candidate = self.root / "rejected.jsonl"
        for message in messages:
            with self.subTest(message=message):
                candidate.write_text("".join(json.dumps(e) + "\n" for e in transport_events(message)))
                self.assertIsNone(runner.connection_failure(candidate))

    def test_transport_errors_after_work_or_unknown_events_never_qualify(self):
        candidate = self.root / "work-before-failure.jsonl"
        activities = [
            {"type": "item.started", "item": {"id": "cmd", "type": "command_execution"}},
            {"type": "item.updated", "item": {"id": "file", "type": "file_change"}},
            {"type": "item.completed", "item": {"id": "msg", "type": "agent_message", "text": "partial"}},
            {"type": "item.completed", "item": {"id": "thought", "type": "reasoning", "text": "thinking"}},
            {"type": "item.started", "item": {"id": "mcp", "type": "mcp_tool_call"}},
            {"type": "turn.completed", "usage": {"output_tokens": 0}},
            {"type": "usage", "usage": {}}, {"type": "future.event"},
        ]
        for cause, _ in TRANSPORT_CAUSES:
            for activity in activities:
                with self.subTest(cause=cause, activity=activity):
                    events = transport_events("stream disconnected before completion: " + cause)
                    events.insert(2, activity)
                    candidate.write_text("".join(json.dumps(e) + "\n" for e in events))
                    self.assertIsNone(runner.connection_failure(candidate))

    def test_mixed_errors_and_invalid_counters_do_not_qualify(self):
        candidate = self.root / "mixed.jsonl"
        message = "stream disconnected before completion: Connection refused (os error 111)"
        for index in (2, -1):
            events = transport_events(message)
            events[index] = ({"type": "error", "message": "HTTP 401: authentication failed"} if index == 2
                             else {"type": "turn.failed", "error": {"message": "request timed out"}})
            candidate.write_text("".join(json.dumps(e) + "\n" for e in events))
            self.assertIsNone(runner.connection_failure(candidate))
        for counter in ("6/5", "0/5", "1/0", "-1/5", "1/five"):
            candidate.write_text("".join(json.dumps(e) + "\n" for e in transport_events(message, counter)))
            self.assertIsNone(runner.connection_failure(candidate))
        for value in (None, 1, [], {}):
            events = transport_events(message)
            events[-1]["error"]["message"] = value
            candidate.write_text("".join(json.dumps(e) + "\n" for e in events))
            self.assertIsNone(runner.connection_failure(candidate))

    def test_transport_families_can_recover_once(self):
        repo, _ = self.repository()
        self.succeed_second = True
        for index in (2, 5, 7, 9):
            cause, expected = TRANSPORT_CAUSES[index]
            with self.subTest(expected=expected):
                self.commands.clear()
                with patch.object(runner, "CONNECTION_RETRY_DELAY", 0.01):
                    code, meta, directory = self.invoke("routing", ["--mode", "task", "--repo", str(repo)],
                        name="transport-" + str(index),
                        env={"DELEGATOR_TEST_CONNECTION_ERROR": "stream disconnected before completion: " + cause})
                self.assertEqual(code, 0, meta)
                self.assertEqual(len(self.commands), 2)
                self.assertEqual(self.commands[0], self.commands[1])
                self.assertEqual(meta["connection_retry_count"], 1)
                self.assertEqual(meta["connection_retry_reason"], expected)
                self.assertTrue((directory / "attempts/attempt-1/stream.jsonl").is_file())

    def test_transport_failures_retain_work_and_opt_out_guards(self):
        repo, _ = self.repository()
        message = "stream disconnected before completion: IO error: Connection reset by peer (os error 104)"
        for name, mode, extra, activity in (
                ("changed", "routing_changed", [], ""),
                ("started", "routing", [], '{"type":"item.started","item":{"type":"command_execution"}}'),
                ("disabled", "routing", ["--connection-retries", "0"], "")):
            with self.subTest(name=name):
                self.commands.clear()
                code, meta, directory = self.invoke(mode, ["--mode", "task", "--repo", str(repo), *extra], name=name,
                    env={"DELEGATOR_TEST_CONNECTION_ERROR": message, "DELEGATOR_TEST_ROUTING_EXTRA": activity})
                self.assertEqual(code, 1)
                self.assertEqual(len(self.commands), 1)
                self.assertEqual(meta["connection_retry_count"], 0)
                if name == "changed":
                    self.assertEqual((directory / "worktree/a.txt").read_text(), "partial work\n")
                    self.assertEqual(runner.connection_failure(directory / "stream.jsonl"), "connection reset")
                    self.assertIn("No-work verification failed:", meta["connection_retry_disabled_reason"])
                elif name == "started":
                    self.assertIn("Event stream is not a recognized connection failure without observed work",
                                  meta["connection_retry_disabled_reason"])
                    events = [json.loads(line) for line in (directory / "stream.jsonl").read_text().splitlines()]
                    control = self.root / "without-started-item.jsonl"
                    control.write_text("".join(json.dumps(e) + "\n" for e in events if e["type"] != "item.started"))
                    self.assertEqual(runner.connection_failure(control), "connection reset")
                else:
                    self.assertEqual(meta["connection_retries_requested"], 0)
                    self.assertEqual(runner.connection_failure(directory / "stream.jsonl"), "connection reset")

    def test_cause_erasing_http_fallback_remains_ineligible(self):
        repo, _ = self.repository()
        for index, terminal in enumerate(("Connection failed: error sending request", "request timed out")):
            self.commands.clear()
            _, meta, directory = self.invoke("routing", ["--mode", "task", "--repo", str(repo)],
                name="opaque-fallback-" + str(index), env={
                    "DELEGATOR_TEST_CONNECTION_ERROR": "stream disconnected before completion: No such host is known. (os error 11001)",
                    "DELEGATOR_TEST_HTTP_FALLBACK_ERROR": terminal})
            self.assertEqual(len(self.commands), 1)
            self.assertEqual(meta["connection_retry_count"], 0)
            self.assertIn("Event stream is not a recognized connection failure without observed work",
                          meta["connection_retry_disabled_reason"])
            self.assertIn("Falling back from WebSockets to HTTPS", (directory / "stream.jsonl").read_text())

    def test_reconnect_sequence_is_consistent_until_one_fallback(self):
        message = "stream disconnected before completion: Connection refused (os error 111)"
        candidate = self.root / "counter-sequence.jsonl"
        for next_counter in ("2/5", "1/5", "3/10"):
            events = transport_events(message)
            events.insert(3, {"type": "error", "message": f"Reconnecting... {next_counter} ({message})"})
            candidate.write_text("".join(json.dumps(e) + "\n" for e in events))
            self.assertIsNone(runner.connection_failure(candidate))
        events = transport_events(message)
        events.insert(4, {"type": "error", "message": f"Reconnecting... 1/3 ({message})"})
        candidate.write_text("".join(json.dumps(e) + "\n" for e in events))
        self.assertEqual(runner.connection_failure(candidate), "connection refused")
        events.insert(5, {"type": "item.completed", "item": {"id": "second-fallback", "type": "error", "message":
                      "Falling back from WebSockets to HTTPS transport. " + message}})
        candidate.write_text("".join(json.dumps(e) + "\n" for e in events))
        self.assertIsNone(runner.connection_failure(candidate))

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
                self.assertIn("Event stream is not a recognized connection failure without observed work",
                              meta["connection_retry_disabled_reason"])

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

    def test_partial_archive_failure_preserves_original_error(self):
        original = runner.shutil.copyfileobj
        def disk_full(source, destination, *args, **kwargs):
            if Path(source.name).name == "stderr.log":
                destination.write(b"partial")
                raise OSError(28, "archive disk full")
            return original(source, destination, *args, **kwargs)
        with patch.object(runner.shutil, "copyfileobj", side_effect=disk_full):
            _, meta, directory = self.task()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "artifact_error")
        self.assertIn("archive disk full", meta["attempt_artifact_error"])
        self.assertNotIn("FileExistsError", meta["attempt_artifact_error"])
        self.assertEqual((directory / "attempts/attempt-1/stderr.log").read_bytes(), b"partial")
        self.assertEqual((directory / "stream.jsonl").read_text(), FIXTURE.read_text())
        self.assertEqual(meta["attempts"][0]["status"], "artifact_error")

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

    def test_post_delay_inventory_failure_keeps_exception_type(self):
        original = runner.retry_task_state
        calls = []
        def unavailable(worktree, scratch):
            calls.append(worktree)
            if len(calls) == 3:
                raise PermissionError("retry inventory denied")
            return original(worktree, scratch)
        with patch.object(runner, "retry_task_state", side_effect=unavailable):
            _, meta, _ = self.task()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(meta["status"], "incomplete")
        self.assertIn("No-work verification failed: PermissionError: retry inventory denied",
                      meta["connection_retry_disabled_reason"])

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
