# Rule: Architect owns governance; developers implement

**Always-loaded protocol rule.**

## The rule

When assigning ownership in any artifact (governance docs, ADRs, schema-authoring rules, risk/assumption registers, RACI tables, validation plans, contract-promotion policies, threat models, security architecture):

| Concern | Owner |
|---|---|
| Governance / rules / "what's allowed" | **Architect** |
| Domain content (what fields, what enum values, business meaning) | **Domain experts** |
| Implementation (writing the JSON Schema, seeding the DB, building the worker) | **Developers** |

Default to **architect** for any architecture-level decision. Do NOT assign architecture-level governance to developers (TLs, senior engineers, lead developers) even if they have technical depth in the area.

## Why

Technical depth ≠ ownership. A developer may know the schema registry deeply because they implement it; that doesn't make them the governance owner. Governance authority is the architect's responsibility. Diffusing it produces inconsistent decisions across components.

## Specifics

- "Schema authoring governance" → architect (NOT a developer who happens to author schemas)
- "Contract promotion policy" → architect
- "Architecture decision document" → architect
- "Threat model" → architect (with security input)
- "Database schema" → architect for governance + domain expert for content + developer for changesets
- "Test strategy document" → architect for principles + developer for implementation
- Sign-off slots in templates → architect signs off; developer implements

## Application

When generating templates, RACI tables, or ownership matrices, default Accountable / Approver to architect for architectural items. Surface for confirmation if the user assigns it to a TL or developer instead.

This rule combines with the `adr-from-decision` and `risk-register-update` skills' ownership defaults — both pre-fill architect as decision-maker and require explicit override.
