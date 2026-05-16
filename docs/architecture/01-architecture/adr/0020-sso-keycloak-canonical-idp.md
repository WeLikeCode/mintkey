# ADR-0020: Keycloak as canonical IdP for all operator-facing UIs

## Status
Accepted — 2026-05-15.

Amends [ADR-0005](0005-admin-tech-stack.md) §"Internal auth fallback", [ADR-0014](0014-iter-1-2-corrections.md) §14.2 (Keycloak default), and [ADR-0019](0019-admin-ui-bff-and-write-auth.md) §3 (whoami).

---

## Context

Before this ADR, admin-ui authenticated operators against an Argon2id hash stored in `operators.internal_password_hash`. Keycloak existed in the compose stack but had no realm and was unused. This was incoherent — the rationale for bundling Keycloak was "Keycloak default out-of-the-box" (ADR-0005), yet operator login bypassed it entirely.

The inconsistency surfaced during implementation: "what is the purpose of Keycloak if you keep the password hash in the DB?" This ADR resolves that question by making Keycloak the canonical, sole operator IdP and demoting internal-password-auth to an explicit break-glass mechanism.

SSO-A through SSO-F (commits 46fc9768 through 9f90eea6) implemented the complete SSO stack before this ADR was written. This ADR documents the decisions taken in that work, surfaces the trade-offs, and establishes the guardrails for future changes.

**What was built:**
- Keycloak `mintkey` realm with 3 confidential PKCE clients (`mintkey-admin-api`, `mintkey-grafana`, `mintkey-jaeger`) and 3 realm roles.
- admin-api OIDC flow: PKCE, server-side token exchange, JWKS verification (1h cache), shadow-table operator lookup, `mintkey_session` cookie.
- admin-ui login page with Keycloak button and collapsed break-glass accordion; admin-ui holds no OIDC `client_secret`.
- Grafana native OIDC (`GF_AUTH_GENERIC_OAUTH_*`) with JMESPath role mapping.
- Jaeger behind `oauth2-proxy` v7.6.0 (`jaeger-auth` service) with `extra_hosts: host-gateway` for browser-visible issuer URL.
- 6 public-URL env vars in `.env.example`; Kong admin port bound to `127.0.0.1` (D4).
- DB changelog 015: `mintkey_app` + `mintkey_subscriber` roles get passwords; `operators.internal_password_hash` is NULL by default.
- Break-glass CLI: `mintkey admin reset-password` / `mintkey admin clear-password`.

---

## Decision

**Adopt Keycloak as the canonical IdP for all operator-facing UIs** (admin-ui, Grafana, Jaeger).

One realm (`mintkey`), three confidential PKCE clients (`mintkey-admin-api`, `mintkey-grafana`, `mintkey-jaeger`). Realm roles map to application roles as documented in [`docs/AUTH.md`](../../AUTH.md).

**admin-api owns the OIDC flow on behalf of admin-ui (BFF pattern, ADR-0019).** admin-ui redirects to admin-api for OIDC; admin-api holds the `client_secret`; admin-ui never does.

**Grafana uses its native OIDC support.** No proxy or custom adapter needed; role mapping via JMESPath on `realm_access.roles`.

**Jaeger sits behind an `oauth2-proxy` sidecar** (`jaeger-auth` service). Jaeger itself has no OIDC awareness; the proxy enforces authentication before forwarding.

**Internal auth (`operators.internal_password_hash`) is OFF by default.** The `internal_password_hash IS NULL` gate means break-glass login returns 404 unless the CLI has set a hash. Break-glass is explicit, audited, and operator-initiated (D2-b). It is NOT controlled by an env-var feature flag — the hash presence IS the feature flag.

**The OIDC implementation is pluggable in code** (env-driven generic names: `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, etc.) but **Keycloak is the only supported deployment** (D5).

**Service-token auth and agent API keys are OUT OF SCOPE.** They remain separate from operator auth and do not flow through Keycloak.

---

## Consequences

### Behavioral changes
- Operators no longer manage admin passwords via direct DB writes or the old Argon2id path; they use the Keycloak Account Console (`http://localhost:8443/realms/mintkey/account/`).
- `operators.internal_password_hash` is NULL by default. A NULL hash means `POST /v1/auth/internal-login` returns 404 — this is the expected, secure posture.
- admin-api carries the OIDC `client_secret`; admin-ui never does. This is not optional — it is the BFF pattern.
- Adding a new operator-facing UI = add a Keycloak client, wire native OIDC or an oauth2-proxy sidecar, and document the redirect URI.

### Constraints introduced
- Operators must run Keycloak (already in compose). If Keycloak is down, operators cannot log in unless they have previously issued a break-glass password.
- Cross-machine deployments require setting 6 public URL env vars (documented in [`docs/NETWORK.md`](../../NETWORK.md)).

---

## Trade-offs surfaced

| Risk | Severity | Mitigation |
|---|---|---|
| Keycloak single point of failure for operator login | Medium | CLI break-glass per D2-b; break-glass is deliberate, not a default fallback |
| In-process `state_store` in admin-api `oidc.py` | Low (pre-alpha) | Single-replica only; flagged as follow-up before any horizontal scaling of admin-api |
| 6 env vars required for cross-machine SSO | Low | Documented in `docs/NETWORK.md`; defaults work for localhost |
| Keycloak memory footprint (~512 MB, ~30s start) | Low (pre-alpha) | Accepted for laptop self-hosters; same tradeoff as ADR-0005 |

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Per-request `/userinfo` instead of shadow operators table | Latency on every request; FK churn when Keycloak users exist without a local operator row (D1) |
| env-var feature flag for internal-login enable/disable | The `internal_password_hash IS NULL` gate is intrinsically tied to whether internal-login can succeed; a separate flag would be redundant and create divergence (D2-b) |
| oauth2-proxy in front of Prometheus | Rejected for pre-alpha; Grafana is the only operator path to metrics; Prometheus stays internal (D3) |
| Generic OIDC vendor-agnostic UI text ("Sign in with SSO") | User explicitly chose Keycloak; naming Keycloak in the UI reduces operator confusion |
| Admin-ui holds its own OIDC client_secret | Security regression — admin-ui runs in the browser context (Node/Express); admin-api is the trusted server-side component (BFF pattern, ADR-0019) |

---

## Amends

### ADR-0005 §"Internal auth fallback"
ADR-0005 described internal auth as "used for the bootstrap admin and as a break-glass when OIDC is unreachable. Toggleable per deployment." **This is superseded:** internal auth is OFF by default (hash IS NULL gate) and is not toggleable via env var. It is enabled only by the `reset-password` CLI command as a deliberate, audited break-glass action.

### ADR-0014 §14.2 (Keycloak default)
ADR-0014 §14.2 amended ADR-0003 (Vault Adapter boot secret). The section is unrelated to the Keycloak default decision. The relevant change from this ADR is to ADR-0005's Keycloak framing: **Keycloak is now the ONLY operator IdP, not just the default.** The code is pluggable (env-driven) but Keycloak is the supported deployment.

### ADR-0019 §3 (whoami)
ADR-0019 stated "`GET /v1/auth/whoami` is implemented ... it is no longer a stub." **This ADR confirms it is wired and authoritative.** admin-ui middleware calls whoami on every request (15s LRU cache in admin-api). The session cookie is the identity carrier; Keycloak is the upstream IdP that established that session.

---

## Open follow-ups

- Distribute `state_store` to Redis or Postgres before any admin-api horizontal scaling.
- Consider Keycloak HA (active-passive replica) before any claim of high-availability deployment.
- Prometheus OIDC protection deferred to Phase 2 (D3).

## Related

- [`docs/AUTH.md`](../../AUTH.md) — operator-facing reference for SSO setup, break-glass, troubleshooting.
- [`docs/NETWORK.md` — Keycloak / SSO public URLs](../../NETWORK.md#keycloak--sso-public-urls) — env vars for cross-machine deployments.
- [ADR-0005](0005-admin-tech-stack.md) — admin tech stack; auth section amended here.
- [ADR-0014](0014-iter-1-2-corrections.md) — iteration 1+2 corrections; Keycloak framing amended here.
- [ADR-0019](0019-admin-ui-bff-and-write-auth.md) — AdminJS BFF pattern; whoami confirmed authoritative here.
