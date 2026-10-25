# The egress proxy enforces the call budgets operators set

## Why

Operators can put a call budget on a permission grant (`constraints.budget`: a ceiling per hourly, daily, weekly or
monthly period). Everything around the budget is delivered: admin-api validates it and serves its status and reset
endpoints (`api/permissions.py`, `api/budgets.py`, `api/budget_consumers.py`), the admin UI edits and displays it
(`BudgetForm`, `BudgetStatusPanel`, `BudgetConsumersPage`), the MCP server reports it in `describe_service`, the
`budget_counters` table exists (Liquibase `029-budget-counters.yaml`), and Grafana and the alert rules read its
metrics. The project's guardrails say the proxy enforces it atomically and answers 429 `budget_exceeded` when it is
exhausted. The proxy's handler contains that check, but it runs only when two handler fields are set, and nothing sets
them: no budget is ever counted or enforced, and the counters the UI shows never move.

A broker that shows a limit it does not apply misleads the operator who relies on it. Removing the feature would mean
removing a configured, operator-visible feature from five components and a table; wiring it is a proxy-only change
that reuses the check, its tests and its metrics. This change wires it.

## What Changes

- When `DATABASE_URL` is set, the proxy opens a Postgres pool (at most 4 connections) and turns the budget check on.
- The budget of a request is the budget of the permission grant that matches the token's agent (`sub`), service
  (`aud`) and action (`scope`), read from `permission_grants`. Answers are cached for 5 s; a `budget.config_updated`
  notification on `mintkey:agent` clears the cache.
- Every budget statement runs in its own transaction that first sets `app.current_tenant` to the token's tenant, so the
  row-level security policies of `permission_grants` and `budget_counters` admit the rows. Each statement has a 1 s
  deadline.
- When the database cannot be read or written, the request proceeds without a budget check (fail open), as the
  existing check already does for counter errors.
- Without `DATABASE_URL` nothing changes.

## Capabilities

### New Capabilities
- `proxy-budget-enforcement`: how the egress proxy finds a request's budget, counts it and refuses an exhausted one.

## Impact

- Changed: `apps/proxy-plugin/cmd/proxy-plugin/main.go` (`ServeHTTP`'s budget block, `changesSubscriber`, `main`).
- New modules: `apps/proxy-plugin/internal/budget/store.go` (grant resolver, tenant-scoped SQL access),
  `apps/proxy-plugin/cmd/proxy-plugin/budget_wiring.go` (the handler methods that turn the check on).
- New test: `apps/proxy-plugin/cmd/proxy-plugin/budget_wiring_test.go`.
- Callers: an agent whose grant has an exhausted budget gets 429 `budget_exceeded` with `Retry-After` (the existing
  response) and the upstream is not called. Grants without a budget behave as before.
- Operators (migration): budgets already configured start to be enforced at deploy time; review them first in the
  admin UI's budget consumers page, and reset or raise any that should not stop traffic. The proxy keeps up to 4 more
  connections to Postgres. Its role (`mintkey_app` in compose) needs `SELECT` on `permission_grants` and `SELECT`,
  `INSERT`, `UPDATE` on `budget_counters`, which the existing grants give it.
- Out of scope: budgets for classical service API keys, the SSH and email proxies, and changing the fail-open choice.

## Issue Intake (remediation gate)

1. **Problem statement**: grant budgets are configured and displayed but never enforced by the proxy.
2. **User-visible symptom**: an agent keeps calling past its ceiling; the admin UI shows 0 used.
3. **Expected behavior**: each proxied call counts against the grant's budget; past the ceiling the proxy answers 429
   `budget_exceeded` until the period ends or an operator resets it.
4. **Evidence**: `ServeHTTP` in `apps/proxy-plugin/cmd/proxy-plugin/main.go` runs the budget block only when
   `h.budgetResolver` and `h.budgetDB` are set; no code assigns them.
5. **Scope**: the proxy files under Impact.
6. **Out of scope**: as listed under Impact.
7. **Risk level**: availability (calls past a ceiling now stop, by design) and UX.
8. **Verification target**: the Go suite of `apps/proxy-plugin`, and a person's live check against the compose stack.
9. **Owner decisions needed**: none; wiring was chosen over removal (design.md D1).
