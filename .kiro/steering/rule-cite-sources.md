# Rule: Cite sources for every claim

**Always-loaded protocol rule.**

## The rule

Every assertion, validation, recommendation, or check the agent produces MUST include a citation to its source within this repository. No unsourced claims.

Acceptable sources (in priority order):

1. **Steering files** — `.kiro/steering/*.md`
2. **Architecture docs** — `docs/architecture/` (ADRs, risk register, vision)
3. **Requirements** — `docs/requirements/requirements.csv` (by REQ-ID)
4. **Open questions** — `docs/architecture/open-questions.md`
5. **Contracts** — `contracts/` (OpenAPI, AsyncAPI, JSON Schema)
6. **Skills** — `.kiro/skills/<name>/SKILL.md`
7. **Code** — specific file + line range
8. **External docs** — URL with retrieval date (last resort)

## Citation format

Inline, parenthetical, pointing to the file:

```
The system requires tenant isolation at every layer (architecture-principles.md §P-4).
This contradicts REQ-023 (docs/requirements/requirements.csv).
Per the branching model (ADR-0003), feature branches require PR review.
```

For longer validations, use a "Sources" footer:

```
### Sources
- `.kiro/steering/rule-real-risks-not-padding.md` — three-question test
- `docs/architecture/adrs/ADR-0005.md` — schema registry decision
- `REQ-041` — tenant data must not leak across boundaries
```

## What this means in practice

- **Reviewing code:** cite the convention or principle being checked.
- **Flagging a risk:** cite the evidence per the three-question test.
- **Proposing architecture:** cite the principle or ADR that supports or conflicts.
- **Extracting requirements:** cite the source document and location within it.
- **Validating assumptions:** cite the evidence that validates or invalidates.
- **Answering questions:** cite where the answer lives in the repo, or state "no documented source — this is inference."

## When no source exists

If the agent cannot find a documented source for a claim:

1. State explicitly: "No documented source in this repository."
2. Recommend where the source should be created (steering file, ADR, open question, requirement).
3. Do NOT present the claim as established fact.

## Why

Unsourced claims from an LLM are indistinguishable from hallucination. Citations make every output auditable, traceable, and challengeable. The architect can verify any claim by following the citation. This builds trust and prevents drift between what the agent says and what the project actually decided.

## Anti-patterns

- "Best practice says…" without a file reference — whose best practice? Where is it written?
- Citing a steering file that doesn't actually contain the claimed rule.
- Citing "common knowledge" or "industry standard" — if it matters, it's in a steering file or ADR.
- Over-citing (every sentence) when a single footer suffices for a coherent section.
