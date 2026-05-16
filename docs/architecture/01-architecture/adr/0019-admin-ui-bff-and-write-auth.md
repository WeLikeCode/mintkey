# ADR‑0019: AdminJS is a backend‑for‑frontend over the admin‑api REST API; write authentication

## Status
Accepted — 2026-05-12. **Amends** [ADR‑0013](0013-adminjs-pin.md) (AdminJS no longer uses a DB adapter), [ADR‑0014](0014-iter-1-2-corrections.md) §14.5 (extends "all AdminJS writes route via FastAPI" to "all AdminJS *data access* routes via FastAPI") and §14.6 (refines the `AdminUiSignedRequest` model — now *additive* to the session cookie, not a substitute for operator identity), and [ADR‑0016](0016-round-2-corrections.md) §16.1 (the `jti` denylist is carried; the JWT now sits on top of the session cookie). Drafted from `team/remediation/ADMIN_UI_SPEC.md` and the adversarial‑review findings F‑SEC‑1/F‑SEC‑2 (unbounded blast radius of the JWT‑only model) and F‑UI‑1/F‑UI‑2 (the `@adminjs/sql` read connection never had a tenant scope).

> **AMENDED by ADR-0020 (2026-05-15):** §3 — admin-api OIDC callback is the single front door for operator login; admin-ui relays the `mintkey_session` cookie to `GET /v1/auth/whoami` on every request (15s LRU cache). The OIDC flow is wired and authoritative; Keycloak is the canonical IdP per ADR-0020. See [ADR-0020](0020-sso-keycloak-canonical-idp.md).

## Context
ADR‑0005/ADR‑0013 chose AdminJS as the operator UI, reading via `@adminjs/sql` (a read‑only DB connection) and writing via FastAPI with an `AdminUiSignedRequest` Ed25519 JWT (ADR‑0014.5/0014.6, `jti`‑replay‑protected per ADR‑0016.1). Two problems surfaced in implementation and the adversarial reviews:

1. **The read DB connection is the wrong shape.** A pooled `@adminjs/sql` connection from the AdminJS process needs `app.current_tenant` set per request for Postgres RLS to scope it — and AdminJS's data layer has no clean per‑request hook for that. The implementation never set it (every list view returned zero rows; the role it connected as didn't exist). It also means RLS is enforced in *two* places (admin‑api for writes, the read connection for reads) — a divergence risk.
2. **The write‑auth model has an unbounded blast radius.** The `AdminUiSignedRequest` JWT alone carried `sub`/`tnt` and admin‑api trusted them. So a leak of AdminJS's Ed25519 private key lets an attacker mint a JWT for *any* operator in *any* tenant — the 60 s TTL doesn't help (mint repeatedly), and there is no binding to a real, authenticated operator session (F‑SEC‑1/F‑SEC‑2).

The project owner directed: **AdminJS should use the admin‑api REST API, not a direct DB connection**; and for the write‑auth question, **use the best practice that is also easy to test, and document the decision everywhere.**

## Decision

### 1. AdminJS is a backend‑for‑frontend (BFF) over the admin‑api REST API — no database connection
AdminJS holds **no** database connection: no `@adminjs/sql`, no `pg`, no `connect‑pg‑simple`. The admin‑api is the single front door. AdminJS is a thin presentation layer:
- **All data access — list, show, create, update, delete, and audit reads — goes through admin‑api REST endpoints.** A custom AdminJS resource adapter (`RestResource`/`RestDatabase`) maps AdminJS's data‑layer interface (`find`/`findOne`/`create`/`update`/`delete`/`count`/`properties`) onto those calls; property schemas come from the OpenAPI component schemas.
- **Admin‑api owns RLS.** It sets `app.current_tenant` (and, for the PlatformAdmin "all tenants" view, `app.platform_admin_view='on'` per ADR‑0016.3) per request from the operator's session. RLS is enforced in exactly one place.
- **Admin‑api owns the session.** AdminJS's `authenticate()` POSTs `/v1/auth/internal-login`; admin‑api verifies the operator (Argon2id, identical‑body/equalized‑timing per ADR‑0017.5) and issues the `mintkey_session` cookie (`HttpOnly; Secure; SameSite=Strict`); AdminJS relays that `Set‑Cookie` to the browser. On every subsequent request AdminJS relays the browser's `mintkey_session` cookie on its outgoing calls to admin‑api, and validates the session by calling `GET /v1/auth/whoami` (caching the result in‑process briefly — default 15 s — so a multi‑replica AdminJS works; admin‑api is the shared state). The OIDC path terminates at admin‑api the same way. AdminJS keeps no Postgres‑backed session store.

### 2. Write authentication: session cookie + `AdminUiSignedRequest` JWT, both required, must agree; identity from the session
For every **state‑changing** admin‑api endpoint reachable from AdminJS (`POST`/`PATCH`/`PUT`/`DELETE` under `/v1/tenants/...` and the custom actions — service test, register/rotate credential, revoke, rotate API key, create agent, grant permission, etc.), admin‑api requires **all** of:
1. a valid, unexpired `mintkey_session` cookie — admin‑api looks it up in `sessions` and reads the **authoritative** `operator_id` + `tenant_id` + roles;
2. a valid `AdminUiSignedRequest` Ed25519 JWT in `Authorization: Bearer` — signature verifies against AdminJS's public key (fetched from the Vault Adapter at startup, force‑refreshed on verify failure per ADR‑0016.2), `iss="mintkey/admin-ui"`, `aud="mintkey/admin-api"`, `iat`/`exp` within bounds (`exp ≤ iat + 60 s`), `jti` not present in `admin_request_jti` (insert it; conflict ⇒ 401 `replay_detected`);
3. **agreement:** `jwt.sub == session.operator_id` **and** `jwt.tnt == session.tenant_id`; and when the request asserts the PlatformAdmin "all tenants" view, `session.is_platform_admin == true`. Any mismatch ⇒ 401.

The **effective identity** used for the operation — stamped into the tenant‑context GUC and into the audit event's `actor_id` — is the **session's**, never the JWT's. The JWT is a *channel proof* ("this came through the AdminJS process, which is the only holder of the private key") + replay protection + a sanity cross‑check; it does **not** grant identity. **Reads** require only the valid session cookie (no JWT) — admin‑api scopes the read by the session's tenant.

This is the standard "the cookie says *who*; the signature says *that it came from the trusted channel*" pattern — a session + double‑submit, hardened with an asymmetric signature instead of a shared token.

### 3. Admin‑api obligations this implies
- `GET /v1/auth/whoami` is implemented (reads the `mintkey_session` cookie → `{operator_id, email, tenant_id, is_platform_admin, memberships}` or 401); it is no longer a stub.
- Every AdminJS resource has a `GET` list + `GET` one endpoint, with cursor pagination, the filters/sort the UI needs, and **human‑readable labels in list responses** (e.g. a permission‑grant row carries `agent_name` and `service_name`) so AdminJS does not N+1.
- One auth middleware path: for *every* `/v1/tenants/...` request (read or write) admin‑api authenticates the operator from the session and sets `app.current_tenant` from it; state‑changing requests additionally run the JWT + `jti` + agreement checks of §2. The CSRF middleware is exempted on the JWT‑bearing routes (the JWT + the `SameSite=Strict` cookie already defeat CSRF on those).

## Consequences

### Positive
- **Single front door, single RLS enforcement point.** RLS lives only in admin‑api; the divergence risk is gone, along with the `@adminjs/sql` / `mintkey_app_ro` / `SET app.current_tenant`‑on‑a‑pooled‑connection complexity.
- **Bounded blast radius.** A leak of AdminJS's Ed25519 private key *alone* is useless — the attacker also needs a live `mintkey_session` cookie for the target operator. A stolen session cookie *alone* is useless for writes — the attacker also needs to sign with AdminJS's key. Either single compromise is contained; you need *both* to forge a write.
- **Identity is unforgeable by the channel.** Because the effective identity is the session's (which admin‑api minted after verifying credentials), AdminJS — even a compromised AdminJS — cannot act *as* an operator it has no session cookie for. The audit attribution is trustworthy.
- **Easy to test.** Unit tests, each a one‑liner: valid cookie + matching valid JWT → allowed; cookie but no JWT → 401 (a direct call); JWT but no cookie → 401 (a forged call); `jwt.sub` ≠ session operator → 401; `jwt.tnt` ≠ session tenant → 401; replayed `jti` → 401; expired JWT → 401; expired session → 401; non‑PlatformAdmin asserting "all tenants" → 401; a read with a valid cookie and no JWT → allowed and tenant‑scoped. AdminJS side: testable with the `RestResource` adapter against a stubbed admin‑api (assert the request shape — cookie relayed on reads; cookie + JWT on writes) and end‑to‑end against a real testcontainer admin‑api.

### Costs
- A new component: the `RestResource`/`RestDatabase` AdminJS adapter (~200–400 LOC, well‑defined).
- Admin‑api must provide complete `GET` list/show endpoints for every resource with denormalized labels — more endpoint surface (covered by the `ENDPOINT_COVERAGE.md` work in `team/remediation/MEGA_PROMPT.md` §6).
- Slightly more per‑request work: AdminJS calls `whoami` per request (cheap; cached briefly), and admin‑api does a session lookup on every `/v1/tenants/...` call (it does so for writes already; now also for reads — one indexed lookup).

### Risks
- **The relayed‑cookie BFF mechanics** (cookie domain/path so the browser→AdminJS→admin‑api relay works across compose hosts) need care — mis‑configuration breaks login. Mitigated by an end‑to‑end browser test of login + a write.
- **`whoami` cache staleness** — if an operator is revoked, AdminJS may briefly act on a stale `whoami` (bounded by the cache TTL, ≤ 15 s; admin‑api re‑checks the session on every write regardless, so a revoked operator's *writes* are blocked immediately).
- **Not the maximal hardening.** The strongest form (the AdminJS signing key in a separate sidecar that validates the cookie *before* signing) is out of scope; §2 gets most of the benefit at a fraction of the cost. Revisit if the threat model demands it (follow‑up).

## Implications
- **Amends ADR‑0013** — AdminJS no longer uses `@adminjs/sql`/`pg`; a `RestResource` adapter replaces them. (Status‑line corrigendum on ADR‑0013 points here.)
- **Amends ADR‑0014 §14.5** — "all AdminJS writes route via FastAPI" → "all AdminJS *data access* routes via FastAPI". **Refines ADR‑0014 §14.6** — the `AdminUiSignedRequest` JWT is now *additive* to the session cookie; admin‑api requires both and requires agreement; the effective identity is the session's. (Status‑line corrigenda on ADR‑0014.)
- **Carries ADR‑0016 §16.1** (the `jti` denylist), now on top of the session cookie. (Status‑line corrigendum on ADR‑0016.)
- The Kiro spec is updated to match: `.kiro/specs/mintkey-mvp/design.md §4` (admin‑api auth middleware) + `§5` (Admin UI), `requirements.md` REQ‑SEC‑5, `tasks.md` T‑1.0.13 (the signed‑request middleware) and the AdminJS‑resource tasks (now REST‑backed, no `@adminjs/sql`).
- `team/remediation/ADMIN_UI_SPEC.md` and `team/remediation/PROMPT_ADMIN_UI.md` reflect this — the cookie + JWT‑must‑agree rule is the rule, not "consider".
- `AGENTS.md` / `CLAUDE.md` guardrails gain a line: "AdminJS is a BFF over the admin‑api REST API — no DB connection; reads via the relayed `mintkey_session` cookie; writes via cookie + `AdminUiSignedRequest` JWT, must agree, identity from the session (ADR‑0019)."
- `docs/architecture/01-architecture/05-threat-model.md` gains an entry: "AdminJS process / private‑key compromise" → bounded by the cookie requirement; the maximal mitigation (signing‑key sidecar) is a documented future option.

## Open follow-ups
- Move the AdminJS signing key into a separate sidecar that validates the cookie before signing (the maximal hardening) — Phase 2+; only if the threat model demands it.
- `whoami` cache TTL — pinned default 15 s; revisit under load.
- Whether reads from AdminJS should also be replay‑protected / signed — current decision: **no** (reads are idempotent and tenant‑scoped by the session; a `jti` per read would bloat `admin_request_jti`). Revisit only if a concrete need appears.

## Related
- [ADR‑0005 admin tech stack](0005-admin-tech-stack.md) — chose AdminJS + FastAPI.
- [ADR‑0013 AdminJS pin](0013-adminjs-pin.md) — amended here (no DB adapter).
- [ADR‑0014 iter 1+2 corrections](0014-iter-1-2-corrections.md) — §14.5 extended here to all data access; §14.6 refined here (cookie + JWT, must agree).
- [ADR‑0016 round‑2 corrections](0016-round-2-corrections.md) — §16.1 (`jti` denylist) carried; §16.2 (JWKS force‑refresh) used for the AdminJS public key; §16.3 (PlatformAdmin RLS escape) — the "all tenants" view signals admin‑api, which sets `app.platform_admin_view='on'`.
- [ADR‑0017 round‑3 corrections](0017-round-3-corrections.md) — §17.5 (internal‑login timing equalization) on the login path; the `AdminUiSignedRequest` security scheme defined there.
- [ADR‑0018 classical service API keys](0018-classical-service-api-keys.md) — the same least‑authority / indirection spirit.
- `team/remediation/ADMIN_UI_SPEC.md` — the per‑screen UX spec that implements this.
