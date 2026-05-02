# Changelog

All notable changes to this template are recorded here. Engagements track which template version they bootstrapped from in `.kiro/setup-state.json` (`template_version` field).

## [0.1.0] — 2026-05-08

Initial release. Template skeleton generalized for cross-engagement reuse.

### Includes

- **Bootstrap wizard** with 16 mandatory + 9 optional questions and explicit refusal conditions ([bootstrap/questionnaire.md](bootstrap/questionnaire.md))
- **Steering loading protocol** with the three real Kiro inclusion modes (default-load / `fileMatch` / `manual`), frontmatter spec, anti-pollution rules, and audit tool ([.kiro/steering/STEERING-PROTOCOL.md](.kiro/steering/STEERING-PROTOCOL.md))
- **8-skill catalog** including `architecture-advisor`, `think-tiger`, `adversarial-review`, `spec-first-check`, `adr-from-decision`, `risk-register-update`, `assumption-validate`, `decision-log-append` ([.kiro/steering/skills-catalog.md](.kiro/steering/skills-catalog.md))
- **5 default-loaded protocol rules** (steering files, no frontmatter): architect-doc-ownership, real-risks-not-padding, role-ownership-architect-vs-developer, smallest-first-cut, steering-load-discipline ([.kiro/steering/](.kiro/steering/))
- **Reference templates** bundled with the skills that consume them: ADR template (`.kiro/skills/adr-from-decision/references/`), risk register template (`.kiro/skills/risk-register-update/references/`), assumption register template (`.kiro/skills/assumption-validate/references/`)
- **5 onboarding tracks** for architect / backend / frontend / data-ml / lead ([docs/onboarding/](docs/onboarding/))
- **Contracts directory** with SDD authoring guide ([contracts/README.md](contracts/README.md))
- **Architect-owned `docs/architecture/`** with banner enforcement ([docs/architecture/README.md](docs/architecture/README.md))
- **4 archetype layouts** (single-app, polyglot-monorepo, microservices, modular-monolith) ([archetypes/README.md](archetypes/README.md))
- **Tooling spec** for audit, vibe-check, spec-trace, contract-lint, doctor, template-diff ([tools/README.md](tools/README.md))

### Designed against (anti-patterns this version actively prevents)

- Loading all steering files into every agent context
- Padding risk registers with speculative entries
- Editing `docs/architecture/` directly (architect-owned)
- Vibe coding (no spec, no code)
- Treating prototype / PoC code as production-architecture truth
- Architect work being assigned to TLs / developers
- ADRs that are decoration (zero referencing tests / code)

## [0.2.0] — 2026-05-08

### Added

- **Wizard script** ([bootstrap/setup-wizard.sh](bootstrap/setup-wizard.sh) + [bootstrap/lib/wizard-helpers.sh](bootstrap/lib/wizard-helpers.sh)) — interactive bash that asks the 25 questions, validates with refusal conditions (kebab-case codename, ≥120-char business goal with platitude denylist, architect email required, three-real-risks structured input), detects conflicts, and renders all engagement files including ADR-0001-bootstrap recording the choices.
- **Generic steering templates** ([bootstrap/templates/](bootstrap/templates/)) for `product`, `structure`, `architecture-principles`, `tech`, `repo-governance` — all with `[REQUIRES-UPDATE]` markers the architect fills in. Architecture-principles ships 8 generic baseline principles (P-1 through P-8) plus slots for engagement-specific additions.
- **Archetype recommendation** ([archetypes/RECOMMENDATIONS.md](archetypes/RECOMMENDATIONS.md)) — pragmatic guidance on which 2 of the 4 archetypes to scaffold first (polyglot-monorepo + single-app), with concrete proposals for each.

### Roadmap

- 0.3: Build the polyglot-monorepo + single-app archetype scaffolds per RECOMMENDATIONS.md
- 0.4: Tooling scripts (kiro-steering-audit, vibe-check, spec-trace, contract-lint, doctor)
- 0.5: CI templates for major providers (GitLab, GitHub Actions, Azure DevOps)
- 0.6: 2-3 worked example engagements (clinical-trials, iot-predictive, fintech-kyc) so engagements have anonymized references to draw on

### Known limitations

- Wizard is interactive bash — no GUI. Adequate for a CLI-first architect; might want a minimal web UI later.
- Archetype skeletons still not populated (only RECOMMENDATIONS.md describes what to build).
- Tooling (audit, spec-trace, vibe-check, doctor) specified in `tools/README.md` but scripts not implemented.
- Generic steering templates use `[REQUIRES-UPDATE]` markers — the architect must fill in engagement-specific content. The wizard does NOT auto-write rich content; it scaffolds, the architect refines.

### Anti-patterns explicitly NOT addressed (out of scope)

- Specific cloud provider patterns (AWS / GCP / Azure / on-prem) — engagement-specific
- Specific frameworks (NestJS / FastAPI / Spring) — wizard records the choice; template doesn't prescribe
- CI/CD pipeline implementations beyond skeletons — engagement-specific
- Customer-facing public docs — out of scope, this is internal scaffolding

---

*Template ownership: Enterprise Business Architect Practice. Maintained by {{architect handle}}.*
