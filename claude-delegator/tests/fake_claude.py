"""Offline child used by Python tests; never calls a model."""
import json
import os
from pathlib import Path
import sys
import time

mode = os.environ.get("CLAUDE_PY_TEST_MODE", "success")
if mode == "no_stdin":
    time.sleep(30)
prompt = sys.stdin.read()
if mode == "verify_guidance":
    guidance = Path(sys.argv[sys.argv.index("--append-system-prompt-file") + 1]).read_bytes()
    assert guidance.endswith(("x" * (256 * 1024)).encode())
    assert prompt.startswith("/code-review high")
print(json.dumps({"type": "system", "subtype": "mock_started"}), flush=True)
if mode == "timeout":
    print('{"type":', end="", flush=True)
    time.sleep(30)
review = "No actionable findings\nREVIEW_COMPLETE"
if mode == "overflow":
    review = "[P2] example.py:1 - Fixture finding. Test only.\nMORE_FINDINGS_REMAIN"
if mode == "malformed":
    print("not valid JSON", flush=True)
if mode == "unexpected":
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}))
if mode == "inspect_snapshot":
    expected = json.loads(os.environ["CLAUDE_PY_TEST_FILES"])
    for name, data in expected.items():
        assert Path(name).read_bytes().hex() == data, name
    assert os.environ["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert os.environ["CLAUDE_CODE_MAX_RETRIES"] == "0"
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": review}]}}))
print(json.dumps({"type": "result", "is_error": mode == "failure", "subtype": "error_mock" if mode == "failure" else "success",
                  "result": review, "usage": {"input_tokens": 0 if mode == "zero_usage" else 1, "output_tokens": 0 if mode == "zero_usage" else 1}}))
sys.exit(7 if mode == "nonzero" else 0)
