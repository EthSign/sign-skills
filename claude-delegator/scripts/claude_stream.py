"""Parse and classify Claude CLI ``stream-json`` output.

This module deliberately has no process-management or filesystem-write side
effects.  The caller remains responsible for publishing durable run artifacts.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_NATIVE_TOOL_ALLOWLIST = frozenset(
    {"Read", "Glob", "Grep", "Task", "Agent", "ReportFindings"}
)
_NATIVE_TOOL_ALLOWLIST_FOLDED = frozenset(name.casefold() for name in _NATIVE_TOOL_ALLOWLIST)
_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
_RESPONSE_FIELDS = (
    ("claude_is_error", "is_error"),
    ("claude_subtype", "subtype"),
    ("claude_num_turns", "num_turns"),
    ("claude_session_id", "session_id"),
    ("reported_cost_usd", "total_cost_usd"),
    ("claude_duration_ms", "duration_ms"),
    ("claude_api_duration_ms", "duration_api_ms"),
    ("claude_stop_reason", "stop_reason"),
    ("claude_terminal_reason", "terminal_reason"),
)


def _metadata(native: bool, exit_code: int | None, timed_out: bool) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "status": "unclassified",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "usage_source": None,
        "input_tokens": None,
        "output_tokens": None,
        "cache_creation_input_tokens": None,
        "cache_read_input_tokens": None,
        "model_usage_cost_usd": None,
        "model_usage": [],
        "tool_call_count": 0,
        "tool_usage": {},
        "inspected_paths": [],
        "unexpected_tool_calls": [],
        "unexpected_tool_policy": "diagnostic_cli_enforced" if native else "fatal",
        "metadata_collection_error": None,
        "output_format": "stream-json",
        "response_protocol": (
            "claude-native-code-review-v1" if native else "findings-first-completion-v3"
        ),
        "completion_marker": None,
        "native_review_completed": False,
        "overflow_reported": False,
        "invalid_stream_line_count": 0,
        "partial_output_recovered": False,
        "recovered_output_chars": 0,
        "durable_artifact_error": None,
    }
    metadata.update({target: None for target, _ in _RESPONSE_FIELDS})
    return metadata


def _assistant_text(message: Any) -> str:
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text")
        for block in content
        if isinstance(block, Mapping)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and block.get("text")
    ]
    return "\n".join(parts)


def _review_path(value: str, snapshot: Path | None, evidence: Path | None) -> str:
    """Map paths below the temporary roots to stable review-relative names."""

    try:
        full = os.path.abspath(os.path.normpath(value))
        folded_full = os.path.normcase(full)
        for root, label in ((snapshot, "repository"), (evidence, "evidence")):
            if root is None:
                continue
            full_root = os.path.abspath(os.path.normpath(os.fspath(root)))
            folded_root = os.path.normcase(full_root)
            if folded_full == folded_root:
                return label
            prefix = folded_root.rstrip("/\\") + os.sep
            if folded_full.startswith(prefix):
                relative = full[len(full_root.rstrip("/\\")) :].lstrip("/\\")
                return f"{label}/{relative.replace(os.sep, '/').replace(chr(92), '/')}"
    except (OSError, TypeError, ValueError):
        pass
    return value


def _number(value: Any) -> int | float | None:
    """Return a finite non-negative JSON number, accepting legacy numeric strings."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number: int | float = value
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    if isinstance(number, float) and not math.isfinite(number):
        return None
    if number < 0:
        return None
    return number


def _add_response_metadata(metadata: dict[str, Any], response: Mapping[str, Any]) -> bool:
    for target, source in _RESPONSE_FIELDS:
        metadata[target] = response.get(source)

    positive_usage = False
    model_usage = response.get("modelUsage")
    if isinstance(model_usage, Mapping) and model_usage:
        metadata["usage_source"] = "modelUsage"
        totals: dict[str, int | float] = {field: 0 for field in _TOKEN_FIELDS}
        models: list[dict[str, Any]] = []
        reported_costs: list[int | float] = []
        model_fields = (
            ("input_tokens", "inputTokens"),
            ("output_tokens", "outputTokens"),
            ("cache_creation_input_tokens", "cacheCreationInputTokens"),
            ("cache_read_input_tokens", "cacheReadInputTokens"),
        )
        for name, raw_value in model_usage.items():
            value = raw_value if isinstance(raw_value, Mapping) else {}
            model = {
                "model": str(name),
                "canonical_model": value.get("canonicalModel"),
                "input_tokens": value.get("inputTokens"),
                "output_tokens": value.get("outputTokens"),
                "cache_creation_input_tokens": value.get("cacheCreationInputTokens"),
                "cache_read_input_tokens": value.get("cacheReadInputTokens"),
                "cost_usd": value.get("costUSD"),
            }
            models.append(model)
            for target, source in model_fields:
                raw = value.get(source)
                if raw is None:
                    continue
                parsed = _number(raw)
                if parsed is None:
                    if metadata["metadata_collection_error"] is None:
                        metadata["metadata_collection_error"] = (
                            f"Claude returned an invalid {target} value."
                        )
                    continue
                totals[target] += parsed
                positive_usage = positive_usage or parsed > 0
            raw_cost = value.get("costUSD")
            if raw_cost is not None:
                parsed_cost = _number(raw_cost)
                if parsed_cost is not None:
                    reported_costs.append(parsed_cost)
        metadata.update(totals)
        metadata["model_usage"] = models
        # Only total costs Claude actually reported; do not derive a cost from tokens.
        if reported_costs:
            try:
                metadata["model_usage_cost_usd"] = sum(reported_costs)
            except OverflowError:
                # Cost is diagnostic metadata.  An unrepresentable aggregate must
                # never turn into a fabricated finite value or abort classification.
                metadata["model_usage_cost_usd"] = None
        return positive_usage

    metadata["usage_source"] = "usage"
    usage = response.get("usage")
    usage = usage if isinstance(usage, Mapping) else {}
    for field in _TOKEN_FIELDS:
        raw = usage.get(field)
        metadata[field] = raw
        if raw is None:
            continue
        parsed = _number(raw)
        if parsed is None:
            if metadata["metadata_collection_error"] is None:
                metadata["metadata_collection_error"] = (
                    f"Claude returned an invalid {field} value."
                )
            continue
        positive_usage = positive_usage or parsed > 0
    return positive_usage


def _render_result(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def parse_stream(
    path: Path,
    *,
    native: bool,
    exit_code: int | None,
    timed_out: bool = False,
    snapshot: Path | None = None,
    evidence: Path | None = None,
) -> dict[str, Any]:
    """Parse a Claude JSONL stream and classify its terminal review state.

    ``complete`` means the review itself is complete.  It is false for every
    failure and for a valid ``MORE_FINDINGS_REMAIN`` overflow response.
    """

    metadata = _metadata(native, exit_code, timed_out)
    response: dict[str, Any] | None = None
    latest_assistant = ""
    partial_parts: list[str] = []
    invalid_count = 0
    tool_usage: dict[str, int] = {}
    tool_names: dict[str, str] = {}
    inspected: dict[str, str] = {}
    unexpected: dict[str, str] = {}
    allowlist = _NATIVE_TOOL_ALLOWLIST_FOLDED if native else frozenset()

    with Path(path).open("r", encoding="utf-8", errors="replace", newline=None) as stream:
        for raw_line in stream:
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                invalid_count += 1
                continue
            if not isinstance(message, Mapping):
                continue
            message_type = message.get("type")
            if message_type == "result":
                response = dict(message)
                continue
            if message_type == "assistant":
                assistant = message.get("message")
                candidate = _assistant_text(assistant)
                if candidate:
                    latest_assistant = candidate
                if not isinstance(assistant, Mapping):
                    continue
                content = assistant.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                        continue
                    raw_name = block.get("name")
                    name = raw_name if isinstance(raw_name, str) else ""
                    folded_name = name.casefold()
                    if folded_name not in tool_names:
                        tool_names[folded_name] = name
                    recorded_name = tool_names[folded_name]
                    tool_usage[recorded_name] = tool_usage.get(recorded_name, 0) + 1
                    if folded_name not in allowlist:
                        unexpected.setdefault(folded_name, name)
                    tool_input = block.get("input")
                    if not isinstance(tool_input, Mapping):
                        continue
                    for field in ("file_path", "path"):
                        value = tool_input.get(field)
                        if isinstance(value, str) and value:
                            reviewed_path = _review_path(value, snapshot, evidence)
                            inspected.setdefault(reviewed_path.casefold(), reviewed_path)
                continue
            if message_type == "stream_event":
                event = message.get("event")
                if not isinstance(event, Mapping) or event.get("type") != "content_block_delta":
                    continue
                delta = event.get("delta")
                if (
                    isinstance(delta, Mapping)
                    and delta.get("type") == "text_delta"
                    and isinstance(delta.get("text"), str)
                ):
                    partial_parts.append(delta["text"])

    recovered = latest_assistant or "".join(partial_parts)
    metadata["invalid_stream_line_count"] = invalid_count
    metadata["tool_usage"] = tool_usage
    metadata["tool_call_count"] = sum(tool_usage.values())
    metadata["inspected_paths"] = sorted(inspected.values(), key=str.casefold)
    metadata["unexpected_tool_calls"] = sorted(unexpected.values(), key=str.casefold)
    metadata["recovered_output_chars"] = len(recovered)

    positive_usage = False
    raw_result: Any = None
    result: str | None = None
    protocol = ""
    if response is not None:
        positive_usage = _add_response_metadata(metadata, response)
        raw_result = response.get("result")
        if raw_result is None and recovered:
            raw_result = recovered
        if raw_result is None:
            raw_result = response.get("structured_output")
        result = _render_result(raw_result)
        protocol = raw_result if isinstance(raw_result, str) else recovered
    diagnostic_result = result if result is not None else (recovered or None)

    # Timeout has priority over all stream and terminal-response validation.
    if timed_out:
        metadata["status"] = "error_timeout"
        metadata["partial_output_recovered"] = bool(diagnostic_result)
        return {
            "response": response,
            "result": diagnostic_result,
            "complete": False,
            "metadata": metadata,
        }

    if response is None:
        metadata["status"] = "missing_result_event"
        metadata["partial_output_recovered"] = bool(recovered)
        return {
            "response": None,
            "result": recovered or None,
            "complete": False,
            "metadata": metadata,
        }

    if invalid_count:
        metadata["status"] = "malformed_stream"
        metadata["partial_output_recovered"] = bool(diagnostic_result)
        return {
            "response": response,
            "result": diagnostic_result,
            "complete": False,
            "metadata": metadata,
        }

    if metadata["metadata_collection_error"]:
        metadata["status"] = "malformed_usage_metadata"
        metadata["partial_output_recovered"] = bool(diagnostic_result)
        return {
            "response": response,
            "result": diagnostic_result,
            "complete": False,
            "metadata": metadata,
        }

    is_error = response.get("is_error") is True
    subtype = response.get("subtype")
    subtype_error = isinstance(subtype, str) and subtype.lower().startswith("error_")
    if exit_code != 0 or is_error or subtype_error:
        base_status = subtype if isinstance(subtype, str) and subtype not in ("", "success") else "claude_error"
        metadata["status"] = f"partial_{base_status}" if diagnostic_result else base_status
        metadata["partial_output_recovered"] = bool(diagnostic_result)
        return {
            "response": response,
            "result": diagnostic_result,
            "complete": False,
            "metadata": metadata,
        }

    if unexpected and not native:
        metadata["status"] = "security_boundary_violation"
        return {
            "response": response,
            "result": diagnostic_result,
            "complete": False,
            "metadata": metadata,
        }

    if raw_result is None or result is None:
        metadata["status"] = "missing_result"
        return {
            "response": response,
            "result": recovered or None,
            "complete": False,
            "metadata": metadata,
        }

    if (
        native
        and isinstance(protocol, str)
        and protocol.startswith("Failed to authenticate. API Error: 401")
        and "OAuth access token has expired." in protocol
    ):
        metadata["status"] = "authentication_failed"
        metadata["partial_output_recovered"] = False
        return {"response": response, "result": result, "complete": False, "metadata": metadata}

    if native and not positive_usage:
        metadata["status"] = "native_review_no_model_usage"
        metadata["partial_output_recovered"] = bool(result)
        return {"response": response, "result": result, "complete": False, "metadata": metadata}

    if native:
        if not isinstance(protocol, str) or not protocol.strip():
            metadata["status"] = "native_review_empty"
            return {
                "response": response,
                "result": recovered or None,
                "complete": False,
                "metadata": metadata,
            }
        metadata["native_review_completed"] = True
        metadata["status"] = "success_native_review"
        return {"response": response, "result": result, "complete": True, "metadata": metadata}

    last_protocol_line: str | None = None
    for protocol_line in protocol.split("\n"):
        if protocol_line.strip():
            last_protocol_line = protocol_line.removesuffix("\r")
    if last_protocol_line == "MORE_FINDINGS_REMAIN":
        metadata["completion_marker"] = "MORE_FINDINGS_REMAIN"
        metadata["overflow_reported"] = True
        metadata["status"] = "success_with_overflow"
        return {"response": response, "result": result, "complete": False, "metadata": metadata}
    if last_protocol_line == "REVIEW_COMPLETE":
        metadata["completion_marker"] = "REVIEW_COMPLETE"
        metadata["status"] = "success"
        return {"response": response, "result": result, "complete": True, "metadata": metadata}

    metadata["status"] = "protocol_incomplete"
    metadata["partial_output_recovered"] = bool(protocol)
    return {"response": response, "result": result, "complete": False, "metadata": metadata}


__all__ = ["parse_stream"]
