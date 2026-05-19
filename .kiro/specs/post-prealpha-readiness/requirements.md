# Requirements Document

## Introduction

Post-prealpha readiness is a consolidated spec covering four workstreams that bring the Mintkey project from the `v0.1.0-prealpha` tag to a state where: (1) documentation accurately reflects current capabilities without overclaiming, (2) May 18 security residuals are closed or explicitly deferred with owner actions, (3) the Builder B-1 experience is complete with demo targets, snippets, and troubleshooting, and (4) Kiro enablement artifacts (KIRO.md, pattern library, stubs plan) are in place.

## Glossary

- **Roadmap_Doc**: The file at `docs/architecture/00-vision/06-roadmap.md`
- **Kiro_Readiness_Doc**: The file at `docs/architecture/00-vision/07-kiro-readiness.md`
- **SECURITY_Doc**: The file at `SECURITY.md`
- **DEBUG_Doc**: The file at `docs/DEBUG.md`
- **Makefile**: The file at `Makefile` (GNU Make task runner)
- **EvidenceRef**: A parenthetical citation to a file path, commit SHA, or tool output that proves a status claim
- **Pattern_Doc**: A markdown file under `docs/patterns/` with six sections: Goal, Where the change lives, Step-by-step, Tests to write, Common pitfalls, References
- **Demo_Target**: A Makefile target that orchestrates `docker compose up`, health-check, and user-facing output
- **Mock_Demo_Flow**: The PAT-free 10-minute mock demo flow documented at `docs/guides/10min-mock-demo.md`
- **Scorecard_Residual**: An OpenSSF Scorecard alert accepted and documented in SECURITY_Doc §Accepted Scorecard Residuals
- **ADR**: Architecture Decision Record under `docs/architecture/01-architecture/adr/`

## Requirements

### Requirement 1: Roadmap backup/restore accuracy

**User Story:** As an operator reading the roadmap, I want the document to accurately reflect that dev-workflow backup/restore scripts exist, so that I do not waste time building something that already ships.

#### Acceptance Criteria

1. WHEN the Roadmap_Doc Section 1 "What is not yet in place" list is rendered, THE Roadmap_Doc SHALL NOT contain the claim "No backup/restore procedure" (EvidenceRef: `scripts/dev-backup.sh`, `scripts/dev-restore.sh`, `scripts/dev-backup-cron.example.sh` exist on main).
2. THE Roadmap_Doc SHALL distinguish between "dev-workflow backup/restore scripts exist" and "production DR validated" by stating that dev-workflow scripts are available while production DR remains unvalidated.
3. THE Roadmap_Doc SHALL include an EvidenceRef for the backup/restore status claim citing the script paths on main.

### Requirement 2: No production-readiness overclaim

**User Story:** As a potential adopter, I want documentation to never overclaim production readiness, so that I make informed deployment decisions.

#### Acceptance Criteria

1. THE Roadmap_Doc SHALL NOT claim production-grade backup/restore, HA, or DR capability.
2. THE README SHALL NOT contradict the current state on main (EvidenceRef: diff against main HEAD).
3. WHEN PROGRESS.md status claims are reviewed, THE PROGRESS_Doc SHALL correct any claim that contradicts verified tool output from the current main branch.
4. THE Kiro_Readiness_Doc SHALL reflect any status changes resulting from this spec's deliverables (EvidenceRef: updated status table rows).

### Requirement 3: EvidenceRef on every status sentence

**User Story:** As an architect reviewing documentation, I want every status claim to have a traceable evidence reference, so that claims are auditable.

#### Acceptance Criteria

1. THE Roadmap_Doc SHALL include an EvidenceRef (file path, commit SHA, or CI output reference) for every status sentence in Section 1 and Section 3.
2. IF a status sentence in the Roadmap_Doc lacks an EvidenceRef, THEN THE Roadmap_Doc SHALL be updated to add one or the sentence SHALL be removed.

### Requirement 4: Security residual closure (Scorecard)

**User Story:** As the project owner, I want May 18 scorecard residuals turned into explicit owner-action tasks or documented dismissals, so that no residual is silently forgotten.

#### Acceptance Criteria

1. THE SECURITY_Doc SHALL confirm that each accepted Scorecard_Residual has a documented owner action (dismiss in GitHub UI with rationale comment, or create a follow-up task).
2. THE SECURITY_Doc SHALL document the exact steps for GitHub alert dismissal for each Scorecard_Residual.
3. WHEN a Scorecard_Residual has a code fix available, THE System SHALL create a remediation task referencing the fix.

### Requirement 5: GO-2026-XXXX vulnerability resolution

**User Story:** As the project owner, I want the Go advisory identified by Scorecard to be resolved or explicitly deferred with full context, so that the security posture is clear.

#### Acceptance Criteria

1. THE SECURITY_Doc SHALL identify the full advisory ID for the GO-2026-XXXX vulnerability (EvidenceRef: GitHub Security tab or `govulncheck` output).
2. WHEN an upstream patch exists for the flagged Go dependency, THE System SHALL create a remediation task to bump the dependency.
3. WHEN no upstream patch exists, THE SECURITY_Doc SHALL document the deferral with rationale and a revisit trigger.

### Requirement 6: Weak hashing migration strategy

**User Story:** As the architect, I want a documented migration strategy for `agents.api_key_fingerprint` and `service_api_keys.key_fingerprint` weak hashing, so that the path forward is clear.

#### Acceptance Criteria

1. THE System SHALL document a migration strategy for weak-hash columns choosing one of: (a) maintenance-window reissue, (b) dual-fingerprint cutover, or (c) accept-for-prealpha with documented rationale.
2. THE migration strategy document SHALL state the chosen approach, the risk of the current state, and the trigger for executing the migration.
3. IF the chosen strategy is "accept for prealpha", THEN THE SECURITY_Doc SHALL document the acceptance with rationale and a revisit-at criterion.

### Requirement 7: Audit hash chain SHA-256 preservation

**User Story:** As the architect, I want the audit hash chain algorithm (SHA-256) preserved per ADR-0014.7 unless a new ADR supersedes it, so that no silent algorithm change occurs.

#### Acceptance Criteria

1. THE System SHALL NOT modify the audit hash chain algorithm from SHA-256 without a new ADR that supersedes ADR-0014.7.
2. IF a code change touches the audit hash chain, THEN THE code change SHALL include tests verifying SHA-256 continuity.

### Requirement 8: No credential leakage

**User Story:** As a security reviewer, I want assurance that no credential, API key, or secret is printed or committed in any deliverable of this spec.

#### Acceptance Criteria

1. THE System SHALL NOT print, log, or commit any credential, API key, or secret value in any file produced by this spec.
2. WHEN code changes are made, THE code changes SHALL pass the red-team fingerprint grep (`scripts/red-team-fingerprints.txt`) with zero matches.

### Requirement 9: ADR immutability

**User Story:** As the architect, I want accepted ADRs to remain unedited, so that the architectural record is preserved.

#### Acceptance Criteria

1. THE System SHALL NOT edit any file under `docs/architecture/01-architecture/adr/` that has status "Accepted".
2. IF a decision must change, THEN THE System SHALL propose a new ADR that supersedes the existing one.

### Requirement 10: Code changes have tests

**User Story:** As a developer, I want every code change in this spec to have corresponding tests, so that regressions are caught.

#### Acceptance Criteria

1. WHEN a code change is made as part of this spec, THE code change SHALL include at least one test that exercises the changed behavior.
2. THE test suite SHALL pass after all code changes are applied (EvidenceRef: test runner output with exit code 0).

### Requirement 11: `make demo` target

**User Story:** As a builder evaluating Mintkey, I want a single `make demo` command that starts the stack, waits for health, prints the admin URL and bootstrap password, and shows safe next steps, so that first-run friction is minimal.

#### Acceptance Criteria

1. WHEN `make demo` is invoked, THE Makefile SHALL execute `docker compose up -d` and wait for all containers to reach healthy state.
2. WHEN all containers are healthy, THE Demo_Target SHALL print the admin URL (`http://localhost:8081`).
3. WHEN all containers are healthy, THE Demo_Target SHALL print the bootstrap admin password retrieved from the bootstrap-secrets volume.
4. WHEN all containers are healthy, THE Demo_Target SHALL print safe next steps pointing to `docs/guides/github-quickstart.md`.
5. THE Demo_Target SHALL NOT destroy Docker volumes.
6. THE Demo_Target SHALL recommend running `bash scripts/dev-backup.sh` before any destructive path.
7. IF Docker is unavailable, THEN THE Demo_Target SHALL exit with a non-zero code and print a clear error message indicating Docker is required.

### Requirement 12: `make demo-mock` target

**User Story:** As a builder without external API keys, I want a `make demo-mock` command that runs the full 10-minute PAT-free mock demo flow end-to-end, so that I can evaluate Mintkey without credentials.

#### Acceptance Criteria

1. WHEN `make demo-mock` is invoked, THE Makefile SHALL start the stack (if not running), wait for health, and execute the full Mock_Demo_Flow end-to-end.
2. THE `make demo-mock` target SHALL complete without requiring any external API key or PAT.
3. IF the mock demo flow fails, THEN THE target SHALL exit with a non-zero code and print diagnostic output.

### Requirement 13: "Agent never sees the secret" proof walkthrough

**User Story:** As a builder, I want a structured walkthrough proving the agent never touches the real credential, so that I can verify the core security claim.

#### Acceptance Criteria

1. THE System SHALL produce a document at `docs/guides/agent-never-sees-secret.md`.
2. THE document SHALL walk through: token request, proxy call, audit log entry, and OTel trace — demonstrating zero credential exposure at each step.
3. THE document SHALL include copy-paste commands that a reader can execute against a running stack.

### Requirement 14: Python agent snippet

**User Story:** As a Python developer building an agent, I want a ready-to-use code snippet showing how to request a token and call a service through the proxy, so that integration takes minutes.

#### Acceptance Criteria

1. THE System SHALL produce a Python snippet at `examples/python-agent-snippet/`.
2. THE snippet SHALL demonstrate: authenticate with agent API key, request a JWT via MCP, call a backend service through the egress proxy.
3. THE snippet SHALL include a README with prerequisites and execution instructions.

### Requirement 15: TypeScript agent snippet

**User Story:** As a TypeScript developer building an agent, I want a ready-to-use code snippet showing how to request a token and call a service through the proxy, so that integration takes minutes.

#### Acceptance Criteria

1. THE System SHALL produce a TypeScript snippet at `examples/typescript-agent-snippet/`.
2. THE snippet SHALL demonstrate: authenticate with agent API key, request a JWT via MCP, call a backend service through the egress proxy.
3. THE snippet SHALL include a README with prerequisites and execution instructions.

### Requirement 16: OpenAI-compatible API example

**User Story:** As a builder using OpenAI-compatible APIs, I want an example integration showing how to register and broker access to an OpenAI-compatible endpoint, so that the most common AI builder pattern is covered.

#### Acceptance Criteria

1. THE System SHALL produce an example integration demonstrating Mintkey brokering access to an OpenAI-compatible API endpoint.
2. THE example SHALL include service registration configuration, agent grant setup, and a working call through the proxy.

### Requirement 17: Troubleshooting expansion in DEBUG.md

**User Story:** As a builder hitting first-run failures, I want expanded troubleshooting guidance covering the most common issues, so that I can self-serve without filing a bug.

#### Acceptance Criteria

1. THE DEBUG_Doc SHALL include a troubleshooting entry for "stack not running" (Docker not started or compose not up).
2. THE DEBUG_Doc SHALL include a troubleshooting entry for "bootstrap password / KEK mismatch" (MINTKEY_BOOTSTRAP_KEK disagreement between seed-job and reader services).
3. THE DEBUG_Doc SHALL include a troubleshooting entry for "oauth2-proxy / Jaeger auth issues" (cookie-secret cascade, redirect loop).
4. THE DEBUG_Doc SHALL include a troubleshooting entry for "`make smoke` failures" (common causes and resolution steps).
5. THE DEBUG_Doc SHALL include a troubleshooting entry for "backup before reset" (directing users to `scripts/dev-backup.sh` before `docker compose down -v`).
6. THE DEBUG_Doc SHALL include a troubleshooting entry for "MCP config mismatch" (MCP server URL or tool schema version disagreement with client config).

### Requirement 18: Root KIRO.md as thin link hub

**User Story:** As a Kiro agent reading the repo for the first time, I want a root `KIRO.md` that provides a one-paragraph summary and links to AGENTS.md, steering/, and architecture/, so that context loading is fast and focused.

#### Acceptance Criteria

1. THE System SHALL produce a file at `/KIRO.md` (repo root).
2. THE KIRO.md SHALL contain a one-paragraph product summary.
3. THE KIRO.md SHALL link to `AGENTS.md` for coding-agent instructions.
4. THE KIRO.md SHALL link to `.kiro/steering/` for governance rules.
5. THE KIRO.md SHALL link to `docs/architecture/` for architectural source of truth.
6. THE KIRO.md SHALL defer detailed content to the linked documents (thin hub, not a duplicate).

### Requirement 19: Pattern library documents

**User Story:** As a Kiro agent or developer adding a feature, I want pattern library documents for the three most common operations, so that I can follow a proven step-by-step recipe.

#### Acceptance Criteria

1. THE System SHALL produce `docs/patterns/add-rest-endpoint.md` with six sections: Goal, Where the change lives, Step-by-step, Tests to write, Common pitfalls, References.
2. THE System SHALL produce `docs/patterns/add-mcp-tool.md` with the same six sections.
3. THE System SHALL produce `docs/patterns/add-audit-event.md` with the same six sections.
4. WHEN a Pattern_Doc references an ADR or contract, THE reference SHALL be a relative link to the canonical file path.

### Requirement 20: Minimal stubs plan

**User Story:** As the architect planning Kiro enablement, I want a documented plan (or minimal implementation) for stub services (Vault Adapter, Kong/proxy recorder, OIDC/Keycloak mock), so that the path to testable Kiro-generated code is clear.

#### Acceptance Criteria

1. THE System SHALL produce a stubs plan document or minimal stub implementations for: Vault Adapter (in-memory), Kong/proxy recorder (HTTP request recorder), and OIDC/Keycloak mock (canned ID tokens).
2. THE stubs plan SHALL state the interface each stub implements, the location it will live (`tests/stubs/`), and the minimum viable scope for CI use.
3. IF minimal implementations are provided instead of a plan, THEN THE implementations SHALL include at least one test demonstrating the stub's behavior.

### Requirement 21: Kiro readiness doc update

**User Story:** As the architect, I want the Kiro readiness document updated to reflect deliverables from this spec, so that the status table is current.

#### Acceptance Criteria

1. WHEN KIRO.md is created, THE Kiro_Readiness_Doc status table SHALL update the "KIRO.md project conventions" row from ⏳ to ✅ with an EvidenceRef.
2. WHEN pattern library documents are created, THE Kiro_Readiness_Doc status table SHALL update the "Pattern library" row to reflect partial completion with an EvidenceRef.
3. WHEN stubs plan or implementations are produced, THE Kiro_Readiness_Doc status table SHALL update the "Stub services" row to reflect the new state with an EvidenceRef.
