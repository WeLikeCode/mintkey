# Tasks: agent-auth-unavailable

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run the
touched suite, `ruff check` and (admin-api) `mypy --strict src/admin_api/`.

## 1. The REST middleware answers 503 when the key could not be checked

- [ ] 1.1 Tests first, new file `apps/mcp-server/tests/test_rest_auth_unavailable.py`: build the app the way
  `_build_app` in `apps/mcp-server/tests/test_bearer_auth.py` does (a fake `validate_agent_key` set on
  `mcp_server.main`, `get_db_session` overridden with an `AsyncMock` session), and cover the six scenarios of the
  requirement "A REST request whose agent key could not be checked gets 503 auth_unavailable": list_services with a
  Bearer key and `(None, "service_unavailable")` gives 503, the body `{"code": "mintkey:auth_unavailable"}`,
  `Retry-After: 1` and an unused session; request_token with `X-API-Key` gives the same and the body holds no key;
  `"invalid_key"` gives 401 `mintkey:auth_required`; a valid context gives 200; no key means no call and 401; `/health`
  means no call and 200. They fail before the change because the middleware ignores the reason (401 instead of 503).
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
  monkeypatched to raise. Cover the four scenarios of the requirement "admin-api answers 503 when the verify fails for a
  reason other than the key": `MemoryError` on a known agent gives 503 `{"mintkey:code":
  "mintkey:verify_unavailable"}`; `VerifyMismatchError` and `InvalidHashError` give 401 `INVALID_KEY_RESPONSE`; an
  unknown key with a `MemoryError` from the dummy verify gives 401. The first fails before the change (401 instead of
  503). Then in `apps/admin-api/src/admin_api/api/internal.py`, `validate_agent_key`: add
  `VERIFY_UNAVAILABLE_RESPONSE: dict[str, object] = {"mintkey:code": "mintkey:verify_unavailable"}` and replace the
  known-agent branch's `except Exception` by `except (VerificationError, InvalidHashError)` (401, as today) followed by
  `except Exception` returning `JSONResponse(status_code=503, content=VERIFY_UNAVAILABLE_RESPONSE)`. The unknown-key
  branch is unchanged.

## 3. admin-api's memory limit fits its verify concurrency

- [ ] 3.1 Tests first, new file `tests/acceptance/test_admin_api_verify_capacity.py`: a helper that turns a memory
  value (`512m`, `1g`, `512Mi`, `1Gi`) into MiB, and a check `required_mib(concurrency) = concurrency * 64 + 256`
  applied to the `admin-api` service of `infra/compose/docker-compose.yml` and `infra/compose/docker-compose.ghcr.yml`
  (its `mem_limit` and `environment`) and to `adminApi` in `deploy/helm/mintkey/values.yaml`
  (`resources.limits.memory`; the concurrency from an entry named `MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY` in
  `global.extraEnv`, or in `adminApi.extraEnv` when that key exists, else 4). Cover
  the three scenarios of the requirement "admin-api's memory limit fits its verify concurrency": the three files give
  512 MiB each; an in-memory definition with concurrency 8 and 512 MiB fails with a message naming the file, the limit
  and 768 MiB; a definition without a limit is skipped. The first fails before the change (256 MiB). Then set
  `mem_limit: 512m` for `admin-api` in both compose files and `limits: {cpu: "500m", memory: "512Mi"}` for `adminApi`
  in `deploy/helm/mintkey/values.yaml`.
