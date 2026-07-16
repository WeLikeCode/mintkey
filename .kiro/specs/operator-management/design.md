# Operator Management — Design

See ADR-0031 and `openspec/changes/operator-management/design.md` for the full rationale. Summary:

## Components
- **admin-api**: `apps/admin-api/src/admin_api/api/operators.py` — a flat `/v1/operators` router
  mirroring `api/tenants.py` (platform-admin, `_set_platform_admin_rls`, bound-param `text()` SQL,
  `mintkey:code` error envelope). Registered via `include_router` in `main.py`.
- **admin-ui**: `apps/admin-ui/src/resources/operators.ts` (RestResource + ResourceWithOptions),
  registered in `index.ts`, gated on `currentAdmin.isPlatformAdmin`. Writes via `apiWrite`
  (`lib/api-client.ts`) with `operatorOptsFromAdmin` → signed request + CSRF.
- **contracts**: `openapi.yaml` (paths + schemas + `OperatorId` param) and
  `audit-event.schema.json` (3 event types).

## Data
- Reuses `public.operators` + `operator_tenant_memberships` (Liquibase `002`/`014`). No migration
  (ADR-0031 D5). Wire IDs derived from the UUID PK via `db_uuid_to_wire(id,"op")`.

## Authz & audit
- `require_platform_admin_session` on all endpoints. Writes additionally require the
  AdminUiSignedRequest envelope + CSRF header (ADR-0019). Audit `actor_id` from session; events emitted
  against the operator's home `tenant_id`.

## Testing
- admin-api unit (fake-session pattern), admin-ui vitest, Playwright e2e, plus the arch gates
  (openapi-parity, audit-coverage, PlatformAdmin-RLS, SQLi). Verification output pasted into the PR.
