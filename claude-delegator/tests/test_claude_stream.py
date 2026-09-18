from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "claude_stream.py"
SPEC = importlib.util.spec_from_file_location("claude_stream", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
CLAUDE_STREAM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLAUDE_STREAM)
parse_stream = CLAUDE_STREAM.parse_stream


class TextJoiningTests(unittest.TestCase):
    def test_recovered_blocks_use_protocol_lf(self):
        message = {"content": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]}
        self.assertEqual(CLAUDE_STREAM._assistant_text(message), "first\nsecond")


def assistant(text: str, *tools: dict[str, object]) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": text}, *tools],
        },
    }


def terminal(result: object, *, usage: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "type": "result",
        "is_error": False,
        "subtype": "success",
        "result": result,
        "usage": usage
        if usage is not None
        else {
            "input_tokens": 1,
            "output_tokens": 1,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


class ParseStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "stream.jsonl"

    def write(self, *records: object, raw: str | None = None) -> None:
        lines = [json.dumps(record) for record in records]
        if raw is not None:
            lines.append(raw)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def parse(self, *, native: bool = False, exit_code: int | None = 0, **kwargs: object) -> dict[str, object]:
        return parse_stream(self.path, native=native, exit_code=exit_code, **kwargs)

    def test_bounded_success_requires_final_marker(self) -> None:
        review = "No actionable findings\nREVIEW_COMPLETE"
        self.write(assistant(review), terminal(review))

        parsed = self.parse()

        self.assertTrue(parsed["complete"])
        self.assertEqual(parsed["result"], review)
        self.assertEqual(parsed["metadata"]["status"], "success")
        self.assertEqual(parsed["metadata"]["completion_marker"], "REVIEW_COMPLETE")

    def test_bounded_overflow_is_successful_but_incomplete(self) -> None:
        review = "[P1] finding\nMORE_FINDINGS_REMAIN"
        self.write(assistant(review), terminal(review))

        parsed = self.parse()

        self.assertFalse(parsed["complete"])
        self.assertEqual(parsed["metadata"]["status"], "success_with_overflow")
        self.assertTrue(parsed["metadata"]["overflow_reported"])

    def test_bounded_tool_request_is_a_security_boundary_violation(self) -> None:
        tool = {"type": "tool_use", "name": "Read", "input": {"file_path": "secret.txt"}}
        review = "No actionable findings\nREVIEW_COMPLETE"
        self.write(assistant(review, tool), terminal(review))

        parsed = self.parse()

        self.assertFalse(parsed["complete"])
        self.assertEqual(parsed["metadata"]["status"], "security_boundary_violation")
        self.assertEqual(parsed["metadata"]["unexpected_tool_calls"], ["Read"])

    def test_native_unexpected_tool_is_diagnostic_and_paths_are_relative(self) -> None:
        snapshot = Path(self.temporary.name) / "snapshot"
        reviewed = snapshot / "src" / "example.py"
        tool = {
            "type": "tool_use",
            "name": "constructor",
            "input": {"file_path": str(reviewed)},
        }
        review = "No actionable findings"
        response = terminal(review)
        response.pop("usage")
        response["modelUsage"] = {
            "claude-test": {
                "inputTokens": 3,
                "outputTokens": 2,
                "cacheCreationInputTokens": 0,
                "cacheReadInputTokens": 0,
            }
        }
        self.write(assistant(review, tool), response)

        parsed = self.parse(native=True, snapshot=snapshot)

        self.assertTrue(parsed["complete"])
        metadata = parsed["metadata"]
        self.assertEqual(metadata["status"], "success_native_review")
        self.assertEqual(metadata["unexpected_tool_calls"], ["constructor"])
        self.assertEqual(metadata["inspected_paths"], ["repository/src/example.py"])
        self.assertEqual(metadata["model_usage_cost_usd"], None)

    def test_native_tool_allowlist_and_counts_are_case_insensitive(self) -> None:
        review = "No actionable findings"
        self.write(
            assistant(
                review,
                {"type": "tool_use", "name": "Read", "input": {}},
                {"type": "tool_use", "name": "read", "input": {}},
            ),
            terminal(review),
        )

        parsed = self.parse(native=True)

        self.assertTrue(parsed["complete"])
        self.assertEqual(parsed["metadata"]["tool_usage"], {"Read": 2})
        self.assertEqual(parsed["metadata"]["unexpected_tool_calls"], [])

    def test_native_zero_usage_cannot_complete(self) -> None:
        review = "No actionable findings"
        self.write(
            assistant(review),
            terminal(
                review,
                usage={
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            ),
        )

        parsed = self.parse(native=True)

        self.assertFalse(parsed["complete"])
        self.assertEqual(parsed["metadata"]["status"], "native_review_no_model_usage")
        self.assertTrue(parsed["metadata"]["partial_output_recovered"])

    def test_native_positive_usage_does_not_make_empty_review_complete(self) -> None:
        self.write(terminal(""))

        parsed = self.parse(native=True)

        self.assertFalse(parsed["complete"])
        self.assertEqual(parsed["metadata"]["status"], "native_review_empty")

    def test_boolean_usage_is_rejected_instead_of_counted_as_a_token(self) -> None:
        review = "No actionable findings"
        self.write(
            assistant(review),
            terminal(
                review,
                usage={
                    "input_tokens": True,
                    "output_tokens": 1,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            ),
        )

        parsed = self.parse(native=True)

        self.assertEqual(parsed["metadata"]["status"], "malformed_usage_metadata")
        self.assertIn("invalid input_tokens", parsed["metadata"]["metadata_collection_error"])

    def test_timeout_has_priority_and_returns_recovered_partial_text(self) -> None:
        self.write(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "partial review"},
                },
            },
            raw="not JSON",
        )

        parsed = self.parse(native=True, exit_code=None, timed_out=True)

        self.assertEqual(parsed["metadata"]["status"], "error_timeout")
        self.assertEqual(parsed["metadata"]["invalid_stream_line_count"], 1)
        self.assertEqual(parsed["result"], "partial review")
        self.assertTrue(parsed["metadata"]["partial_output_recovered"])

    def test_timeout_keeps_terminal_result_and_terminal_metadata(self) -> None:
        response = terminal("terminal review")
        response["total_cost_usd"] = 0.25
        self.write(assistant("older partial review"), response, raw="not JSON")

        parsed = self.parse(native=True, exit_code=None, timed_out=True)

        metadata = parsed["metadata"]
        self.assertEqual(metadata["status"], "error_timeout")
        self.assertEqual(parsed["result"], "terminal review")
        self.assertEqual(metadata["reported_cost_usd"], 0.25)
        self.assertEqual(metadata["input_tokens"], 1)
        self.assertEqual(metadata["invalid_stream_line_count"], 1)

    def test_terminal_result_with_invalid_stream_line_is_malformed(self) -> None:
        review = "No actionable findings\nREVIEW_COMPLETE"
        self.write(assistant(review), terminal(review), raw="not JSON")

        parsed = self.parse()

        self.assertEqual(parsed["metadata"]["status"], "malformed_stream")
        self.assertFalse(parsed["complete"])
        self.assertEqual(parsed["result"], review)

    def test_malformed_stream_keeps_terminal_only_result(self) -> None:
        self.write(terminal("terminal-only review"), raw="not JSON")

        parsed = self.parse()

        self.assertEqual(parsed["metadata"]["status"], "malformed_stream")
        self.assertEqual(parsed["result"], "terminal-only review")
        self.assertTrue(parsed["metadata"]["partial_output_recovered"])

    def test_negative_model_usage_fails_closed(self) -> None:
        review = "No actionable findings"
        response = terminal(review)
        response.pop("usage")
        response["modelUsage"] = {
            "claude-test": {
                "inputTokens": -1,
                "outputTokens": 5,
                "cacheCreationInputTokens": 0,
                "cacheReadInputTokens": 0,
                "costUSD": 0.01,
            }
        }
        self.write(assistant(review), response)

        parsed = self.parse(native=True)

        self.assertEqual(parsed["metadata"]["status"], "malformed_usage_metadata")
        self.assertIn("invalid input_tokens", parsed["metadata"]["metadata_collection_error"])

    def test_process_error_uses_subtype_and_recovered_text(self) -> None:
        review = "[P1] recovered finding"
        response = terminal(None)
        response["is_error"] = True
        response["subtype"] = "error_mock"
        self.write(assistant(review), response)

        parsed = self.parse(exit_code=1)

        self.assertEqual(parsed["metadata"]["status"], "partial_error_mock")
        self.assertEqual(parsed["result"], review)

    def test_process_error_keeps_terminal_only_result(self) -> None:
        response = terminal("terminal error evidence")
        response["is_error"] = True
        response["subtype"] = "error_mock"
        self.write(response)

        parsed = self.parse(exit_code=1)

        self.assertEqual(parsed["metadata"]["status"], "partial_error_mock")
        self.assertEqual(parsed["result"], "terminal error evidence")
        self.assertTrue(parsed["metadata"]["partial_output_recovered"])

    def test_structured_bounded_result_without_text_is_safely_incomplete(self) -> None:
        response = terminal(None)
        response["structured_output"] = {"findings": []}
        self.write(response)

        parsed = self.parse()

        self.assertEqual(parsed["metadata"]["status"], "protocol_incomplete")
        self.assertEqual(parsed["result"], '{\n  "findings": []\n}')
        self.assertFalse(parsed["complete"])

    def test_nonfinal_marker_is_protocol_incomplete(self) -> None:
        review = "REVIEW_COMPLETE\ntrailing text"
        self.write(assistant(review), terminal(review))

        parsed = self.parse()

        self.assertEqual(parsed["metadata"]["status"], "protocol_incomplete")
        self.assertFalse(parsed["complete"])

    def test_string_assistant_content_is_not_recovered(self) -> None:
        self.write({"type": "assistant", "message": {"content": "synthetic text"}})

        parsed = self.parse()

        self.assertEqual(parsed["metadata"]["status"], "missing_result_event")
        self.assertIsNone(parsed["result"])
        self.assertFalse(parsed["metadata"]["partial_output_recovered"])

    def test_native_authentication_failure_precedes_usage_success(self) -> None:
        review = (
            "Failed to authenticate. API Error: 401: "
            "OAuth access token has expired."
        )
        self.write(assistant(review), terminal(review))

        parsed = self.parse(native=True)

        self.assertEqual(parsed["metadata"]["status"], "authentication_failed")
        self.assertFalse(parsed["complete"])


if __name__ == "__main__":
    unittest.main()
