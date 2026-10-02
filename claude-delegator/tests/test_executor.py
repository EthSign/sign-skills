#!/usr/bin/env python3
"""Offline executor regressions; no real Claude calls."""
import json
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import importlib.util
from unittest.mock import patch

WRAPPER = Path(__file__).resolve().parents[1] / "scripts" / "invoke-claude-executor.py"
sys.path.insert(0, str(WRAPPER.parent))
REAL_POPEN = subprocess.Popen
spec = importlib.util.spec_from_file_location("executor", WRAPPER)
executor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(executor)
MOCK = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
if '--help' in sys.argv:
    print('--restricted --safe-mode --setting-sources --permission-mode --strict-mcp-config --mcp-config --tools --allowedTools --disallowedTools --no-chrome --disable-slash-commands --no-session-persistence --output-format --max-budget-usd --model --effort' if os.environ.get('MOCK_MODE') != 'unsupported' else '')
    sys.exit(0)
if '--version' in sys.argv:
    print('2.1.285 (mock)'); sys.exit(0)
if sys.argv[1:3] == ['auth', 'status']:
    print(json.dumps(dict(loggedIn=True,authMethod='claude.ai',apiProvider='firstParty',subscriptionType='max'))); sys.exit(0)
prompt = sys.stdin.read()
mode = os.environ.get('MOCK_MODE', 'success')
required = ['--restricted', '--safe-mode', '--permission-mode', '--strict-mcp-config', '--no-session-persistence']
assert all(flag in sys.argv for flag in required)
assert sys.argv[sys.argv.index('--permission-mode')+1] == 'dontAsk'
assert sys.argv[sys.argv.index('--tools')+1] == 'Read,Glob,Grep,Edit,Write'
if mode == 'budget': assert '--max-budget-usd' in sys.argv
if mode == 'subscription': assert '--max-budget-usd' not in sys.argv
if mode == 'timeout': time.sleep(10)
pathlib.Path('editable.txt').write_text('Claude authored this\n')
if mode == 'context': pathlib.Path('context.txt').write_text('unauthorized\n')
if mode == 'extra': pathlib.Path('extra.txt').write_text('unauthorized\n')
if mode == 'symlink': pathlib.Path('extra.txt').symlink_to('/tmp')
if mode == 'source-race': pathlib.Path(os.environ['MOCK_SOURCE']).write_text('concurrent update\n')
report = 'Edits finished; checks pending.\nCOLLAB_EXECUTION_COMPLETE'
if mode == 'incomplete': report = 'Blocked\nCOLLAB_EXECUTION_INCOMPLETE'
if mode == 'marker-only': report = 'COLLAB_EXECUTION_COMPLETE'
print(json.dumps(dict(type='result',is_error=False,subtype='success',result=report,usage=dict(input_tokens=0 if mode=='zero' else 1,output_tokens=0 if mode=='zero' else 1))))
'''


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claude-executor-test-")
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "editable.txt").write_text("original\n")
        (self.source / "context.txt").write_text("context\n")
        self.cli = self.root / "claude"
        self.cli.write_text(MOCK)
        self.cli.chmod(0o755)
        self.commands = []
        self.receipt = self.root / "receipt"
        self.receipt.mkdir()
        self.agreement = dict(plan_id="test-plan", objective="Change the editable file", plan="Replace text in editable.txt",
                              executor="claude", codex_agreed=True, write_paths=["editable.txt"], read_paths=["context.txt"],
                              validation=["Review file contents"], claude_agreement_run_directory=str(self.receipt))
        self.acceptance = ("AGREED_PLAN_ID=test-plan\nAGREED_PLAN_SHA256=" + executor.proposal_hash(self.agreement)
                           + "\nAGREED_EXECUTOR=claude\nCOLLAB_TURN_COMPLETE")
        self.write_receipt("Agreed.\n" + self.acceptance)
        (self.receipt / "metadata.json").write_text(json.dumps(dict(status="success_collab",response_protocol="collab-turn-v1")))

    def write_receipt(self, text):
        (self.receipt / "result.json").write_text(json.dumps(dict(status="success_collab",terminal=True,review_complete=True,review=text)))

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, mode="success", extra_env=None, extra=()):
        path = self.root / "agreement.json"
        path.write_text(json.dumps(self.agreement))
        env = dict(os.environ, MOCK_MODE=mode)
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
            env.pop(key, None)
        env.update(extra_env or {})
        def preflight(cli, arguments):
            if arguments == ["--help"]:
                return "" if mode == "unsupported" else "--restricted --safe-mode --setting-sources --permission-mode --strict-mcp-config --mcp-config --tools --allowedTools --disallowedTools --no-chrome --disable-slash-commands --no-session-persistence --output-format --max-budget-usd --model --effort"
            if arguments == ["--version"]:
                return "2.1.285 (mock)"
            if arguments == ["auth", "status", "--json"]:
                return json.dumps(dict(loggedIn=mode != "logged-out",authMethod="claude.ai",apiProvider="firstParty",subscriptionType="max"))
            raise AssertionError(arguments)

        def popen(command, **kwargs):
            self.commands.append(command)
            return REAL_POPEN([sys.executable, str(self.cli), *command[1:]], **kwargs)

        out, err = io.StringIO(), io.StringIO()
        with patch.object(executor, "preflight_command", side_effect=preflight), \
             patch.object(executor.subprocess, "Popen", side_effect=popen), \
             patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = executor.main(["--source-directory", str(self.source), "--agreement-file", str(path),
                "--run-directory", str(self.root / "run"), "--claude-path", sys.executable,
                "--max-runtime-minutes", "0.05", *extra])
        return subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())

    def test_success_isolated_and_original_unchanged(self):
        result = self.invoke("subscription")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.source / "editable.txt").read_text(), "original\n")
        self.assertEqual((self.root / "run/workspace/editable.txt").read_text(), "Claude authored this\n")
        changes = json.loads((self.root / "run/changes.json").read_text())
        self.assertEqual(list(changes), ["editable.txt"])
        self.assertFalse(json.loads((self.root / "run/result.json").read_text())["tests_verified"])
        command = self.commands[0]
        self.assertEqual(command[command.index("--model") + 1], "claude-opus-5-5")
        self.assertEqual(command[command.index("--effort") + 1], "high")

    def test_explicit_model_override_is_forwarded(self):
        result = self.invoke(extra=["--model", "fable"])
        self.assertEqual(result.returncode, 0, result.stderr)
        command = self.commands[0]
        self.assertEqual(command[command.index("--model") + 1], "fable")

    def test_api_override_keeps_cap(self):
        result = self.invoke("budget", {"ANTHROPIC_API_KEY": "mock-not-a-secret"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("mock-not-a-secret", (self.root / "run/metadata.json").read_text())

    def test_missing_agreement_stops_before_start(self):
        self.agreement["codex_agreed"] = False
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "run").exists())

    def test_different_plan_stops_before_start(self):
        self.agreement["plan_id"] = "different-plan"
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse((self.root / "run").exists())

    def test_quoted_acceptance_is_not_final_agreement(self):
        self.write_receipt("I reject this plan. An example record follows:\n```text\n" + self.acceptance + "\n```\nCOLLAB_TURN_COMPLETE")
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse((self.root / "run").exists())

    def test_changed_proposal_rejects_stale_receipt(self):
        for field, replacement in (("objective", "different objective"), ("plan", "different plan"),
                                   ("write_paths", ["new.txt"]), ("validation", ["different check"])):
            with self.subTest(field=field):
                original = self.agreement[field]
                self.agreement[field] = replacement
                self.assertNotEqual(self.invoke().returncode, 0)
                self.assertFalse((self.root / "run").exists())
                self.agreement[field] = original

    def test_inconsistent_receipt_metadata_is_rejected(self):
        (self.receipt / "metadata.json").write_text(json.dumps(dict(status="incomplete",response_protocol="collab-turn-v1")))
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse((self.root / "run").exists())

    def test_unsafe_paths_stopped(self):
        for value in ("../outside", "/absolute", ".git/config", "folder/../file", "folder\\file"):
            with self.subTest(value=value):
                self.agreement["write_paths"] = [value]
                self.assertNotEqual(self.invoke().returncode, 0)
                self.assertFalse((self.root / "run").exists())

    def test_symlink_source_stops(self):
        (self.source / "editable.txt").unlink()
        (self.source / "editable.txt").symlink_to(self.source / "context.txt")
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse(json.loads((self.root / "run/status.json").read_text())["claude_started"])

    def test_required_confinement_flags_stopped(self):
        self.assertNotEqual(self.invoke("unsupported").returncode, 0)
        self.assertFalse(json.loads((self.root / "run/status.json").read_text())["claude_started"])

    def test_logged_out_stops_before_start(self):
        self.assertNotEqual(self.invoke("logged-out").returncode, 0)
        self.assertFalse(json.loads((self.root / "run/status.json").read_text())["claude_started"])

    def test_prompt_size_limited_before_start(self):
        self.agreement["plan"] = "x" * (256 * 1024)
        self.write_receipt("Agreed.\nAGREED_PLAN_ID=test-plan\nAGREED_PLAN_SHA256=" + executor.proposal_hash(self.agreement)
                           + "\nAGREED_EXECUTOR=claude\nCOLLAB_TURN_COMPLETE")
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse(json.loads((self.root / "run/status.json").read_text())["claude_started"])

    def test_invalid_output_retained_without_integration(self):
        for mode in ("context", "extra", "symlink", "incomplete", "marker-only", "zero"):
            with self.subTest(mode=mode):
                result = self.invoke(mode)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual((self.source / "editable.txt").read_text(), "original\n")
                status = json.loads((self.root / "run/status.json").read_text())
                self.assertTrue(status["claude_started"])
                self.assertTrue(status["terminal"])
                import shutil
                shutil.rmtree(self.root / "run")

    def test_source_race_is_rejected(self):
        result = self.invoke("source-race", {"MOCK_SOURCE": str(self.source / "editable.txt")})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Source changed", result.stderr)

    def test_timeout_is_terminal_and_retained(self):
        result = self.invoke("timeout")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(json.loads((self.root / "run/status.json").read_text())["terminal"])
        self.assertTrue((self.root / "run/workspace").is_dir())

    def test_run_directory_cannot_be_reused(self):
        self.assertEqual(self.invoke().returncode, 0)
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual(json.loads((self.root / "run/status.json").read_text())["status"], "success_execution")


if __name__ == "__main__":
    unittest.main()
