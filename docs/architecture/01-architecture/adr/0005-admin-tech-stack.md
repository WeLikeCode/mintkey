# ADR‑0005: Admin REST API (Python + FastAPI), Admin UI (AdminJS), Postgres + Liquibase, and Operator auth via OIDC with Keycloak default

## Status
Accepted — 2026-05-10. Promoted from [`docs/proposal/P-006-admin-tech-stack-and-auth.md`](../../proposal/P-006-admin-tech-stack-and-auth.md). The recommended option in P‑006 was 6A‑1 (Go); the accepted decision is 6A‑2 (Python + FastAPI) plus a tighter set of dependent choices.

> **AMENDED by ADR-0020 (2026-05-15):** Internal auth fallback is now OFF by default. Operator identity flows through Keycloak. The `operators.internal_password_hash IS NULL` gate replaces the "toggleable per deployment" model; break-glass is CLI-issued only. See [ADR-0020](0020-sso-keycloak-canonical-idp.md).

## Context
[P‑006](../../proposal/P-006-admin-tech-stack-and-auth.md) presented three coupled sub‑decisions for the control‑plane operator surface (Admin REST API, Admin Web UI, operator authentication). Each had multiple options. The accepted option set differs from the proposal's primary recommendation in two ways:
- **6A** picks Python + FastAPI (option 6A‑2) over Go (the cohesion‑driven recommendation), prioritizing OpenAPI‑first developer experience over single‑language uniformity.
- **6B** picks AdminJS (a COTS Node.js admin framework) over the HTMX path, prioritizing zero‑custom‑UI‑code over single‑binary simplicity.

These choices increase polyglot in the control plane (Python + Node + Go) but minimize *custom code we own*, which aligns with the operator preference established in [ADR‑0004](0004-egress-proxy-kong.md).

## Decision

### Admin REST API (C2 in [container view](../02-container-view.md))
- **Language / runtime**: **Python 3.12+**.
- **Web framework**: **FastAPI**.
- **OpenAPI**: FastAPI generates the OpenAPI document from the typed handlers; iteration 4's [`docs/contracts/rest/`](../../contracts/rest/) is published *from* the running app (or hand‑written and round‑tripped — to be settled in iteration 2).
- **Validation / models**: **Pydantic v2**.
- **DB driver**: `asyncpg` for runtime queries; `psycopg[binary]` for tooling.
- **DB schema migrations**: **Liquibase** with YAML changelogs. Liquibase runs as a one‑shot job in compose (and as a Helm pre‑install hook in production). Changelogs live under `admin-api/db/changelog/`. Version‑controlled, reviewable, language‑agnostic.
- **Default DB engine**: **PostgreSQL 16** (explicit). No database abstraction layer aimed at supporting other engines in v1.
- **OTel**: `opentelemetry-instrumentation-fastapi` + `opentelemetry-instrumentation-asyncpg`.
- **Testing**: `pytest` + `pytest-asyncio` + `httpx` for handler tests + `testcontainers` for integration tests against a real Postgres.

### Admin Web UI (C1)
- **Framework**: **AdminJS** (Node.js, COTS) — per operator preference for off‑the‑shelf UI.
- **Adapter**: `@adminjs/sql` reading directly from the same Postgres for **list / show / simple edit** views.
- **Sensitive operations** (credential rotation, agent revoke, anything with audit‑critical side effects) are configured as **AdminJS Custom Actions** that dispatch to the FastAPI Admin REST API via service‑to‑service auth, so the audit chokepoint and validation logic stay in one place.
- **Auth integration**: AdminJS uses `@adminjs/express` + `passport-openidconnect` to authenticate operators against Keycloak. After OIDC login, AdminJS calls FastAPI's `GET /v1/auth/whoami` to fetch the operator's role and uses it for resource visibility.
- **Custom React components**: only when AdminJS's defaults are insufficient (e.g., a credential‑rotation form with confirmation). Minimized.
- **Deployment**: separate container (`mintkey/admin-ui`, Node 20+).
- **Trade‑off acknowledged**: AdminJS is React under the hood and adds Node to the control plane. The user has explicitly chosen this for the COTS benefit; we accept the polyglot cost.

### Operator authentication (6C‑4 — generic OIDC + internal fallback, **Keycloak default out‑of‑the‑box**)
- **Default IdP**: **Keycloak**, **enabled by default** in compose. Realm and client are pre‑seeded by the seed job. Operator can swap to any other OIDC IdP by env var.
- **Generic OIDC**: any OIDC‑compliant provider works (Auth0, Okta, Azure AD, AWS Cognito, …).
- **Internal auth fallback**: username + Argon2id password, used for the bootstrap admin and as a break‑glass when OIDC is unreachable. Toggleable per deployment.

> **[Amended by ADR-0020]** Internal auth is OFF by default; Keycloak OIDC is the only operator IdP. Break-glass via CLI. See [docs/AUTH.md](../../../AUTH.md).

- **Authorization model**: roles live in our Identity service (`Admin`, `Auditor`, `AgentOwner`); Keycloak (or any IdP) only answers "who is this". Roles are decoupled from the IdP.
- **Sessions**: HttpOnly Secure SameSite=Strict cookie; server‑side sessions in Postgres; OIDC refresh tokens stored encrypted via the Vault Adapter ([ADR‑0003](0003-credential-storage-strategy.md)).
- **Bootstrap**: the seed job creates the initial Admin operator AND seeds the Keycloak `mintkey` realm with a `mintkey-admin` confidential client. The default password and Keycloak admin password are written to `./data/bootstrap-secrets` (mode 0600) and printed to compose logs.

### Cross‑cutting
- **No separate Auth container** for v1 — auth lives inside the Admin REST API as a router + middleware.
- **No BFF in the FastAPI for the UI** — AdminJS *is* the UI; it has its own backend (Express) that proxies sensitive ops to FastAPI.
- **The Admin REST API and AdminJS share the same Postgres** for v1; in a future iteration, AdminJS could be reconfigured to call FastAPI exclusively if shared‑DB coupling becomes a problem.

## Why these choices

### Why Python + FastAPI over Go
- FastAPI's OpenAPI‑first DX is a meaningful productivity advantage for a CRUD‑heavy admin surface, and iteration 4 produces a substantial OpenAPI surface.
- Pydantic v2 gives us zero‑boilerplate validation that doubles as the OpenAPI schema.
- Polyglot is acceptable: the security‑critical components (Vault Adapter, Credential Broker, Egress Proxy plugin) remain Go; the UI is Node (AdminJS); the Admin API and likely the MCP Server are Python.
- We pay the polyglot cost; we gain DX velocity for the surface that grows fastest in iteration 4 and 5.

### Why AdminJS over HTMX or a SPA we'd build
- "Off‑the‑shelf with config" is the explicit operator preference (also cited in [ADR‑0004](0004-egress-proxy-kong.md)).
- AdminJS is COTS for admin panels; it auto‑generates list/show/edit views from a resource declaration.
- Custom UI code is bounded to a small set of resource definitions, hooks for sensitive ops, and the OIDC integration.
- Trade: AdminJS bypasses our FastAPI for non‑sensitive CRUD; we mitigate by constraining what it touches and routing sensitive ops back through FastAPI.

### Why Keycloak default (not optional)
- Keycloak is the canonical OSS OIDC IdP; including it by default removes the most common deployment‑day question ("how do I log in?").
- Self‑hosters get a one‑command bootstrap with realistic auth from minute one.
- Operators who want to swap to Auth0/Okta/Azure AD set two env vars and disable the bundled Keycloak service.

### Why Liquibase for migrations
- Language‑agnostic (XML/YAML/JSON changelogs), so the schema is not entangled with the Python runtime.
- Mature in enterprise Java contexts but used widely in polyglot stacks; clean changeset semantics.
- Predictable rollbacks; supports preconditions; can be run as a job before the API container starts.

### Why PostgreSQL explicitly
- We were already implying it. Making it explicit lets us use Postgres‑specific features without hedging: `LISTEN/NOTIFY` for the change channel option, `JSONB` for audit‑event payloads, partial indexes, etc.
- Single‑engine simplifies operations and reduces test matrix.

## Consequences

### Positive
- Iteration 4 contracts (OpenAPI, MCP, events) round‑trip cleanly from FastAPI's typed handlers and Pydantic models.
- Admin UI is mostly off‑the‑shelf; custom UI code is minimized.
- Keycloak is in by default — fewer configuration questions on day one.
- Liquibase changelogs are reviewable, language‑agnostic, and operable independently of the API.
- Each strong constraint (Postgres‑specific features, Liquibase, Keycloak default) is captured here and consumable by Kiro in iteration 5.

### Costs
- **Three languages in the control plane**: Python (Admin API, MCP Server), Node.js (AdminJS), Go (Vault Adapter, Broker, proxy plugin, Kong‑syncer). Polyglot cost on operations and shared libraries.
- **AdminJS direct‑Postgres access** couples the UI to our schema; schema migrations must consider AdminJS resource definitions.
- **Two front doors for writes**: AdminJS for non‑sensitive CRUD, FastAPI for sensitive ops. Discipline required to keep audit coverage complete (mitigated by DB triggers for non‑FastAPI writes — covered in iteration 2).
- **Keycloak as a default container** adds memory and start‑up time to the docker‑compose experience (~512 MB and ~30 s warm‑up). Acceptable but worth noting for laptop self‑hosters.

### Risks
- **AdminJS API churn**: AdminJS is actively developed; major version bumps have historically required resource‑definition rewrites. Mitigation: pin version per release; integration tests against the pinned version.
- **Schema drift between Liquibase and AdminJS** (resource definitions can lag): mitigated by code‑gen of AdminJS resource skeletons from the Liquibase schema in CI.
- **Audit coverage gap** if AdminJS writes bypass FastAPI: mitigated by DB triggers that emit audit events for any direct write, and by routing sensitive ops to FastAPI.

## Implications
- [`02-container-view.md`](../02-container-view.md): C1 (Admin Console) is now realized by an `admin-ui` container running AdminJS; C2 (Admin REST API) is FastAPI; the `audit` chokepoint is reinforced via DB triggers as a defense‑in‑depth measure.
- [`05-deployment/README.md`](../../05-deployment/README.md): Keycloak is a first‑class compose service; AdminJS gets its own container; a Liquibase one‑shot migration job runs before the Admin API starts.
- [`docs/contracts/rest/`](../../contracts/rest/): the OpenAPI document is **emitted by FastAPI** and the contract source of truth lives in the FastAPI code (decorators + Pydantic models). The `contracts/rest/openapi.yaml` file is generated and checked in.
- [`docs/00-vision/04-glossary.md`](../../00-vision/04-glossary.md): glossary unchanged but the "Admin REST API + BFF" entry can drop the BFF role since AdminJS owns the UI.

## Open follow‑ups (iteration 2)
- Pin Python, FastAPI, AdminJS, Liquibase, Keycloak, and Postgres versions.
- Decide: AdminJS direct‑DB writes for which entities, vs. FastAPI‑mediated for which.
- DB‑trigger audit policy: which tables get triggers; which fields are recorded.
- Service‑to‑service auth between AdminJS and FastAPI: shared secret, mTLS, or OIDC client credentials.
- Code‑gen pipeline: `oapi-typescript-codegen` for AdminJS to talk to FastAPI; AdminJS resources from Liquibase schema.
- Whether the MCP Server is Python (cohesion with Admin API) or Go (cohesion with Broker/Vault Adapter). Captured as a separate iteration‑2 ADR.
- Keycloak realm bootstrap: ship a default realm export in `seed/keycloak/realm-mintkey.json`.

## Related
- [P‑006 admin tech stack and auth](../../proposal/P-006-admin-tech-stack-and-auth.md) — Accepted (this ADR), with 6A‑2 + AdminJS + Keycloak default chosen.
- [ADR‑0003 credential storage strategy](0003-credential-storage-strategy.md) — Vault Adapter is used to store the OIDC client secret and the OIDC refresh tokens.
- [ADR‑0004 egress proxy Kong](0004-egress-proxy-kong.md) — same operator preference (off‑the‑shelf with config) drove this ADR.
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — sessions are (operator, tenant); `OperatorTenantMembership` table; tenant selector in AdminJS; Keycloak realm‑per‑tenant becomes an opt‑in; new `tenants` resource.
