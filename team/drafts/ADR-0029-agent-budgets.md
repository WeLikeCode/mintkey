# ADR-0029: Agent Budgets — Call-count ceilings per grant with proxy circuit-breaking

## Status
Accepted — 2026-06-27

## Context

The existing `Constraints.rate_limit` (ADR-0016.4) shapes instantaneous throughput but does not answer "how many total calls can the agent make before it's cut off?" Operators need hard ceilings on the total number of proxied requests per grant within a quota period. When the ceiling is reached, the proxy must hard-fail without touching the upstream.

This extends S-SEC-3 (bounded blast radius) and S-MT-3 (noisy-neighbor isolation) from rate-shaping into absolute spend control.

## Decision

Adopt **Option B from P-011**: a separate `budget_counters` table with atomic `UPDATE...RETURNING` in Postgres.

Key decisions:
1. Budget configuration lives in `permission_grants.constraints.budget` (ceiling, period, alert_thresholds).
2. Counter state lives in a dedicated `budget_counters` table (composite PK: permission_id, period_start).
3. The proxy enforces budgets atomically via `UPDATE SET used=used+1 WHERE used < ceiling RETURNING used, ceiling`.
4. Period boundaries are UTC-aligned (hourly/daily/weekly/monthly).
5. Four new audit event types: `budget.threshold_reached`, `budget.exceeded`, `budget.config_updated`, `budget.reset`.
6. Budget changes propagate via existing `mintkey:agent` LISTEN/NOTIFY channel (ADR-0010).

## Consequences

- New Liquibase changeset `019-budget-counters.yaml` with RLS policy.
- `Constraints` schema gains `budget` property (contract version bump).
- Proxy plugin gains step 10 (budget check) after JWT verification.
- `describe_service` MCP output gains budget fields for agent self-awareness.
- Grafana dashboard gains budget consumption panel + alert rule.

## Forward-links

This ADR is referenced by and extends:
- [ADR-0006](../docs/architecture/01-architecture/adr/0006-token-format-and-binding.md) — adds budget check as step 10 in the proxy verification flow.
- [ADR-0010](../docs/architecture/01-architecture/adr/0010-change-channel-postgres-listen-notify.md) — reuses `mintkey:agent` channel for budget events.
- [ADR-0016](../docs/architecture/01-architecture/adr/0016-round-2-corrections.md) — extends `Constraints` closed schema with `budget` property.

## Related

- [P-011](docs/architecture/proposal/P-011-agent-budgets.md) — Original proposal.
- [ADR-0008](docs/architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md) — RLS on budget_counters.
- S-SEC-3 — Bounded blast radius quality attribute.
- S-MT-3 — Noisy-neighbor isolation quality attribute.

---

> **NOTE**: This is a DRAFT awaiting architect approval. Once accepted,
> it should be placed at `docs/architecture/01-architecture/adr/0029-agent-budgets.md`
> and forward-links added to ADR-0006, ADR-0010, and ADR-0016.
