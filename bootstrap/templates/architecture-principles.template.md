# {{ENGAGEMENT_NAME}} — Architecture Principles

> The constitution. 3-10 stable rules that anchor every decision. **Each principle MUST be testable** — if you can't write a test or check that asserts it, it's a slogan, not a principle.

## Generic baseline (template-shipped)

These apply to almost any engagement. Keep, modify, or delete based on Q6 / Q7 / Q11 answers — but if you delete one, document the trade-off as ADR-0001-bootstrap.

### P-1. Append-only business records

Audit-relevant entities never mutate in place. Corrections are new records that reference and supersede the original. **Test:** any UPDATE to an audit-relevant column fails CI lint.

### P-2. Idempotent processing

Replaying the same input produces no duplicate side effects. Every pipeline step is safe to retry. **Test:** golden-fixture replay tests assert byte-equal outputs (or tolerance-bounded, documented).

### P-3. Single-writer-per-table

Each persisted entity has exactly one writing service. Other services read. Cross-domain writes require explicit grants AND a documented exception. **Test:** PostgreSQL GRANT matrix asserts at runtime.

### P-4. Multi-layer tenant isolation

If multi-tenant: enforce at API layer, DB query layer, object-store key layer, AND pipeline-execution layer. **Test:** integration tests inject cross-tenant payloads at every layer; all must reject.

### P-5. Contract-first development

Inter-component interfaces are versioned, language-neutral contracts authored before implementation. Generated SDKs are derivatives — never hand-edited. **Test:** `make spec-trace` reports zero implementations without spec back-references.

### P-6. Observability by default

Every service emits structured JSON logs with correlation IDs and tenant context. OpenTelemetry traces cross every plane boundary. **Test:** OTel exporter is wired; CI rejects services without instrumented entry points.

### P-7. Schema-driven over hardcoded structure

User-facing forms, validation rules, and entity attribute taxonomies derive from versioned schemas. **Test:** no hardcoded form structure in frontend (lint rule).

### P-8. ADR-traceable decisions

Every architectural decision lives in `docs/architecture/adrs/`. ADRs are immutable once Accepted; reversal is a new ADR with `Supersedes:`. **Test:** zero hits on grep for "TODO: write ADR" in code; every Accepted ADR has ≥ 1 referencing test.

---

## Engagement-specific principles

> [REQUIRES-UPDATE]

Add 0-3 principles unique to this engagement. Each must be testable. Examples that are NOT engagement-specific (and belong in the generic set) are removed; examples that ARE engagement-specific (e.g., "every image preserved as raw evidence") go here.

### P-9. [REQUIRES-UPDATE: e.g., "Raw uploaded data is the evidence of record; derived artifacts never replace it"]

[REQUIRES-UPDATE: rationale + test]

### P-10. [REQUIRES-UPDATE]

---

## What does NOT belong here

- Implementation guidelines → those are conventions (per-language, per-area steering files)
- Decisions with rationale → those are ADRs
- Per-feature requirements → those are in `.kiro/specs/`
- Stylistic preferences → not principles

## Cross-references

- [`.kiro/steering/rule-`](../steering/rule-) — protocol rules that override these principles when in conflict
- [`docs/architecture/adrs/`](../../docs/architecture/adrs/) — decisions justified by these principles
