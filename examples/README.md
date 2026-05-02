# Examples

> Full-fidelity reference engagements (anonymized). Examples **demonstrate** rather than **prescribe**.

## Why examples beat defaults

A default *prescribes*; an example *demonstrates*. New engagements that look at an example see "this is one team's solved instance" rather than "this is what you must do." The defaults stay slim and principle-led; the examples carry the war-stories.

This also de-risks template evolution — adding a new example never breaks existing engagements, while changing a default might.

## Each example contains

- `WHY.md` — explaining the engagement's constraints that produced these choices
- The populated `engagement.yml` (the wizard answers)
- The rendered steering set
- Selected ADRs that capture the load-bearing decisions
- A `LESSONS.md` with what the team would do differently

## Examples shipped

(Roadmap — populate by anonymizing real engagements.)

| Example | Domain | Why it's worth studying |
|---|---|---|
| `clinical-trials/` *(pending)* | Healthcare clinical trial data | eCRF schema-driven forms, study-site tenancy, regulatory audit trail |
| `iot-predictive/` *(pending)* | Industrial IoT predictive maintenance | Time-series ingestion, edge-to-cloud event flow, idempotency at scale |
| `fintech-kyc/` *(pending)* | KYC document pipeline | Append-only audit, regulator-facing API contracts, IdP integration patterns |

## How to use an example

1. Read its `WHY.md` first. Don't copy patterns whose forcing function doesn't apply to your engagement.
2. Diff its `engagement.yml` against yours. Identify what's similar, what's different.
3. Read its ADRs that match your area. Cite them in your own ADRs if relevant: "Per the {example-name} example ADR-0007, we adopt …"
4. Examples are **not maintained in lockstep with templates**. Treat as historical reference, not living code.

## How to contribute an example

1. Anonymize: strip client name, person names, system names that reveal the client. Use generic stand-ins.
2. Verify with the architect of record that the anonymization is sufficient before publishing.
3. Add `WHY.md` and `LESSONS.md` — these are what make it useful, not the steering files themselves.
4. Open a PR; the template maintainer reviews.

## Anti-patterns

- Treating an example as a default — examples are *one solution*, not *the solution*.
- Copying steering files from an example without reading WHY.md — patterns travel poorly without context.
- Editing examples to add new patterns — examples are frozen-in-time. New patterns go to template defaults or new examples.
