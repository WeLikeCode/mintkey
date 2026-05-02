# ADR‑0015: Liquibase is the source of truth for the database schema; SQLAlchemy mirrors it

## Status
Accepted — 2026-05-10. Amends/clarifies [ADR‑0005](0005-admin-tech-stack.md) and [ADR‑0012](0012-python-stack-pin.md).

## Context
ADR‑0005 chose Liquibase for schema migrations. ADR‑0012 chose SQLAlchemy 2.x async with `Mapped` types for the Python ORM. Both define the schema; without an explicit policy, drift is silent and undetectable until runtime.

**The user has stated, and this ADR formalizes**: schema changes happen in Liquibase only. SQLAlchemy is a mirror, not an authority.

## Decision

### Source of truth
**Liquibase YAML changelogs are the source of truth for the database schema.** Any schema change — new tables, new columns, type changes, RLS policies, indexes, constraints, sequences, Postgres extensions, role grants — is defined in Liquibase and applied via the migration runner.

**SQLAlchemy `Mapped` types in `mintkey-models` are a mirror of the Liquibase‑applied DB.** They never define a column that doesn't exist in Liquibase.

### Workflow for a schema change
1. Author the Liquibase changelog under `admin-api/db/changelog/<vNN>-<description>.yaml`.
2. Apply against a local Postgres: `liquibase update`.
3. Regenerate (or hand‑mirror) the SQLAlchemy `Mapped` declarations in `mintkey-models/src/mintkey_models/sql.py`.
4. Update Pydantic models in `mintkey-models/src/mintkey_models/schemas.py` if the wire surface changes.
5. Update the canonical OpenAPI in `docs/contracts/rest/openapi.yaml` if the wire surface changes (per [ADR‑0014.3](0014-iter-1-2-corrections.md)).
6. Commit changelog + SQLAlchemy + Pydantic + OpenAPI together.

### CI enforcement
A CI step:
1. Spins up a fresh Postgres container.
2. Runs `liquibase update` from the changelog.
3. Generates a SQLAlchemy declaration set from the introspected schema using `sqlacodegen`.
4. Compares the generated set against the checked‑in `mintkey-models/src/mintkey_models/sql.py` after canonical formatting (so whitespace/order doesn't trip the diff).
5. Fails the build on any difference.

This guarantees Liquibase and SQLAlchemy always agree.

### What lives in Liquibase
- Tables.
- Columns (types, defaults, NOT NULL, references).
- Primary, foreign, unique, and check constraints.
- Indexes.
- **RLS policies** (per [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md) and [ADR‑0014.8](0014-iter-1-2-corrections.md)).
- Postgres roles and grants (`mintkey_app`, `mintkey_migrate`, `mintkey_subscriber`).
- Postgres extensions (`pgcrypto`, `pg_trgm`, etc., as needed).
- Sequences (where ULIDs aren't used).
- Triggers, if any. (None in v1 per [ADR‑0014.5](0014-iter-1-2-corrections.md), but if added later, in Liquibase.)

### What does NOT live in Liquibase
- DML data seeds (the seed job, not the migration runner, owns these).
- Application‑level constants (those live in code).
- Test fixtures (the test layer loads these).

### Generation tool
Default: **`sqlacodegen` v3+** with `--generator declarative`.
Hand‑mirroring is acceptable so long as the CI diff passes — the contract is "checked‑in SQLAlchemy must match the introspected schema", not "you must use the tool".

### Same‑migration RLS rule
A new domain table **must** be created with its RLS policy in the same Liquibase changeset (not a follow‑up changeset). The RLS architecture test ([ADR‑0014.8](0014-iter-1-2-corrections.md)) catches this if it's missed, but the rule should be enforced at PR review and via an `architectural-test:rls-same-changeset` lint.

### Roles introduced
- `mintkey_migrate` — superuser equivalent for Liquibase only. Bypasses RLS. Used by the Liquibase one‑shot job.
- `mintkey_app` — application role. RLS applies. Used by Admin REST API, MCP Server, Vault Adapter, Broker.
- `mintkey_subscriber` — read‑only role with `LISTEN` privileges on the change channels. Used by the proxy plugin and Kong‑syncer.

## Consequences

### Positive
- One source of truth for schema. Drift is impossible if CI passes.
- SQLAlchemy stays a query and mapping layer; it doesn't carry migration concerns.
- Liquibase's history‑based migrations + rollback capability are fully utilized.
- Schema state is reviewable from version control alone.
- Operators can reason about schema state from Liquibase changelogs without needing to read Python code.
- KIRO.md will document this workflow so Kiro doesn't try to add columns in SQLAlchemy.

### Costs
- A schema change requires updating two‑or‑more files (changelog + SQLAlchemy + maybe Pydantic + maybe OpenAPI). The `sqlacodegen` step + CI diff reduces this to "edit the changelog, regenerate the rest".
- New developers must learn Liquibase YAML syntax — adequately documented but a learning curve.

### Risks
- `sqlacodegen` output may need manual cleanup; the CI diff catches any divergence.
- A misordered Liquibase changeset can break a downstream environment. Mitigated by Liquibase's changeset hashes and standard practices (no rewriting committed changesets; use `<rollback>` blocks).

## Implications
- ADR‑0012's "Type‑safe queries: SQLAlchemy 2.x async" remains; this ADR clarifies SQLAlchemy is downstream, not upstream, of the schema.
- The `mintkey-models` package convention now includes a generation step.
- Iteration 4's OpenAPI canonicality story (per [ADR‑0014.3](0014-iter-1-2-corrections.md)) is parallel: same idea, different artifact.
- KIRO.md (when written) explicitly forbids editing SQLAlchemy `Mapped` declarations to add columns; the Kiro workflow for "add a field to Service" is "edit the Liquibase changelog → regenerate models".
- The seed job uses `mintkey_app`‑equivalent grants for inserts; not migration role.

## Open follow‑ups
- Whether to allow `alembic`‑style autogeneration **from** SQLAlchemy as a development convenience for prototyping (not for production migrations). *Lean: no — adds a third tool and confuses authority.*
- Specific `sqlacodegen` version pin and any forks/patches we depend on.
- Schema lint rules (`varchar` always with length; foreign keys always have `ON DELETE` policy; etc.) — small ADR or KIRO.md note.

## Related
- [ADR‑0005 admin tech stack](0005-admin-tech-stack.md) — chose Liquibase + SQLAlchemy.
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — RLS policies live in Liquibase.
- [ADR‑0012 Python stack pin](0012-python-stack-pin.md) — SQLAlchemy as ORM.
- [ADR‑0014 iter 1+2 corrections](0014-iter-1-2-corrections.md) — OpenAPI canonical YAML; RLS arch test.
