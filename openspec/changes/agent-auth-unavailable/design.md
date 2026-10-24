# Design: agent-auth-unavailable

## Context

`agent_key_middleware` (`apps/mcp-server/src/mcp_server/main.py`) takes the key from `Authorization: Bearer mk_agent_…`
or `X-API-Key: mk_agent_…`, calls `validate_agent_key` (`mcp_server.auth.agent_key`) and sets
`request.state.agent_context` on success. Each REST tool reads it through `get_agent_context`
(`mcp_server.tools.discovery`) and answers 401 `mintkey:auth_required` when it is missing. `validate_agent_key`
already returns a reason: `"invalid_key"` when admin-api answered 4xx, `"service_unavailable"` on a timeout, a
connection error or a 5xx. Paths in the middleware's bypass list (`/health`, `/v1/health`, `/metrics`,
`/v1/tools/instructions`, `/v1/tools/bootstrap`, `/`, `/v1`, `/mcp`, `/v1/mcp`, `/v1/tools`) are not validated by the
middleware; the JSON-RPC dispatcher behind `/`, `/mcp` and `/v1/mcp` validates the key itself.

## Decisions

**D1. The middleware answers the 503 itself.** One place covers every REST tool; the dozen `agent_ctx is None` checks
in the tool modules stay as they are and keep answering 401 for a missing or rejected key. When a key was found and
the reason is `"service_unavailable"`, the middleware returns `JSONResponse(status_code=503, content={"code":
"mintkey:auth_unavailable"}, headers={"Retry-After": "1"})` without calling the route. Status 503 with `Retry-After` is
what HTTP clients and agents already treat as "try again"; 401 tells them to fix their credentials.

**D2. The 503 leaks nothing about the key.** The key was never judged, so the answer cannot depend on it: the same
constant body for a timeout, a connection error and a 5xx, and no echo of the key or its prefix. The
agent-enumeration guard (Req 6 AC2: every rejection has the same body) still holds, because every rejection still
answers the same 401.

**D3. admin-api separates "the key is wrong" from "the check broke".** In `validate_agent_key`
(`apps/admin-api/src/admin_api/api/internal.py`), the verify of a known agent's stored hash catches
`argon2.exceptions.VerificationError` (`VerifyMismatchError` subclasses it) and `argon2.exceptions.InvalidHashError`
(a `ValueError` subclass, raised for a malformed stored hash) as today's 401: both concern the key or its stored hash.
Any other `Exception` (a `MemoryError`, a failure of the thread the verify runs in) answers 503 with
`{"mintkey:code": "mintkey:verify_unavailable"}` and logs one WARNING naming the exception class only. The MCP server
already reads any admin-api status of 500 or more as `"service_unavailable"` (`mcp_server.auth.agent_key`), so this 503
becomes the middleware's 503 of D1; each half is tested on its own side. `asyncio.CancelledError` is a `BaseException`
and propagates. The unknown-key branch (the `DUMMY_HASH` verify) keeps its 401 whatever the verify raises: the
fingerprint lookup has already found no agent. Timing equalisation (ADR-0017.5) covers the normal outcomes and is
unchanged; the new branch is an abnormal one.

**D4. The memory limit is derived from the concurrency, not tuned by hand.** The rule is
`limit >= C x 64 MiB + 256 MiB`. 64 MiB is the memory cost of `argon2.PasswordHasher()`'s defaults (65536 KiB), which
the stored hashes use; 256 MiB covers the process (about 200 MiB measured) with headroom. In compose, C is
`MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY` in the service's `environment` mapping, else 4, the code default; in the Helm
chart C is always 4, because no value reaches admin-api's environment (`global.extraEnv` is for the Go services). With
C = 4 the limit is 512 MiB: `mem_limit: 512m` in `infra/compose/docker-compose.yml` and
`infra/compose/docker-compose.ghcr.yml`, and `adminApi.resources.limits.memory: 512Mi` in
`deploy/helm/mintkey/values.yaml`, whose CPU limit (`500m`) and requests stay as they are. Lowering C instead would
make bursts queue longer behind the 5 s timeout, which is the symptom being fixed.

**D5. What is not changed.** No validation cache (it would keep a revoked key working for its lifetime), no new
timeout, no Argon2id parameter change, and no change to the JSON-RPC path, which already answers `-32603` for the same
reason.

## Failure cases

- admin-api down or slow during a REST tool call: 503 `mintkey:auth_unavailable`, `Retry-After: 1`, the route not run.
- admin-api answers 4xx: 401 `mintkey:auth_required` from the tool, as before.
- No `mk_agent_` key: no validation, the tool's 401 as before.
- A bypass path while admin-api is down: served without validation, as before.
- The verify of a known hash raises an unexpected exception: admin-api 503, then the MCP server's 503.
- An admin-api definition without a memory limit (`docker-compose.test.yml`, `docker-compose.e2e.yml`): not checked;
  there is no cap to fit.
