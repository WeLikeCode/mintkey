# Archetype scaffolds — what to build, and in what order

> The README lists 4 archetypes (single-app, polyglot-monorepo, microservices, modular-monolith). Building all 4 well takes weeks. This file recommends a **pragmatic scaffolding order** based on which archetypes are most-used and which most benefit from a worked skeleton.

## Recommendation: build only 2 scaffolds first

| Order | Archetype | Why |
|---|---|---|
| **1 (priority)** | `polyglot-monorepo/` | The most expensive archetype to set up from scratch. Most enterprise-style engagements (multi-language, contract-shared, multiple deployable units) land here. A worked skeleton saves the most architect-time. |
| **2** | `single-app/` | The simplest. Worth shipping for Discovery / PoC engagements that don't need monorepo overhead. Building it forces the template to handle the no-monorepo case cleanly. |
| **defer** | `microservices/` | Multi-repo coordination is engagement-specific (which org owns the contracts repo, how versioning works across repos). Hard to scaffold generically. |
| **defer** | `modular-monolith/` | Module-boundary enforcement depends heavily on the chosen language ecosystem (Java with ArchUnit, TS with `dependency-cruiser`, Python with `import-linter`). Not portable enough to ship as a generic scaffold. |

## What "scaffold" means here

Each scaffold is an `archetypes/<name>/` directory containing:

- **`WHEN-TO-USE.md`** — forcing functions, trade-offs, "pick this if…"
- **`Makefile`** — bootstrap / doctor / dev / test:smoke targets matching the layout
- **`README.md.template`** — top-level README the engagement will customize
- **`structure.template.md`** — populated `.kiro/steering/structure.md` matching this layout
- **A populated tree** — empty stub directories with `.gitkeep` and a per-directory `README.md` explaining purpose
- **A CI workflow stub** for one major provider (default GitHub Actions; engagements port to GitLab / Azure DevOps)

Critically, scaffolds **do NOT** prescribe:
- Specific frameworks (no NestJS, no FastAPI, no Spring)
- Specific persistence (no Postgres, no MongoDB)
- Specific event bus (no Kafka, no NATS)

Those come from the wizard, not the scaffold.

## Concrete proposal for `polyglot-monorepo/`

```
polyglot-monorepo/
├── WHEN-TO-USE.md
├── Makefile
├── README.md.template
├── structure.template.md
├── .gitignore
├── apps/
│   ├── README.md           # "One deployable per subdir. App boundary rules."
│   └── _example-app/.gitkeep
├── workers/
│   ├── README.md           # "Async processing units. Idempotent. Cite contracts."
│   └── _example-worker/.gitkeep
├── packages/
│   ├── README.md           # "Shared libraries. No app-specific code. No DB access."
│   └── _example-package/.gitkeep
├── contracts/              # already in template — reused as-is
├── infra/
│   ├── README.md
│   ├── database/.gitkeep   # per-env migration changesets (engagement chooses tool)
│   └── deploy/.gitkeep
├── tests/                  # already in template — reused as-is
└── ci/
    ├── README.md
    └── github-actions.yml.template
```

Total: ~15 files. Realistic to ship in a day's focused work. Each `README.md` is ≤ 100 lines.

## Concrete proposal for `single-app/`

```
single-app/
├── WHEN-TO-USE.md
├── Makefile
├── README.md.template
├── structure.template.md
├── .gitignore
├── src/
│   └── README.md           # "Single app. No monorepo overhead. Module boundaries via lint."
├── contracts/              # reused
├── infra/
│   └── database/.gitkeep
├── tests/                  # reused
└── ci/
    └── github-actions.yml.template
```

~8 files. Half a day's work.

## What the template ships TODAY

Only [`archetypes/README.md`](README.md). The two recommended scaffolds (polyglot-monorepo + single-app) are the next concrete deliverable.

## Why not ship all 4 now

- **Microservices archetype:** the contract-sharing-across-repos question is the hardest part, and the answer is engagement-specific. Shipping a generic scaffold would be misleading. Better: in `examples/`, anonymize a real microservices engagement once we've done one.
- **Modular-monolith:** the module-boundary tooling differs per ecosystem. Shipping with one ecosystem's tools (e.g., Python `import-linter`) prescribes Python; shipping with all 4 ecosystems is over-investment for an archetype that's less common than monorepo.

## What an engagement does today (until scaffolds ship)

1. Architect runs the wizard.
2. Wizard writes the always-loaded steering files based on the answers.
3. Architect manually creates the directory structure based on the rendered `structure.md` (the template's structure.md.template gives them an outline).
4. Architect adopts patterns from worked example engagements in `examples/` (when populated) selectively.

This is fine for v0.1. The scaffolds are the v0.3 milestone in [CHANGELOG.md](../CHANGELOG.md).

## When to revisit

Build the scaffolds:

- After 2-3 real engagements have used the template — the patterns that recur become the scaffold defaults
- Before the template is open-sourced more broadly inside the Enterprise Business Architect Practice — scaffolds make adoption faster

Until then, the wizard + protocol rules + skills catalog do most of the heavy lifting. The scaffolds are mostly directory creation, which is cheap to defer.
