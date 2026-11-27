"""
Unit tests: the audit contract lists the denied-operation event.

Requirement: agent-principal › The contract lists the denied-operation event

  - scenario "the contract lists it": `ev_agent_operation_denied` exists under
    `$defs` with `event_type` `agent.operation.denied`, `target_type` `agent`,
    and a payload holding exactly `agent_id`, `role` and `operation` (all
    required, `additionalProperties` false, `role` one of `consumer` and
    `publisher`, `operation` a string of at most 256 characters);
    `agent.operation.denied` is a key of `discriminator.mapping`, the `$ref` of
    the definition is in `oneOf`, and the envelope's `actor_type` already
    allows `agent`.

Sources:
  - `openspec/changes/agent-principal-and-egress/specs/agent-principal/spec.md`
    — The contract lists the denied-operation event
  - `openspec/changes/agent-principal-and-egress/design.md` — D3
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


def _definition(schema: dict[str, Any]) -> dict[str, Any]:
    definition = schema["$defs"].get("ev_agent_operation_denied")
    assert definition is not None, "ev_agent_operation_denied is missing from $defs"
    return definition


def test_C_c66906b5_definition_states_event_and_payload() -> None:
    """C-c66906b5: the definition pins the event, target and payload shape."""
    definition = _definition(_load_schema())

    assert (
        definition["properties"]["event_type"]["const"]
        == "agent.operation.denied"
    )
    assert definition["properties"]["target_type"]["const"] == "agent"

    payload = definition["properties"]["payload"]
    assert payload["type"] == "object"
    assert payload["additionalProperties"] is False
    assert set(payload["properties"]) == {"agent_id", "role", "operation"}
    assert set(payload["required"]) == {"agent_id", "role", "operation"}

    role = payload["properties"]["role"]
    assert set(role["enum"]) == {"consumer", "publisher"}

    operation = payload["properties"]["operation"]
    assert operation["type"] == "string"
    assert operation["maxLength"] == 256


def test_C_c66906b5_mapping_one_of_and_envelope_actor() -> None:
    """C-c66906b5: the event is mapped, in `oneOf`, and the envelope allows agent."""
    schema = _load_schema()
    definition = _definition(schema)

    mapping = schema["discriminator"]["mapping"]
    assert (
        mapping.get("agent.operation.denied")
        == "#/$defs/ev_agent_operation_denied"
    )

    one_of_refs = [
        entry.get("$ref") for entry in schema["oneOf"] if isinstance(entry, dict)
    ]
    assert "#/$defs/ev_agent_operation_denied" in one_of_refs

    # The envelope already allows an agent actor; the definition adds no enum value.
    assert "agent" in schema["$defs"]["actor_type"]["enum"]
    assert "actor_type" not in definition["properties"]
