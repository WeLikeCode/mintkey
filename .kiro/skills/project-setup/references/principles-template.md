# Architecture Principles — {{PROJECT_CODENAME}}

> Default-load steering file. These are the load-bearing rules for this engagement.
> Architect-owned. Changing a principle requires an ADR.

## Core principles

1. **Spec before code.** No implementation without a referenced ADR, contract, or spec. The `spec-first-check` skill is the gate.
2. **Architect owns governance.** ADRs, contracts, schema rules, and `docs/architecture/` are the architect's responsibility. Developers implement against governance; they don't author it.
3. **`docs/architecture/` is ADD-only.** Suggest diffs; never apply silently.
4. **Real risks, no padding.** Every risk entry must answer: what breaks, what evidence, which component.
5. **Smallest first cut.** Ship the smallest artifact that unblocks the next decision.

## Engagement-specific principles

{{ENGAGEMENT_PRINCIPLES}}

## Defaults active for this project

| Pattern | Status | Override ADR |
|---|---|---|
| Append-only business records | {{IMMUTABLE_RECORDS}} | — |
| Idempotent processing | {{IDEMPOTENT_PROCESSING}} | — |
| Single-writer-per-table | {{SINGLE_WRITER}} | — |
| Multi-tenant isolation | {{MULTI_TENANT}} | — |
| Contract-first development | On | — |
| Observability by default | {{OBSERVABILITY}} | — |

## API contract format

{{API_CONTRACT_FORMAT}}

## Persistence

{{PERSISTENCE_PRIMARIES}}

## AI / ML in critical path

{{AI_ML_STATUS}}
