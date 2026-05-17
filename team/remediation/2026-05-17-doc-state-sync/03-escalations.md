# Doc-State Sync — Escalations

**Session:** `2026-05-17-doc-state-sync`

(None at session start. Tracked here if reviewer round 3 fails on any chunk, or if an out-of-scope inconsistency is discovered.)

## ESC-C2-01: PROGRESS.md §1 checklist row 1 — stale container count

**Flagged by:** C-2 implementer
**File:** `PROGRESS.md:10`
**Current text:** `Stack boots — all 15 containers healthy`
**Issue:** Per `EV-COMPOSE-SERVICES`, the actual count is 17 long-running containers + 2 one-shot jobs. The "15 containers" claim in the §1 checklist is actively wrong (not merely dated).
**Action needed:** Orchestrator or next implementer with §1 checklist scope should update row 1 to "all 17 long-running containers + 2 one-shot jobs healthy" citing `EV-COMPOSE-SERVICES`.
**Why not fixed by C-2:** Task instructions direct checklist-row fixes to escalation rather than silent edit, to preserve reviewer auditability.

**Resolution (2026-05-17, orchestrator):** RESOLVED in-line by orchestrator extending C-2 scope. PROGRESS.md:12 updated to `Stack boots — all 17 long-running containers + 2 one-shot jobs healthy` with a `Container count updated 2026-05-17 to reflect current docker-compose.yml` annotation in the `Last verified` cell. Cited `EV-COMPOSE-SERVICES`. REV-2 PASS verified.

---

## ESC-C3-01: Roadmap Section 7 L192/L193 — Enterprise rows contradict Section 3 corrections

**Flagged by:** REV-3 reviewer (PASS-WITH-RESIDUAL)
**Files:** `docs/architecture/00-vision/06-roadmap.md:192-193`
**Issue:** Section 7 Enterprise table rows still said `10 Dockerfiles run as root today` and `Base image @sha256 digest pinning | Deferred (F-23)`, contradicting Section 3 L89-91 (transitioned to ✅ in C-3) and the underlying evidence `EV-DOCKERFILE-USER` + `EV-DOCKERFILE-PIN`.

**Resolution (2026-05-17, orchestrator):** RESOLVED in-line by orchestrator extending C-3 scope. Both rows reframed at the Enterprise bar:
- L192: rewritten as `Non-root Dockerfile USER directive across the full image set + image-signing / attestation | Partial | High | Long-running Python/Node containers run as non-root with USER 65532 + HEALTHCHECK since PR #33 REL-3; one-shot init containers (seed-job, liquibase) intentionally root (PR #47). Enterprise bar additionally requires non-root strategy for init containers, image signing (Cosign), and provenance attestation (SLSA L1+).`
- L193: rewritten as `Base image @sha256 digest pinning with automated bump policy | Partial | High | All 15 Dockerfile FROM directives SHA-pinned since PR #35 (commit 373221f). Enterprise bar adds automated digest-bump workflow with provenance attestation.`
- L201 / L215 (E-1 exit criteria) left as-is — defensible as Enterprise-bar restatement (additional attestation / signing / full coverage required beyond what landed in PRs #33/#35).

Cited EvidenceRefs: `EV-DOCKERFILE-USER`, `EV-DOCKERFILE-PIN`, `EV-SEED-JOB-ROOT`. No new ledger rows added.
