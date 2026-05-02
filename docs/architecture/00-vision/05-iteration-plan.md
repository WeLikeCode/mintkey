# Iteration plan (architecture phase)

We work in numbered architectural iterations. Each iteration is a *commit‑able* deliverable that an outsider could pick up and continue from.

## Why iterate?
The system has high coupling between security model, runtime topology, and protocol surface. Trying to design all of it at once produces internally inconsistent docs. Iterating lets us lock the upstream layer before refining the downstream one, and lets you push back at the cheapest possible point.

## The iterations

### Iteration 1 — High‑level architectural vision *(this commit)*
- Vision, problem, personas, glossary.
- C4 system context (L1) + container view (L2).
- Quality attribute scenarios (SEI ADD format).
- Threat model (STRIDE‑light).
- *Views and Beyond* mapping.
- ADR practice established (ADR‑0001).
- Skeleton stubs for tech stack, flows, observability, deployment.
- Open proposals for the most consequential undecided choices.

**Exit criteria**: every container in the container view has a clear responsibility statement, every quality attribute has at least one measurable scenario, and the top‑3 architectural risks are named and have an open proposal.

### Iteration 2 — Tech stack
- Per‑container language and runtime choice (ADR per container).
- Storage choices (Postgres vs. SQLite vs. ...).
- Vault backing choice (HashiCorp Vault vs. envelope‑on‑Postgres + KMS).
- Web UI framework.
- MCP server library.
- Proxy framework (custom Go vs. Envoy filter vs. Caddy plugin vs. ...).
- OTel collector wiring.
- Testing libraries per language.

**Exit criteria**: a `docker-compose.yml` could be written from the docs alone.

### Iteration 3 — Flows *(in progress: builder happy path drafted)*
- **Drafted**: [E2E‑01 Builder happy path](../03-flows/E2E-01-builder-happy-path.md) plus the six component flows it composes ([F‑OP‑01](../03-flows/F-OP-01-bootstrap-and-login.md) through [F‑AG‑02](../03-flows/F-AG-02-brokered-call-happy-path.md)).
- **Backlog (same template)**: F‑OP‑05 rotate credential, F‑OP‑06 revoke agent, F‑OP‑07 investigate audit, F‑AG‑03 brokered call (denied), F‑AG‑04 token expired mid‑call, F‑AG‑05 fetch OpenAPI, F‑SY‑01 KEK rotation, F‑SY‑02 audit hash‑chain verification, F‑SY‑03 OTel context propagation. Drafted as Phase 1 implementation reaches them.

Each flow has a sequence diagram + pre/post‑conditions + quality‑attribute checklist + test plan (unit + integration + live‑smoke) + Kiro spec inputs.

**Exit criteria**: every flow ends in a state transition that can be asserted in a test, and Kiro can generate a spec triple from the flow's "Kiro spec inputs" section.

### Iteration 4 — Contracts
- `contracts/rest/` — admin REST OpenAPI 3.1.
- `contracts/mcp/` — MCP tool definitions (typed schemas per tool).
- `contracts/events/` — audit and OTel event schemas.

**Exit criteria**: a Kiro spec can be derived mechanically from each contract.

### Iteration 5 — Spec‑driven implementation
- Move to Kiro for specs.
- TDD per spec, with tests pinned to contracts.
- Docker Compose MVP runnable.

## Iteration 2 (closing) — remaining open questions
The big iteration‑2 decisions are all settled. Remaining work is small:
- ~~Shared Go stack~~ — Done. [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md).
- ~~Python stack pin~~ — Done. [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md).
- ~~AdminJS pin~~ — Done. [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md).
- Audit Service placement (in‑process with Admin API for v1, separate later) — implicit in ADR‑0005; can land as a small ADR if a real ambiguity surfaces during implementation.
- Observability detail (after iteration 4 starts) — span naming, attribute allowlist, sampling. Driven by the contract surface.

### Iteration 2 exit
Per the [tech‑stack dashboard](../02-tech-stack/README.md): every cell in the "decided" matrix has a pinned library; the "open" matrix has only the observability detail (which depends on iteration 4) and the audit service placement (which is implicit). A reviewer can write a credible `docker-compose.yml` from the docs alone. Iteration 2 closes when iteration 4 contracts are drafted and the observability detail ADR lands.

## Accepted decisions (iteration 1)
- [`P-001`](../proposal/P-001-product-name-candidates.md) → [ADR‑0002](../01-architecture/adr/0002-product-name-mintkey.md): Product name is **Mintkey**.
- [`P-002`](../proposal/P-002-credential-storage-strategy.md) → [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md): Pluggable Vault Adapter; v1 backend is encrypted file on externally mounted volume; v2 HashiCorp Vault; v3 SQL+KMS.
- [`P-003`](../proposal/P-003-token-format-and-binding.md) → [ADR‑0006](../01-architecture/adr/0006-token-format-and-binding.md): JWS Ed25519 JWT + fast revocation channel; default 10‑min TTL; JWKS distribution; `cnf.jkt` opt‑in.
- [`P-004`](../proposal/P-004-proxy-deployment-topology.md) → [ADR‑0007](../01-architecture/adr/0007-proxy-deployment-topology.md): Explicit forward proxy with per‑service virtual‑host alias; egress allowlisted to registered base URL; transparent intercept deferred.
- [`P-005`](../proposal/P-005-egress-proxy-implementation.md) → [ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md): Egress Proxy is Kong Gateway (DB‑less) + Go plugin via go‑pdk.
- [`P-006`](../proposal/P-006-admin-tech-stack-and-auth.md) → [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md): Admin API Python + FastAPI; Admin UI AdminJS; Liquibase migrations; Postgres 16 default; OIDC + Keycloak default.
- [`P-007`](../proposal/P-007-multi-tenancy.md) → [ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md): multi‑tenant by architecture, single‑tenant by default UX; row‑level + RLS default; DB‑per‑tenant opt‑in.
- [`P-008`](../proposal/P-008-mcp-server-stack.md) → [ADR‑0009](../01-architecture/adr/0009-mcp-server-stack-python.md): MCP Server is Python + Anthropic `mcp` SDK; shared `mintkey-models` package.
- [`P-009`](../proposal/P-009-change-channel-transport.md) → [ADR‑0010](../01-architecture/adr/0010-change-channel-postgres-listen-notify.md): change channel on Postgres `LISTEN/NOTIFY`; tenant‑scoped channel names; reconciliation endpoint.
- [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md): shared Go stack (Go 1.22, `pgx/v5`, `chi/v5`, `go-jose/v4`, `sqlc`, `slog`, OTel, pure‑Go SQLite, distroless).
- [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md): Python stack pin (Python 3.12, FastAPI, SQLAlchemy 2.x async, `authlib`, Argon2id, `structlog`, `ruff` + `mypy --strict`, `uv`, shared `mintkey-models` package).
- [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md): AdminJS pin set (Node 20, AdminJS 7.x with `@adminjs/express` + `@adminjs/sql`, `passport-openidconnect`, `connect-pg-simple`, `pino`, `vitest`, `pnpm`).
- [ADR‑0014](../01-architecture/adr/0014-iter-1-2-corrections.md): adversarial‑review corrections to iterations 1 + 2 (global change channels with app‑layer tenant filter; service identity boot secret; OpenAPI canonical YAML; no plaintext cache in proxy plugin; all AdminJS writes via FastAPI; signed AdminJS↔FastAPI requests; mandatory audit hash chain; RLS arch test; agent SDK refresh‑before‑call).
- [ADR‑0015](../01-architecture/adr/0015-liquibase-schema-source-of-truth.md): Liquibase is the source of truth for the schema; SQLAlchemy mirrors it.
- [ADR‑0016](../01-architecture/adr/0016-round-2-corrections.md): round‑2 corrections — `jti` denylist in Postgres, JWKS force‑refresh on unknown `kid`, PlatformAdmin RLS escape in AdminJS, closed `Permission.constraints` schema, `mtls` auth scheme, admin‑settings endpoint, MCP behavior on tenant/agent deletion. Deferred items tracked in [open‑questions.md](../01-architecture/open-questions.md).
- [ADR‑0017](../01-architecture/adr/0017-round-3-corrections.md): round‑3 corrections — 12 new wire surfaces (AdminUiSignedRequest / ServiceIdentity / CsrfHeader security schemes; `platform_admin.access` audit event; `BrokeredTokenClaims` schema; ULID‑with‑prefix canonical; etc.) + 19 mechanical contract corrections from the multi‑perspective review.
