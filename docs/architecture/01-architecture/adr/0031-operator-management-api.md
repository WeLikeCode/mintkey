# ADR-0031: Operator Management API — promote Keycloak realm-`mintkey` users to Mintkey operators

## Status
Proposed — 2026-07-16

## Context

`public.operators` (Liquibase `002-operators.yaml`, `014-operators-keycloak.yaml`) is the
identity of record for humans who administer Mintkey. Today an operator can only be created
out-of-band — by the seed-job (`apps/seed-job/create_operator.py`) or a direct DB write. There
is no REST or Admin-UI surface to:

- promote an existing Keycloak realm-`mintkey` user to a Mintkey operator,
- list operators,
- change an operator's `display_name` / `is_platform_admin` / `status`, or
- deactivate an operator.

ADR-0020 made Keycloak the canonical IdP: operators authenticate via OIDC and are matched by
`oidc_sub`, with a lazy email→`oidc_sub` link on first login (`auth/oidc.py`
`lookup_operator_by_oidc_sub`). ADR-0027 established session-derived authz. ADR-0017.10 made the
prefixed-ULID the canonical wire-ID form. This ADR adds the missing CRUD surface and settles the
three decisions that shape its contract.

## Decision

### D1 — Path scoping & authz: `/v1/operators`, platform-admin only
Operator management is a **platform-level** action: it mints and revokes the humans who hold
`is_platform_admin` and tenant-admin roles, and it spans tenants. It therefore lives at the flat
`/v1/operators` collection (mirroring `/v1/tenants`, the existing platform resource) and every
endpoint is gated by `require_platform_admin_session`. The home tenant is carried in the request
body (`tenant_id` on create) and as a query filter (list), not in the path. Cross-tenant reads/
writes use the platform-admin RLS view (`app.platform_admin_view='on'`), exactly as
`api/tenants.py` does.

*Rejected:* `/v1/tenants/{tenant_id}/operators` + `require_tenant_session`. Operators are
tenant-scoped *data*, but delegating operator creation (and platform-admin grants) to tenant
admins widens the trust boundary; keeping it platform-admin-only is the conservative choice.

### D2 — Wire ID: `op_`-prefixed ULID
Operators expose an `op_<26-char Crockford>` wire ID, derived from the existing `operators.id`
UUID column via `db_uuid_to_wire(id, "op")` / `wire_to_db_uuid(wire, "op")`. This matches
ADR-0017.10 and every other resource (`agent_`, `tenant_`, `svc_`, `perm_`, `sec_`). No schema
change: the DB PK stays a UUID; only the serialized form is prefixed.

### D3 — Keycloak linkage is by email + lazy `oidc_sub`; admin-api gets NO realm-admin
The create endpoint accepts `{ email, display_name?, oidc_sub?, is_platform_admin?, tenant_id }`
and inserts an `operators` row. It **does not call Keycloak**. If `oidc_sub` is supplied it is
stored (and must be unique); otherwise the existing lazy email→`oidc_sub` link (ADR-0020) binds it
on the operator's first "Sign in with Keycloak". This is the codebase's intended "shadow operator"
flow. Consequently admin-api is **not** granted Keycloak realm-admin credentials — that blast-radius
increase is deliberately avoided.

*Explicit non-goal:* creating the Keycloak user itself from admin-api (that requires realm-admin
and is out of scope; the Keycloak user is provisioned by a Keycloak admin or the seed-job CLI).

### D4 — Delete is a soft-deactivate
`DELETE /v1/operators/{operator_id}` sets `status = 'disabled'` (it does not hard-delete). `sessions`
and `operator_tenant_memberships` FK-reference `operators(id)`; a hard delete would orphan or fail.
Deactivation is idempotent (`204`).

### D5 — No `updated_at` migration
`operators` has no `updated_at` column and this ADR adds none; `PATCH` updates the mutable columns
only. (A future attribution/audit-column migration may add `updated_at`/`created_by` if needed.)

### D6 — Audit & write-auth
Every write emits an append-only, hash-chained audit event — `operator.created`, `operator.updated`,
`operator.deleted` — with `actor_type = "platform_admin"`, `actor_id` taken from the **session** (not
any JWT body), against the operator's home `tenant_id`. `internal_password_hash` is never serialized
in any response or audit payload (S-SEC-1). Writes require the AdminUiSignedRequest envelope + the
double-submit CSRF header (ADR-0019, ADR-0017.3).

## Consequences

**Positive**
- First-class, audited operator lifecycle; the manual seed-job path is no longer the only way.
- No new privilege for admin-api (D3) — the smallest viable trust surface.

**Costs / new surface**
- New router `apps/admin-api/src/admin_api/api/operators.py` (+ `include_router` in `main.py`;
  update `tests/acceptance/openapi_snapshot.json` for the new `/v1/operators` prefix).
- `docs/architecture/contracts/rest/openapi.yaml` gains 2 paths, the `Operator` /
  `CreateOperatorRequest` / `UpdateOperatorRequest` / `OperatorPage` schemas, and an `OperatorId`
  parameter.
- `docs/architecture/contracts/events/audit-event.schema.json` gains 3 event types.
- New Admin-UI `operators` resource + promote/edit/deactivate actions.

**Risks**
- Privileged write surface (grants `is_platform_admin`). Mitigated by platform-admin gating (D1),
  signed-request + CSRF (D6), and full audit.

## Alternatives considered
| Option | Why not |
|---|---|
| Tenant-scoped path + tenant-session | Delegates platform-admin creation to tenant admins (D1). |
| admin-api creates the KC user (realm-admin) | Large blast-radius increase; unnecessary for the promote flow (D3). |
| Raw-UUID wire ID | Diverges from ADR-0017.10; inconsistent with every other resource (D2). |
| Hard delete | Violates `sessions` / membership FKs (D4). |

## Related
- [ADR-0020](0020-sso-keycloak-canonical-idp.md) — Keycloak canonical IdP; operator `oidc_sub` + lazy link.
- [ADR-0027](0027-session-based-tenant-and-platform-admin-authz.md) — session-derived authz.
- [ADR-0019](0019-admin-ui-bff-and-write-auth.md) — signed-request write auth + CSRF.
- [ADR-0017](0017-round-3-corrections.md) §10 — prefixed-ULID wire form.
- OpenSpec change: `openspec/changes/operator-management/`.
- Kiro spec: `.kiro/specs/operator-management/`.
