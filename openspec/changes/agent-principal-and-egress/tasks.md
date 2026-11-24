# Tasks: agent-principal-and-egress

Each task writes its tests first and sees them fail for the reason it names, then changes the code; a new module is
stubbed by the red step with the names and signatures of the spec (functions raise `NotImplementedError`). Run the touched
suites, `ruff check`, and `mypy --strict` (`apps/admin-api` `src/admin_api/`, `packages/python/mintkey-models`
`mintkey_models/`). No test needs a database, a network or a clock: DNS goes through `resolve_host`, the sessions are fakes.

## 1. The egress policy

- [ ] 1.1 Tests first, new file `packages/python/mintkey-models/tests/test_egress.py` (`monkeypatch.setattr(egress,
  "resolve_host", ...)` and `setenv`), covering the three scenarios of "Agent-supplied URLs must be public https targets";
  red stubs `packages/python/mintkey-models/mintkey_models/egress.py`. Then fill it in.

## 2. The key check

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_agent_key_check.py` (a fake session answering the key lookup by
  substring; `internal._verify_argon2` patched as `tests/unit/admin_api/test_validate_agent_key_errors.py` does), covering
  the two scenarios of "The key check is one function" (recording fake sessions); the second scenario also runs
  `tests/unit/admin_api/test_validate_agent_key_errors.py` unchanged. Then in `apps/admin-api/src/admin_api/api/internal.py`
  move the `set_config` statement, the lookup, the verify and the expiry branches of `validate_agent_key` into
  `check_agent_key(session, api_key)` (the `set_config` statement first), so that `validate_agent_key` issues no statement
  of its own and answers exactly as before.

## 3. The principal

- [ ] 3.1 Tests first, new file `tests/unit/admin_api/test_agent_principal.py`, covering the five scenarios of "An agent key
  yields a principal": `admin_api.auth.agent_principal.AsyncSessionLocal` is patched with a factory of recording fake
  async-context-manager sessions, `internal.check_agent_key` with an `AsyncMock` (the last scenario uses the real function); the handler runs inside a `FastAPI()`
  with a probe route. Red stubs `apps/admin-api/src/admin_api/auth/agent_principal.py` with every name of the spec
  (`AgentPrincipal`, `AgentApiError`, `agent_api_error_handler`, `agent_error_body`, `require_agent_principal`,
  `require_publisher_principal`, `record_denied_operation`). Then fill in `AgentPrincipal`, `AgentApiError`, the handler, `agent_error_body` and `require_agent_principal` (dedicated session,
  commit, close, 503 on a database failure).

- [ ] 3.2 Tests first, new file `tests/unit/admin_api/test_agent_role_refusal.py` (a `FastAPI()` with the probe route `POST
  /v1/agent/probe` that depends on `require_publisher_principal`, `require_agent_principal` overridden to return an
  `AgentPrincipal`, `AsyncSessionLocal` patched with a fake session factory and `audit_emit` patched at
  `admin_api.auth.agent_principal`), covering the two scenarios of "A role that is too low is refused and recorded". Then
  fill in `require_publisher_principal` and `record_denied_operation` (tenant context first, no platform view) in
  `apps/admin-api/src/admin_api/auth/agent_principal.py`.

## 4. The audit contract

- [ ] 4.1 Tests first, new file `tests/unit/admin_api/test_audit_schema_agent_denied.py` (loads
  `docs/architecture/contracts/events/audit-event.schema.json`), covering the scenario "the contract lists it"; it fails
  before the change. Then edit the schema file. The admin UI's audit filter list is not changed here.
