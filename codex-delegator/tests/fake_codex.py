"""Offline child fixture, invoked only by test_runner.py."""
import json
import os
from pathlib import Path
import sys
import time

mode = os.environ.get("DELEGATOR_TEST_MODE", "success")
prompt = sys.stdin.read()
print(json.dumps({"type": "thread.started", "thread_id": "offline-fixture"}), flush=True)
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
    if mode == "many_findings":
        result["findings"] = [{"priority": "P2", "file": "a.txt", "line": i + 1,
                               "title": "Fixture", "body": "Fixture only"} for i in range(12)]
    destination = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    destination.write_text("{}" if mode == "invalid_final" else json.dumps(result), encoding="utf-8")
sys.exit(4 if mode == "nonzero" else 0)
