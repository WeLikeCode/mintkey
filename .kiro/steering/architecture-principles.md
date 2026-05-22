# Architecture Principles

The constitution for Mintkey. These principles are stable. Deviations require an ADR.

## P-1 — The agent never holds a usable credential

The real backend credential is decrypted only inside the Vault Adapter and consumed only inside the Egress Proxy's request mutation step. It is never serialized into a response visible to the agent, never present in any log, and never cached in plaintext beyond the request scope. This is the core security invariant of the system.

*Enforced by:* S-SEC-1 integration test; structured log field allowlist; CI red-team grep.

## P-2 — Audit is a chokepoint, not an afterthought

Every state-change handler — credential CRUD, token issuance, token use, permission grant/revoke, KEK rotation, login — emits an audit event via the single `audit.emit()` helper. There is no second path. The audit chokepoint is enforced by an architecture test in CI, not by discipline alone.

*Enforced by:* architecture test asserting no state-change bypasses the audit helper; append-only Postgres table with optional hash chain (ADR-0014).

## P-3 — Tenant isolation is structural, not optional

Every domain table carries `tenant_id UUID NOT NULL`. Every domain table has a Postgres RLS policy. The application sets `SET LOCAL app.current_tenant` at the start of every DB transaction. A token issued in tenant A cannot validate against a service in tenant B (`tnt` claim enforced by the Egress Proxy). Cross-tenant access is impossible by construction, not by convention.

*Enforced by:* RLS architecture test asserting 100% domain table coverage; integration test fuzzing cross-tenant IDs; JWT `tnt` claim validation in proxy (ADR-0008).

## P-4 — Contract-first, then code

Contracts (OpenAPI, MCP tool schemas, event schemas, Vault Adapter proto) are written before implementation. Server stubs and client SDKs are generated from contracts. CI verifies the running service emits OpenAPI matching the checked-in contract. No hand-maintained generated artefacts.

*Enforced by:* contract round-trip check in CI; `spec-first-check` skill gates implementation work.

## P-5 — Control plane and data plane are separated

The control plane (Admin API, MCP Server, Broker, Vault Adapter, Audit) and the data plane (Egress Proxy) have different SLOs, different scaling axes, and different deploy cadences. Control plane downtime must not break in-flight agent work (S-AVAIL-1). They are separate processes from day one.

*Enforced by:* separate containers; proxy validates JWT locally against cached JWKS without calling the control plane per request.

## P-6 — Smallest viable surface, off-the-shelf where possible

Prefer COTS over custom code for non-security-critical components (Kong for proxying, AdminJS for the admin UI, Keycloak for OIDC, Liquibase for migrations). Custom code is reserved for the security-critical path: the Vault Adapter, the Credential Broker, and the proxy plugin. Every custom component must justify its existence against an available alternative.

*Rationale:* ADR-0004 (Kong), ADR-0005 (AdminJS + Keycloak), ADR-0015 (Liquibase).

## P-7 — Observability is a first-class deliverable

Every container emits OTel traces, metrics, and structured JSON logs from day one. A single agent request must be traceable end-to-end from MCP discovery through token issuance through proxy-egressed backend call (S-OBS-1). Pre-baked Grafana dashboards ship with the repo.

*Enforced by:* S-OBS-1 scenario; OTel auto-instrumentation in every service; span attribute allowlist enforced in CI.

## P-8 — Schema is owned by Liquibase, mirrored by code

The Liquibase YAML changelogs in `apps/admin-api/db/changelog/` are the single source of truth for the database schema. SQLAlchemy `Mapped` types and Go `sqlc` queries mirror the schema; they do not define it. Breaking schema changes require a new changeset and a deprecation window.

*Enforced by:* ADR-0015; CI diff between Liquibase-applied schema and SQLAlchemy introspection.

## P-9 — Revocation is seconds, not deploys

An operator revocation must propagate to the MCP Server, Credential Broker, and Egress Proxy within ≤ 5 seconds (S-OPS-1). This is achieved via the Postgres `LISTEN/NOTIFY` change channel (ADR-0010) and a `jti` denylist in Postgres (ADR-0016). JWT expiry alone is not sufficient.

*Enforced by:* S-OPS-1 integration test; change-channel subscriber in every component that caches agent state.

## P-10 — Polyglot is a cost, not a feature

The repo uses three languages (Go, Python, Node) because each serves a distinct purpose: Go for security-critical, latency-sensitive components; Python for the CRUD-heavy admin surface with OpenAPI-first DX; Node for the COTS AdminJS UI. Adding a fourth language requires an ADR that justifies the cost against the benefit.

*Rationale:* ADR-0005, ADR-0011, ADR-0012, ADR-0013.
