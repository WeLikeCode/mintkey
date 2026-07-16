# Agent Budgets — Requirements

## Overview

Call-count/rate ceilings per agent×service permission grant. The proxy hard-fails with `budget_exceeded` before touching the upstream when the ceiling is hit. Counter lives in Postgres (atomic `UPDATE...RETURNING`), propagated via the existing change channel. Audit events fire at configurable consumption thresholds.

## References

- [P-011 Agent Budgets proposal](../../../docs/architecture/proposal/P-011-agent-budgets.md)
- [ADR-0016.4](../../../docs/architecture/01-architecture/adr/0016-round-2-corrections.md) — Closed Constraints schema
- [ADR-0006](../../../docs/architecture/01-architecture/adr/0006-token-format-and-binding.md) — Token format + proxy verification
- [ADR-0010](../../../docs/architecture/01-architecture/adr/0010-change-channel-postgres-listen-notify.md) — Change channel
- [S-SEC-3](../../../docs/architecture/01-architecture/03-quality-attributes.md) — Bounded blast radius
- [S-MT-3](../../../docs/architecture/01-architecture/03-quality-attributes.md) — Noisy-neighbor isolation
- [S-PERF-1](../../../docs/architecture/01-architecture/03-quality-attributes.md) — Proxy latency overhead

## Functional Requirements

### FR-1: Budget configuration on permission grants
Operators can set a `budget` constraint on any permission grant specifying:
- `ceiling` (integer, ≥ 1) — maximum calls allowed in a single period.
- `period` (enum: `hourly`, `daily`, `weekly`, `monthly`) — reset cadence.
- `alert_thresholds` (array of integers 1–100, default `[50, 80, 100]`) — percentage levels that trigger audit events.

Budget is optional; grants without it have unlimited calls (subject only to rate_limit if set).

### FR-2: Proxy circuit-breaking
When the budget ceiling is reached, the proxy MUST:
- Return HTTP 429 with error body `{"error": "budget_exceeded", "permission_id": "...", "retry_after": "<ISO 8601 period_end>"}`.
- NOT touch the upstream service.
- NOT decrement/increment the counter beyond the ceiling.

### FR-3: Atomic counter increment
Each successful proxied request increments the counter by exactly 1. The increment and ceiling check MUST be a single atomic database operation (no race window under concurrent requests).

### FR-4: Period rollover
When a new period starts:
- A new counter row is created (lazily on first request or eagerly via scheduled check).
- Previous period rows are retained read-only for audit and billing history.
- The agent regains its full budget without operator intervention.

### FR-5: Manual budget reset
Operators can reset the budget for a grant mid-period via a dedicated API endpoint. This creates a new counter row for the remainder of the current period with `used = 0`.

### FR-6: Budget configuration updates
Operators can update the ceiling or period for an existing grant. Changes:
- Take effect immediately for the current period (ceiling increase allows more calls; ceiling decrease may trigger immediate exhaustion if already over).
- Propagate to the proxy within ≤ 5 seconds via the change channel (S-OPS-1).

### FR-7: Audit events at thresholds
The system emits audit events when budget consumption crosses each configured threshold:
- `budget.threshold_reached` — at 50%, 80%, or custom levels.
- `budget.exceeded` — when a request is denied.
- `budget.config_updated` — when operator changes budget config.
- `budget.reset` — when budget is manually or automatically reset.

### FR-8: MCP budget visibility
Agents can discover their current budget status via `describe_service`:
- `budget.ceiling`, `budget.period`, `budget.used`, `budget.remaining`, `budget.period_end`.

This enables agents to self-throttle or request budget increases.

### FR-9: Admin API endpoints
- `GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget` — current budget status.
- `POST /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget/reset` — manual reset.
- Budget config is set/updated via the existing `POST`/`PATCH` on permission grants (in `constraints.budget`).

### FR-10: Change-channel propagation
Budget config changes fire a `budget.config_updated` event on the `mintkey:agent` channel. The proxy subscriber invalidates cached budget state for the affected grant.

## Non-Functional Requirements

### NFR-1: Latency impact
Budget check adds ≤ 2 ms p99 to the proxy hot path (within S-PERF-1's total ≤ 30 ms p99 budget). Single atomic Postgres query, same connection pool as the jti denylist.

### NFR-2: Accuracy
At < 100 RPS per proxy instance, the counter must be exact (no over-counting, no under-counting). No local caching that introduces drift.

### NFR-3: Tenant isolation
Budget counters carry `tenant_id` and are covered by RLS (same as all domain tables per ADR-0008). Counter for tenant A is invisible to tenant B.

### NFR-4: Cascade deletion
When a permission grant is deleted, its budget counter rows are cascade-deleted.

### NFR-5: Observability
- Prometheus gauge: `mintkey_budget_used{permission_id, agent_id, service_id, tenant_id}`.
- Prometheus counter: `mintkey_budget_denied_total{permission_id, agent_id, service_id, tenant_id}`.
- Grafana panel: budget consumption % per agent×service with threshold lines.

### NFR-6: Historical retention
Expired period counter rows are retained indefinitely (append-only, matching audit philosophy). Operators can query historical usage.

## Out of Scope

- Per-tenant aggregate budgets (total across all agents) — future enhancement.
- Cost-based budgets (dollar amount tracking) — future enhancement.
- Automatic budget increase/decrease based on usage patterns — future enhancement.
- Budget inheritance from service-level defaults — future enhancement.
- Budget alerts via external channels (email, Slack) — operators use Grafana alerting.
