# Proposals

A proposal captures **one open architectural question with two-or-more options, a recommendation, and a rationale**. Proposals are the upstream of ADRs.

## Lifecycle
1. Open question identified → new proposal `P-NNN-name.md`.
2. Discussion happens in‑place (edits + a "Discussion" section).
3. A recommendation is selected → promoted to an ADR in [`../01-architecture/adr/`](../01-architecture/adr/).
4. Proposal status updates to `Accepted (→ ADR-NNNN)` or `Rejected`.

## Format
Every proposal MUST have:
- **Status** — `Open` | `Accepted (→ ADR‑NNNN)` | `Rejected` | `Superseded`.
- **Question** — the decision to be made, in one sentence.
- **Context** — what makes this hard, what constraints apply, which quality attribute scenarios are touched.
- **Options** — at least two, each with description, pros, cons, cost.
- **Recommendation** — which option, and why.
- **Implications** — what changes downstream once decided.

## Currently open
*(none)*

## Accepted
- [`P-001-product-name-candidates.md`](P-001-product-name-candidates.md) → [ADR‑0002](../01-architecture/adr/0002-product-name-mintkey.md). Product name: **Mintkey**.
- [`P-002-credential-storage-strategy.md`](P-002-credential-storage-strategy.md) → [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md). Pluggable Vault Adapter. v1 backend is encrypted file on externally mounted volume; v2 HashiCorp Vault; v3 SQL+KMS.
- [`P-003-token-format-and-binding.md`](P-003-token-format-and-binding.md) → [ADR‑0006](../01-architecture/adr/0006-token-format-and-binding.md). JWS Ed25519 JWT + fast revocation channel; default 10‑min TTL; JWKS distribution; cnf.jkt opt‑in.
- [`P-004-proxy-deployment-topology.md`](P-004-proxy-deployment-topology.md) → [ADR‑0007](../01-architecture/adr/0007-proxy-deployment-topology.md). Explicit forward proxy with per‑service virtual‑host alias; transparent intercept deferred; egress allowlisted to registered base URL.
- [`P-005-egress-proxy-implementation.md`](P-005-egress-proxy-implementation.md) → [ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md). Egress Proxy is Kong Gateway DB‑less + Go plugin via go‑pdk; Envoy + ext_authz preserved as upgrade path.
- [`P-006-admin-tech-stack-and-auth.md`](P-006-admin-tech-stack-and-auth.md) → [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md). Admin API: Python + FastAPI; Admin UI: AdminJS; migrations: Liquibase; default DB: Postgres 16; auth: OIDC with Keycloak default.
- [`P-007-multi-tenancy.md`](P-007-multi-tenancy.md) → [ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md). Multi‑tenant by architecture, single‑tenant by default UX. Row‑level + RLS by default; DB‑per‑tenant opt‑in.
- [`P-008-mcp-server-stack.md`](P-008-mcp-server-stack.md) → [ADR‑0009](../01-architecture/adr/0009-mcp-server-stack-python.md). MCP Server is Python + Anthropic Python SDK; shared `mintkey-models` Pydantic package.
- [`P-009-change-channel-transport.md`](P-009-change-channel-transport.md) → [ADR‑0010](../01-architecture/adr/0010-change-channel-postgres-listen-notify.md). Change channel runs on Postgres `LISTEN/NOTIFY`; tenant‑scoped channels; reconciliation via `GET /v1/changes?since=<event_id>`.
