# Event schemas — *iteration 4 placeholder*

This directory will contain schemas for two related concerns:

1. **Audit events** — written by the Audit Service, consumable by the Admin REST API for the audit query endpoint.
2. **OTel span attribute conventions** — the allowlist of attributes our spans may carry, with explicit redaction policy for credential‑adjacent fields.

## Coming in iteration 4
- `audit-event.schema.json` — a discriminated union over `event_type`.
- `span-attributes.md` — naming conventions and required/optional attribute lists per span name.
- A redaction policy file enforced by CI.

## Conventions (preview)
- Audit events are **append‑only**; corrections are new events, not edits.
- Audit events carry both `actor_id` (operator/agent/system) and `target_id` (the affected resource).
- Audit events include a `prev_hash` and `hash` field when hash chaining is enabled.
- OTel span attributes are an **explicit allowlist**: anything not on the list is dropped at the SDK layer.
