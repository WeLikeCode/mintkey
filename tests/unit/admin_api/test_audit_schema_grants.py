"""
Unit tests: the audit contract records the grantor and the expiry.

Requirement: grant-expiry › The audit contract records the grantor and the expiry

  - scenario "the contract names them": `ev_agent_permission_granted` lists
    `expires_at`, `grantor_type` and `grantor_id`; `ev_agent_permission_revoked`
    lists `grantor_type`, `grantor_id`, `revoked_by_type` and `revoked_by_id`;
    `ev_token_denied` lists `grant_expired` in its `reason_code` enum; and the
    `required` lists they had are unchanged.

Sources:
  - `openspec/changes/grant-expiry/spec.md` — The audit contract records the
    grantor and the expiry
  - `openspec/changes/grant-expiry/design.md` — D8 (the revoke events name the
    grantor; the denial reason `grant_expired`)
  - `docs/architecture/contracts/events/audit-event.schema.json`
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "architecture"
    / "contracts"
    / "events"
    / "audit-event.schema.json"
)


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def _payload(schema: dict[str, Any], definition: str) -> dict[str, Any]:
    return schema["$defs"][definition]["properties"]["payload"]


def test_C_29874427_granted_payload_lists_expiry_and_grantor() -> None:
    """C-29874427: `agent.permission.granted` lists the expiry and the grantor."""
    payload = _payload(_load_schema(), "ev_agent_permission_granted")

    properties = payload["properties"]
    assert "expires_at" in properties
    assert "grantor_type" in properties
    assert "grantor_id" in properties

    # The new properties are optional: the required list it had is unchanged.
    assert payload["required"] == [
        "permission_id",
        "agent_id",
        "service_id",
        "action",
    ]


def test_C_29874427_revoked_payload_lists_grantor_and_revoker() -> None:
    """C-29874427: `agent.permission.revoked` lists the grantor and the revoker."""
    payload = _payload(_load_schema(), "ev_agent_permission_revoked")

    properties = payload["properties"]
    assert "grantor_type" in properties
    assert "grantor_id" in properties
    assert "revoked_by_type" in properties
    assert "revoked_by_id" in properties

    # The new properties are optional: the required list it had is unchanged.
    assert payload["required"] == [
        "permission_id",
        "agent_id",
        "service_id",
        "action",
    ]


def test_C_29874427_token_denied_lists_grant_expired_reason() -> None:
    """C-29874427: `token.denied` lists `grant_expired` in its reason enum."""
    payload = _payload(_load_schema(), "ev_token_denied")

    enum = payload["properties"]["reason_code"]["enum"]
    assert "grant_expired" in enum

    # The required list it had is unchanged.
    assert payload["required"] == [
        "agent_id",
        "service_id",
        "scope",
        "reason_code",
    ]
