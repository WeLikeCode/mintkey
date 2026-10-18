# Design — Operator Management API

## Context
`public.operators` + `operator_tenant_memberships` already exist (Liquibase `002`/`014`) with RLS
(`tenant_isolation`: `tenant_id = app.current_tenant OR app.platform_admin_view='on'`) and unique
indexes on `(tenant_id, email)` and partial `oidc_sub`. The closest existing endpoint pattern is
`api/tenants.py` (platform-level, `require_platform_admin_session`, `_set_platform_admin_rls`). The
KC-write logic that would be needed to *create* users lives only in `apps/seed-job/create_operator.py`
and is intentionally not brought into admin-api (ADR-0031 D3).

## Decisions
### D1 — Reuse the `tenants.py` platform pattern
`operators.py` copies the `tenants.py` shape: flat `APIRouter(prefix="/v1/operators")`,
`_authz: None = Depends(require_platform_admin_session)`, `_set_platform_admin_rls(session)` at the
top of each handler, bound-parameter `text()` SQL (no f-strings — ADR-0008), `mintkey:code`/`title`
error envelope via `JSONResponse`, `IntegrityError → 409`.

### D2 — Wire IDs via existing helpers
`db_uuid_to_wire(id, "op")` on the way out; a local `_wire_to_uuid(op_id)` wrapping
`wire_to_db_uuid(op_id, "op")` on the way in (→ `422 invalid_id` on malformed input, mirroring
`agents.py`).

### D3 — Audit against the home tenant
`audit_emit(tenant_id=<operator.tenant_id>, actor_type="platform_admin", actor_id=<session operator>,
target_type="operator", ...)`. The zero-UUID used for the RLS GUC is not a valid audit-chain tenant;
the operator's real `tenant_id` (which has an `audit_chain_state` row) is used.

### D4 — No secret leakage
`SELECT`s enumerate the safe columns only; `internal_password_hash` is never selected into a response
model nor placed in an audit payload.

## Testing strategy
- **admin-api unit** (`tests/unit/admin_api/test_operators.py`, fake-session pattern from
  `test_email_permission_grants.py`): create happy-path (201, one INSERT, `operator.created`); 409 on
  dup email; 409 on dup `oidc_sub`; response omits `internal_password_hash`; PATCH sets flag + emits
  `operator.updated`; PATCH 404; DELETE soft-deactivate + `operator.deleted` + idempotent 204; audit
  `actor_type=platform_admin`.
- **Contract gates**: `openapi-spec-validator` on the YAML; `tests/acceptance/test_openapi_parity.py`
  (router imported + `include_router` + snapshot updated for the new `/v1/operators` prefix).
- **Architecture gates**: SQLi (bound params), audit chokepoint/append-only, PlatformAdmin RLS,
  secret-plaintext.
- **admin-ui vitest** (`tests/test_operators.test.ts`): new-action handler posts to `/v1/operators`
  and surfaces the success/error notice; list render.
- **Playwright** (`e2e/tests/NN-operators.spec.ts` + `e2e/pages/operators.ts`): platform-admin
  promotes → sees the row → toggles platform-admin → deactivates.

## Risks & mitigations
- **Privileged surface** (grants `is_platform_admin`): platform-admin gate + signed-request + CSRF +
  audit. Independent adversarial review of the authz path before merge.
- **RLS mistake exposing cross-tenant rows**: covered by the PlatformAdmin RLS architecture gate and a
  unit test asserting the `platform_admin_view` GUC is set.
- **Snapshot drift** breaking the parity gate: `tests/acceptance/openapi_snapshot.json` regenerated as
  an explicit task step.
