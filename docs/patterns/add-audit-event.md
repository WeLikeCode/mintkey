# Pattern: Add an Audit Event Type

## Goal

Use this guide to introduce a new audit event type in Mintkey. Audit events are the system's
compliance record — every state change must produce one (P-2, ADR-0014.7). This guide covers
adding the event type to the contract schema, calling `audit_emit()` at the correct chokepoint,
updating the architecture test allowlist, and writing tests that verify both emission and
hash-chain integrity.

---

## Where the change lives

- `docs/architecture/contracts/events/audit-event.schema.json` — canonical event schema; add
  the new event type here first (P-4)
- `apps/admin-api/src/admin_api/api/<resource>.py` — the FastAPI handler that owns the state change
  and must call `audit_emit()` (the audit chokepoint)
- `mintkey_models/src/mintkey_models/audit.py` — `audit_emit()` helper (do not modify; call it)
- `tests/acceptance/test_audit_coverage.py` — architecture test; update its event-type allowlist
- `tests/acceptance/test_audit_append_only.py` — chain integrity test (no changes needed unless
  you are altering the hash algorithm — which requires a new ADR superseding ADR-0014.7)

---

## Step-by-step

1. **Add the event type to the schema.** Open
   `docs/architecture/contracts/events/audit-event.schema.json`. In the `$defs` section, add a
   new `ev_<resource>_<action>` definition following the existing pattern:
   ```json
   "ev_<resource>_<action>": {
     "title": "<Resource><Action>",
     "type": "object",
     "required": ["event_type", ...],
     "properties": {
       "event_type": { "const": "<resource>.<action>" },
       ...
     }
   }
   ```
   Then add `"<resource>.<action>"` to the main `event_type` enum and add a `oneOf` entry
   pointing at the new definition. Validate:
   ```bash
   python3 -c "import json; from jsonschema import Draft202012Validator as V; V.check_schema(json.load(open('docs/architecture/contracts/events/audit-event.schema.json')))"
   ```

2. **Write a failing acceptance test.** In `tests/acceptance/test_<resource>.py` (or a new
   file), add a test that performs the state change and then calls `GET /audit-events` asserting
   that an event with `event_type == "<resource>.<action>"` is present.

3. **Call `audit_emit()` in the handler.** In the FastAPI router function that owns the state
   change, after the DB write succeeds:
   ```python
   from mintkey_models.audit import audit_emit
   await audit_emit(
       conn=ctx.db,
       event_type="<resource>.<action>",
       actor_type="operator",       # or "agent" / "system"
       actor_id=ctx.operator_id,
       tenant_id=ctx.tenant_id,
       target_type="<resource>",
       target_id=resource_id,
       payload={
           "<resource>_id": resource_id,
           # include before/after state for update events
           # NEVER include credential values, tokens, or secrets
       },
   )
   ```

4. **Update the architecture test allowlist.** Open
   `tests/acceptance/test_audit_coverage.py`. If it maintains an explicit set of covered event
   types, add `"<resource>.<action>"` to it.

5. **Run all tests:**
   ```bash
   make lint-contracts
   make test-unit
   make test-arch
   make test-acceptance   # requires running stack
   ```

6. **Verify hash-chain integrity still passes:**
   ```bash
   pytest tests/acceptance/test_audit_append_only.py -v
   pytest tests/acceptance/test_audit_chain.py -v
   ```

---

## Tests to write

- **Unit test** — mock the DB session; call the handler; assert `audit_emit` was called exactly
  once with `event_type="<resource>.<action>"` and that the payload does not contain any
  credential value.
- **Acceptance test** — perform the state change against a running stack; query
  `GET /audit-events?event_type=<resource>.<action>`; assert exactly one event is returned with
  the correct `target_id` and `tenant_id`.
- **Architecture test** — add the new event type to `test_audit_coverage.py`'s allowlist so CI
  will catch if the emission is later removed.
- **Chain integrity** — `tests/acceptance/test_audit_append_only.py` and
  `tests/acceptance/test_audit_chain.py` run against the whole event stream. Run them after
  adding the new type; they should pass without modification.

---

## Common pitfalls

- **Emitting outside the audit chokepoint.** The FastAPI Admin REST API is the only permitted
  emission point (P-2). Go services that need audit events must call the admin-api over HTTP,
  not write to the audit table directly.
- **Forgetting the schema enum update.** If `event_type` is not in the enum, the schema
  validation in `test_audit_coverage.py` rejects it. Add the enum value in step 1.
- **Including sensitive data in the payload.** The `payload` field must never contain credential
  values, plaintext tokens, or secrets. The `test_no_plaintext_in_audit.py` acceptance test
  catches this, but check during code review too.
- **Altering the hash algorithm.** The audit hash chain uses SHA-256 per ADR-0014.7. Any change
  to the algorithm requires a new ADR superseding ADR-0014.7. The existing tests in
  `test_audit_append_only.py` and `test_audit_chain.py` enforce this invariant.
- **Cross-tenant event access.** The audit query is tenant-scoped. `PlatformAdmin` cross-tenant
  queries themselves emit an `ev_platform_admin_access` event — do not skip this for admin tools.

---

## References

- [ADR-0014 — Iter 1-2 corrections (audit chain invariants, § 0014.7)](../architecture/01-architecture/adr/0014-iter-1-2-corrections.md)
- [ADR-0008 — Multi-tenancy (tenant_id on every audit event)](../architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md)
- [Audit event schema](../architecture/contracts/events/audit-event.schema.json)
- [test_audit_append_only.py](../../tests/acceptance/test_audit_append_only.py) — chain integrity
- [test_audit_coverage.py](../../tests/acceptance/test_audit_coverage.py) — coverage gate
- Existing examples: `ev_service_registered` (service registration), `ev_proxy_hit` (proxy call),
  `ev_agent_created` (agent creation) — all in `audit-event.schema.json`
