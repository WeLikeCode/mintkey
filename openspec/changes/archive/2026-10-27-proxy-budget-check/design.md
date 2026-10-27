# Design: proxy-budget-check

## Context

- `ServeHTTP` (`apps/proxy-plugin/cmd/proxy-plugin/main.go`) has a budget block after the audience check:
  `if h.budgetResolver != nil && h.budgetDB != nil`, it calls `h.budgetResolver.Resolve(agentID, serviceID, tenantID)`
  and, for a non-nil budget, `budget.Check(r.Context(), h.budgetDB, permissionID, tenantID, cfg)`, which upserts the
  period's row in `budget_counters` and returns `*budget.ErrBudgetExceeded` at the ceiling; the block then answers 429,
  emits `budget.exceeded` / `budget.threshold_reached` and updates the budget metrics. Any other error is logged and
  the request proceeds. `budget.DB` is `QueryRow(ctx, sql string, args ...any) Row`, `Row` is `Scan(dest ...any) error`.
  `budget.ConfigResolver` has only `Resolve(agentID, serviceID, tenantID)`; its one implementation,
  `InMemoryConfigResolver`, is filled by nothing. Tests set both fields by hand (`testHandlerWithBudget` in
  `proxy_test.go`).
- Grants are rows of `permission_grants(id, tenant_id, agent_id, service_id, action, constraints JSONB, ...)`, one per
  (agent, service, action); the budget is `constraints.budget` = `{ceiling, period, alert_thresholds}`. Both tables
  have the policy `tenant_isolation` on `current_setting('app.current_tenant', true)::uuid`, and the proxy connects as
  `mintkey_app`, which does not bypass row-level security.
- The token's `sub`, `aud` and `tnt` are database UUIDs when the MCP server requested it (`request_token.py` passes
  `agent_ctx` ids, which admin-api returns as `str(row.id)` / `str(row.tenant_id)`, and the service UUID); the
  issuer's package comment, which says prefixed ULIDs, is stale. The proxy imports `github.com/lib/pq` (the change
  subscriber) and has no other database client.
- From `proxy-revocation-enforced`: `internal/wireid` (`ToUUID`, `Canonical`) and `proxyHandler.changesSubscriber`.
  From `token-request-scope-claims`: the scope-claims check before the `read:atlas` gate, and the test helper
  `buildScopeClaimsJWT` in `cmd/proxy-plugin/scope_claims_test.go`.

## Interfaces

New file `apps/proxy-plugin/internal/budget/store.go`:

```go
// ActionResolver resolves the budget of the grant of one action. The proxy prefers it over ConfigResolver.
type ActionResolver interface {
	ResolveAction(ctx context.Context, agentID, serviceID, tenantID, action string) *ResolvedBudget
}

const GrantBudgetSQL = `SELECT id::text, constraints->'budget' FROM permission_grants
WHERE agent_id = $1 AND service_id = $2 AND action = $3 AND jsonb_typeof(constraints->'budget') = 'object'
LIMIT 1`

const SetTenantSQL = `SELECT set_config('app.current_tenant', $1, true)`

var ErrNoTenant = errors.New("budget: no tenant in context")

func WithTenant(ctx context.Context, tenantID string) context.Context // unexported key type
func TenantFrom(ctx context.Context) string                           // "" when absent

// GrantResolver reads budgets from permission_grants through db and caches each answer, a budget or none, for ttl.
type GrantResolver struct { /* db DB; ttl time.Duration; now func() time.Time; mu sync.Mutex; cache map[string]grantEntry */ }

func NewGrantResolver(db DB, ttl time.Duration) *GrantResolver
func (g *GrantResolver) ResolveAction(ctx context.Context, agentID, serviceID, tenantID, action string) *ResolvedBudget
func (g *GrantResolver) Resolve(agentID, serviceID, tenantID string) *ResolvedBudget // always nil
func (g *GrantResolver) InvalidateBudget(permissionID string)                      // clears every cached answer

// SQLDB runs each statement in its own transaction that first runs SetTenantSQL with TenantFrom(ctx).
type SQLDB struct { /* db *sql.DB; timeout time.Duration */ }

func NewSQLDB(db *sql.DB, timeout time.Duration) *SQLDB
func (s *SQLDB) QueryRow(ctx context.Context, query string, args ...any) Row // the work happens in Row.Scan
```

`ResolveAction`:
1. `a, s, t` = `wireid.ToUUID` of `agentID` (`"agent_"`), `serviceID` (`"svc_"`), `tenantID` (`"tenant_"`). If one
   fails or `action == ""`, return nil without a query and without caching.
2. Key `a|s|t|action`; a cached answer younger than `ttl` is returned.
3. `db.QueryRow(WithTenant(ctx', t), GrantBudgetSQL, a, s, action).Scan(&permissionID /* string */, &raw /* []byte */)`
   with `ctx'` = `ctx` plus a 1 s timeout. `sql.ErrNoRows` → none. Another error → log
   `proxy-plugin: budget grant lookup failed` with the error, none. Otherwise unmarshal `raw` into `BudgetConfig`; an
   error or `Ceiling < 1` → none; else `&ResolvedBudget{PermissionID: permissionID, Config: cfg}`.
4. Cache the answer (none included) with the time, and return it.

`SQLDB` row `Scan(dest...)`: `t := TenantFrom(ctx)`; `""` → `ErrNoTenant` (no database call). Else, under
`context.WithTimeout(ctx, timeout)`: `BeginTx(ctx, nil)`; `ExecContext(SetTenantSQL, t)`;
`QueryRowContext(query, args...).Scan(dest...)`; on any error `_ = tx.Rollback()` and return the error (so
`sql.ErrNoRows` reaches `budget.Check` unchanged); else `Commit()`.

New file `apps/proxy-plugin/cmd/proxy-plugin/budget_wiring.go`:

```go
const (
	budgetGrantCacheTTL    = 5 * time.Second // config changes reach the proxy within 5 s (S-OPS-1)
	budgetStatementTimeout = time.Second
	budgetMaxOpenConns     = 4
)

// useBudgetDB turns the budget check on: counters in db, budgets from the grants in db.
func (h *proxyHandler) useBudgetDB(db budget.DB) {
	h.budgetDB = db
	h.budgetResolver = budget.NewGrantResolver(db, budgetGrantCacheTTL)
}

// useBudgetSQL turns the budget check on over a Postgres pool.
func (h *proxyHandler) useBudgetSQL(db *sql.DB) { h.useBudgetDB(budget.NewSQLDB(db, budgetStatementTimeout)) }
```

`main.go`:
- `changesSubscriber` appends `changes.WithBudgetCache(bc)` to `opts` when `h.budgetResolver` implements
  `changes.BudgetCacheInvalidator`; `main`'s own budget option block is removed and the call becomes
  `handler.changesSubscriber(dsn)`.
- In `main`, inside `if dsn := os.Getenv("DATABASE_URL"); dsn != ""` and before the subscriber is built:
  `budgetSQL, err := sql.Open("postgres", dsn)`; on error log the fixed text
  `proxy-plugin: budget enforcement disabled: DATABASE_URL could not be parsed` (never the error, which can quote the
  DSN); else `budgetSQL.SetMaxOpenConns(budgetMaxOpenConns)`, `defer budgetSQL.Close()`,
  `handler.useBudgetSQL(budgetSQL)`. `main.go` imports `database/sql` and `_ "github.com/lib/pq"`.
- `ServeHTTP`'s budget block: `resolved` comes from `ResolveAction(r.Context(), agentID, serviceID, tenantID, scope)`
  when `h.budgetResolver` implements `budget.ActionResolver`, else from `Resolve(agentID, serviceID, tenantID)` as
  today. For a non-nil `resolved`, `budgetTenant := wireid.Canonical(tenantID, "tenant_")` and the call becomes
  `budget.Check(budget.WithTenant(r.Context(), budgetTenant), h.budgetDB, resolved.PermissionID, budgetTenant,
  resolved.Config)`. The rest of the block (429 body, `Retry-After`, audit events, metrics labels) is unchanged.

## Decisions

**D1. Wire, not remove.** The facts under Why: the check and its 429 contract, the counter table, the admin-api
endpoints, the admin UI, the MCP output, the dashboards and the written guardrails all exist and are visible to
operators; only the proxy's wiring is missing (`.kiro/specs/agent-budgets/tasks.md` ticks T-BUD-3.2, whose integration
test is a skip stub in `tests/acceptance/test_budget_enforcement.py`). Removing would leave every configured budget
silently dropped and touch five components and a table; wiring is contained in the proxy.

**D2. The budget belongs to the grant of the token's action.** Grants are per (agent, service, action), and `scope`
is the action the grant check used. `ConfigResolver` lacks the action; rather than change its signature (its tests
call it), the new `ActionResolver` is preferred when present, and `InMemoryConfigResolver` keeps working for the
existing tests.

**D3. Row-level security is honoured, not bypassed.** Each statement sets `app.current_tenant` with `is_local = true`
inside its transaction, so a pooled connection never carries one tenant's setting into another request. No new
database role is needed.

**D4. Fail open on database errors, with a bound.** A broken budget store must not stop all traffic; the existing
block already fails open on counter errors. Each statement has a 1 s deadline, and a failed lookup is cached as "no
budget" for 5 s so an outage costs one wait per (agent, service, action) per 5 s.

**D5. Cache for 5 s, cleared on change.** A lookup per request would add a database round trip to every proxied call.
Five seconds matches the propagation bound of S-OPS-1; `budget.config_updated` clears the whole cache (its `target_id`
can be in either id form, and changes are rare).

**D6. Tests reach new code through existing entry points.** The repository's test gate runs new tests against the
code before the change: the test file declares interfaces for `useBudgetDB` and `useBudgetSQL` and asserts the
handler has them (`t.Fatal` otherwise), drives `ServeHTTP` with a fake `budget.DB`, and records the SQL that
`useBudgetSQL` issues through a fake `database/sql` driver. No red test names a symbol this change adds (scaffold:
none): besides the two probed methods, the test uses `budget.DB`, `budget.Row`, `database/sql`, `testHandler`,
`testSvcUUIDA`, and two symbols of the earlier changes, `proxyHandler.changesSubscriber` and `buildScopeClaimsJWT`,
which exist once those are merged. No dependency is added (`database/sql` and the module's
existing `github.com/lib/pq`), so the gate's run against the earlier code is not skipped; a Go test failure is
reported as `<failure message="Failed">`, which the gate counts as an assertion failure.

## Failure cases

- `DATABASE_URL` unset: no pool, no budget check, as today.
- Postgres down: the lookup or the counter statement fails within 1 s; the request proceeds; one log line per failure.
- A token whose `sub`, `aud` or `tnt` is not a UUID or a wire id (an application issuing its own ids): no lookup.
- A grant with a malformed budget (`ceiling` < 1, not an object): no budget.
- Counter row at the ceiling: 429 `budget_exceeded` with `Retry-After`, the existing answer
  (`TestBudgetEnforcement_CeilingHit_Returns429` keeps covering its body).
- A budget changed by an operator: applied at the next request after the notification, or within 5 s.

## Relation to the other changes

Assumes `proxy-revocation-enforced` and `token-request-scope-claims` are merged (see Context). `proxy-data-plane-paths`
changes the audience check that runs just before the budget block, not the block itself.

## Open questions

- The SQL (the grant lookup, the counter upsert under row-level security with `set_config`) is checked in the gates
  only against a fake driver. A person verifies it once on the compose stack: a grant with `ceiling` 2, three calls,
  the third answers 429, and `budget_counters.used` is 2.
- That `mintkey_app` holds `SELECT, INSERT, UPDATE` on `budget_counters` is inferred from
  `019-grants-defensive.yaml`'s default privileges; the same live check confirms it.
