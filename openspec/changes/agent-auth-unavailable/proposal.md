# A valid agent key that could not be checked is not a 401

## Why

A REST tool call with a valid agent key sometimes fails with `401 {"code": "mintkey:auth_required"}`, the answer for
a missing or wrong key. The agent then believes its key is revoked. Seen on a local stack on 2026-10-24: twelve
`GET /v1/tools/list_services` calls one second apart with the same key gave 200 in about 0.15 s seven times, then 401
after 5.7 to 8.8 s four times, and 200 after 6.3 s once. The MCP server's log of that stack shows 9 such 401s; over
the same period admin-api answered 2,064 of 2,065 `POST /v1/internal/validate-agent-key` calls with 200 (the other
one was a 500 while Postgres was in recovery).

Two faults combine:

1. **The REST path drops the reason.** `mcp_server.auth.agent_key.validate_agent_key` returns
   `(None, "service_unavailable")` when admin-api times out (5 s), cannot be reached or answers 5xx: the key was never
   judged. `agent_key_middleware` in `apps/mcp-server/src/mcp_server/main.py` ignores that reason and leaves no agent
   context, so every REST tool answers 401 `mintkey:auth_required`. The JSON-RPC dispatcher already tells the two
   apart (`-32603 "Auth service temporarily unavailable; retry"` in `mcp_server.tools.jsonrpc`); the REST tools do not.
2. **admin-api runs out of memory headroom while it verifies.** Each Argon2id verify allocates the stored hash's
   memory cost (64 MiB at the `argon2.PasswordHasher()` defaults the keys are hashed with), and
   `admin_api.api.internal` runs up to `MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY` (default 4) at once. Its own comment says
   to size the container at "concurrency * ~64 MiB + base RSS". The limit is `mem_limit: 256m` in
   `infra/compose/docker-compose.yml` and `infra/compose/docker-compose.ghcr.yml`, and `256Mi` in
   `deploy/helm/mintkey/values.yaml`, while the process alone uses about 200 MiB (`docker stats`: 200.4 MiB of 256 MiB).
   One verify then pushes the container into swap, and a check that takes 0.15 s takes seconds, past the MCP server's
   5 s timeout.

A third, smaller fault has the same shape: when the verify of a known agent's hash raises something other than a
mismatch (for example `MemoryError`), `validate_agent_key` in admin-api answers 401, so the MCP server treats a key
that was never judged as rejected.

## What Changes

- The MCP server's HTTP middleware answers a request whose `mk_agent_` key could not be judged with
  `503 {"code": "mintkey:auth_unavailable"}` and `Retry-After: 1`, and does not run the route. A rejected key, a
  request without a key, the auth bypass paths and the JSON-RPC dispatcher behave as before.
- admin-api's `POST /v1/internal/validate-agent-key` answers 503 `{"mintkey:code": "mintkey:verify_unavailable"}`
  when the verify of a known agent's hash raises anything other than `argon2.exceptions.VerificationError` or
  `argon2.exceptions.InvalidHashError`. Every key-related failure keeps its 401.
- admin-api's memory limit becomes 512 MiB in both compose files and in the Helm values: 4 verifies x 64 MiB plus
  256 MiB for the process. A test checks the rule on every admin-api definition that sets a limit.

## Capabilities

### New Capabilities
- `agent-key-auth`: how a request authenticated by an agent key is answered when the key is valid, rejected, or could
  not be checked, and the capacity admin-api needs to check keys.

## Impact

- Changed: `apps/mcp-server/src/mcp_server/main.py` (`agent_key_middleware`),
  `apps/admin-api/src/admin_api/api/internal.py` (`validate_agent_key`), `infra/compose/docker-compose.yml`,
  `infra/compose/docker-compose.ghcr.yml` and `deploy/helm/mintkey/values.yaml` (the admin-api memory limit).
- New tests: `apps/mcp-server/tests/test_rest_auth_unavailable.py`,
  `tests/unit/admin_api/test_validate_agent_key_errors.py`, `tests/acceptance/test_admin_api_verify_capacity.py`.
- Clients: a REST client sees 503 with `Retry-After` instead of 401 for a check that did not happen, and can retry.
  No response body says whether a key exists.
- Out of scope: caching validation results, changing the 5 s timeout, the Argon2id parameters, or the JSON-RPC path.

## Issue Intake (remediation gate)

1. **Problem statement**: a REST tool call with a valid, active agent key is answered 401 `mintkey:auth_required`
   when admin-api is slow, unreachable or failing.
2. **User-visible symptom**: an agent's `list_services` or `request_token` fails as if its key were wrong, at random;
   a retry seconds later works.
3. **Expected behavior**: a key that was checked and rejected gets 401; a key that could not be checked gets 503 with
   `Retry-After`; on a healthy stack the check stays well under the 5 s timeout.
4. **Evidence**: the timings and log counts under Why, and the memory reading of the admin-api container.
5. **Scope**: the three changes above.
6. **Risk**: low. The 503 body is one constant and says nothing about the key; the memory limit only grows.
