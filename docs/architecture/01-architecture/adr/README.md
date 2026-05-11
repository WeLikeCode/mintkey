# Architecture Decision Records

We capture every significant decision as an ADR using the Michael Nygard format. ADRs are immutable: once Accepted, they stay; if a later decision changes course, write a new ADR that supersedes the old one and update the old one's status.

## Format
One markdown file per ADR, prefix‑numbered:

```
0001-record-architecture-decisions.md
0002-…
```

## Statuses
- **Proposed** — under discussion (often started life in `proposal/`).
- **Accepted** — decision is in force.
- **Superseded by ADR‑XXXX** — see the new one.
- **Deprecated** — context no longer applies.

## Workflow
1. A material question arises → write a proposal in `proposal/P-NNN-…md` with options + recommendation.
2. Reach agreement → promote the recommended option to an ADR here, status `Accepted`.
3. The proposal links to the ADR; the ADR links back to the proposal for the option set.

## Naming
- Proposals: `P-NNN-short-kebab-name.md` (NNN is sequential).
- ADRs: `NNNN-short-kebab-name.md` (NNNN is sequential, **separate** numbering).

## Index
- [`0001-record-architecture-decisions.md`](0001-record-architecture-decisions.md) — Accepted.
- [`0002-product-name-mintkey.md`](0002-product-name-mintkey.md) — Accepted. Adopts **Mintkey** as the product name. Promoted from [P‑001](../../proposal/P-001-product-name-candidates.md).
- [`0003-credential-storage-strategy.md`](0003-credential-storage-strategy.md) — Accepted. Pluggable Vault Adapter. v1 backend is encrypted file on externally mounted volume; v2 HashiCorp Vault; v3 SQL+KMS. Promoted from [P‑002](../../proposal/P-002-credential-storage-strategy.md).
- [`0004-egress-proxy-kong.md`](0004-egress-proxy-kong.md) — Accepted. Egress Proxy is **Kong Gateway (DB‑less) + Go plugin via go‑pdk**. Envoy + ext_authz preserved as documented upgrade path. Promoted from [P‑005](../../proposal/P-005-egress-proxy-implementation.md).
- [`0005-admin-tech-stack.md`](0005-admin-tech-stack.md) — Accepted. **Admin REST API: Python + FastAPI; Admin UI: AdminJS (COTS); migrations: Liquibase; default DB: PostgreSQL 16; auth: generic OIDC with Keycloak default.** Promoted from [P‑006](../../proposal/P-006-admin-tech-stack-and-auth.md).
- [`0006-token-format-and-binding.md`](0006-token-format-and-binding.md) — Accepted. **JWS Ed25519 JWT** (default 10‑min TTL, JWKS distribution, `cnf.jkt` opt‑in) **+ fast revocation channel** for `agent.revoked`/`token.revoked` with TTL‑based graceful degradation. Promoted from [P‑003](../../proposal/P-003-token-format-and-binding.md).
- [`0007-proxy-deployment-topology.md`](0007-proxy-deployment-topology.md) — Accepted. **Explicit forward proxy** (`/v1/call/<service_id>/<path>`) **with per‑service virtual‑host alias** (`<service-slug>.proxy.local/<path>`); egress allowlisted to the registered base URL of the bound service; transparent intercept deferred; v1 supports HTTP/1.1 + HTTP/2 only. Promoted from [P‑004](../../proposal/P-004-proxy-deployment-topology.md).
- [`0008-multi-tenancy-row-level-with-db-tier.md`](0008-multi-tenancy-row-level-with-db-tier.md) — Accepted. **Multi‑tenant by architecture, single‑tenant by default UX.** Row‑level isolation (`tenant_id` + Postgres RLS) by default; DB‑per‑tenant opt‑in for high‑isolation tier. JWT gains `tnt` claim; Vault Adapter, plugin, sessions, Keycloak all become tenant‑aware. Cross‑cutting amendments to ADRs 0003–0007. Promoted from [P‑007](../../proposal/P-007-multi-tenancy.md).
- [`0009-mcp-server-stack-python.md`](0009-mcp-server-stack-python.md) — Accepted. **MCP Server is Python 3.12+ with the Anthropic `mcp` SDK.** Cohesion with the Admin REST API; shared `mintkey-models` Pydantic package; HTTP/SSE default transport. TypeScript preserved as documented re‑platform path. Promoted from [P‑008](../../proposal/P-008-mcp-server-stack.md).
- [`0010-change-channel-postgres-listen-notify.md`](0010-change-channel-postgres-listen-notify.md) — Accepted. **Change channel runs on Postgres `LISTEN/NOTIFY`** — zero extra container, transactional with state changes, tenant‑scoped channel names. Redis dropped from Phase 1 compose. Behind a small abstraction so a future swap to Redis/NATS is a one‑file change. Promoted from [P‑009](../../proposal/P-009-change-channel-transport.md).
- [`0011-shared-go-stack.md`](0011-shared-go-stack.md) — Accepted. **Shared Go stack** for Broker, Vault Adapter, Kong‑syncer, and Egress Proxy plugin. Go 1.22, workspace, `pgx/v5`, `chi/v5`, `go-jose/v4`, `sqlc`, `slog`, OTel native, pure‑Go SQLite (`modernc.org/sqlite`), `golangci-lint`. Distroless container images.
- [`0012-python-stack-pin.md`](0012-python-stack-pin.md) — Accepted. **Python stack pin** (appendix to ADR‑0005 / ADR‑0009). Python 3.12, FastAPI, `asyncpg`, **SQLAlchemy 2.x async**, `authlib` for OIDC, Argon2id, `structlog`, `ruff` + `mypy --strict`, `uv` package manager, `pytest` + `testcontainers`. Shared `mintkey-models` package.
- [`0013-adminjs-pin.md`](0013-adminjs-pin.md) — Accepted. **AdminJS pin set** (appendix to ADR‑0005). Node 20 LTS, **AdminJS 7.x** with `@adminjs/express` + `@adminjs/sql`, `passport-openidconnect` for Keycloak, `connect-pg-simple` for Postgres‑backed sessions, `pino` logging, `vitest` testing, `pnpm`. Sensitive operations dispatch to FastAPI via Custom Actions.
- [`0014-iter-1-2-corrections.md`](0014-iter-1-2-corrections.md) — Accepted. **Iteration 1+2 corrections from adversarial review.** Global change channels with app‑layer tenant filter (amends ADR‑0010). Service identity boot secret for Vault Adapter callers (amends ADR‑0003). Checked‑in OpenAPI YAML is canonical (amends ADR‑0005). No plaintext cache in proxy plugin (amends ADR‑0004 / ADR‑0011). All AdminJS writes route via FastAPI (amends ADR‑0013). AdminJS↔FastAPI signed request, not shared static token (amends ADR‑0013). Audit hash chain mandatory. RLS architecture test. Agent SDK refresh‑before‑call pattern.
- [`0015-liquibase-schema-source-of-truth.md`](0015-liquibase-schema-source-of-truth.md) — Accepted. **Liquibase is the source of truth for the database schema.** SQLAlchemy `Mapped` types are a generated/hand‑mirrored view, verified by CI diff against the live introspected schema. Schema changes happen in Liquibase only.
- [`0016-round-2-corrections.md`](0016-round-2-corrections.md) — Accepted. **Round‑2 corrections from the second adversarial pass.** `jti` denylist in Postgres; JWKS force‑refresh on unknown `kid`; PlatformAdmin AdminJS visibility with RLS escape; closed `Permission.constraints` schema; `mtls` auth scheme; admin‑settings endpoint; MCP behavior on tenant/agent deletion. Remaining medium‑severity items tracked in [`open-questions.md`](../open-questions.md).
- [`0017-round-3-corrections.md`](0017-round-3-corrections.md) — Accepted. **Round‑3 corrections from multi‑perspective contract review.** 12 new wire‑level decisions (AdminUiSignedRequest / ServiceIdentity / CsrfHeader security schemes; `platform_admin.access` audit event for cross‑tenant reads; internal‑login timing equalization; span redaction extended to `*_token`/`*_secret` patterns; `/v1/changes?since=<unknown>` → 410; `BrokeredTokenClaims` schema; `t_default` canonical slug; REST↔MCP error‑code mapping; ULID‑with‑prefix canonical wire form; change‑event `actor_type`; `system_…` actor prefix). Plus 19 mechanical contract corrections in the appendix. OQ‑014..OQ‑022 added to open‑questions.
- [`0018-classical-service-api-keys.md`](0018-classical-service-api-keys.md) — Proposed. **Classical service API keys (`mk_svckey_…`) for non‑agent clients** — the non‑agent flavour of the credential‑indirection invariant (`Client → Mintkey‑issued key → Mintkey → real backend credential → Backend`). Operator‑issued, bound to an existing Agent + Service + a subset of its grants + optional expiry + optional `Constraints` (all four kinds enforced per request); Argon2id‑hashed at rest, fingerprint‑indexed; server‑resolved by the Broker (`POST /v1/api-keys/resolve`, `svcid_proxy`‑authed) with a short proxy resolution cache; instantly revocable. New `service_api_keys` table (Liquibase). Amends ADR‑0016.6 (`AdminSettings.api_key`) and ADR‑0017.10 (`mintkey:code` enum). Does **not** change brokered JWTs (ADR‑0006). Promoted from [P‑010](../../proposal/P-010-extended-token-class.md) (Option E). Awaiting acceptance.
