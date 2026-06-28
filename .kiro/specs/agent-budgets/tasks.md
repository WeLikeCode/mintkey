# Agent Budgets — Tasks

## Milestone M-BUD-1: Schema & Contract Foundation

### T-BUD-1.1: Liquibase changeset for `budget_counters` table
- [x] Create `apps/admin-api/db/changelog/019-budget-counters.yaml` per design §1.
- [x] Table: `budget_counters(permission_id UUID, period_start TIMESTAMPTZ, period_end TIMESTAMPTZ, ceiling INTEGER, used INTEGER DEFAULT 0, tenant_id UUID)`.
- [x] PK: `(permission_id, period_start)`.
- [x] FK: `permission_id → permission_grants(id) ON DELETE CASCADE`, `tenant_id → tenants(id)`.
- [x] RLS: `tenant_isolation` policy matching existing pattern (design §1).
- [x] Index: `idx_budget_counters_active(permission_id, period_end DESC)`.
- [x] Verify: run Liquibase against test DB; `information_schema.columns` confirms schema; `pg_policies` confirms RLS.
- **Refs**: FR-3, FR-4, NFR-3, NFR-4, design §1.

### T-BUD-1.2: Extend `Constraints` schema in OpenAPI
- [x] Add `budget` property to `Constraints` schema in `docs/architecture/contracts/rest/openapi.yaml`.
- [x] Properties: `ceiling` (integer, min 1), `period` (enum: hourly/daily/weekly/monthly), `alert_thresholds` (array of int 1–100, default [50,80,100]).
- [x] Verify: `openapi-spec-validator` passes; Redocly lint passes.
- **Refs**: FR-1, design §2.

### T-BUD-1.3: Add budget audit event types to contracts
- [x] Add `budget.threshold_reached`, `budget.exceeded`, `budget.config_updated`, `budget.reset` to `AuditEventType` enum in OpenAPI.
- [x] Add `budget` to `target_type` enum in audit-event.schema.json.
- [x] Add payload schemas for each event type in `docs/architecture/contracts/events/audit-event.schema.json`.
- [x] Verify: JSON Schema Draft 2020-12 validation passes.
- **Refs**: FR-7, design §7.

### T-BUD-1.4: Add budget endpoints to OpenAPI
- [x] `GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget` — returns `BudgetStatus`.
- [x] `POST /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget/reset` — returns `BudgetStatus`.
- [x] Define `BudgetStatus` schema: `{ceiling, period, used, remaining, period_start, period_end, alert_thresholds}`.
- [x] Verify: Redocly lint passes; no breaking changes to existing endpoints.
- **Refs**: FR-9, design §5.

### T-BUD-1.5: Update MCP tools contract
- [x] Extend `your_constraints` in `describe_service` output schema (`docs/architecture/contracts/mcp/tools.yaml`) with `budget` object.
- [x] Fields: `ceiling`, `period`, `used`, `remaining`, `period_end`, `alert_thresholds`.
- [x] `budget` is nullable (null when no budget configured).
- [x] Verify: YAML lint passes.
- **Refs**: FR-8, design §8.

---

## Milestone M-BUD-2: Admin API (Python)

### T-BUD-2.1: SQLAlchemy model for `budget_counters`
- [x] Add `BudgetCounter` mapped class to `packages/python/mintkey-models/`.
- [x] Mirror the Liquibase schema exactly (composite PK, all columns).
- [x] Add `BudgetCounterOut` Pydantic read model and `BudgetStatus` response model.
- [x] Verify: model introspection matches Liquibase-applied schema.
- **Refs**: design §1, T-BUD-1.1.

### T-BUD-2.2: Budget config validation in grant creation/update
- [x] Extend the `GrantPermissionRequest` handler to validate `constraints.budget` against the closed schema.
- [x] On grant creation with budget: upsert initial `budget_counters` row for current period.
- [x] On grant update (PATCH): if ceiling changed, update the current counter row's ceiling; if period changed, close current row and create new.
- [x] Emit `budget.config_updated` audit event.
- [x] Fire change-channel `NOTIFY mintkey:agent` with `budget.config_updated` payload.
- [x] Verify: unit test — invalid budget rejected; valid budget persists and counter created.
- **Refs**: FR-1, FR-6, FR-10, design §5, §6.

### T-BUD-2.3: GET /budget endpoint
- [x] Implement `GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget`.
- [x] Query `budget_counters` for current period; return `BudgetStatus`.
- [x] 404 if grant has no budget constraint.
- [x] Verify: integration test — returns correct `used`, `remaining`, `period_end`.
- **Refs**: FR-9, design §5.

### T-BUD-2.4: POST /budget/reset endpoint
- [x] Implement `POST /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget/reset`.
- [x] Create new counter row with `used=0` for current period remainder.
- [x] Emit `budget.reset` audit event.
- [x] Fire change-channel notification.
- [x] Return new `BudgetStatus`.
- [x] Verify: integration test — after reset, `used=0`; subsequent proxy call succeeds.
- **Refs**: FR-5, design §5.

### T-BUD-2.5: Period helper utilities
- [x] Implement `budget_period_bounds(period: str, now: datetime) → (start, end)` utility.
- [x] UTC-aligned: hourly=top of hour, daily=midnight, weekly=Monday midnight, monthly=1st midnight.
- [x] Unit tests for all four period types including edge cases (month boundaries, leap year, DST-irrelevant since UTC).
- **Refs**: design §3.

---

## Milestone M-BUD-3: Proxy Plugin (Go)

### T-BUD-3.1: Budget enforcement package
- [x] Create `apps/proxy-plugin/internal/budget/` package.
- [x] `Check(ctx, db, permissionID, tenantID, budgetConfig) → (used, ceiling, error)`.
- [x] Implements the atomic upsert: `INSERT...ON CONFLICT DO UPDATE SET used=used+1 WHERE used < ceiling RETURNING used, ceiling`.
- [x] If 0 rows (ceiling hit): return `ErrBudgetExceeded` with `{used, ceiling, period_end}`.
- [x] Period boundary calculation (same logic as Python, design §3).
- [x] Unit tests with mock DB (testify + pgx mock).
- **Refs**: FR-2, FR-3, FR-4, NFR-1, design §4.

### T-BUD-3.2: Integrate budget check into proxy request flow
- [x] After JWT verification (step 9), call `budget.Check` if the resolved grant has `constraints.budget`.
- [x] On `ErrBudgetExceeded`: return 429 with the error body per design §10.
- [x] Set `Retry-After` header to `period_end` (RFC 7231 HTTP-date format).
- [x] Emit `mintkey_budget_denied_total` Prometheus counter on deny.
- [x] Verify: integration test — agent hits ceiling; next request gets 429; upstream never called.
- **Refs**: FR-2, design §4, §10.

### T-BUD-3.3: Threshold audit emission
- [x] After successful increment, check if `used` crossed any threshold in `alert_thresholds`.
- [x] If crossed: emit `budget.threshold_reached` audit event via `audit.Emit` (async, non-blocking).
- [x] Track which thresholds have already fired for this period (avoid duplicate events).
- [x] Unit test: crossing 50% triggers event; crossing 50% again does not.
- **Refs**: FR-7, design §7.

### T-BUD-3.4: Change-channel subscriber for budget invalidation
- [x] Extend existing `mintkey:agent` channel handler to recognize `budget.config_updated` events.
- [x] On receipt: invalidate any locally cached budget config for the affected `permission_id`.
- [x] Unit test: inject `budget.config_updated` event; verify cached state cleared.
- **Refs**: FR-10, design §6.

### T-BUD-3.5: Prometheus metrics
- [x] `mintkey_budget_used` gauge — set after each successful increment.
- [x] `mintkey_budget_ceiling` gauge — set when budget config is loaded.
- [x] `mintkey_budget_denied_total` counter — incremented on each 429.
- [x] Labels: `permission_id`, `agent_id`, `service_id`, `tenant_id`.
- [x] Verify: metrics endpoint exposes all three after a budget-checked request.
- **Refs**: NFR-5, design §9.

---

## Milestone M-BUD-4: MCP Server & Observability

### T-BUD-4.1: Extend `describe_service` with budget info
- [x] In MCP server's `describe_service` handler, query `budget_counters` for the agent's grants on the target service.
- [x] Populate `your_constraints.budget` with `{ceiling, period, used, remaining, period_end, alert_thresholds}`.
- [x] If no budget: `budget: null`.
- [x] Verify: MCP tool call returns budget info; matches actual counter state.
- **Refs**: FR-8, design §8.

### T-BUD-4.2: Grafana dashboard panel
- [x] Add budget consumption panel to existing Grafana dashboard JSON.
- [x] Panel: bar gauge showing `used/ceiling` per agent×service.
- [x] Color: green < 50%, yellow 50–80%, red > 80%.
- [x] Verify: panel renders in Grafana with test data.
- **Refs**: NFR-5, design §9.

### T-BUD-4.3: Prometheus alert rule
- [x] Add `BudgetNearExhaustion` alert to `infra/observability/alert_rules.yml`.
- [x] Trigger: `mintkey_budget_used / mintkey_budget_ceiling > 0.9` for 1m.
- [x] Severity: warning.
- [x] Verify: alert fires in test Prometheus with synthetic metrics.
- **Refs**: NFR-5, design §9.

---

## Milestone M-BUD-5: Integration & Acceptance Tests

### T-BUD-5.1: End-to-end budget enforcement test
- [x] Test scenario: create agent, grant with budget ceiling=5, make 5 calls (all succeed), 6th call returns 429.
- [x] Assert upstream service received exactly 5 calls.
- [x] Assert 429 response body matches design §10.
- [x] Assert `budget.exceeded` audit event emitted.
- **Refs**: FR-2, FR-3.

### T-BUD-5.2: Period rollover test
- [x] Test scenario: exhaust budget; advance clock past period_end; next call succeeds (new period).
- [x] Assert new counter row created.
- **Refs**: FR-4.

### T-BUD-5.3: Manual reset test
- [x] Test scenario: exhaust budget; operator calls POST /budget/reset; next call succeeds.
- [x] Assert `budget.reset` audit event emitted.
- [x] Assert change-channel notification fired.
- **Refs**: FR-5.

### T-BUD-5.4: Config update propagation test
- [x] Test scenario: agent at 8/10 budget; operator increases ceiling to 20; next call succeeds.
- [x] Assert change-channel notification fired within ≤ 5s.
- [x] Assert `budget.config_updated` audit event emitted.
- **Refs**: FR-6, FR-10.

### T-BUD-5.5: Architecture tests
- [x] Assert `budget_counters` has RLS policy (extend existing `test_rls_coverage.py`).
- [x] Assert cascade delete: deleting a grant removes its counter rows.
- **Refs**: NFR-3, NFR-4.

---

## Milestone M-BUD-6: Documentation & ADR

### T-BUD-6.1: Formalize ADR-0029
- [x] Promote P-011 to ADR-0029 once the architect accepts.
- [x] Status: Accepted.
- [x] Add forward-links from ADR-0006, ADR-0010, ADR-0016.
- **Refs**: P-011.

### T-BUD-6.2: Update AGENTS.md / CLAUDE.md
- [x] Add budget guardrails to the "Mintkey-specific guardrails" section.
- [x] Add `budget_counters` to the "How to add an X" table.
- **Refs**: project conventions.
