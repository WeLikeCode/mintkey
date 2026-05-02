# Documentation entry point

This documentation is organized using the **CMU SEI *Views and Beyond*** method (Clements et al., *Documenting Software Architectures*, 2nd ed., 2010), the **C4 model** for visual views (Brown), **Architecture Decision Records** (Nygard) for every significant choice, and **Quality Attribute Scenarios** (Bass et al., *Software Architecture in Practice*) to define what "good" means measurably.

## Layout

| Section                     | Purpose                                                                                                            | Iteration |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------|-----------|
| [`00-vision/`](00-vision/)  | What we are building, for whom, with what vocabulary, plus the roadmap and Kiro‑readiness checklist.                | 1         |
| [`01-architecture/`](01-architecture/) | The architecture itself: system context, container view, quality attributes, ADRs, threat model.            | 1         |
| [`02-tech-stack/`](02-tech-stack/)     | Concrete tech choices per container, captured as ADRs.                                                       | 2         |
| [`03-flows/`](03-flows/)               | Behavioral flows (sequence diagrams) for major user journeys.                                                | 3         |
| [`04-observability/`](04-observability/) | Observability strategy (OTel, Jaeger, Prometheus, Grafana).                                                | 1 (high‑level) → 2 (detail) |
| [`05-deployment/`](05-deployment/)       | Deployment topology, beginning with Docker Compose for MVP.                                                | 1 (skeleton) → 2 (detail)   |
| [`proposal/`](proposal/)                 | Decision proposals — one option‑set per file. Each accepted proposal becomes an ADR.                          | ongoing   |
| [`contracts/`](contracts/)               | Wire‑level contracts: REST OpenAPI, MCP tool definitions, event schemas.                                     | 4          |

## Suggested reading order
1. [`00-vision/01-problem-statement.md`](00-vision/01-problem-statement.md)
2. [`00-vision/02-product-vision.md`](00-vision/02-product-vision.md)
3. [`00-vision/03-personas-and-stakeholders.md`](00-vision/03-personas-and-stakeholders.md)
4. [`00-vision/04-glossary.md`](00-vision/04-glossary.md)
5. [`00-vision/05-iteration-plan.md`](00-vision/05-iteration-plan.md)
6. [`00-vision/06-roadmap.md`](00-vision/06-roadmap.md) — phases, milestones, future state
7. [`00-vision/07-kiro-readiness.md`](00-vision/07-kiro-readiness.md) — what's needed to enable agentic development
8. [`01-architecture/01-system-context.md`](01-architecture/01-system-context.md)
9. [`01-architecture/02-container-view.md`](01-architecture/02-container-view.md)
10. [`01-architecture/03-quality-attributes.md`](01-architecture/03-quality-attributes.md)
11. [`01-architecture/05-threat-model.md`](01-architecture/05-threat-model.md)
12. [`01-architecture/04-views-and-beyond.md`](01-architecture/04-views-and-beyond.md) *(meta — explains the documentation method)*
13. [`01-architecture/adr/`](01-architecture/adr/) — all 17 accepted ADRs (start with 0001)
14. [`proposal/`](proposal/) — proposals (P-001..P-009; all currently Accepted with their ADR pointer)
15. [`contracts/`](contracts/) — iteration-4 wire-level contracts (OpenAPI, MCP tool schemas, event schemas, vault.proto)
16. [`01-architecture/open-questions.md`](01-architecture/open-questions.md) — 22 tracked OQ-NNN items deferred to phases 1+

> **Note on layout in this repo (mintkey)**: this `architecture/` directory is the **architectural source of truth** copied from the upstream architecture-only repo. ADRs are accessible at **two paths** to satisfy both layouts:
>
> - **Canonical (SEI Views & Beyond)**: [`01-architecture/adr/`](01-architecture/adr/) — the real files.
> - **Legacy / project scaffold**: [`adrs/`](adrs/) — symlinks pointing at the canonical files.
>
> Both paths show the same content. Edits to either are edits to the same file. New ADRs added to the canonical path need a one-line `ln -s` in `adrs/` to also appear there.

## Conventions
- **Diagrams**: Mermaid embedded in markdown. Render to HTML with the `viz-architecture` skill ([`.claude/skills/viz-architecture/SKILL.md`](../.claude/skills/viz-architecture/SKILL.md)).
- **Quality attribute scenarios**: SEI ADD format — Source, Stimulus, Environment, Artifact, Response, Response Measure.
- **ADRs**: Nygard format. Immutable once Accepted; superseded entries are kept for history.
- **Open questions**: each document closes with an *Open questions* section if any remain.

## Out of scope for the documentation phase
- Source code.
- Wire‑level message formats — those live under `contracts/` (iteration 4).
- Provider‑specific implementation details — those become ADRs once decided (iteration 2).
