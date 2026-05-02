# Open Questions

**Owner:** Alexandru Iacobescu (architect of record)
**Last updated:** 2026-05-10

Architectural questions that are identified, non-blocking for the current phase, and tracked until resolved. When resolved, an entry moves to an ADR (or amendment) and is marked **Resolved → ADR-NNNN**.

See also: `docs/architecture/01-architecture/open-questions.md` for the detailed per-question register (OQ-001 through OQ-022) that predates this wizard-seeded file. That register is the canonical source for iteration-level open questions. This file tracks wizard-deferred answers and setup-phase gaps.

---

## Wizard-deferred answers

### WQ-001 — Architect email address

**Question:** The architect email used during setup (`alexandru.iacobescu@mintkey.dev`) is inferred from the workspace path. Confirm or correct the canonical architect email for ADR author blocks and CODEOWNERS.

**Phase:** Immediate — correct before first ADR is authored.

**Status:** Open

---

### WQ-002 — BA artifacts for requirements ingestion

**Question:** No BA artifacts were provided at setup (Q26 = None yet). At MVP phase this is unusual. Are there existing requirements documents, user stories, or meeting notes that should be ingested into `docs/requirements/requirements.csv`?

**Follow-up:** If yes, use the `requirements-extract` skill: "extract requirements from `<path>`".

**Phase:** Before Phase 1 milestone 1.0.

**Status:** Open

---

### WQ-003 — CODEOWNERS file

**Question:** A `CODEOWNERS` file routing `docs/architecture/` and `.kiro/steering/` to the architect has not been created. This is a Phase 1 exit criterion per `docs/architecture/00-vision/07-kiro-readiness.md`.

**Action:** Create `CODEOWNERS` at repo root with at minimum:
```
docs/architecture/  @alexandru-iacobescu
.kiro/steering/     @alexandru-iacobescu
```

**Phase:** Before first developer onboards.

**Status:** Open

---

### WQ-004 — Branching model documentation

**Question:** GitHub Flow was recorded as the branching model but no `branching-and-release.md` steering file was generated (deferred per Q16 = Full). The key rules (feature branches, PR required, no direct push to main) should be documented.

**Phase:** Before first developer onboards.

**Status:** Open

---

### WQ-005 — Observability stack preference (optional Q17)

**Question:** Q17 was not answered during setup. The tech stack implies OpenTelemetry default (OTel Collector → Jaeger + Prometheus + Grafana per ADR-0005). Confirm this is the intended observability stack or specify a vendor preference.

**Phase:** Before Phase 1 milestone 1.10 (Observability dashboards).

**Status:** Open — defaulting to OpenTelemetry per ADR-0005.

---

### WQ-006 — Test data strategy (optional Q22)

**Question:** Q22 (test-data strategy) was not answered. The kiro-readiness doc lists fixtures as `⏳ not started`. Confirm whether test data will be synthetic, anonymized prod, or customer-supplied.

**Phase:** Before Phase 1 milestone 1.11 (Demo script + CI smoke test).

**Status:** Open

---

## Maintenance

- New deferred answers from re-runs of the setup wizard land here as `WQ-NNN`.
- Iteration-level open questions (OQ-001 through OQ-022) live in `docs/architecture/01-architecture/open-questions.md`.
- When resolved, mark Status as `Resolved → <ADR or commit>` and keep for 30 days, then remove.
