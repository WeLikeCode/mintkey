"""
Unit tests: the audit contract lists the role and ownership events.

Requirement: agent-roles-and-ownership › The new events are in the audit
contract

  - scenario "the contract lists both events": `ev_agent_role_changed` and
    `ev_service_ownership_transferred` exist under `$defs` with exactly the
    payload property names the requirement gives, each event type maps to its
    definition in `discriminator.mapping`, and both `$ref`s are in `oneOf`.

Sources:
  - `openspec/changes/agent-roles-and-ownership/spec.md` — The new events are in
    the audit contract
  - `openspec/changes/agent-roles-and-ownership/design.md` — D6 (one definition
    per event type under `$defs`, one `oneOf` entry, one mapping entry)
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
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
    return schema


def _one_of_refs(schema: dict[str, Any]) -> list[Any]:
    return [entry.get("$ref") for entry in schema["oneOf"] if isinstance(entry, dict)]


def test_C_c807e49c_agent_role_changed_definition() -> None:
    """C-c807e49c: `agent.role.changed` is defined, mapped and in `oneOf`."""
    schema = _load_schema()

    assert "ev_agent_role_changed" in schema["$defs"]
    definition = schema["$defs"]["ev_agent_role_changed"]

    assert definition["properties"]["event_type"]["const"] == "agent.role.changed"
    assert definition["properties"]["target_type"]["const"] == "agent"

    payload = definition["properties"]["payload"]
    assert set(payload["properties"]) == {"agent_id", "from_role", "to_role"}
    assert set(payload["required"]) == {"agent_id", "from_role", "to_role"}

    mapping = schema["discriminator"]["mapping"]
    assert mapping.get("agent.role.changed") == "#/$defs/ev_agent_role_changed"
    assert "#/$defs/ev_agent_role_changed" in _one_of_refs(schema)


def test_C_c807e49c_service_ownership_transferred_definition() -> None:
    """C-c807e49c: `service.ownership_transferred` is defined, mapped and in `oneOf`."""
    schema = _load_schema()

    assert "ev_service_ownership_transferred" in schema["$defs"]
    definition = schema["$defs"]["ev_service_ownership_transferred"]

    assert (
        definition["properties"]["event_type"]["const"]
        == "service.ownership_transferred"
    )
    assert definition["properties"]["target_type"]["const"] == "service"

    payload = definition["properties"]["payload"]
    assert set(payload["properties"]) == {
        "service_id",
        "from_agent_id",
        "to_agent_id",
    }
    assert set(payload["required"]) == {
        "service_id",
        "from_agent_id",
        "to_agent_id",
    }

    mapping = schema["discriminator"]["mapping"]
    assert (
        mapping.get("service.ownership_transferred")
        == "#/$defs/ev_service_ownership_transferred"
    )
    assert "#/$defs/ev_service_ownership_transferred" in _one_of_refs(schema)
