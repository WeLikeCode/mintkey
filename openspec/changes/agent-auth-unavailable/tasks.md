# Tasks: agent-auth-unavailable

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run the
touched suite, `ruff check` and (admin-api) `mypy --strict src/admin_api/`.

## 1. The REST middleware answers 503 when the key could not be checked

- [ ] 1.1 Tests first, new file `apps/mcp-server/tests/test_rest_auth_unavailable.py`: build the app the way
  `_build_app` in `apps/mcp-server/tests/test_bearer_auth.py` does (a fake `validate_agent_key` set on
  `mcp_server.main`, `get_db_session` overridden with an `AsyncMock` session), and cover the two scenarios of the
  requirement "A REST request whose agent key could not be checked gets 503 auth_unavailable": list_services with a
  Bearer key and `(None, "service_unavailable")` gives 503, the body `{"code": "mintkey:auth_unavailable"}`,
  `Retry-After: 1` and an unused session; request_token with `X-API-Key` gives the same and the body holds no key.
  They fail before the change because the middleware ignores the reason (401 instead of 503). The cases that keep
  their answer (a rejected key, no key, a valid key, a bypass path) need no new test: the middleware is nested in
  `create_app()`, which the red step's zero-value check cannot reach; `apps/mcp-server/tests/test_bearer_auth.py`
  already covers a valid key and a missing or non-agent key, and the other two keep a code path this task leaves as
  it is.
  Then in `apps/mcp-server/src/mcp_server/main.py`, `agent_key_middleware`: when a key was found and
  `validate_agent_key` returns no context with the reason `"service_unavailable"`, return
  `JSONResponse(status_code=503, content={"code": "mintkey:auth_unavailable"}, headers={"Retry-After": "1"})`;
  everything else unchanged.

## 2. admin-api answers 503 when the verify breaks

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_validate_agent_key_errors.py`: call
  `admin_api.api.internal.validate_agent_key(ValidateAgentKeyRequest(api_key="mk_agent_x"), session)` directly, with
  `session` a fake whose `execute` is an `AsyncMock` (the first call is the `set_config` statement; the second returns
  a result whose `fetchone()` gives a row with `id`, `tenant_id`, `api_key_hash`, `status="active"`,
  `api_key_expires_at=None`, or `None` for the unknown-key case) and `admin_api.api.internal._verify_argon2`
  monkeypatched to raise. Cover the five scenarios of the requirement "admin-api answers 503 when the verify fails for a
  reason other than the key" (`caplog` for the WARNING of the logger `admin_api.api.internal`). The first fails before
  the change (401 instead of 503). Every test asserts `isinstance(response, JSONResponse)` before it reads
  `status_code` or the body, so that a `validate_agent_key` that answers `None` fails it by assertion. Then in
  `apps/admin-api/src/admin_api/api/internal.py`: add
  `logger = logging.getLogger(__name__)`, import `VerificationError` and `InvalidHashError` from `argon2.exceptions`,
  add `VERIFY_UNAVAILABLE_RESPONSE: dict[str, object] = {"mintkey:code": "mintkey:verify_unavailable"}`, and in
  `validate_agent_key` replace the known-agent branch's `except Exception` by `except (VerificationError,
  InvalidHashError)` (401, as today) followed by `except Exception as exc`, which logs
  `logger.warning("validate-agent-key: verify failed (%s)", type(exc).__name__)` and returns
  `JSONResponse(status_code=503, content=VERIFY_UNAVAILABLE_RESPONSE)`. The unknown-key branch is unchanged.

## 3. admin-api's memory limit fits its verify concurrency

- [ ] 3.1 Tests first, new file `tests/acceptance/test_admin_api_verify_capacity.py`, and the new helper module
  `apps/admin-api/src/admin_api/capacity.py` with `to_mib`, `required_mib`, `compose_concurrency` and
  `capacity_problem` exactly as the requirement "admin-api's memory limit fits its verify concurrency" gives them
  (red stubs the module, green fills it in). The test imports them from `admin_api.capacity`, reads the three
  definitions the requirement names with `yaml.safe_load` (compose: `services["admin-api"]["mem_limit"]` and
  `compose_concurrency` of its `environment`; Helm: `adminApi["resources"]["limits"]["memory"]` with concurrency 4),
  and covers its five scenarios. The first fails before the change (256 MiB). Then set
  `mem_limit: 512m` for `admin-api` in `infra/compose/docker-compose.yml` and `infra/compose/docker-compose.ghcr.yml`,
  and change only `adminApi.resources.limits.memory` from `256Mi` to `512Mi` in `deploy/helm/mintkey/values.yaml`
  (the CPU limit `500m` and the requests stay).
