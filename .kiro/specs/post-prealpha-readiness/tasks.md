# Implementation Plan: Post-Prealpha Readiness

## Overview

Four workstreams delivering documentation accuracy, security residual closure, Builder B-1 experience, and Kiro enablement artifacts. Primarily documentation, Makefile targets, shell scripts, and example code — no core service code changes. Tasks T-0 through T-2 are already complete (spec creation).

## Tasks

- [x] 1. Evidence baseline and spec creation (T-0, T-1, T-2)
  - [x] 1.1 Gather evidence from repo state (T-0)
    - Verify existence of `scripts/dev-backup.sh`, `scripts/dev-restore.sh`, `scripts/dev-backup-cron.example.sh`
    - Verify current state of `SECURITY.md`, `docs/DEBUG.md`, `Makefile`, `docs/architecture/00-vision/06-roadmap.md`
    - _Requirements: 1, 2, 3_
  - [x] 1.2 Create requirements.md (T-1)
    - Already complete — `.kiro/specs/post-prealpha-readiness/requirements.md` exists
    - _Requirements: all_
  - [x] 1.3 Create design.md (T-2)
    - Already complete — `.kiro/specs/post-prealpha-readiness/design.md` exists
    - _Requirements: all_

- [x] 2. Roadmap and status reconciliation (T-3, WS-1)
  - [x] 2.1 Fix Roadmap_Doc backup/restore claim
    - Edit `docs/architecture/00-vision/06-roadmap.md` Section 1: remove "No backup/restore procedure"
    - Replace with accurate statement distinguishing dev-workflow scripts from production DR
    - Add EvidenceRef citing `scripts/dev-backup.sh`, `scripts/dev-restore.sh`, `scripts/dev-backup-cron.example.sh`
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2 Add EvidenceRef to all status sentences in Roadmap_Doc
    - Audit Sections 1 and 3 of `docs/architecture/00-vision/06-roadmap.md`
    - Add EvidenceRef (file path, commit SHA, or CI output) to every status sentence
    - Remove or correct any status sentence that contradicts verified state on main
    - _Requirements: 2.1, 3.1, 3.2_
  - [x] 2.3 Create evidence tracking table
    - Create `.kiro/specs/post-prealpha-readiness/evidence.md` with claim/evidence/verified columns
    - Populate with evidence citations gathered during roadmap audit
    - _Requirements: 3.1, 3.2_

- [x] 3. Security residual inventory and owner-action matrix (T-4, WS-2)
  - [x] 3.1 Document Scorecard owner actions in SECURITY.md
    - For each accepted Scorecard_Residual in `SECURITY.md §Accepted Scorecard Residuals`, add "GitHub UI Dismissal Steps" subsection
    - Include exact click-path instructions for GitHub alert dismissal
    - _Requirements: 4.1, 4.2_
  - [x] 3.2 Resolve GO-2026-XXXX vulnerability
    - Check GitHub Security → Code scanning alerts for full advisory ID
    - If upstream patch exists: document dep-bump task
    - If no patch: document deferral with rationale and revisit trigger in SECURITY.md
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 3.3 Document weak hash migration strategy
    - Create `docs/architecture/01-architecture/security-notes/weak-hash-migration.md`
    - Document current state, risk assessment, chosen approach (accept-for-prealpha), and revisit trigger
    - Update SECURITY.md with acceptance rationale and revisit criterion
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 3.4 Document audit hash chain SHA-256 invariant
    - Document in SECURITY.md that SHA-256 is per ADR-0014.7 and any change requires a new ADR
    - Reference existing tests in `tests/acceptance/test_audit_append_only.py`
    - _Requirements: 7.1, 7.2_

- [x] 4. Security fixes that do not require owner decisions (T-5, WS-2)
  - [x] 4.1 Create remediation tasks for fixable Scorecard residuals
    - For any Scorecard_Residual with an available code fix, create a concrete remediation task
    - Reference the specific fix (dep bump, config change, etc.)
    - _Requirements: 4.3, 10.1_

- [ ] 5. Checkpoint — Security and documentation accuracy
  - Ensure all SECURITY.md updates are consistent with ADR immutability (Requirement 9)
  - Verify no accepted ADR was edited
  - Verify red-team fingerprint grep passes with zero matches (Requirement 8)
  - Ask the user if questions arise.

- [x] 6. `make demo` target (T-6, WS-3)
  - [x] 6.1 Implement `make demo` Makefile target
    - Add `demo` target to `Makefile` with Docker availability check, `docker compose up -d`, health-check polling (180s timeout), and success output (admin URL, bootstrap password, next steps)
    - Ensure target never destroys volumes and recommends `scripts/dev-backup.sh`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_
  - [x] 6.2 Implement `make demo-mock` Makefile target
    - Add `demo-mock` target that auto-starts stack if not running, then executes mock demo flow
    - Create `scripts/demo-mock-flow.sh` orchestrating: register mock service, create agent, request JWT, proxied call, verify response
    - _Requirements: 12.1, 12.2, 12.3_

- [ ] 7. Agent-never-sees-secret proof walkthrough (T-7, WS-3)
  - [ ] 7.1 Create `docs/guides/agent-never-sees-secret.md`
    - Write structured walkthrough: setup, token request, proxy call, audit log check, OTel trace check, conclusion
    - Include copy-paste commands executable against a running stack
    - Demonstrate zero credential exposure at each step
    - _Requirements: 13.1, 13.2, 13.3_

- [ ] 8. Python agent snippet (T-8, WS-3)
  - [ ] 8.1 Create `examples/python-agent-snippet/`
    - Create `agent.py` (~40 lines): authenticate with agent API key, request JWT via MCP, call backend through egress proxy
    - Create `requirements.txt` with `httpx`
    - Create `README.md` with prerequisites and execution instructions
    - _Requirements: 14.1, 14.2, 14.3_

- [ ] 9. TypeScript agent snippet (T-9, WS-3)
  - [ ] 9.1 Create `examples/typescript-agent-snippet/`
    - Create `agent.ts` (~40 lines): authenticate, request JWT, call backend through proxy
    - Create `package.json` with minimal deps
    - Create `tsconfig.json` with minimal config
    - Create `README.md` with prerequisites and execution instructions
    - _Requirements: 15.1, 15.2, 15.3_

- [ ] 10. OpenAI-compatible API example (T-10, WS-3)
  - [ ] 10.1 Create `examples/openai-compatible/`
    - Create `README.md` explaining the pattern (register OpenAI-compatible endpoint, grant agent, call through proxy)
    - Create `register-service.sh` with curl commands for service registration
    - Create `agent.py` calling the OpenAI-compatible endpoint through Mintkey's proxy
    - Use mock-backend in echo mode (no real API key needed)
    - _Requirements: 16.1, 16.2_

- [ ] 11. Troubleshooting update (T-11, WS-3)
  - [ ] 11.1 Expand `docs/DEBUG.md` with new troubleshooting entries
    - Add entry: "Stack not running" (Docker not started / compose not up)
    - Add entry: "Bootstrap password / KEK mismatch" (MINTKEY_BOOTSTRAP_KEK disagreement)
    - Add entry: "oauth2-proxy / Jaeger auth issues" (cookie-secret cascade, redirect loop)
    - Add entry: "`make smoke` failures" (common causes and resolution)
    - Add entry: "Backup before reset" (directing to `scripts/dev-backup.sh`)
    - Add entry: "MCP config mismatch" (URL or schema version disagreement)
    - Follow existing DEBUG.md format: symptom, diagnostic commands, resolution steps
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6_

- [ ] 12. Checkpoint — Builder B-1 experience complete
  - Ensure all WS-3 deliverables exist and contain required sections
  - Verify no credentials appear in any example code (placeholder values only)
  - Verify red-team fingerprint grep passes with zero matches (Requirement 8)
  - Ask the user if questions arise.

- [ ] 13. Root KIRO.md (T-12, WS-4)
  - [ ] 13.1 Create `/KIRO.md` at repo root
    - Write thin link hub (< 100 lines): one-paragraph summary, quick links to AGENTS.md, `.kiro/steering/`, `docs/architecture/`, `docs/patterns/`
    - Include tech stack table and "How to make a change" section
    - Include key invariants (P-1 through P-4)
    - Do NOT duplicate content from AGENTS.md or architecture docs
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

- [ ] 14. Pattern docs: REST endpoint, MCP tool, audit event (T-13, WS-4)
  - [ ] 14.1 Create `docs/patterns/add-rest-endpoint.md`
    - Six sections: Goal, Where the change lives, Step-by-step, Tests to write, Common pitfalls, References
    - Use relative links to ADRs and contracts
    - _Requirements: 19.1, 19.4_
  - [ ] 14.2 Create `docs/patterns/add-mcp-tool.md`
    - Six sections: Goal, Where the change lives, Step-by-step, Tests to write, Common pitfalls, References
    - Use relative links to ADRs and contracts
    - _Requirements: 19.2, 19.4_
  - [ ] 14.3 Create `docs/patterns/add-audit-event.md`
    - Six sections: Goal, Where the change lives, Step-by-step, Tests to write, Common pitfalls, References
    - Use relative links to ADRs and contracts
    - _Requirements: 19.3, 19.4_

- [ ] 15. Minimal stubs plan (T-14, WS-4)
  - [ ] 15.1 Create `tests/stubs/README.md`
    - Document three priority stubs: Vault Adapter (in-memory, Go), Kong/Proxy Recorder (HTTP, Go), OIDC/Keycloak Mock (Python)
    - State interface, location, minimum viable scope, and language for each
    - Include uniform conventions and CI integration plan
    - _Requirements: 20.1, 20.2_

- [ ] 16. Update Kiro readiness doc (T-14 cont., WS-4)
  - [ ] 16.1 Update `docs/architecture/00-vision/07-kiro-readiness.md` status table
    - "KIRO.md project conventions" row: ⏳ → ✅ with EvidenceRef `/KIRO.md`
    - "Pattern library" row: ❌ → 🟢 (partial) with EvidenceRef `docs/patterns/*.md`
    - "Stub services" row: ❌ → 🟢 (plan documented) with EvidenceRef `tests/stubs/README.md`
    - _Requirements: 21.1, 21.2, 21.3_

- [ ] 17. Verification and final report (T-15)
  - [ ] 17.1 Run final verification checks
    - Verify all deliverable files exist at expected paths
    - Run red-team fingerprint grep across all new/modified files (zero matches required)
    - Verify no accepted ADR was edited (`git diff` on `docs/architecture/01-architecture/adr/`)
    - Verify Kiro_Readiness_Doc status table is current
    - Confirm evidence.md is populated with all claims and their EvidenceRefs
    - _Requirements: 8.1, 8.2, 9.1, 2.4, 10.2_
  - [ ] 17.2 Produce final readiness report
    - Summarize all deliverables with file paths
    - List any deferred items or owner decisions still needed
    - Confirm all 21 requirements are addressed
    - _Requirements: all_

## Notes

- Tasks 1.1–1.3 are pre-completed (spec creation phase)
- No property-based tests — deliverables are documentation, Makefile targets, and example code
- Verification is through file existence checks, content assertions, and red-team greps
- Do NOT edit accepted ADRs (Requirement 9) — security updates go to SECURITY.md
- All example code uses placeholder values (`YOUR_AGENT_API_KEY`, `<agent-key>`) — never real credentials
- `docs/architecture/` is architect-owned; updates to `07-kiro-readiness.md` are permitted by this spec's scope

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "3.1", "3.2"] },
    { "id": 1, "tasks": ["2.2", "3.3", "3.4"] },
    { "id": 2, "tasks": ["2.3", "4.1"] },
    { "id": 3, "tasks": ["6.1", "7.1", "8.1", "9.1", "10.1", "11.1", "13.1", "14.1", "14.2", "14.3", "15.1"] },
    { "id": 4, "tasks": ["6.2", "16.1"] },
    { "id": 5, "tasks": ["17.1"] },
    { "id": 6, "tasks": ["17.2"] }
  ]
}
```
