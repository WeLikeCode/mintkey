# Tasks: proxy-budget-check

The task writes its tests first and sees them fail for the reason it names, then changes the code. The tests are
top-level Go functions without `t.Run` and use only API that exists before the change (design D6). Run
`go test ./... -short`, `go vet ./...` and `golangci-lint run` in `apps/proxy-plugin`.

## 1. The proxy enforces grant budgets over Postgres

- [x] 1.1 Tests first, new file `apps/proxy-plugin/cmd/proxy-plugin/budget_wiring_test.go` (package `main`, using
  `testHandler()`, `testSvcUUIDA` of `proxy_test.go` and `buildScopeClaimsJWT` of `scope_claims_test.go`). Declare
  `type budgetDBUser interface { useBudgetDB(db budget.DB) }` and `type budgetSQLUser interface { useBudgetSQL(db
  *sql.DB) }`; every test asserts the handler implements the one it needs (else `t.Fatal`). Tokens are
  `buildScopeClaimsJWT(t, testSvcUUIDA, map[string]any{"sub": "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd", "tnt":
  "11111111-2222-3333-4444-555555555555"})` (scope `call`), except in the non-UUID test, which passes no `extra`;
  requests are `GET /v1/x` with the token's key at `h.pubKeys["testkey"]`; "reaches the credential fetch" asserts 502.
  - A file-local fake `budget.DB`, `grantStoreDB` (fields: `budgetJSON string`, `grantErr error`, `ceiling`, `used
    int`, `periodEnd time.Time`; records `grantArgs [][]any` and `counterCalls int`; a mutex). `QueryRow` answers a
    query containing `FROM permission_grants` by recording its args and returning a row that fails with `grantErr`
    when set, with `sql.ErrNoRows` when `budgetJSON` is `""`, else holds `"99999999-8888-7777-6666-555555555555"` and
    `[]byte(budgetJSON)`; a query containing `ON CONFLICT` by incrementing `counterCalls` and, while `used < ceiling`,
    incrementing `used` and returning `(used, ceiling)`, else `sql.ErrNoRows`; any other query by returning `(used,
    ceiling, periodEnd)`. Its row type `grantStoreRow` scans into `*string`, `*[]byte`, `*int` and `*time.Time`.
  - `TestBudgetIsReadFromTheGrantOfTheTokenAction` covers "the grant's budget is counted and enforced" (ceiling 1,
    `periodEnd` a fixed future time; the 429 body's `error` and `permission_id` are asserted).
  - `TestBudgetGrantCacheIsClearedByConfigUpdate` covers "a configuration change clears the cache", with
    `h.changesSubscriber("").HandleNotification(...)` for the notification (built after `useBudgetDB`, so the
    subscriber carries the resolver's cache).
  - `TestBudgetLookupFailureFailsOpen` covers "a lookup error lets the request through" (`grantErr` =
    `errors.New("connection refused")`; `counterCalls` stays 0).
  - `TestBudgetLookupSkippedForNonUUIDIdentifiers` covers "identifiers that are not UUIDs are not looked up".
  - `TestBudgetStatementsRunInTenantTransaction` covers "the lookup and the counter run inside tenant transactions"
    with a file-local `database/sql/driver` fake registered once in an `init` function as
    `sql.Register("budgetrec", ...)`: `Open` returns a connection whose `Begin` records `BEGIN` and returns a
    transaction recording `COMMIT` or `ROLLBACK`; `Prepare(query)` returns a statement (`NumInput` -1) that records
    the query and its args on `Exec` (answering `driver.RowsAffected(1)`) and on `Query`, which answers one row
    `("99999999-8888-7777-6666-555555555555", []byte(`{"ceiling":5,"period":"daily"}`))` (columns `id`, `budget`) for a
    query containing `FROM permission_grants`, one row `(int64(1), int64(5))` (columns `used`, `ceiling`) for a query
    containing `INSERT INTO budget_counters`, and no row otherwise. The test opens `sql.Open("budgetrec", "")`, calls
    `useBudgetSQL`, makes one request (502), and maps the record to `BEGIN`, `SET_TENANT:<first arg>` (a query
    containing `set_config('app.current_tenant'`), `GRANT`, `UPSERT`, `COMMIT`, `ROLLBACK`, asserting exactly
    `[BEGIN, SET_TENANT:11111111-2222-3333-4444-555555555555, GRANT, COMMIT, BEGIN,
    SET_TENANT:11111111-2222-3333-4444-555555555555, UPSERT, COMMIT]`.
  Every test fails before the change because the handler has neither method.
  Then create `apps/proxy-plugin/internal/budget/store.go` (`ActionResolver`, `GrantBudgetSQL`, `SetTenantSQL`,
  `ErrNoTenant`, `WithTenant`, `TenantFrom`, `GrantResolver`, `SQLDB`, exactly as design.md gives them) and
  `apps/proxy-plugin/cmd/proxy-plugin/budget_wiring.go` (the constants, `useBudgetDB`, `useBudgetSQL`); in
  `apps/proxy-plugin/cmd/proxy-plugin/main.go` make the three edits of design.md (`changesSubscriber` adds the budget
  option, `main` opens the pool and drops its own budget option block, `ServeHTTP` prefers `ActionResolver` and passes
  the tenant in the context). `ConfigResolver`, `InMemoryConfigResolver`, `budget.Check` and the existing tests
  (`TestBudgetEnforcement_*` in `proxy_test.go`) are not changed and keep passing.
