# Tasks: agent-service-routes

Each task writes its tests first and sees them fail for the reason it names, then changes the code; a new module is
stubbed by the red step with the names and signatures of the spec (functions raise `NotImplementedError`). Run the touched
suites, `ruff check` and `mypy --strict` (`apps/admin-api` `src/admin_api/`). No test needs a database, a network or a
clock: DNS goes through `resolve_host` of `mintkey_models.egress`, the vault through a fake `put_credential`.

Route tests build a `FastAPI()` with the `agent.router` of `admin_api/api/agent.py`, `agent_api_error_handler` and
`validation_error_handler`, `get_db_session` overridden with a fake session (records `(str(statement), params)`, answers by
substrings of the statement, raises `IntegrityError` on request), `require_agent_principal` overridden to return
`AgentPrincipal(<tenant UUID>, <agent UUID>, "publisher")`, `get_vault_client` overridden with a fake, and `audit_emit`,
`notify_change` and `check_agent_target_url` patched at `admin_api.api.agent_services`.

## 1. The owned-service lookup

- [ ] 1.1 Tests first, new file `tests/unit/admin_api/test_agent_publishing_service.py`, covering the three scenarios of "The
  owned service lookup is one function" (the fake session answers a statement containing `FROM services` with the service
  row: `owner_agent_id`, `base_url`, `auth_scheme` and a `credential_set` flag). Red stubs
  `apps/admin-api/src/admin_api/services/agent_publishing.py` with the three names of the spec. Then fill it in.

## 2. Create and list

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_agent_services_create.py`, covering the three scenarios of "A
  publisher creates a service" and the scenario of "A publisher lists its own services". Red creates
  `apps/admin-api/src/admin_api/api/agent_services.py` (a `router` with no routes) and `apps/admin-api/src/admin_api/api/agent.py`
  (`router = APIRouter(prefix="/v1/agent")` including it). Then add the POST and the GET routes; the service id is derived
  as `create_service` of `apps/admin-api/src/admin_api/api/services.py` does (`_new_svc_id`, 128-bit decode).

## 3. Update

- [ ] 3.1 Tests first, new file `tests/unit/admin_api/test_agent_services_update.py`, covering the five scenarios of "A
  publisher updates only its own services". Then add the PATCH route to `apps/admin-api/src/admin_api/api/agent_services.py`
  (every body with `extra="forbid"`).

## 4. The credential

- [ ] 4.1 Tests first, new file `tests/unit/admin_api/test_agent_credential.py`, covering the four scenarios of "A credential
  is written, never read, and bound to its target" (the fake vault records its `put_credential` call and keywords and can
  raise). Then add the PUT route to `apps/admin-api/src/admin_api/api/agent_services.py` (it takes the `Request`, reads
  `await request.json()` and validates by hand with fixed 422 titles; no request model), with the statements of steps 3b
  to 4 of `create_credential` in `apps/admin-api/src/admin_api/api/credentials.py` (same SQL, no operator checks), passing
  `egress_scope="public"` to `put_credential`.

## 5. The audit contract

- [ ] 5.1 Tests first, new file `tests/unit/admin_api/test_audit_schema_agent_services.py` (loads
  `docs/architecture/contracts/events/audit-event.schema.json`), covering the scenario "the contract lists them"; it fails
  before the change. Then edit the schema file. The admin UI's audit filter list is not changed here.

## 6. Wiring, isolation and the snapshot

- [ ] 6.1 Tests first, new file `tests/unit/admin_api/test_agent_routes_isolation.py` (builds `create_app()` with
  `MINTKEY_AUDIT_HMAC_KEY` and `MINTKEY_VAULT_BACKEND=sqlite` set as `tests/architecture/test_authz_coverage.py` does,
  walks the routes and their dependency trees, sends the cookie-less POST with `httpx.ASGITransport`, and reads
  `tests/acceptance/openapi_snapshot.json`), covering the three scenarios of "The agent routes are separate from the
  operator routes" (the consumer scenario patches `admin_api.auth.agent_principal.AsyncSessionLocal` and `audit_emit` as
  `tests/unit/admin_api/test_agent_role_refusal.py` does). Then in `apps/admin-api/src/admin_api/main.py` import `router as agent_router` from `admin_api.api.agent`,
  include it, register `agent_api_error_handler` for `AgentApiError` and call `csrf_exempt("/v1/agent")`. In the same task
  edit the data fixture `tests/acceptance/openapi_snapshot.json`: add exactly the entry `"agent": "/v1/agent"` (in key order,
  before `"agent_secrets"`) and change no other line. This edit is part of the
  reviewed text of this task. If L4 holds the file as a data fixture and raises a question, the expected answer is: allow
  exactly this entry. The end state of the task: `tests/acceptance/test_openapi_parity.py` passes, and so does the new test.
