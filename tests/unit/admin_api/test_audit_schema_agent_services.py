"""
Unit tests: the audit contract lists the agent credential events.

Requirement: agent-service-credential › The new events are in the audit
contract

  - scenario "the contract lists them": `ev_service_credential_set` and
    `ev_service_credential_cleared` exist under `$defs` with exactly the
    payload property names the requirement gives (all required,
    `additionalProperties` false, no credential value), each event type maps
    to its definition in `discriminator.mapping` and its `$ref` is in
    `oneOf`; `owner_agent_id` is a property of `ev_service_registered` and is
    not in its `required` list; and `ev_service_updated`'s `fields_changed`
    enum keeps its six values and gains `auth_scheme`.

Sources:
  - `openspec/changes/agent-service-routes/specs/agent-service-credential/spec.md`
    — The new events are in the audit contract
  - `openspec/changes/agent-service-routes/design.md` — D8 (one definition per
    event type under `$defs`, one `oneOf` entry, one mapping entry;
    `owner_agent_id` optional; `auth_scheme` added to `fields_changed`)
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


def _definition(schema: dict[str, Any], name: str) -> dict[str, Any]:
    assert name in schema["$defs"], f"{name} is missing from $defs"
    definition: dict[str, Any] = schema["$defs"][name]
    return definition


def _one_of_refs(schema: dict[str, Any]) -> list[Any]:
    return [entry.get("$ref") for entry in schema["oneOf"] if isinstance(entry, dict)]


def test_C_e79dc506_credential_set_definition() -> None:
    """C-e79dc506: `service.credential.set` is defined with its payload shape."""
    definition = _definition(_load_schema(), "ev_service_credential_set")

    assert definition["properties"]["event_type"]["const"] == "service.credential.set"
    assert definition["properties"]["target_type"]["const"] == "service"

    payload = definition["properties"]["payload"]
    assert payload["type"] == "object"
    assert payload["additionalProperties"] is False
    assert set(payload["properties"]) == {"service_id", "key_version", "auth_scheme"}
    assert set(payload["required"]) == {"service_id", "key_version", "auth_scheme"}


def test_C_e79dc506_credential_cleared_definition() -> None:
    """C-e79dc506: `service.credential.cleared` is defined with its payload shape."""
    definition = _definition(_load_schema(), "ev_service_credential_cleared")

    assert (
        definition["properties"]["event_type"]["const"]
        == "service.credential.cleared"
    )
    assert definition["properties"]["target_type"]["const"] == "service"

    payload = definition["properties"]["payload"]
    assert payload["type"] == "object"
    assert payload["additionalProperties"] is False
    assert set(payload["properties"]) == {"service_id", "reason", "fields_changed"}
    assert set(payload["required"]) == {"service_id", "reason", "fields_changed"}


def test_C_e79dc506_credential_events_mapped_and_in_one_of() -> None:
    """C-e79dc506: both credential events are mapped and listed in `oneOf`."""
    schema = _load_schema()

    mapping = schema["discriminator"]["mapping"]
    assert (
        mapping.get("service.credential.set")
        == "#/$defs/ev_service_credential_set"
    )
    assert (
        mapping.get("service.credential.cleared")
        == "#/$defs/ev_service_credential_cleared"
    )

    one_of_refs = _one_of_refs(schema)
    assert "#/$defs/ev_service_credential_set" in one_of_refs
    assert "#/$defs/ev_service_credential_cleared" in one_of_refs


def test_C_e79dc506_service_registered_owner_optional() -> None:
    """C-e79dc506: `ev_service_registered` gains an optional `owner_agent_id`."""
    definition = _definition(_load_schema(), "ev_service_registered")
    payload = definition["properties"]["payload"]

    assert "owner_agent_id" in payload["properties"]
    assert "owner_agent_id" not in payload["required"]
    # The required list it had is unchanged.
    assert set(payload["required"]) == {
        "service_id",
        "name",
        "base_url",
        "auth_scheme",
        "actions",
        "display_name",
    }


def test_C_e79dc506_service_updated_fields_enum_gains_auth_scheme() -> None:
    """C-e79dc506: `fields_changed` keeps its six values and adds `auth_scheme`."""
    definition = _definition(_load_schema(), "ev_service_updated")
    fields_changed = definition["properties"]["payload"]["properties"]["fields_changed"]

    assert fields_changed["items"]["enum"] == [
        "display_name",
        "description",
        "base_url",
        "actions",
        "openapi_url",
        "status",
        "auth_scheme",
    ]
