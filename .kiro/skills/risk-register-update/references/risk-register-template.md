# {{ENGAGEMENT}} — Risk Register

**Project:** {{ENGAGEMENT_NAME}}
**Author:** {{ARCHITECT}}
**Status:** {{vN}}, {{YYYY-MM-DD}}
**Format:** Confluence-paste-ready

> Every entry passes the **three-question test**: (a) what specifically breaks, (b) cited evidence, (c) named affected component. See [`.kiro/steering/rule-real-risks-not-padding.md`](../steering/rule-real-risks-not-padding.md).

---

| Risk ID | Description | Impact | Probability | Mitigation (before it happens) | Owner |
|---|---|---|---|---|---|
| **R-01** | **{{Short title}}** — {{specific failure mode + evidence citation}} | **{{CRITICAL/HIGH/MEDIUM/LOW}}** | **{{HIGH/MEDIUM/LOW}}** | <ul><li>{{mitigation 1}}</li><li>{{mitigation 2}}</li></ul> | {{Owner — default architect for arch-level risks}} |
| **R-02** | … | … | … | … | … |

---

## Severity rating reference

| Label | Meaning |
|---|---|
| **CRITICAL** | If this happens, the platform fails its core value proposition or a security incident occurs |
| **HIGH** | Significant rework, demo impact, or stakeholder confidence loss |
| **MEDIUM** | Manageable but requires deliberate response within current sprint |
| **LOW** | Background concern; track but do not actively work |

| Probability label | Meaning |
|---|---|
| **HIGH** | More likely to occur than not within the current planning window |
| **MEDIUM** | Plausible occurrence within the current planning window |
| **LOW** | Unlikely but consequence warrants tracking |

---

## How this register is maintained

- **Owner of register:** {{Architect}}
- **Update cadence:** End of each sprint, or when new evidence lands
- **Companion register:** [assumption-register.md](./assumption-register.md) — assumptions become risks if invalidated
- **Update flow:** Use the `/risk-register-update` skill — it enforces the three-question test
- **Closure criteria:** A risk is closed when its mitigation is fully implemented AND validated, OR when the risk no longer applies. Closed risks remain in the register with a strikethrough for audit traceability.

---

## What does NOT belong here

(per the real-risks-not-padding rule)

- Generic platform concerns (data sovereignty, container access, terminology drift) → operational considerations, not risks
- Speculative "could potentially happen in some configuration"
- Citations of prototype / PoC code as evidence the production architecture has the same flaw
- Stakeholder clarification questions → goes to [`open-questions.md`](./open-questions.md), not Risks
- Risks invented by AI subagents to look thorough

If you can't answer "what specifically breaks, what's the evidence, and what depends on this," it's not a risk. Send it to backlog.

---

*Seeded by the `project-setup` skill. Update via the `risk-register-update` skill.*
