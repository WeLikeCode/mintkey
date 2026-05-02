# {{ENGAGEMENT_NAME}} — Structure

> Top-level repo layout. ≤ 1 page. If you need to explain *why* a layout choice was made, that's an ADR — link to it.

## Layout

[REQUIRES-UPDATE: ASCII tree of the top-level directories. Driven by archetype choice + Q9/Q11. The bootstrap wizard recommends a starting layout but the architect customizes.]

```
{{ENGAGEMENT_NAME}}/
├── apps/                # [REQUIRES-UPDATE: deployable apps; remove if archetype = single-app]
├── workers/             # [REQUIRES-UPDATE: data-processing workers; remove if no async pipeline]
├── packages/            # [REQUIRES-UPDATE: shared libraries; remove if archetype = single-app]
├── contracts/           # API contracts — source of truth
├── infra/               # Deployment / CI / IaC
├── docs/                # Architecture canon + onboarding
├── tests/               # contract / acceptance / unit
└── tools/               # audit, lint, wizard, spec-trace
```

## Boundary rules

[REQUIRES-UPDATE: 3-7 invariants. Examples:]

1. **Contracts are the source of truth.** No code in `contracts/`; no inline schemas in code.
2. **One deployable per `apps/<name>/`.** Mixing two services in one app dir is a smell.
3. **Workers don't share code with apps.** They share contracts. Cross-import is forbidden.
4. **Migrations live in `infra/database/`.** No ORM-managed schema.
5. **Per-environment config lives in `infra/<env>/`.** No code-level environment switching.

## Boundary enforcement

[REQUIRES-UPDATE: how each rule above is enforced — lint config, CI check, GRANT matrix, etc.]

## Where things live (cheat sheet)

| What | Where |
|---|---|
| API contracts | `contracts/openapi/` |
| Event contracts | `contracts/asyncapi/` |
| Reusable payload types | `contracts/jsonschema/` |
| Architecture decisions | `docs/architecture/adrs/` |
| Requirements tracker | `docs/requirements/requirements.csv` |
| BA source artifacts | `docs/requirements/sources/` |
| Conventions | `.kiro/steering/` |
| Skills | `.kiro/skills/` |
| ADRs in draft | `team/{handle}/drafts/` |

## What does NOT belong here

- Implementation specifics (per-component README files)
- Domain glossary (that's `product.md`)
- Code-style rules (those are language-conventions files)

## Cross-references

- ADR-0001 records archetype choice
- [`.kiro/steering/STEERING-PROTOCOL.md`](./STEERING-PROTOCOL.md) for steering layout rules
- [`docs/onboarding/README.md`](../../docs/onboarding/README.md) for onboarding paths
