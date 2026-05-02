# Archetypes

> Repo layouts the bootstrap wizard offers. Pick one at Q9 + Q11 + Q16 time.

## Available archetypes

| Archetype | Best for | Repo layout |
|---|---|---|
| `single-app/` | Single service, one team, single language | `src/`, `tests/`, `contracts/`, no monorepo tooling |
| `polyglot-monorepo/` | Multi-language, shared contracts, multiple deployable units | `apps/`, `packages/`, `workers/`, `infra/`, monorepo orchestrator (Nx / Turbo / Bazel) |
| `microservices/` | Multi-team, service-per-repo, contract registry | One repo per service + a separate `contracts/` repo |
| `modular-monolith/` | Single deployable, internal modular boundaries enforced | `src/<module>/`, lint-rules enforce module-imports |

## Each archetype contains

- A skeleton `structure.md` matching that layout
- Default `Makefile` targets (`bootstrap`, `doctor`, `dev`, `test:smoke`)
- CI workflow stubs that match the layout
- A `WHEN-TO-USE.md` explaining the trade-offs

## Picking an archetype

The wizard recommends an archetype based on Q9 (languages), Q11 (persistence primaries), and Q16 (steering depth):

- 1 language + 1 deployable + Skeleton phase → `single-app/`
- 2+ languages + multiple deployables → `polyglot-monorepo/`
- 1 language + multiple modular boundaries → `modular-monolith/`
- Multi-team + separate-repo culture → `microservices/`

The architect can override. The choice is recorded as ADR-0001-bootstrap.

## What archetypes do NOT include

- Specific framework choices (NestJS vs FastAPI vs Spring)
- Specific persistence (Postgres vs MySQL vs Mongo)
- Specific event bus (NATS vs Kafka vs RabbitMQ)
- Specific deployment target (K8s vs ECS vs serverless)

These are wizard answers, not archetype properties. Archetypes are pure layout.

## Adding a new archetype

1. Identify the gap (existing 4 should cover ~85% of greenfield engagements).
2. Mirror the directory structure of an existing archetype.
3. Write `WHEN-TO-USE.md` with a clear forcing function.
4. Update wizard logic to recommend it.
5. PR for template-maintainer review.
