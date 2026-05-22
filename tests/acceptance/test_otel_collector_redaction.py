"""
Acceptance test: otel-collector-config.yaml contains the required two-layer
redaction processors as mandated by ADR-0017.6 and design §13.

Validates:
  1. processors.attributes/redact exists with delete actions for all required keys.
  2. processors.redaction exists with blocked_values patterns for sk_, pk_, eyJ.
  3. The traces pipeline includes both attributes/redact and redaction processors.
  4. mintkey.tenant_id and mintkey.agent_id are NOT in the delete list (allowlisted).

Source: ADR-0017.6; design §13; T-1.10.1.
"""
import re
from pathlib import Path

import pytest
import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "infra" / "observability" / "otel-collector-config.yaml"

# Keys that MUST be deleted by the attributes/redact processor.
_REQUIRED_DELETE_KEYS = {
    "mintkey.token",
    "mintkey.api_key",
    "mintkey.password",
    "mintkey.authorization_header",
    "http.request.header.authorization",
    "http.request.header.cookie",
    "http.response.header.set-cookie",
}

# Keys that must NOT appear in the delete list (they are on the allowlist).
_ALLOWLISTED_KEYS = {"mintkey.tenant_id", "mintkey.agent_id"}

# Regex patterns that must appear in blocked_values (one per credential family).
_REQUIRED_BLOCKED_PATTERNS = [
    re.compile(r"sk_"),       # Stripe-style secret keys
    re.compile(r"pk_"),       # Public keys
    re.compile(r"eyJ"),       # JWT-shaped tokens
    re.compile(r"mk_agent_"), # Mintkey agent API keys
    re.compile(r"mk_svckey_"), # Mintkey service API keys
]


@pytest.fixture(scope="module")
def otel_config() -> dict:
    assert _CONFIG_PATH.exists(), (
        f"otel-collector-config.yaml not found at {_CONFIG_PATH}"
    )
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_otel_collector_config_has_required_redaction_processors(otel_config: dict) -> None:
    """
    Top-level acceptance test combining all redaction invariants into one function
    per the task spec.  Detailed assertions follow.

    Source: ADR-0017.6; T-1.10.1.
    """
    processors = otel_config.get("processors", {})

    # ── 1. attributes/redact section exists ──────────────────────────────────
    assert "attributes/redact" in processors, (
        "processors.attributes/redact is missing from otel-collector-config.yaml"
    )

    # ── 2. All required keys have delete actions ──────────────────────────────
    actions = processors["attributes/redact"].get("actions", [])
    deleted_keys = {
        a["key"] for a in actions if a.get("action") == "delete"
    }
    missing_keys = _REQUIRED_DELETE_KEYS - deleted_keys
    assert not missing_keys, (
        f"attributes/redact is missing delete actions for: {missing_keys}"
    )

    # ── 3. redaction section exists ───────────────────────────────────────────
    assert "redaction" in processors, (
        "processors.redaction is missing from otel-collector-config.yaml"
    )

    # ── 4. blocked_values covers sk_, pk_, eyJ patterns ──────────────────────
    blocked_values: list[str] = processors["redaction"].get("blocked_values", [])
    assert blocked_values, "processors.redaction.blocked_values is empty"

    for pattern in _REQUIRED_BLOCKED_PATTERNS:
        matched = any(pattern.search(bv) for bv in blocked_values)
        assert matched, (
            f"No blocked_values pattern matches {pattern.pattern!r}. "
            f"Current blocked_values: {blocked_values}"
        )

    # ── 5. traces pipeline includes both redaction processors ─────────────────
    pipelines = otel_config.get("service", {}).get("pipelines", {})
    assert "traces" in pipelines, "service.pipelines.traces is missing"

    traces_processors: list[str] = pipelines["traces"].get("processors", [])
    assert "attributes/redact" in traces_processors, (
        "traces pipeline does not include attributes/redact processor"
    )
    assert "redaction" in traces_processors, (
        "traces pipeline does not include redaction processor"
    )

    # ── 6. Allowlisted keys are NOT deleted ───────────────────────────────────
    for key in _ALLOWLISTED_KEYS:
        assert key not in deleted_keys, (
            f"{key!r} must NOT be in the delete list — it is an allowlisted "
            f"observability attribute per ADR-0017.6"
        )
