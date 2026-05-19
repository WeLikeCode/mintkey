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
- **The dev KEKs (vault, bootstrap) hardcoded in `docker-compose.yml`.** These are documented development fixtures, not production secrets. See [`PORTS.md`](PORTS.md) for annotations. In a production deployment, each KEK is loaded from a secrets manager or keyfile; the `docker-compose.yml` values are for local development only. `MINTKEY_VAULT_KEK` protects vault credentials; `MINTKEY_BOOTSTRAP_KEK` protects the bootstrap admin password written by the seed-job.
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
- The `docker-compose.yml` dev KEKs (`MINTKEY_VAULT_KEK`, `MINTKEY_BOOTSTRAP_KEK`) are not secrets. They are development fixtures. Do not use them in a production deployment. Rotate both in any non-local environment.

## Bootstrap KEK (`MINTKEY_BOOTSTRAP_KEK`)

The seed-job encrypts the bootstrap admin password with a Fernet key (`MINTKEY_BOOTSTRAP_KEK`) before writing it to the `bootstrap-secrets` volume (S6 CodeQL cleartext-storage fix). All services that read `admin_password` from the volume must have `MINTKEY_BOOTSTRAP_KEK` set to the same key. This includes `admin-ui` and any CI pipeline that reads the file. Generate a fresh key with:

```sh
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store it in your secrets manager and inject it as `MINTKEY_BOOTSTRAP_KEK` into both the seed-job and all reader services. The dev default in `docker-compose.yml` must not be used in production.

---

## Operational bugs

Operational bugs that are not security vulnerabilities go to [`docs/REPORTING.md`](docs/REPORTING.md), not here.

---

## Accepted Scorecard Residuals (v0.1.0-prealpha)

The following OpenSSF Scorecard checks are intentionally not addressed in this release. Each has a documented rationale and a clear "revisit at" criterion. These were reviewed and accepted by the project owner on 2026-05-18 (session S11, branch `fix/s11-scorecard-residuals-2026-05-18`).

Operators and contributors should be aware of these gaps. None of them affect the runtime security of a correctly deployed Mintkey instance — they are project-hygiene and process checks, not vulnerability findings (with the exception of VulnerabilitiesID, documented separately below).

### Code-Review (HIGH)

- **Score**: 0 (Found 0/9 approved changesets)
- **Why accepted**: This is a solo-author pre-v1 project. Requiring >=1 approved reviewer per PR plus a no-admin-bypass branch protection rule would block iteration with no second human available to do reviews. Admin-merge stays allowed for now.
- **Revisit when**: Project gains a second active contributor, or before v1.0 stable -- whichever comes first.

**GitHub UI Dismissal Steps**:
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `CodeReviewID`
3. Click the alert -> "Dismiss alert" -> reason: "Won't fix"
4. Paste this comment text:
   > Accepted residual per SECURITY.md - solo-author pre-v1 project; no second reviewer available; admin-merge required until a second active contributor joins.
5. Click "Dismiss alert"

### Maintained (HIGH -- auto-resolving)

- **Score**: 0 (project < 90 days old)
- **Why accepted**: The repository was created on 2026-05-02 (first commit `b216c76`). Scorecard requires >= 90 days of activity. This check auto-resolves at day 90 with no action required.
- **Revisit when**: 2026-07-31. No action needed; the alert will close naturally once the repo is 90 days old.

**GitHub UI Dismissal Steps**:
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `MaintainedID`
3. Click the alert -> "Dismiss alert" -> reason: "Won't fix"
4. Paste this comment text:
   > Accepted residual per SECURITY.md - repo created 2026-05-02; alert auto-resolves at 90 days (2026-07-31) with no action required.
5. Click "Dismiss alert"

### Fuzzing (MEDIUM)

- **Score**: 0 (no fuzzer integration detected)
- **Why accepted**: Fuzzing is a post-v1 hardening goal. Current test investment is in unit, integration, and architecture tests. Fuzzing adds value but is not blocking for a pre-alpha credential broker.
- **Revisit when**: Post-v1.0 stable. Candidates for fuzzing: Go `egress-proxy` URL/header parsing and Python credential-broker input parsing. Consider `go test -fuzz` for Go and `hypothesis` for Python.

**GitHub UI Dismissal Steps**:
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `FuzzingID`
3. Click the alert -> "Dismiss alert" -> reason: "Won't fix"
4. Paste this comment text:
   > Accepted residual per SECURITY.md - fuzzing is a post-v1.0 hardening goal; not blocking for pre-alpha.
5. Click "Dismiss alert"

### CII-Best-Practices (LOW)

- **Score**: 0 (no OpenSSF Best Practices badge)
- **Why accepted**: Pursuing a CII Best Practices badge requires governance docs, threat model, security testing evidence, and stable contribution processes -- most of which exist but need formal attestation. The badge process is appropriate once the project is stable at v1.0.
- **Revisit when**: Pre-v1.0 stable release. The groundwork (SECURITY.md, threat model, CODE_OF_CONDUCT.md, CONTRIBUTING.md, CodeQL, Dependabot) is substantially in place.

**GitHub UI Dismissal Steps**:
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `CIIBestPracticesID`
3. Click the alert -> "Dismiss alert" -> reason: "Won't fix"
4. Paste this comment text:
   > Accepted residual per SECURITY.md - badge process is pre-v1.0 goal; governance docs, threat model, and CodeQL are substantially in place pending formal attestation.
5. Click "Dismiss alert"

### Vulnerabilities -- GO-2026-4918 (HIGH)

- **Score**: 0 (Scorecard flagged Go advisory GO-2026-4918 / CVE-2026-33814)
- **Advisory**: [GO-2026-4918](https://pkg.go.dev/vuln/GO-2026-4918) -- Infinite loop in HTTP/2 transport when processing a `SETTINGS_MAX_FRAME_SIZE` of 0, causing the transport to enter an infinite loop of writing CONTINUATION frames.
- **Affected module**: `golang.org/x/net` -- fixed in `v0.53.0`. Current `go.mod` pins `golang.org/x/net v0.52.0`.
- **Patch status**: **PATCHED upstream** -- `golang.org/x/net v0.53.0` is available and resolves this advisory.
- **Status**: **Dep-bump required.** This is NOT an accepted residual. A follow-up session must bump `golang.org/x/net` from `v0.52.0` to `v0.53.0` (or latest patched) in `go.mod` + `go.sum`.
- **Follow-up task**: Run `go get golang.org/x/net@v0.53.0 && go mod tidy` in the repo root; verify `go.sum` is updated; run `make test` to confirm no regressions. File as a dedicated remediation session or merge alongside the next dependency update batch.
- **Revisit when**: The dep-bump session lands on `main`; confirm the `VulnerabilitiesID` Scorecard alert closes after the next scan.

**GitHub UI Dismissal Steps** (hold off on dismissing until the dep-bump is merged; once merged, dismiss the now-resolved alert):
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `VulnerabilitiesID`
3. After dep-bump merges: click the alert -> "Dismiss alert" -> reason: "Fixed"
4. Paste this comment text:
   > Resolved: bumped golang.org/x/net to v0.53.0 per SECURITY.md - GO-2026-4918 (CVE-2026-33814) patched upstream.
5. Click "Dismiss alert"

### Pinned-Dependencies -- `pip install --no-deps .` (MEDIUM)

- **Score**: 9 (Scorecard: "pipCommand not pinned by hash")
- **Context**: `mock-backend/Dockerfile:16` runs `pip install --no-deps .` for the local-path mock-backend package itself. The PREVIOUS line (`mock-backend/Dockerfile:15`) installs all third-party deps with `--require-hashes` against `mock-backend/requirements-hashes.txt`. The single un-hashed line is the local-package install, which has no downloadable artifact to hash.
- **Status**: Accepted residual. Fixing this would require pre-building and publishing a `mock-backend` wheel (out of scope for a fixture used only by tests).
- **Revisit when**: A formal release process exists for the mock-backend wheel.

**GitHub UI Dismissal Steps**:
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `PinnedDependenciesID`
3. Find the alert referencing `mock-backend/Dockerfile` -> "Dismiss alert" -> reason: "Won't fix"
4. Paste this comment text:
   > Accepted residual per SECURITY.md - local-path package install has no hash-pinnable artifact; all third-party deps on the preceding line are hash-pinned; fix requires pre-building a wheel (out of scope for a test fixture).
5. Click "Dismiss alert"

### Pinned-Dependencies -- `tools/deps.sh` curl-bootstrap (MEDIUM)

- **Score**: 9 (Scorecard: "downloadThenRun not pinned by hash")
- **Context**: `tools/deps.sh:49` includes a `curl -LsSf https://astral.sh/uv/install.sh | sh` fallback as the THIRD installation path (after Homebrew and after hash-verified `pip3 install --require-hashes`). The installer script is fetched at runtime from astral-sh's TLS-protected endpoint without a hash check.
- **Status**: Accepted residual. The fallback is unreachable on any machine with Homebrew OR pip3, which covers the developer-machine target audience. Not invoked in CI (CI uses `astral-sh/setup-uv@<sha>` GitHub Action instead).
- **Revisit when**: astral-sh publishes signed install-script hashes that can be verified.

**GitHub UI Dismissal Steps**:
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `PinnedDependenciesID`
3. Find the alert referencing `tools/deps.sh` -> "Dismiss alert" -> reason: "Won't fix"
4. Paste this comment text:
   > Accepted residual per SECURITY.md - curl-bootstrap is third-priority fallback unreachable on any Homebrew or pip3 machine; CI uses hash-pinned astral-sh/setup-uv action instead; fix pending astral-sh publishing signed hashes.
5. Click "Dismiss alert"

### SAST -- coverage rate (MEDIUM)

- **Score**: 9 (Scorecard: "SAST tool detected but not run on all commits: 26 commits out of 30 are checked")
- **Context**: CodeQL runs on every push to `main` and on every PR. The gap is intermediate commits (squash-merge intermediates, dependabot rebases) that don't trigger a fresh CodeQL run. Effective coverage: ~87% of public commits.
- **Status**: Accepted residual for `v0.1.0-prealpha`. The cost of scanning every commit (4x current CI minutes for marginal coverage gain) is not justified at this stage.
- **Revisit when**: We adopt squash-only merge (eliminating intermediate commits) OR move toward production deployment where 100% scan coverage is a compliance requirement.

**GitHub UI Dismissal Steps**:
1. Open https://github.com/WeLikeCode/mintkey/security/code-scanning?query=is%3Aopen+tool%3Ascorecard
2. Filter by rule: `SASTID`
3. Click the alert -> "Dismiss alert" -> reason: "Won't fix"
4. Paste this comment text:
   > Accepted residual per SECURITY.md - CodeQL runs on all PRs and main pushes; ~87% coverage gap is squash-merge intermediates; 100% scan coverage deferred until production deployment requirements apply.
5. Click "Dismiss alert"

---

## Fixable Scorecard residuals -- backlog

None of the 8 Scorecard residuals above have an immediately available code fix that is within scope at the pre-alpha stage. The assessment for each:

- **CodeReviewID** -- requires a second human reviewer; not a code change. Accepted forever (solo project).
- **MaintainedID** -- auto-resolves at 90 days; no action needed.
- **FuzzingID** -- requires building and maintaining a fuzzing harness; deferred to post-v1.0.
- **CIIBestPracticesID** -- requires formal badge attestation process; deferred to pre-v1.0 stable.
- **VulnerabilitiesID (GO-2026-4918)** -- upstream patch is available (`golang.org/x/net v0.53.0`); this is a dep-bump task tracked in the Vulnerabilities section above, not a "fixable Scorecard residual" in the code-change sense.
- **PinnedDependenciesID (`mock-backend/Dockerfile`)** -- fixing requires pre-building and publishing a wheel; out of scope for a test fixture.
- **PinnedDependenciesID (`tools/deps.sh`)** -- fixing requires astral-sh to publish signed installer hashes; blocked on upstream action.
- **SASTID** -- fixing requires adopting squash-only merge to eliminate intermediate commits; process change, not a code fix; deferred.

The one item with an actionable dep-bump -- GO-2026-4918 -- is tracked in the Vulnerabilities section above.

---

## Audit hash chain integrity (SHA-256 invariant)

The audit-event chain in `mintkey-models/mintkey_models/audit.py` uses SHA-256 per [ADR-0014.7](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md). This is NOT a credential hash -- it is a tamper-evident chain where each event's `hash` incorporates the previous event's `prev_hash`. Changing the algorithm requires a new ADR superseding ADR-0014.7, a migration of all existing `hash`/`prev_hash` columns, and lockstep updates to `audit-verify-job/verify.py`.

Enforced by:
- `tests/acceptance/test_audit_append_only.py` -- verifies chain integrity invariants
- ADR-0014.7 -- documents the algorithm choice and the genesis seed `sha256("mintkey-audit-genesis-v1:" || tenant_id)`

Any CodeQL `py/weak-sensitive-data-hashing` alert against `audit.py` is a **FALSE POSITIVE** for this use case. The security goal is tamper-evidence (collision resistance), not secret protection. Dismiss in GitHub UI with rationale: "SHA-256 mandated by ADR-0014.7 for audit chain integrity; not credential hashing."

See also: [`docs/architecture/01-architecture/security-notes/weak-hash-migration.md`](docs/architecture/01-architecture/security-notes/weak-hash-migration.md) for the full weak-hash classification (3 CodeQL sites) and the accept-for-prealpha rationale.

---

## Weak-hash acceptance (CodeQL py/weak-sensitive-data-hashing)

Three CodeQL `py/weak-sensitive-data-hashing` sites were classified in session `2026-05-18-s5-codeql-weak-hashing`:

- `admin-api/src/admin_api/api/internal.py:119` -- SHA-256 fingerprint of a 32-byte CSPRNG agent API key; used as a DB lookup index before Argon2id verification. Brute-force infeasible at 2^256 keyspace.
- `admin-api/src/admin_api/api/proxy.py:64` -- same pattern for service-key fingerprint.
- `mintkey-models/mintkey_models/audit.py:85` -- SHA-256 audit chain (ADR-0014.7-mandated; see Audit hash chain integrity section above).

**Acceptance rationale**: Accepted for prealpha. Sites 1+2 fingerprint high-entropy 32-byte CSPRNG keys; rainbow-table attacks require enumeration of 2^256 inputs, which is computationally infeasible. The CodeQL rule fires because it pattern-matches `hashlib.sha256(<sensitive>)` without context about input entropy. Real risk only exists for low-entropy inputs (e.g., user-set passwords), which is not the case here.

**Revisit criterion**: Before v1.0 GA, if the project introduces lower-entropy credentials (e.g., user-set passwords stored as fingerprints), migrate sites 1+2 to HMAC-SHA-256 with a project-static key. Site 3 requires a new ADR.

Full migration strategy: [`docs/architecture/01-architecture/security-notes/weak-hash-migration.md`](docs/architecture/01-architecture/security-notes/weak-hash-migration.md)

---

## Trivy alerts on Debian-base images -- acceptance policy (post-2026-05-18 image-pin campaign)

The 8 service images in `docker-compose.yml` are now `@sha256:`-pinned (PRs #70 + #74) to the latest patched digests from upstream Docker Hub. Those digests still contain known Debian-base package CVEs (e.g., `CVE-2025-14104` in `zlib`, `CVE-2022-0563` in `util-linux`, `CVE-2026-3184`, `CVE-2026-27456`) that ship in every image based on `python:3.12-slim-bookworm`, `node:22-bookworm-slim`, etc.

**Pinning locks the digest; it does not remove CVEs that exist in the current upstream patched version.** Reducing the Trivy alert count further requires one of:

1. **Wait for Debian** -- When `debian:bookworm-slim` ships a patched version of the affected package, upstream images (`python:3.12-slim-bookworm`, `node:22-bookworm-slim`, etc.) eventually rebuild on that. The Container Scan workflow now has a weekly cron + `workflow_dispatch` (PR #76); on each successful re-scan, Trivy publishes fresh SARIF and GitHub auto-closes alerts that no longer match the current scan. **This is the chosen policy.**
2. **Distroless / chainguard migration** -- switch runtime stages to `gcr.io/distroless/python3-debian12` / `cgr.dev/chainguard/*`. Eliminates the Debian-base-CVE class entirely. Out of scope per S2 (2026-05-18) owner decision; revisit pre-v1.0 stable.
3. **`.trivyignore` suppression list** -- declare each accepted CVE with a rationale comment. Trivy drops them from SARIF. Adds upkeep burden (new CVE IDs roll in regularly).

For `v0.1.0-prealpha`, **option 1 is the policy**. Expect ~800-900 open Trivy alerts on the dashboard at any given time, with the count drifting as Debian ships patches and the weekly cron re-baselines. Operators reading the security tab should focus on **critical-severity Trivy alerts only** until a distroless migration lands.

### Deferred upstream rebuilds (waiting on producer)

- **`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`** -- CVE-2026-31789 (openssl). Latest astral-sh build still ships `openssl 3.0.18-1~deb12u2`; patched version is `3.0.19`. Re-check trigger: `docker run --rm ghcr.io/astral-sh/uv:python3.12-bookworm-slim dpkg -l openssl` returns >=3.0.19. Open follow-up: re-run S2 session when upstream publishes.

---

**Manual dismissal required**: Scorecard (as of `ossf/scorecard-action@v2.4.3`) does not support per-check ignore overrides via a repo config file. Each alert above must be manually dismissed in the GitHub Security -> Code scanning alerts UI with a rationale comment referencing this section. See `team/remediation/2026-05-18-s11-scorecard-residuals/99-report.md` for the operator steps.
