# Questions — agent-service-routes

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | open | 6.1 | technical | tests/unit/admin_api/test_agent_routes_isolation.py:295 needs tests/acceptance/openapi_snapshot.json unfrozen to add "agent": "/v1/agent" |
<!-- l4:index:end -->

---

## Q-001: tests/unit/admin_api/test_agent_routes_isolation.py:295 needs tests/acceptance/openapi_snapshot.json unfrozen to add "agent": "/v1/agent"

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the answer would unfreeze tests/acceptance/openapi_snapshot.json of task 6.1 (delegate.unfreeze is false)
- **Blocking tasks:** 6.1
- **Kind:** technical
- **Asked:** 2026-11-27T22:11Z by deepseek, run r-20261127T2004Z-3d36, task 6.1

### Context
The frozen test asserts at line 295 that the snapshot maps "agent" to "/v1/agent", and tests/acceptance/test_openapi_parity.py::test_openapi_parity_snapshot compares the whole router map to the same snapshot. Task 6.1 and design D9 say to add exactly that entry to tests/acceptance/openapi_snapshot.json, but the green step's test-path freeze reverts any edit to that file, so both tests fail while every other gate test passes. The red step did not include the fixture entry.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/acceptance/openapi_snapshot.json`, `tests/acceptance/test_openapi_parity.py`, `tests/unit/admin_api/test_agent_routes_isolation.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit agent-service-routes`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/acceptance/openapi_snapshot.json`: add exactly the entry `"agent": "/v1/agent"` (in key order, before `"agent_secrets"`) and change no other line.
2. Leave the snapshot frozen: accept that `test_C_48021709_agent_route_table_and_snapshot` and `test_openapi_parity_snapshot` stay red for this task.

### Harness notes
Harness note: the previous attempt of this task was rejected: red tests still failing: tests.unit.admin_api.test_agent_routes_isolation::test_C_48021709_agent_route_table_and_snapshot
E       AssertionError: {'agent_secrets': '/v1/tenants/{tenant_id}/agent-secrets', 'agents': '/v1/tenants/{tenant_id}/agents', 'api_keys': '/v1/tenants/{tenant_id}/agents/{agent_id}/api-keys', 'audit': '/v1/tenants/{tenant_id}/audit', ...}
E       assert None == '/v1/agent'
E        +  where None = <built-in method get of dict object at 0x7f8ac44ba380>('agent')
E        +    where <built-in method get of dict object at 0x7f8ac44ba380> = {'agent_secrets': '/v1/tenants/{tenant_id}/agent-secrets', 'agents': '/v1/tenants/{tenant_id}/age
../../tests/unit/admin_api/test_agent_routes_isolation.py:295

### Clarifier suggestion
Edit `tests/acceptance/openapi_snapshot.json`: add exactly the entry `"agent": "/v1/agent"` (in key order, before `"agent_secrets"`) and change no other line.

### Answer
<!-- write below this line -->
Take option 1: edit tests/acceptance/openapi_snapshot.json and add exactly the entry "agent": "/v1/agent", in key order before "agent_secrets", changing no other line, as task 6.1 and design D9 say. Answered by the repository owner's delegate.
