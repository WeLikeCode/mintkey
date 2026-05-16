# Security policy

Mintkey is a credential broker. Vulnerabilities in this project are credentials-impacting by definition — a flaw here can expose the API keys, OAuth tokens, or service credentials of every agent using the system. This document states what we commit to, what we do not commit to, and how to report a finding.

This project is pre-alpha and self-hosted. There is no managed offering and therefore no managed disclosure SLA. Coordination is best-effort.

---

## Supported versions

`main` is the only branch receiving fixes. The wire surface is declared `experimental` ([`docs/architecture/contracts/rest/openapi.yaml`](docs/architecture/contracts/rest/openapi.yaml) `x-mintkey-stability: experimental`, version `0.1.0-preview.1`). No other version is supported.

---

## Reporting a vulnerability

**Do not file security vulnerabilities as public GitHub Issues.**

Two channels:

1. **Email:** `the+security@ciprianiacobescu.com` with subject `[security] <short title>`.
2. **GitHub Security Advisory (GHSA):** open a private advisory via the "Security" tab of the repository.

Your report should include:

- **Reproduction steps** (numbered, copy-pasteable on a clean `docker compose up`).
- **Affected version:** output of `git rev-parse HEAD`.
- **Impact assessment:** what credential or access is exposed, and under what conditions.
- **Proposed remediation,** if known.

---

## What we will do

- **Acknowledgement:** within 7 days of receipt.
- **Triage:** within 30 days of receipt. We will assess severity against the threat model (see below), assign a fix priority, and communicate the timeline.
- **Public disclosure:** coordinated. We will not disclose until a fix is available or we have determined the issue is not exploitable. We will credit the reporter unless they request anonymity.

---

## What is in scope

Components from the C4 container view ([`docs/architecture/01-architecture/02-container-view.md`](docs/architecture/01-architecture/02-container-view.md)):

- Admin REST API (FastAPI)
- MCP Server (FastAPI)
- Credential Broker (Go)
- Vault Adapter (Go)
- Egress Proxy plugin (Kong + Go plugin)
- Kong-syncer (Go)
- Admin UI (AdminJS / Express)
- Liquibase schema and migrations
- Change-channel transport (Postgres LISTEN/NOTIFY)
- The audit hash-chain implementation

---

## What is out of scope

- **Third-party dependency vulnerabilities.** Report these upstream first (Go modules, Python packages, Node packages, Kong itself, Keycloak, PostgreSQL). We will update dependencies in response to upstream fixes, but the fix path is upstream.
- **The dev KEK hardcoded in `docker-compose.yml`.** This is a documented development fixture, not a production secret. See [`PORTS.md`](PORTS.md) for the annotation. In a production deployment, the KEK is loaded from a keyfile at startup; the `docker-compose.yml` value is for local development only.
- **Attacks that require an already-compromised operator session.** The threat model assumes the operator's authentication path (Keycloak OIDC) is intact. See [`docs/architecture/01-architecture/05-threat-model.md`](docs/architecture/01-architecture/05-threat-model.md).
- **Social engineering attacks against maintainers or operators.** Out of scope for a software security policy.
- **Vulnerabilities in the demo-backend or seed-job containers.** These are development fixtures.

---

## Threat model

[`docs/architecture/01-architecture/05-threat-model.md`](docs/architecture/01-architecture/05-threat-model.md) is the source of truth.

Canonical adversary types:

- **Hostile agent (prompt-injected):** an agent whose prompt has been manipulated. Mintkey contains its blast radius — a prompt-injected agent cannot exfiltrate the raw credential, cannot access services outside its grants, and cannot exceed the JWT TTL.
- **Curious operator:** an operator who attempts to access another tenant's data. Mitigated by Postgres RLS and the `PlatformAdmin` flag ([ADR-0008](docs/architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md), [ADR-0014.8](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)).
- **Network attacker:** an external party intercepting traffic. Mitigated by TLS on external surfaces; internal services communicate over the compose network.
- **Malicious backend:** a backend service that attempts to extract information from the proxy's request. Mitigated by credential injection happening at the proxy without exposing the credential to the agent; the backend sees only what the real credential gives it.

---

## Hardening claims we make

Each claim is linked to its source of truth and the verification command that proves it.

- **Plaintext credentials never appear in any log, audit payload, OTel span attribute, or response visible to the agent.** Sources: [`S-SEC-1`](docs/architecture/01-architecture/03-quality-attributes.md), [`ADR-0014.4`](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md), [`ADR-0017.6`](docs/architecture/01-architecture/adr/0017-round-3-corrections.md). Verification: `docker compose logs | grep -E "$(cat ./scripts/red-team-fingerprints.txt)"` must return empty.
- **Tokens are JWS Ed25519 with short TTL.** Default TTL: 10 minutes (configurable per service). Sources: [`ADR-0006`](docs/architecture/01-architecture/adr/0006-token-format-and-binding.md), [`ADR-0008`](docs/architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md).
- **Audit log is hash-chained per tenant.** Every row carries `prev_hash` + `hash`; genesis is `sha256("mintkey-audit-genesis-v1:" || tenant_id)`. Source: [`ADR-0014.7`](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md). Verification: `POST /v1/admin/audit/verify-chain`.
- **All wire IDs are ULIDs with stable prefixes.** Pattern `^<prefix>_[0-9A-HJKMNP-TV-Z]{26}$`. Source: [`ADR-0017.11`](docs/architecture/01-architecture/adr/0017-round-3-corrections.md).
- **Schema source of truth is Liquibase; SQLAlchemy is mirrored.** Source: [`ADR-0015`](docs/architecture/01-architecture/adr/0015-liquibase-schema-source-of-truth.md). Verification: `sqlacodegen` diff against `mintkey_models/db.py` is empty.
- **PostgreSQL RLS on every tenant-scoped table.** Sources: [`ADR-0008`](docs/architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md), [`ADR-0014.8`](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md). Verification: `pytest tests/architecture/test_rls_coverage.py`.
- **The Agent API Key is returned plaintext exactly once** at agent creation. The `agent.created` audit event carries the fingerprint, not the key. Source: [`CLAUDE.md`](CLAUDE.md) "Audit and security".

---

## Hardening claims we do not make

- We have not been formally audited by a third-party security firm.
- We have not run a fuzzing campaign against any service.
- We have no bug bounty program.
- This is pre-alpha software. The wire surface may change in breaking ways.
- There is no multi-region deployment; single-region self-host only.
- We do not prevent prompt injection inside the agent — we contain its impact on credentials.
- Defense-in-depth has known gaps tracked in [`docs/architecture/01-architecture/open-questions.md`](docs/architecture/01-architecture/open-questions.md) (22 open items as of this writing).
- The `docker-compose.yml` dev KEK is not a secret. It is a fixture. Do not use it in a production deployment.

---

## Operational bugs

Operational bugs that are not security vulnerabilities go to [`docs/REPORTING.md`](docs/REPORTING.md), not here.
