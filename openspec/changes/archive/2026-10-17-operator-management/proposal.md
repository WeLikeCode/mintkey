# Operator Management API

## Why
`public.operators` (Liquibase `002`/`014`) has no REST/UI surface. Promoting a Keycloak
realm-`mintkey` user to a Mintkey operator, listing operators, changing role/status, or
deactivating one all require the seed-job or a direct DB write today. Operators — the humans
who hold `is_platform_admin` and tenant-admin roles — need a first-class, audited,
signed-request CRUD surface.

## What Changes
- New admin-api resource `/v1/operators` (platform-admin only):
  - `GET /v1/operators` — list (query: `q`, `tenant_id`, cursor, limit).
  - `POST /v1/operators` — promote/create by email (`{ email, display_name?, oidc_sub?, is_platform_admin?, tenant_id }`).
  - `PATCH /v1/operators/{operator_id}` — update `display_name` / `is_platform_admin` / `status`.
  - `DELETE /v1/operators/{operator_id}` — deactivate (soft, `status='disabled'`).
- Responses never carry `internal_password_hash`. Operators expose `op_`-prefixed ULID wire IDs.
- No Keycloak call from admin-api: `oidc_sub` is optional and links lazily on first login (ADR-0020).
- New audit events `operator.created` / `operator.updated` / `operator.deleted`.
- New Admin-UI `operators` resource (AdminJS BFF) with promote / edit / deactivate actions.
- ADR-0031 records the path-scoping, wire-ID, KC-linkage, delete, and audit decisions.

## Capabilities
### New Capabilities
- `operator-management`: promotion (create), listing, metadata/role/status update, and
  deactivation of operators, with platform-admin authz, signed-request writes, and full audit.

### Modified Capabilities
<!-- none archived in openspec/specs for this surface yet -->

## Impact
- **Contracts (canonical — edit first)**: `docs/architecture/contracts/rest/openapi.yaml`
  (2 paths + `Operator`/`CreateOperatorRequest`/`UpdateOperatorRequest`/`OperatorPage` schemas +
  `OperatorId` param); `docs/architecture/contracts/events/audit-event.schema.json` (3 event types);
  new ADR `docs/architecture/01-architecture/adr/0031-operator-management-api.md` (+ `adrs/` symlink
  + `README.md` index row).
- **DB**: none (table exists; no `updated_at` added — see ADR-0031 D5).
- **admin-api**: `api/operators.py` router + `include_router` in `main.py`; update
  `tests/acceptance/openapi_snapshot.json`; audit emit.
- **admin-ui**: `resources/operators.ts` + register in `index.ts`; promote/edit/deactivate actions.
- **Tests**: admin-api unit (create happy / 409 dup email / 409 dup oidc_sub / no-hash-in-response /
  platform-admin-actor audit / cross-tenant RLS); admin-ui vitest (handler + render); Playwright e2e
  (promote → list → patch → deactivate); arch gates (openapi parity, audit coverage, RLS, SQLi).
- **Out of scope**: creating the Keycloak user itself (needs realm-admin); operator self-service;
  internal-password reset (stays in the ADR-0020 CLI).

## Issue Intake (remediation gate)
1. **Problem statement**: No API/UI to promote a Keycloak user to a Mintkey operator or manage operators.
2. **User-visible symptom**: Operators are created only via seed-job / direct DB writes; the Admin UI has no Operators screen.
3. **Expected behavior**: A platform admin promotes, lists, edits role/status, and deactivates operators; every operation is audited.
4. **Evidence**: No `operators.py` in `apps/admin-api/src/admin_api/api/` (verified 2026-07-16); table present in Liquibase `002`/`014`.
5. **Scope**: `openapi.yaml` + `audit-event.schema.json` + ADR-0031; admin-api router + audit; admin-ui resource + actions; tests + gates.
6. **Out of scope**: see Impact.
7. **Risk level**: MEDIUM — privileged-role write surface (`is_platform_admin`); orchestrated implementation + independent adversarial review.
8. **Verification target**: all validators green (openapi-spec-validator, `openspec validate --strict`, openapi parity, audit-coverage, RLS/SQLi gates) + live e2e promote→list→patch→deactivate with audit-chain check and zero `internal_password_hash` leakage.
9. **Owner decisions**: wire-ID form and path scoping — resolved in ADR-0031 (D1: `/v1/operators` platform-admin; D2: `op_` ULID).
