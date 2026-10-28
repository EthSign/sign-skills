"""Offline Codex CLI fixture, invoked only by test_runner.py; never calls a model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HELP = ("--ignore-user-config --ignore-rules --ephemeral --output-schema --json --strict-config "
        "--sandbox --output-last-message --skip-git-repo-check")
mode = os.environ.get("DELEGATOR_TEST_MODE", "success")
args = sys.argv[1:]
if args == ["exec", "--help"]:
    print(HELP)
    sys.exit(0)
if args == ["--version"]:
    if mode == "preflight_hang":
        # A grandchild inheriting stdout must not extend the bounded preflight.
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        time.sleep(30)
    print("codex-cli 0.0.0-offline")
    sys.exit(0)
if args == ["login", "status"]:
    sys.exit(0 if os.environ.get("DELEGATOR_TEST_AUTH", "1") == "1" else 1)
assert args[0] == "exec", args
if mode == "no_stdin":
    time.sleep(30)
prompt = sys.stdin.buffer.read().decode("utf-8")
if os.environ.get("DELEGATOR_TEST_PROMPT_COPY"):
    Path(os.environ["DELEGATOR_TEST_PROMPT_COPY"]).write_text(prompt, encoding="utf-8")
print(json.dumps({"type": "thread.started", "thread_id": "offline-fixture"}), flush=True)
task = args[args.index("--sandbox") + 1] == "workspace-write"
if task:
    workspace = Path(args[args.index("-C") + 1])
    assert workspace == Path.cwd()
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "before\n"
    (workspace / "a.txt").write_text("implemented\n", encoding="utf-8")
    (workspace / "new 测试.bin").write_bytes(b"\x00\xffnew\n")
    print(json.dumps({"type": "item.completed", "item": {"type": "file_change"}}), flush=True)
    if mode == "task_background":
        subprocess.Popen([sys.executable, "-c",
                          "import time; from pathlib import Path; time.sleep(3); "
                          "Path('a.txt').write_text('late background write\\n', encoding='utf-8')"])
    if mode == "task_timeout":
        time.sleep(30)
if mode == "review_file_change":
    print(json.dumps({"type": "item.completed", "item": {"type": "file_change"}}), flush=True)
if mode == "timeout_partial":
    destination = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    destination.write_text(json.dumps({"complete": False, "summary": "Partial evidence",
                                      "findings": [], "limitations": ["Not finished"]}), encoding="utf-8")
    print('{"type":', end="", flush=True)
if mode in ("timeout", "timeout_partial"):
    time.sleep(30)
if mode == "malformed":
    print("not JSON", flush=True)
if mode == "null_item":
    print(json.dumps({"type": "item.completed", "item": None}), flush=True)
if mode == "failed":
    print(json.dumps({"type": "turn.failed", "error": {"message": "fixture failure"}}))
if mode == "unexpected":
    print(json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call"}}))
print(json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}))
if mode != "missing_turn":
    print(json.dumps({"type": "turn.completed", "usage": {
        "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 0 if mode == "zero_usage" else 50}}))
if mode == "source_changed":
    Path(os.environ["DELEGATOR_TEST_SOURCE"]).write_text("changed during review", encoding="utf-8")
if mode != "missing_final":
    result = {"complete": mode != "partial", "summary": "Offline fixture", "findings": [], "limitations": []}
    if task:
        result = {"complete": mode != "partial", "summary": "Implemented fixture",
                  "changed_files": ["a.txt", "new 测试.bin"],
                  "tests": [{"command": "fixture-check", "outcome": "passed", "details": "Fixture only"}],
                  "limitations": []}
    if mode == "many_findings":
        result["findings"] = [{"priority": "P2", "file": "a.txt", "line": i + 1,
                               "title": "Fixture", "body": "Fixture only"} for i in range(12)]
    if mode == "read_snapshot":
        # Report what the code-grounded snapshot actually contains.
        snapshot = next(line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("Snapshot: "))
        result["summary"] = (Path(snapshot) / "a.txt").read_text(encoding="utf-8")
    if mode == "document_finding":
        result["findings"] = [
            {"priority": "P2", "file": "", "line": 0, "title": "Document claim", "body": "No code location"},
            {"priority": "P3", "file": "a.txt", "line": 1, "title": "Code evidence", "body": "Fixture only"}]
    destination = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    destination.write_text("{}" if mode == "invalid_final" else json.dumps(result), encoding="utf-8")
sys.exit(4 if mode == "nonzero" else 0)
