# ADR‑0013: AdminJS pin set for the Admin Web UI

## Status
Accepted — 2026-05-10. Appendix to [ADR‑0005](0005-admin-tech-stack.md).

## Context
[ADR‑0005](0005-admin-tech-stack.md) chose **AdminJS** (Node.js, COTS) as the Admin Web UI. This ADR pins the AdminJS‑specific libraries, conventions, and the integration with the FastAPI Admin REST API for sensitive operations.

## Decision

### Pinned libraries

| Concern                | Choice                                                            | Rationale |
|------------------------|-------------------------------------------------------------------|-----------|
| Node.js version        | **Node 20 LTS**                                                   | Long‑term support |
| Package manager        | **pnpm**                                                          | Faster, disk‑efficient, monorepo‑friendly |
| TypeScript             | **TypeScript 5.x strict**                                         | First‑class in AdminJS |
| AdminJS                | **AdminJS 7.x**                                                   | Current stable major |
| AdminJS server adapter | **`@adminjs/express`**                                            | Reference; Express ecosystem |
| AdminJS DB adapter     | **`@adminjs/sql`**                                                | Direct DB access; simplest path; matches schema‑first approach |
| Auth integration       | **`@adminjs/passport` + `passport-openidconnect`**                | Keycloak/OIDC; standard |
| HTTP framework         | **Express** (paired with `@adminjs/express`)                      | Reference |
| Session storage        | **`connect-pg-simple`** (Postgres‑backed sessions)                | Same DB as the rest of the stack; cross‑service session‑lookup if needed |
| Logging                | **`pino`** (JSON logs) + `pino-pretty` for dev                    | Fast structured logs; pairs with structlog (Python) and slog (Go) |
| OTel                   | `@opentelemetry/auto-instrumentations-node` + `@opentelemetry/sdk-node` | Auto‑instruments Express + pg |
| Service‑to‑service auth | shared internal token (delivered via env, rotated per release)    | For Custom Actions that POST to FastAPI |
| Testing                | **`vitest`** + `supertest`                                        | Fast modern test runner; HTTP testing |
| Linting                | **`eslint`** + `@typescript-eslint` + `prettier`                  | Standard |
| Build                  | **`tsc`** + `tsx` for dev runtime                                  | Standard TS toolchain |
| Container image        | multi‑stage build → `node:20-alpine` final                          | Small, glibc‑free |

### AdminJS resource definitions
One AdminJS resource per domain entity:
- `Tenant`, `Operator`, `OperatorTenantMembership`, `Service`, `Credential`, `Agent`, `PermissionGrant`, `AuditEvent`.

Each resource has:
- A `before` hook that filters by the active session's tenant (`req.session.tenant_id`) so the operator only ever sees their own tenant's data.
- Field configuration: `x-mintkey-sensitive` fields (e.g., `Credential.value`, `Agent.api_key`) are **read‑only and write‑only at create**. AdminJS list/show views never display them.
- Standard CRUD enabled for non‑sensitive entities; sensitive operations are Custom Actions (below).

### Sensitive operations as Custom Actions (route to FastAPI)
The audit chokepoint and validation logic stay in the FastAPI ([ADR‑0005](0005-admin-tech-stack.md)). AdminJS dispatches sensitive operations via Custom Actions that POST to FastAPI rather than touching the DB directly:
- **Credential rotate** — `POST /v1/tenants/{tid}/services/{sid}/credentials` (FastAPI does envelope encryption + audit emission).
- **Credential revoke** — `DELETE /v1/tenants/{tid}/services/{sid}/credentials/{key_version}`.
- **Agent revoke** — `POST /v1/tenants/{tid}/agents/{aid}/revoke`.
- **Permission grant / revoke** — `POST/DELETE /v1/tenants/{tid}/agents/{aid}/permissions[/{permId}]`.

For these, AdminJS Custom Actions invoke FastAPI using a service‑to‑service shared token (rotated per release; stored as an env var on the AdminJS container, mirrored on the FastAPI side). The FastAPI verifies the token and treats the request as coming from the operator's session (passed in a special header).

### Auth / session
- Operator authenticates via Keycloak using `passport-openidconnect`.
- AdminJS issues an `mintkey_session` cookie backed by `connect-pg-simple` against Postgres.
- The session record carries `(operator_id, tenant_id, oidc_sub)` and (if multi‑tenant operator) a tenant selector flow.
- After OIDC login, AdminJS calls `GET /v1/auth/whoami` on the FastAPI to fetch the operator's role and active tenant; uses these to scope resource visibility.
- Logout: invalidate session row + (configurable) Keycloak end‑session redirect.

### Project layout

```
admin-ui/
  package.json
  pnpm-lock.yaml
  tsconfig.json
  src/
    server.ts                      # Express + AdminJS bootstrap
    auth/
      oidc.ts                      # passport-openidconnect setup
      session.ts                   # connect-pg-simple session middleware
    fastapi-client/                # client to FastAPI for Custom Actions
      index.ts
    resources/                     # one file per AdminJS resource
      tenant.ts
      operator.ts
      service.ts
      credential.ts
      agent.ts
      permission.ts
      audit-event.ts
    actions/                       # Custom Actions (route to FastAPI)
      credential-rotate.ts
      credential-revoke.ts
      agent-revoke.ts
      permission-grant.ts
      permission-revoke.ts
    components/                    # custom React components when stock isn't enough
      credential-rotate-form.tsx
      audit-filter.tsx
    middleware/
      tenant-context.ts            # injects req.session.tenant_id into hooks
      otel.ts
  Dockerfile
```

### Code style
- TypeScript strict mode; no `any`.
- `eslint --max-warnings=0` in CI.
- `prettier` on every file.
- One file per resource; one file per Custom Action.

### Multi‑tenancy
Per [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md):
- Tenant selector visible only when the operator has > 1 tenant membership.
- Every AdminJS DB query passes through a `before` hook that scopes to the active tenant.
- The AdminJS container does **not** subscribe to the change channel — propagation goes through the FastAPI for AdminJS's purposes (and AdminJS reads fresh from the DB on each list/show view, which is sufficient for an admin UI).

## Consequences

### Positive
- The Admin UI is mostly off‑the‑shelf; custom UI code is bounded to resource definitions, hooks, and a few Custom Actions.
- Postgres‑backed sessions share the same DB as the rest of the stack — no Redis or in‑memory session store.
- pino + auto‑instrumentation gives parity with the Python OTel posture.
- pnpm reduces disk footprint and install time.
- Sensitive operations always go through the FastAPI audit chokepoint.

### Costs
- AdminJS is React under the hood; we accept its bundle size for an internal admin UI.
- AdminJS API churn between major versions can require migration work (see Risks).
- A service‑to‑service shared token is an additional secret to rotate.

### Risks
- **AdminJS major version bumps** may require resource‑definition rewrites. Mitigation: pin version per release; integration tests against the pinned version.
- **React‑version drift** in AdminJS: dependent on AdminJS's own React version policy. Mitigation: limit custom React components to the bare minimum.
- **Service‑to‑service token leak** between AdminJS and FastAPI compromises sensitive operations. Mitigation: rotate per release; restrict the token's scope; emit audit events on use.

## Implications
- The Admin UI runs as `mintkey/admin-ui` container in compose.
- It shares the Postgres DB with the Admin REST API.
- Sensitive operations dispatch to the FastAPI for audit + validation.
- Operator session is established via Keycloak OIDC.
- The Admin UI does not subscribe to the change channel.

## Open follow‑ups
- Whether to use `@adminjs/typeorm` instead of `@adminjs/sql` if we adopt TypeORM elsewhere. *Lean: stay with `@adminjs/sql`; we don't need TypeORM.*
- AdminJS branding (logo, theme).
- Custom React components needed in v1 (credential‑rotate confirmation form, audit log filter form, agent permissions matrix). The full list lands in iteration 3 flows + Phase 1.
- Whether to add a CSRF middleware on the FastAPI side specifically for AdminJS Custom Action calls. *Lean: yes — every state‑changing endpoint gets CSRF.*

## Related
- [ADR‑0005 admin tech stack](0005-admin-tech-stack.md).
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — tenant selector.
- [ADR‑0010 change channel](0010-change-channel-postgres-listen-notify.md) — AdminJS does not subscribe.
- [ADR‑0012 Python stack pin](0012-python-stack-pin.md) — counterpart for the FastAPI side.
