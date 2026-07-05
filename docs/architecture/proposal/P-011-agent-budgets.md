# P‑011: Agent Budgets — Call-count/rate ceilings per grant with proxy circuit-breaking

## Status
Proposed — 2026-06-27.

## Motivation

The existing `Constraints.rate_limit` (ADR-0016.4) shapes instantaneous throughput (`requests_per_second` + `burst`). It answers "how fast can the agent call?" but not "how many total calls can the agent make before it's cut off?"

Operators need **budgets** — hard ceilings on the total number of proxied requests per grant within a billing/quota period. When the ceiling is reached, the proxy must **hard-fail** (`budget_exceeded`) without touching the upstream. This extends [S-SEC-3](../01-architecture/03-quality-attributes.md) (bounded blast radius) and [S-MT-3](../01-architecture/03-quality-attributes.md) (noisy-neighbor isolation) from rate-shaping into absolute spend control.

Use cases:
1. Operator caps a demo agent at 100 calls/day to a paid API.
2. Operator sets a monthly ceiling of 10,000 calls for an agent on a metered SaaS.
3. Agent discovers its remaining budget via MCP and can self-throttle or ask the operator for more.

## Forces

- **S-PERF-1**: proxy p50 ≤ 10 ms. Counter check must add negligible latency.
- **Atomicity**: concurrent requests from the same agent must not double-count or race past the ceiling.
- **Propagation**: budget configuration changes (ceiling updated, budget reset) must reach the proxy within the [S-OPS-1](../01-architecture/03-quality-attributes.md) ≤ 5 s window.
- **Auditability**: operators must know when an agent is approaching or hits its ceiling.
- **Observability**: budget consumption should be visible in Grafana dashboards.
- **Simplicity**: the counter must survive Postgres restarts without loss; no additional infrastructure.

## Options

### Option A — Counter column in `permission_grants` (in-place JSONB update)

Add `budget_used INTEGER DEFAULT 0` and `budget_config JSONB` columns directly to `permission_grants`. Proxy does `UPDATE permission_grants SET budget_used = budget_used + 1 WHERE id = $1 AND budget_used < budget_ceiling RETURNING budget_used`.

**Pros**: No new table. Simple schema.
**Cons**: Hot-row contention on high-throughput grants. JSONB partial update is slower than integer increment. Mixes config (ceiling) with state (counter) in one row.

### Option B — Separate `budget_counters` table (recommended)

A dedicated table:
```sql
CREATE TABLE budget_counters (
  permission_id  UUID NOT NULL REFERENCES permission_grants(id) ON DELETE CASCADE,
  period_start   TIMESTAMPTZ NOT NULL,
  period_end     TIMESTAMPTZ NOT NULL,
  ceiling        INTEGER NOT NULL,
  used           INTEGER NOT NULL DEFAULT 0,
  tenant_id      UUID NOT NULL,
  PRIMARY KEY (permission_id, period_start)
);
```

Budget config lives in `permission_grants.constraints.budget` (ceiling, period type, reset schedule). The counter row is created at period start (lazily on first request or eagerly by a cron). Proxy increments atomically:

```sql
UPDATE budget_counters
SET used = used + 1
WHERE permission_id = $1
  AND now() BETWEEN period_start AND period_end
  AND used < ceiling
RETURNING used, ceiling;
```

If 0 rows returned → budget exhausted → proxy returns `429 budget_exceeded`.

**Pros**: Separation of config (grants.constraints.budget) and state (counter row). Natural partitioning by period. Atomic increment with ceiling check in one query. Historical periods are retained for audit/billing. Clean cascade on grant deletion.
**Cons**: New table + new Liquibase changeset. Proxy needs a DB connection (it already has one for the jti denylist per ADR-0016).

### Option C — Redis counter with Lua script

Atomic `INCR` + `EXPIRE` in Redis. Counter key: `budget:{permission_id}:{period}`.

**Pros**: Fastest possible increment. Sub-ms latency.
**Cons**: Adds Redis as infrastructure (violates the "no extra container" principle per ADR-0010). Counter lost on Redis restart unless persisted. Dual-write consistency between Postgres (config) and Redis (counter).

## Recommendation

**Option B** — separate `budget_counters` table.

Rationale:
1. The proxy already connects to Postgres for the `jti` denylist (ADR-0016). Adding one more atomic UPDATE per request to the same connection adds < 1 ms at our scale (< 100 RPS per instance, per S-PERF-1 scope).
2. No extra infrastructure (stays within ADR-0010 principle).
3. Period-based rows give us natural audit/billing history.
4. `UPDATE...RETURNING` with `used < ceiling` is a single atomic operation — no race conditions.

## Design sketch (if Option B accepted)

### Budget configuration — extends `Constraints`

```yaml
Constraints:
  properties:
    # ... existing rate_limit, time_window, etc.
    budget:
      type: object
      additionalProperties: false
      properties:
        ceiling:
          type: integer
          minimum: 1
          description: Maximum calls allowed within a single period.
        period:
          type: string
          enum: [hourly, daily, weekly, monthly]
          description: Reset cadence.
        alert_thresholds:
          type: array
          items:
            type: integer
            minimum: 1
            maximum: 100
          default: [50, 80, 100]
          description: Percentage thresholds that trigger audit events.
      required: [ceiling, period]
```

### Counter lifecycle

1. **Creation**: On first proxied request for a grant with a budget constraint, if no counter row exists for the current period, create one (upsert).
2. **Increment**: Atomic `UPDATE...RETURNING` with ceiling guard.
3. **Period rollover**: New period → new row. Old rows retained (read-only after expiry).
4. **Deletion**: `ON DELETE CASCADE` from permission_grants.

### Proxy enforcement flow (extends the 10-step verification)

After step 9 (JWT valid, not revoked):
```
10. If grant has budget constraint:
    a. Atomic increment: UPDATE budget_counters SET used=used+1
       WHERE permission_id=$1 AND now() BETWEEN period_start AND period_end
       AND used < ceiling RETURNING used, ceiling
    b. If 0 rows: return 429 {"error": "budget_exceeded", "permission_id": "...", "retry_after": <period_end>}
    c. If used crosses an alert_threshold: emit audit event asynchronously (non-blocking)
11. Proceed to credential lookup.
```

### Change-channel propagation

When an operator updates a grant's budget config (ceiling change, period change), the Admin API:
1. Updates `permission_grants.constraints.budget`.
2. Upserts `budget_counters` for the current period with the new ceiling.
3. Fires `NOTIFY mintkey:agent, '{"event_type":"budget.config_updated", "permission_id":"...", "tenant_id":"..."}'`.

The proxy subscriber invalidates its cached budget config for that grant.

### Audit events

| Event type | Trigger | Payload |
|---|---|---|
| `budget.threshold_reached` | Counter crosses 50%, 80%, or 100% of ceiling | `{permission_id, used, ceiling, threshold_pct, period_start, period_end}` |
| `budget.exceeded` | Proxy denies a request due to exhausted budget | `{permission_id, used, ceiling, period_start, period_end, denied_jti}` |
| `budget.config_updated` | Operator changes ceiling or period | `{permission_id, old_ceiling, new_ceiling, old_period, new_period}` |
| `budget.reset` | New period starts (counter rolls over) | `{permission_id, previous_used, previous_ceiling, new_period_start}` |

### MCP surface — `describe_service` extension

The `your_constraints` object in `describe_service` output gains:
```yaml
budget:
  ceiling: 1000
  period: "daily"
  used: 847
  remaining: 153
  period_end: "2026-06-28T00:00:00Z"
  alert_thresholds: [50, 80, 100]
```

This lets agents self-throttle or request budget increases.

### Observability

- **Metric**: `mintkey.budget.used{permission_id, agent_id, service_id, tenant_id}` — gauge, updated on each increment.
- **Metric**: `mintkey.budget.denied_total{permission_id, agent_id, service_id, tenant_id}` — counter of denied requests.
- **Grafana panel**: Budget consumption % per agent×service, with threshold lines.
- **Alert rule**: Budget > 90% → PagerDuty/Slack notification (operator-configurable).

## Open questions

- **OQ-B1**: Should budget enforcement happen in the proxy plugin (Go, per-request) or in the Credential Broker (Python, at token issuance)? Proxy-side is simpler (single check point, no pre-allocated "token budget") but requires the proxy to maintain a Postgres connection. The proxy already has one (jti denylist). **Recommendation: proxy-side.**
- **OQ-B2**: Should the proxy cache the current counter locally and batch-flush to Postgres? This would reduce DB round-trips but introduce a window where concurrent proxy instances can overshoot the ceiling. **Recommendation: No. At < 100 RPS per instance, one atomic query per request is acceptable and guarantees exact enforcement.**
- **OQ-B3**: Manual budget reset by operator — should this be a PATCH on the grant or a dedicated endpoint (`POST /v1/.../permissions/{id}/budget/reset`)? **Recommendation: dedicated endpoint for clarity.**

## Implications if accepted

- New Liquibase changeset for `budget_counters` table.
- `Constraints` schema gains `budget` property (contract version bump).
- Proxy plugin gains step 10 (budget check).
- Four new audit event types.
- `describe_service` MCP output gains budget fields.
- Grafana dashboard gains budget panel.
- ADR-0029 formalizes this decision.

## Related

- [ADR-0016.4](../01-architecture/adr/0016-round-2-corrections.md) — Closed `Constraints` schema (existing rate_limit).
- [ADR-0006](../01-architecture/adr/0006-token-format-and-binding.md) — Token format and proxy verification flow.
- [ADR-0010](../01-architecture/adr/0010-change-channel-postgres-listen-notify.md) — Change channel transport.
- [S-SEC-3](../01-architecture/03-quality-attributes.md) — Bounded blast radius.
- [S-MT-3](../01-architecture/03-quality-attributes.md) — Noisy-neighbor isolation.
- [S-PERF-1](../01-architecture/03-quality-attributes.md) — Proxy latency budget.
