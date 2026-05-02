# {{ENGAGEMENT}} — Assumption Register

**Project:** {{ENGAGEMENT_NAME}}
**Author:** {{ARCHITECT}}
**Status:** {{vN}}, {{YYYY-MM-DD}}
**Format:** Confluence-paste-ready

Assumptions are things currently believed true that drive specific architectural choices. If invalidated, named components must change. **Validated assumptions remain in the register for traceability** — they show what was uncertain at one point and how it was resolved.

---

| Assumption ID | Description | Confidence | Status | Validation plan / Resolution | Owner |
|---|---|---|---|---|---|
| **A-01** | **{{Short title}}** — {{specific claim + what it drives}} | {{HIGH/MEDIUM/LOW}} | Open / 🟡 Partially validated / ✅ VALIDATED / ⚠️ Invalidated | {{validation plan with evidence citation when changing status}} | {{Owner}} |

---

## Confidence reference

| Confidence | Meaning |
|---|---|
| **HIGH** | Strong basis — confirmed in workshop, documented decision, or technical proof |
| **MEDIUM** | Reasonable basis — supported by partial evidence, similar precedent, or expert judgement |
| **LOW** | Provisional — best-guess assumption pending validation |

## Status reference

| Status | Meaning |
|---|---|
| ✅ **VALIDATED** | Assumption confirmed; promoted to constraint or otherwise no longer at risk |
| 🟡 **Partially validated** | One part of the assumption confirmed; remainder pending defined validation step |
| **Open** | Assumption stands as a working belief; validation plan defined |
| ⚠️ **Invalidated** | Assumption disproven; risk register updated and architectural impact assessed |

---

## Relationship to the risk register

Assumptions and risks are linked: if an assumption is invalidated, one or more risks may activate.

| Assumption | If invalidated, activates Risk |
|---|---|
| {{A-NN}} | {{R-MM — what specifically escalates}} |

---

## How this register is maintained

- **Owner:** {{Architect}}
- **Update cadence:** End of each sprint, when an open question resolves, or when an assumption is invalidated by evidence
- **Companion register:** [risk-register.md](./risk-register.md)
- **Update flow:** Use the `/assumption-validate` skill — it forces evidence citation
- **Validation flow:** When validated, mark `✅ VALIDATED` and record the resolution event. When invalidated, mark `⚠️ Invalidated`, update affected risks, and record the architectural impact.

---

*Seeded by the `project-setup` skill. Update via the `assumption-validate` skill.*
