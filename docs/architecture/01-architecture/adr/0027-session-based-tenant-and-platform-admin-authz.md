# ADR-0027: Session-Based Tenant and Platform-Admin Authorization (admin-api)

## Status
Proposed — 2026-06-15

## Context

The admin-api enforces multi-tenancy with Postgres RLS (ADR-0008): each handler calls `set_tenant_context(session, tenant_id)` which sets `app.current_tenant`, and RLS policies scope rows to that tenant. The effective identity is meant to come from the operator's validated session (ADR-0019: the `mintkey_session` cookie; the signed-request / write-auth model).

An authorization-hardening effort (referenced in code as "SCOPE-A / ADR-SCOPE-A" in `auth/sessions.py`, but never written as an ADR) introduced `require_tenant_session(request, tenant_id)` — a FastAPI dependency that validates the session cookie and enforces `session.tenant_id == path tenant_id`, with a platform-admin bypass via the DB column `operators.is_platform_admin` (`_is_operator_platform_admin`). It was applied to some routers (`services`, `email_services`, `oauth2_providers`) and **never finished**, leaving two gaps:

1. **Tenant-scoped endpoints without `require_tenant_session`.** ~33 handlers across 9 routers (`agents`, `api_keys`, `api_keys_shortcut`, `audit`, `credentials`, `permissions`, `email_permission_grants`, plus stragglers in `services`/`email_services`) take a `/v1/tenants/{tenant_id}/…` path, call `set_tenant_context` with the **path** `tenant_id`, and do **not** verify the caller's session belongs to that tenant. A non-platform-admin operator (or, for the currently-ungated reads, any caller) can read/write another tenant's data by changing the `{tenant_id}` in the URL.

2. **Platform-admin decided by a client-settable header.** `tenants.py`, `audit_admin.py`, and `settings.py` gate on `_is_platform_admin(request)` = `request.headers["X-Platform-Admin"] == "true"` (a documented "MVP stub"), and `middleware/platform_admin_audit.py` keys the cross-tenant audit trail off the same header. The admin-ui BFF sets this header from the validated session, but **admin-api binds `0.0.0.0:8080` directly with no edge proxy and no header sanitization** — so any direct caller who sends `X-Platform-Admin: true` obtains full platform-admin (create/delete any tenant, cross-tenant RLS bypass via `app.platform_admin_view='on'`, read any tenant's audit chain, read/write global settings). This is a directly-exploitable privilege escalation / complete tenant-isolation bypass. (`tenants.py:get_tenant` additionally has no authz check at all.)

This ADR finishes and formalises SCOPE-A: **all authorization is derived from the validated session, never from client-controllable request headers or path parameters alone.**

## Decision

### D1 — `require_tenant_session` on every tenant-scoped data endpoint
Every handler whose route is `/v1/tenants/{tenant_id}/…` and that reads or writes tenant-scoped data SHALL declare `_authz: None = Depends(require_tenant_session)`. This enforces `session.tenant_id == path tenant_id` (platform-admins bypass via the DB flag). Reads are included — they are independently exploitable cross-tenant because they set the RLS context from the path.

### D2 — `require_platform_admin_session` for platform-admin endpoints; remove the header trust
A new dependency `require_platform_admin_session(request)` is added to `auth/sessions.py` (mirroring `require_tenant_session`): it validates the `mintkey_session` cookie and requires `_is_operator_platform_admin(session.operator_id)` (the DB flag), 401 if unauthenticated, 403 otherwise. The cross-tenant/platform-admin endpoints — `tenants.py` CRUD (`create`/`list`/`update`/`delete`/`get`), `audit_admin.py` (`verify-chain`, `acknowledge-tamper`), `settings.py` (`GET`/`PATCH /v1/admin/settings`) — use it. The header-based `_is_platform_admin(request)` helpers are **deleted**; the `X-Platform-Admin` request header is no longer trusted for any authorization or RLS-bypass decision. `middleware/platform_admin_audit.py` derives platform-admin from the session (and records the real `actor_id`) instead of the header.

### D3 — Exempt classes (MUST NOT get tenant enforcement)
- **Public** — `auth.py` (login/logout/whoami/OIDC), `health.py`: no session by design.
- **Internal / service-to-service** — `internal.py`, the internal oauth2-refresh route: authenticated by service identity/token (`X-Mintkey-Service-Token`), not operator sessions.
- **Agent data plane** — `proxy.py`: authenticated by the agent service-API-key (Argon2id), `@no_csrf`.
- **State-token-gated** — the OAuth2 `…/callback` handlers: gated by a single-use `state` token (the IdP redirect carries no operator cookie).
- **Static catalog** — `service_templates.py`: non-tenant, read-only catalog with no tenant data.
- **Non-tenant utility** — `changes.py` (`/v1/changes`): evaluate; if it exposes tenant-scoped change data it MUST move to session-scoped filtering (tracked as a follow-up).

### D4 — Authorization-coverage gate (anti-regression)
An architecture test SHALL assert that **every** route whose path matches `/v1/tenants/{tenant_id}/…` has `require_tenant_session` in its dependency list, except an explicit, documented allowlist (the EXEMPT-other state-token callbacks). A new tenant-scoped handler that forgets the dependency fails CI. (Mirrors the RLS-coverage gate, ADR-0008/0014.)

### D5 — No contract or behavioral change for legitimate callers
Adding session-derived authorization changes no wire contract: the same operators making the same in-tenant calls through the admin-ui BFF are unaffected (the BFF already carries the session cookie; platform-admins still bypass via the DB flag). Only cross-tenant access by a non-owner and header-spoofed platform-admin are newly rejected (403). admin-api unit tests call handlers directly (bypassing `Depends`), so enforcement is verified by TestClient-level cross-tenant tests + the D4 coverage gate, not by the existing direct-call unit tests.

## Consequences

| Good | Bad / Cost |
|---|---|
| Closes a directly-exploitable platform-admin escalation and cross-tenant read/write across the admin-api | ~33 handlers + 5 platform-admin sites edited; many direct-call test sites gain an `_authz=None` kwarg |
| Authorization is uniformly session-derived; the coverage gate prevents future omissions | A second authz layer over RLS (defense-in-depth) — slight per-request cost (one session lookup) |
| `X-Platform-Admin` header trust (spoofable) removed entirely | The admin-ui BFF no longer needs to send it for authz (it may still send it for display); confirm no UI relies on it for authz |

## Alternatives Considered

| Option | Why not |
|---|---|
| Centralized ASGI middleware enforcing tenant for all `/v1/tenants/{tenant_id}/*` | Cleaner in theory, but a bigger change to the auth model, must special-case the tenant-CRUD and callback paths, and diverges from the established per-handler `Depends` pattern. Per-handler + a coverage gate gives the same guarantee with less architectural risk. |
| Keep the `X-Platform-Admin` header but strip/validate it at an edge proxy | admin-api is directly reachable; relying on an edge is fragile. Deriving platform-admin from the validated session is robust regardless of network topology. |
| Fix only the credential-handling routers | Leaves known cross-tenant holes on agents/permissions/audit/etc. The user chose full hardening. |

## Amends
- **ADR-0008 / ADR-0019**: completes the session-derived authorization the RLS + BFF model assumes; formalises the informal "SCOPE-A".
- Supersedes the dangling `ADR-SCOPE-A` code reference in `auth/sessions.py`.

## Open Follow-ups
- `agent_secrets` endpoints get the same `require_tenant_session` rollout on the operator-provisioned-agent-secrets branch (ADR-0026); when both branches merge, the agent_secrets coverage is unified.
- Decide whether `tenants.py:get_tenant` should allow a tenant to read its OWN row (`require_tenant_session`) vs platform-admin-only (`require_platform_admin_session`); this ADR defaults to platform-admin-only (it was previously unauthenticated).
- `changes.py` tenant-scoping review (D3).

## Related
- ADR-0008: Multi-tenancy (RLS)
- ADR-0019: Admin UI BFF + write auth
- ADR-0020: SSO / Keycloak (operator identity)
- ADR-0026: Operator-provisioned agent secrets (sibling branch; same `require_tenant_session` pattern)
