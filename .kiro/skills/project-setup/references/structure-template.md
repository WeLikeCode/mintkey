# Structure — {{PROJECT_CODENAME}}

> Default-load steering file. Describes the top-level repo layout and ownership boundaries.
> Architect-owned. Do not restructure without updating this file.

## Top-level layout

```
{{PROJECT_CODENAME}}/
├── .kiro/
│   ├── steering/         # Governance rules (default / fileMatch / manual)
│   ├── skills/           # Agent skills
│   ├── hooks/            # Event-triggered automation
│   └── specs/            # Per-feature spec docs
│
├── docs/
│   └── architecture/     # ARCHITECT-OWNED — ADRs, registers, vision
│       ├── adrs/
│       ├── risk-register.md
│       ├── assumption-register.md
│       └── open-questions.md
│
├── contracts/            # API / event / schema contracts (contract-first)
│   ├── openapi/          {{#if HAS_OPENAPI}}# REST contracts{{/if}}
│   ├── asyncapi/         {{#if HAS_ASYNC}}# Event contracts{{/if}}
│   └── jsonschema/       # Reusable payload types
│
├── tests/
│   ├── contract/         # Tests against contracts/, not code
│   ├── acceptance/       # Behavioral tests citing ADR / spec IDs
│   └── unit/
│
└── team/{handle}/        # Per-person onboarding sign-offs and drafts
    └── drafts/           # ADR / steering drafts before architect promotes
```

## Ownership boundaries

| Path | Owner | Rule |
|---|---|---|
| `docs/architecture/` | Architect | ADD-only; no silent edits |
| `.kiro/steering/` | Architect | Changes via project-setup or explicit decision |
| `contracts/` | Architect (governance) + Domain experts (content) | Contract-first; no code without contract |
| `team/{handle}/` | Individual contributor | Personal workspace |

## Steering files active for this project

{{ACTIVE_STEERING_FILES}}
