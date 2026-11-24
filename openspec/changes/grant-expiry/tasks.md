# Tasks: grant-expiry

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run the touched
suites, `ruff check` and `mypy --strict` (`apps/admin-api`: `src/admin_api/`) and `ruff check src/` in `apps/mcp-server`.
No test needs a database or the network. The functions take `now`; route tests build expiries relative to the current
time (a day ahead, an hour ago) and the token test uses the tolerance its scenario gives.

Route tests build a `FastAPI()` with the router under test, `get_db_session` overridden by a fake session whose `async
execute(statement, params=None)` records `(str(statement), params)` and answers by substrings of the statement,
`require_tenant_session` overridden with a no-op, `get_session_context` overridden with a function returning
`types.SimpleNamespace(operator_id=<UUID>, tenant_id=<UUID>)`, and `audit_emit` and `notify_change` patched at
`admin_api.api.permissions` (as `create_test_app` in `tests/unit/admin_api/test_permissions.py` does). MCP tests call the
route functions with a fake session, as `apps/mcp-server/tests/test_request_token_scope_claims.py` does.

## 1. The schema

- [ ] 1.1 Tests first, new file `tests/unit/admin_api/test_grant_expiry_migration.py` (paths from
  `Path(__file__).resolve().parents[3]`, `yaml.safe_load`), covering the two scenarios of the requirement "The schema
  stores a grant's expiry and grantor"; it fails before the change (no changelog file, no Core columns). Then create
  `apps/admin-api/db/changelog/030-grant-expiry.yaml` (changesets `030-grant-expiry-columns`, `030-grant-expiry-check`,
  `030-grant-expiry-index`, each with a rollback), append its include to
  `apps/admin-api/db/changelog/db.changelog-master.yaml`, and add the three columns to the Core table in
  `apps/admin-api/src/admin_api/db/tables.py`. Do not touch `packages/python/mintkey-models/mintkey_models/db.py`.

## 2. The rules and the write path

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_grant_expiry_rules.py`, covering the three scenarios of "The
  expiry rules and the cap have one implementation" (`monkeypatch.setenv` and `delenv` for the variable); red stubs the
  module `apps/admin-api/src/admin_api/services/grant_expiry.py` with the names and signatures of the spec (functions
  raising `NotImplementedError`), so the tests fail by assertion. Then fill it in.

- [ ] 2.2 Tests first, new file `tests/unit/admin_api/test_grants_service.py`, covering the seven scenarios of "One write
  path creates and removes grants" (the fake session answers a statement containing `FROM permission_grants` with the
  stored row or None; for "two concurrent writes of one grant" the test defines, in this file, a fake pair of sessions over
  one in-memory table, whose `execute` of a statement containing `pg_advisory_xact_lock` waits on an `asyncio.Lock` per key
  that `commit()` releases, and which records each session's statements in order); red stubs the module `apps/admin-api/src/admin_api/services/grants.py` with the names and
  signatures of the spec. Then fill it in: the select, compare, insert and budget-counter statements are those of
  steps 6, 8 and 9 of `grant_permission` in `apps/admin-api/src/admin_api/api/permissions.py`, extended with the new
  columns and parameters; they stay in the route's SQL style (string literals, bound parameters); the advisory lock statement comes first and the
  select carries the `ORDER BY ... LIMIT 1` of the spec. Move `_new_perm_id`, the 128-bit id derivation and
  `_budget_period_bounds` from `apps/admin-api/src/admin_api/api/permissions.py` into `grants.py` and import them back
  there, so that `from admin_api.api.permissions import _budget_period_bounds` (used by existing tests) still works.

## 3. The operator API

- [ ] 3.1 Tests first, new file `tests/unit/admin_api/test_permissions_expiry.py`, covering the four scenarios of "The
  operator API takes an expiry and records the grantor". Change the existing
  `tests/unit/admin_api/test_permissions.py::test_revoke_returns_204_and_notifies` only in its set-up: build its app
  with `existing_perm` set to a `types.SimpleNamespace` grant row (agent, service, action, constraints, grantor
  fields), because the route now reads the grant it deletes. The new tests fail before the change (no `expires_at`,
  the grantor is the body's, the revoke emits without a row). Then in
  `apps/admin-api/src/admin_api/api/permissions.py`: add `expires_at: Optional[datetime] = None` to
  `PermissionGrantRequest` (a value without an offset reaches `check_grant_expiry`, which refuses it) (keep `granted_by`, unused), build the grantor from `Depends(get_session_context)`, replace
  steps 6 to 9 of `grant_permission` by `write_grant` (keep the agent and service checks, the 422/404 answers and the
  audit and 201/200 responses, with `grant_granted_audit_payload` and the four wire fields), turn the 409 and the
  expiry errors into the flat `JSONResponse` bodies of the requirement (`{"mintkey:code": ..., "title": ..., "reason": ...}`
  for the 422, as the route's `invalid_id` answer is built), replace the DELETE statement of `revoke_permission` by `delete_grant`
  with the audit and NOTIFY payload builders (nothing emitted for None), and add the new columns to the four SELECTs
  of `list_permissions`, `list_tenant_permissions` and `get_permission` and to their objects, plus the `grantor_agent_id`
  parameter. The PATCH and the budget routes are unchanged.

## 4. Expired grants are absent

- [ ] 4.1 Tests first, new file `apps/mcp-server/tests/test_grant_expiry_tokens.py`, covering the scenarios of "An
  expired grant is absent for the agent" about `request_token` (including "the grant select is ordered") and of "A token never outlives its grant" (the
  `request_token` setup of `apps/mcp-server/tests/test_request_token_scope_claims.py`: monkeypatched
  `resolve_service_id`, a fake `httpx` recording the broker payload, `session.execute` answering the grant row, then
  the service row). Red stubs `apps/mcp-server/src/mcp_server/policy/grant_expiry.py` with the names of the spec. The
  tests fail before the change (the broker is called, `ttl_seconds` is 600). Then fill in `grant_ttl_seconds`; in
  `apps/mcp-server/src/mcp_server/tools/request_token.py` select `expires_at` with the grant (add `ORDER BY
  (expires_at IS NULL) DESC, expires_at DESC, created_at DESC, id`; the statement keeps its `LIMIT 1`), read it with `getattr(grant, "expires_at", None)`, deny before the
  rate-limit check with a new branch of `_denial_hint` and `_emit_denial`, and send the computed `ttl_seconds` in the
  broker payload (the email path keeps 600).

- [ ] 4.2 Tests first, new file `apps/mcp-server/tests/test_grant_expiry_discovery.py`, covering the scenario "discovery
  hides what the database says is expired" (call `list_services`, `discover` and `describe_service` of
  `mcp_server.tools.discovery` with a recording fake session). It fails before the change. Then add the filter to the
  three statements of `apps/mcp-server/src/mcp_server/tools/discovery.py` that read `permission_grants` (alias `pg`
  in the two joins; the `describe_service` lookup uses the bare column names).

- [ ] 4.3 Tests first, new file `tests/unit/admin_api/test_grant_expiry_readers.py`, covering the scenario "the other
  readers ignore an expired grant": it creates a classical key through `admin_api.api.api_keys` as
  `tests/unit/admin_api/test_api_keys.py` does and calls `list_agents` and `get_agent` of `admin_api.api.agents` with the
  recording fake session. It fails before the change. Then add `AND (expires_at IS NULL OR expires_at > now())` (with the
  alias where there is one) to the grants load of `apps/admin-api/src/admin_api/api/api_keys.py` and to the seven
  `permission_grants` subqueries of `apps/admin-api/src/admin_api/api/agents.py` (the grant counts and the
  `has_access_to_service_id` conditions).

## 5. The audit contract

- [ ] 5.1 Tests first, new file `tests/unit/admin_api/test_audit_schema_grants.py` (loads
  `docs/architecture/contracts/events/audit-event.schema.json`), covering the scenario "the contract names them"; it
  fails before the change. Then edit the three definitions in the schema file. The admin UI's audit filter list is not
  changed here.
