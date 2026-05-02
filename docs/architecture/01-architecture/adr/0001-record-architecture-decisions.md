# ADR‑0001: Record architecture decisions

## Status
Accepted — 2026-05-10.

## Context
We are building a system whose architecture has high coupling between security, runtime topology, and protocol surface (see [`../02-container-view.md`](../02-container-view.md)). Decisions made early constrain everything downstream. Without a record, future contributors will:
- Re‑litigate settled questions.
- Lose the rationale and mistakenly revert good decisions when the original constraint disappears.
- Be unable to tell "we considered X and rejected it" from "we never thought of X".

## Decision
We record every significant architectural decision as an ADR in `docs/01-architecture/adr/` using the Michael Nygard format (Status, Context, Decision, Consequences). ADRs are append‑only; superseded ones are kept with a status update.

A decision is "significant" if at least one of these is true:
- It affects more than one container.
- It changes a quality attribute target.
- It introduces or removes a runtime dependency.
- It changes a security boundary.
- It would be hard to reverse later.

The proposal‑to‑ADR pipeline is:
1. Open question identified → `proposal/P-NNN-…md` with at least 2 options and a recommendation.
2. Discussion → option selected.
3. Recommended option promoted to an ADR; proposal links to the ADR.

## Consequences
- **Positive**: institutional memory; faster onboarding; cheaper re‑evaluation of single decisions; concrete artefacts to disagree with.
- **Positive**: forces the author to articulate alternatives, not just the chosen path.
- **Cost**: every significant decision now has a paperwork tax (~30–60 minutes per ADR).
- **Risk**: ADRs go stale if not maintained; mitigation is to review the ADR index in every iteration's exit‑criteria check.

## Related
- *Documenting Software Architectures*, Clements et al., 2010 (SEI).
- Nygard, "Documenting Architecture Decisions", 2011.
