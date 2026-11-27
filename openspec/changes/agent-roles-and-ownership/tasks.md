# Tasks: agent-roles-and-ownership

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run the touched
suites, `ruff check` and `mypy --strict` (`apps/admin-api`: `src/admin_api/`; `packages/python/mintkey-models`:
`mintkey_models/`) and `ruff check src/` in `apps/mcp-server`. No test needs a database or the network.

The admin-api route tests build a `FastAPI()` that includes the router under test (as `create_test_app` in
`tests/unit/admin_api/test_permissions.py` does), override `get_db_session` with a fake session whose `async
execute(statement, params=None)` records `(str(statement), params)` and answers by substrings of the statement text,
override `require_tenant_session` with a no-op and `get_session_context` with a function returning
`types.SimpleNamespace(operator_id=<UUID>, tenant_id=<UUID>)`, register `validation_error_handler`, and patch
`audit_emit` and `notify_change` at the router module (`admin_api.api.agents`, `admin_api.api.services`). The tests of "no
session" keep the real `require_tenant_session`, send no cookie, and override only `get_db_session` with the recording fake
(and register `validation_error_handler`), so a 401 is shown with no statement recorded; they never reach a real database.

## 1. One role vocabulary

- [x] 1.1 Tests first, new file `packages/python/mintkey-models/tests/test_roles.py`, covering the scenario "names and
  fallback"; it fails before the change because `mintkey_models.roles` does not exist (red stubs the module with the
  names and signatures of design.md, `normalize_role` raising `NotImplementedError`). Then fill in
  `packages/python/mintkey-models/mintkey_models/roles.py` as design.md gives it.

## 2. The schema

- [x] 2.1 Tests first, new file `tests/unit/admin_api/test_agent_roles_migration.py` (paths from
  `Path(__file__).resolve().parents[3]`, `yaml.safe_load`), covering the two scenarios of the requirement "The schema
  stores an agent's role and a service's owner"; it fails before the change because the changelog file does not exist.
  Then create `apps/admin-api/db/changelog/031-agent-roles-and-ownership.yaml` (changesets `031-agents-role`,
  `031-agents-role-check`, `031-services-owner-columns`, `031-services-owner-fks`, `031-services-owner-index`, each with
  a rollback) and append its include to `apps/admin-api/db/changelog/db.changelog-master.yaml`. Do not touch
  `packages/python/mintkey-models/mintkey_models/db.py`.

## 3. Agent role in the operator API and in the key check

- [x] 3.1 Tests first, new file `tests/unit/admin_api/test_agent_roles.py`, covering the scenarios of "Agent responses
  carry the role", "An operator sets an agent's role", "A demotion changes nothing else", the role-PATCH half of "the error
  bodies" and the first scenario of "The agent-key check reports the role"
  (the last one calls `admin_api.api.internal.validate_agent_key` with a fake session of two results as
  `tests/unit/admin_api/test_validate_agent_key_errors.py` does, `_verify_argon2` patched to succeed, and counts the
  `execute` calls). Each fails before the change (no `role` key, no PATCH route, no `role` in the 200 body). Then in
  `apps/admin-api/src/admin_api/api/agents.py` add `a.role` to the five agent SELECTs and `role` to
  `_agent_row_to_dict` and to the create response, add the `role` query parameter to `list_agents` (filter after the
  fetch, design D5), and add the PATCH route with its body model (`model_config = ConfigDict(extra="forbid")`, `role:
  Literal["consumer", "publisher"]`), the existing-role short-circuit, the UPDATE and the audit event; in
  `apps/admin-api/src/admin_api/api/internal.py` add `role` to the SELECT and to the 200 body.

- [x] 3.2 Tests first, new file `apps/mcp-server/tests/test_agent_context_role.py`, covering the scenario "the MCP
  client keeps the role": it patches `httpx.AsyncClient` in `mcp_server.admin_api_client` with a fake whose `post`
  returns an object with `status_code` 200 and `json()`; it fails before the change because `AgentContext` has no
  `role`. Then in `apps/mcp-server/src/mcp_server/admin_api_client.py` add `role: str = "consumer"` to `AgentContext` and
  read `data.get("role")` through `mintkey_models.roles.normalize_role`. `mcp_server.auth.agent_key.validate_agent_key`
  is unchanged (it already returns the body as the context).

## 4. Service owner in the operator API, and the transfer

- [ ] 4.1 Tests first, new file `tests/unit/admin_api/test_service_ownership.py`, covering the scenarios of "Service
  responses carry the owner", "An operator transfers a service's ownership" (with `admin_api.api.services.notify_change`
  patched and its calls compared with the payloads of the spec), "Operators keep full control of every service" and the
  transfer half of "the error bodies". The fake session answers the agent lookup of the transfer (a statement containing `FROM agents`) with a
  row of `status` and `role`, and the service lookup (a statement containing `FROM services`) with a service row. Each
  fails before the change (no owner keys, no transfer route, the SELECTs lack the columns). Then in
  `apps/admin-api/src/admin_api/api/services.py` add the two columns to the four SELECTs and to
  `_service_row_to_dict`, add the `owner_agent_id` query parameter to `list_services` (filter after the fetch), and add
  the transfer route, its body model (`to_agent_id: Optional[str]` with no default, so the key is required), the
  service lookup `FOR UPDATE`, the checks in the order of the spec, the UPDATE, the audit event and the NOTIFY. Decode the agent id with `_wire_id_to_uuid(value,
  "agent_")` of `admin_api.api.agents` and encode with `db_uuid_to_wire(value, "agent")`.

## 5. The audit contract

- [ ] 5.1 Tests first, new file `tests/unit/admin_api/test_audit_schema_roles.py` (loads
  `docs/architecture/contracts/events/audit-event.schema.json` with `json.loads`), covering the scenario "the contract
  lists both events"; it fails before the change because neither definition exists. Then add `ev_agent_role_changed`
  and `ev_service_ownership_transferred` to `$defs` (modelled on `ev_agent_revoked`), their `$ref`s to `oneOf` and their
  event types to `discriminator.mapping`. The admin UI's audit filter list is not changed here.
