# {{ENGAGEMENT_NAME}} — Tech stack

> **Names only.** Rationale lives in ADRs. ≤ 500 words.

## Backend

[REQUIRES-UPDATE per Q9/Q11/Q14:]

| Concern | Choice | ADR |
|---|---|---|
| Primary language(s) | (Q9) | ADR-NNN |
| API framework | [REQUIRES-UPDATE] | ADR-NNN |
| Persistence | (Q11) | ADR-NNN |
| Migration tool | [REQUIRES-UPDATE] | ADR-NNN |
| Event bus | (Q14) | ADR-NNN |
| Workflow orchestrator | [REQUIRES-UPDATE: only if async/batch in scope] | ADR-NNN |

## Frontend

[REQUIRES-UPDATE per Q10:]

| Concern | Choice | ADR |
|---|---|---|
| Framework | [REQUIRES-UPDATE] | ADR-NNN |
| Build tool | [REQUIRES-UPDATE] | ADR-NNN |
| Form rendering | [REQUIRES-UPDATE: if Q19=Yes, schema-driven library] | ADR-NNN |

## Infrastructure

[REQUIRES-UPDATE per Q8/Q17/Q18:]

| Concern | Choice | ADR |
|---|---|---|
| Object storage | [REQUIRES-UPDATE: if Q11 includes Object store] | ADR-NNN |
| Identity provider | (Q18) | ADR-NNN |
| Container orchestration | [REQUIRES-UPDATE per Q8] | ADR-NNN |
| Observability | (Q17) | ADR-NNN |

## Contracts

| Format | Use |
|---|---|
| OpenAPI 3.1 | REST APIs (if Q12 includes OpenAPI) |
| AsyncAPI 2.6 | Event contracts (if Q14 ≠ No) |
| JSON Schema 2020-12 | Reusable payload types |

## What does NOT belong here

- Versions / version pinning → those go in `package.json` / `pyproject.toml` / equivalents
- Rationale → ADRs
- Migration tooling configuration → `infra/database/` (with the migration tool's own README)

## Cross-references

- ADRs that established each choice — link from each row above
- [`docs/architecture/adrs/`](../../docs/architecture/adrs/)
