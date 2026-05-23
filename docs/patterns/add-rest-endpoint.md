# Pattern: Add a REST Endpoint to the Admin API

## Goal

Use this guide to add a new REST endpoint to the Mintkey Admin API (FastAPI). It covers the
full path from contract to handler to audit emission to tests. Follow this pattern to keep
every endpoint consistent with multi-tenancy (ADR-0008), audit requirements (ADR-0014.7),
and the OpenAPI parity gate that runs in CI.

---

## Where the change lives

- `docs/architecture/contracts/rest/openapi.yaml` — canonical contract; edit this first (P-4)
- `apps/admin-api/src/admin_api/api/<resource>.py` — FastAPI router for the resource
- `apps/admin-api/src/admin_api/services/<resource>.py` — business logic layer (if new resource)
- `packages/python/mintkey-models/src/mintkey_models/audit.py` — `audit_emit()` helper (do not modify; call it)
- `apps/admin-api/db/changelog/` — Liquibase changelogs if a schema change is needed (ADR-0015)
- `tests/acceptance/test_<resource>.py` — acceptance test asserting the full request/response cycle
- `tests/acceptance/test_audit_coverage.py` — architecture test asserting audit emission

---

## Step-by-step

1. **Write the contract first.** Add the path, operation, request schema, and response schema to
   `docs/architecture/contracts/rest/openapi.yaml`. Use OAS 3.1 (`type: ["string", "null"]` for
   nullable, not the OAS 3.0 form). Run the OpenAPI validator:
   ```bash
   python3 -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')))"
   ```

2. **Write a failing acceptance test.** In `tests/acceptance/test_<resource>.py`, add a test
   that calls the new endpoint and asserts the response shape. It will fail until step 4.

3. **Create Pydantic request/response models.** Add `class CreateXRequest(BaseModel)` and
   `class XResponse(BaseModel)` in the API module. Use `str` for ULID wire IDs (never UUID on
   the wire — ADR-0017.11). All timestamps must be `datetime` with `timezone.utc`.

4. **Add the FastAPI router function.** In `apps/admin-api/src/admin_api/api/<resource>.py`, add:
   ```python
   @router.post("/<resources>", response_model=XResponse, status_code=201)
   async def create_x(body: CreateXRequest, ctx: RequestContext = Depends(get_context)):
       ...
   ```
   Pull the `tenant_id` from `ctx.tenant_id` — never from the request body (ADR-0008).

5. **Call the business-logic layer.** Keep the router thin; put DB access in
   `apps/admin-api/src/admin_api/services/<resource>.py`. Use `ctx.db` (async SQLAlchemy session).

6. **Emit the audit event.** Every state-changing handler must call `audit_emit()` (P-2):
   ```python
   from mintkey_models.audit import audit_emit
   await audit_emit(
       conn=ctx.db,
       event_type="<resource>.<action>",  # must match audit-event.schema.json enum
       actor_type="operator",
       actor_id=ctx.operator_id,
       tenant_id=ctx.tenant_id,
       target_type="<resource>",
       target_id=new_id,
       payload={"<resource>_id": new_id, ...},  # never include credential values
   )
   ```

7. **Update the audit schema enum** in
   `docs/architecture/contracts/events/audit-event.schema.json` if the event type is new.

8. **Run lint and tests:**
   ```bash
   make lint
   make test-unit
   make test-acceptance   # requires running stack
   make test-arch
   ```

9. **Verify OpenAPI parity.** The CI `Schema Integrity Gates` job diffs FastAPI's emitted
   OpenAPI against the checked-in YAML. Run it locally:
   ```bash
   make lint-contracts
   ```

---

## Tests to write

- **Unit test** — `tests/unit/admin_api/test_<resource>.py`: mock the DB; assert the service
  function returns the correct response model and calls `audit_emit` exactly once with the
  correct `event_type`.
- **Acceptance test** — `tests/acceptance/test_<resource>.py`: call the real endpoint against a
  running stack; assert HTTP status, response body shape, and that a matching audit event appears
  in `GET /audit-events`.
- **Architecture test** — `tests/acceptance/test_audit_coverage.py` already asserts that every
  state-changing endpoint emits at least one audit event. Add the new endpoint to the coverage
  map if the test uses an explicit allowlist.
- **OpenAPI parity** — `tests/acceptance/test_openapi_parity.py` checks schema drift; no action
  needed if step 1 was done correctly.

---

## Common pitfalls

- **Forgetting audit emission.** The architecture test (`test_audit_coverage.py`) catches this,
  but only at acceptance time. Emit in the router before returning the response.
- **Using UUID instead of ULID with prefix.** All wire IDs must follow `^<prefix>_[0-9A-HJKMNP-TV-Z]{26}$`
  (ADR-0017.11). Generate with `new_ulid("<prefix>")` from `mintkey_models.ids`.
- **Hard-coding `tenant_id` from the request body.** Tenant comes from the authentication
  context (`ctx.tenant_id`), never from a caller-supplied parameter.
- **Hand-editing OpenAPI after FastAPI** (backwards from P-4). Edit the YAML first; then make
  the FastAPI code match it.
- **Missing null safety on optional fields.** Use OAS 3.1 `type: ["string", "null"]`, not
  `nullable: true` (the OAS 3.0 form fails the parity gate).

---

## References

- [ADR-0008 — Multi-tenancy row-level with DB tier](../architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md)
- [ADR-0014 — Iter 1-2 corrections (audit chain, § 0014.7)](../architecture/01-architecture/adr/0014-iter-1-2-corrections.md)
- [ADR-0017 — Round-3 corrections (ULID prefixes, § 0017.11)](../architecture/01-architecture/adr/0017-round-3-corrections.md)
- [REST OpenAPI contract](../architecture/contracts/rest/openapi.yaml)
- [Audit event schema](../architecture/contracts/events/audit-event.schema.json)
- Example endpoint to read: `apps/admin-api/src/admin_api/api/services.py` (`create_service`)
