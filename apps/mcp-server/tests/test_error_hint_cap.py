"""
T-D tests — error hint truncation (P6, FR-19, AC-9).

Tests that _upstream_to_tool_result caps the hint portion at 120 characters.

Source: .kiro/specs/mcp-token-optimization/ FR-19, AC-9.
"""
from __future__ import annotations


def test_error_hint_truncated_to_120() -> None:
    """A 300-char upstream hint is capped at 120 chars in the error text block."""
    from mcp_server.tools.jsonrpc import _upstream_to_tool_result, _synthetic_error_response

    long_hint = "h" * 300
    resp = _synthetic_error_response(
        400,
        {
            "code": "mintkey:test_error",
            "title": "Test Error",
            "detail": "Something went wrong.",
            "hint": long_hint,
        },
    )
    result = _upstream_to_tool_result(resp)
    assert result.get("isError") is True
    text = result["content"][0]["text"]

    assert "hint: " in text, f"Expected 'hint: ' in error text: {text!r}"
    idx = text.index("hint: ")
    hint_segment = text[idx + len("hint: "):]
    assert len(hint_segment) <= 120, (
        f"hint segment exceeds 120 chars ({len(hint_segment)}): {hint_segment!r}"
    )
    assert hint_segment == "h" * 120, (
        f"Expected exactly 120 'h' chars, got: {hint_segment!r}"
    )


def test_short_hint_unchanged() -> None:
    """A hint under 120 chars is passed through unchanged."""
    from mcp_server.tools.jsonrpc import _upstream_to_tool_result, _synthetic_error_response

    short_hint = "Check the service_id parameter."
    resp = _synthetic_error_response(
        404,
        {"code": "mintkey:not_found", "hint": short_hint},
    )
    result = _upstream_to_tool_result(resp)
    assert result.get("isError") is True
    text = result["content"][0]["text"]
    assert short_hint in text, f"Short hint should appear verbatim in: {text!r}"
