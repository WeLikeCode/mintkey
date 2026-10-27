# Proxy budget enforcement

## Purpose

How the egress proxy finds the call budget of a request in the permission grants, counts the call in
`budget_counters`, and refuses a call past the ceiling.

## ADDED Requirements

### Requirement: The proxy enforces the budget of the grant of the token's action
When budget enforcement is on (`proxyHandler.useBudgetDB` or `useBudgetSQL`), the egress proxy SHALL read the budget
of a JWT request from the permission grant that matches the token's `sub`, `aud` and `scope`, passing them as UUIDs to
`budget.GrantBudgetSQL`, and SHALL count the call and answer 429 `budget_exceeded` past the ceiling with the existing
response. The answer of a lookup SHALL be cached for 5 s, and the cache SHALL be cleared when the handler's change
subscriber receives `budget.config_updated`.

#### Scenario: the grant's budget is counted and enforced
- **WHEN** enforcement is on over a store whose grant for (`6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd`, the service, `call`)
  has `{"ceiling": 1, "period": "daily"}`, and a token with that `sub`, the tenant
  `11111111-2222-3333-4444-555555555555` and `scope` `call` makes two requests
- **THEN** the first reaches the credential fetch (502 from the unreachable test vault), the second answers 429 with
  `error` `budget_exceeded` and the grant's `permission_id`, and the store saw one grant lookup, with the arguments
  (`6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd`, the service UUID, `call`)

#### Scenario: a configuration change clears the cache
- **WHEN** the grant has no budget, two requests are made, the handler's change subscriber then receives
  `{"event_type":"budget.config_updated","target_id":"perm_x"}`, and a third request is made
- **THEN** all three reach the credential fetch, and the store saw two grant lookups

### Requirement: Budget statements run in a transaction scoped to the token's tenant
With `useBudgetSQL`, every budget statement SHALL run in its own transaction that begins with
`SELECT set_config('app.current_tenant', $1, true)` bound to the token's tenant as a UUID, and SHALL commit after the
statement.

#### Scenario: the lookup and the counter run inside tenant transactions
- **WHEN** enforcement is on over a recorded SQL connection whose grant lookup returns a budget with `ceiling` 5 and
  whose counter upsert returns `(1, 5)`, and a token of the tenant `11111111-2222-3333-4444-555555555555` makes one
  request
- **THEN** the recorded statements are, in order: begin, the tenant setting with that tenant, the grant lookup,
  commit, begin, the tenant setting with that tenant, the counter upsert, commit

### Requirement: The budget check fails open
When the grant lookup fails, or the token's `sub`, `aud` or `tnt` is neither a UUID nor a wire id, the proxy SHALL
proceed without a budget check and SHALL NOT write a counter; a failed lookup SHALL NOT be retried for 5 s.

#### Scenario: a lookup error lets the request through
- **WHEN** the store's grant lookup returns an error and a valid token of UUID ids makes two requests
- **THEN** both reach the credential fetch (502), the store saw one grant lookup, and no counter statement is issued

#### Scenario: identifiers that are not UUIDs are not looked up
- **WHEN** a token with `sub` `agent_test` and `tnt` `tenant-test-uuid-0001` makes a request
- **THEN** the request reaches the credential fetch (502) and the store saw no grant lookup
