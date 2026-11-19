# agent-key-auth Specification

## Purpose
How the MCP server and admin-api answer a request authenticated by an agent key when the key is valid, rejected, or
could not be checked, and the capacity admin-api needs to check keys without timing out.

## Requirements

### Requirement: A REST request whose agent key could not be checked gets 503 auth_unavailable
The MCP server's HTTP middleware SHALL answer a request on a path outside its auth bypass list that carries an
`mk_agent_` key (`Authorization: Bearer` or `X-API-Key`) with status 503, the body `{"code": "mintkey:auth_unavailable"}`
and the header `Retry-After: 1`, without running the route, when `validate_agent_key` returns the reason
`service_unavailable`. The body SHALL be the same for every cause and SHALL NOT contain the key.

#### Scenario: admin-api cannot judge the key on list_services
- **WHEN** `GET /v1/tools/list_services` carries `Authorization: Bearer mk_agent_<key>` and `validate_agent_key`
  returns `(None, "service_unavailable")`
- **THEN** the response is 503 with the body `{"code": "mintkey:auth_unavailable"}` and `Retry-After: 1`, and the
  route's database session is never used

#### Scenario: the same answer on request_token and with X-API-Key
- **WHEN** `POST /v1/tools/request_token` carries `X-API-Key: mk_agent_<key>` and `validate_agent_key` returns
  `(None, "service_unavailable")`
- **THEN** the response is the same 503 with the same body and `Retry-After: 1`, and the body does not contain the key

### Requirement: admin-api answers 503 when the verify fails for a reason other than the key
`POST /v1/internal/validate-agent-key` SHALL answer 503 with the body `{"mintkey:code": "mintkey:verify_unavailable"}`
when the Argon2id verify of a known agent's stored hash raises an `Exception` that is neither
`argon2.exceptions.VerificationError` (which `VerifyMismatchError` subclasses) nor `argon2.exceptions.InvalidHashError`
(a `ValueError` subclass), and SHALL log one WARNING `validate-agent-key: verify failed (<exception class name>)` that
names only the exception class, never the key, the hash or the agent. `asyncio.CancelledError` is a `BaseException`
and SHALL NOT be caught. A mismatch, an invalid stored hash, an unknown key, a status other than `active` and an
expired key SHALL keep the 401 `INVALID_KEY_RESPONSE` and log nothing new.

#### Scenario: an unexpected error in the verify of a known agent
- **WHEN** the fingerprint lookup finds an active agent and the verify raises `MemoryError`
- **THEN** the response is 503 with the body `{"mintkey:code": "mintkey:verify_unavailable"}`, and one WARNING record
  of the logger `admin_api.api.internal` says `validate-agent-key: verify failed (MemoryError)` and does not contain
  the key

#### Scenario: a mismatch is still a 401
- **WHEN** the fingerprint lookup finds an active agent and the verify raises `argon2.exceptions.VerifyMismatchError`
- **THEN** the response is 401 with `INVALID_KEY_RESPONSE` and no WARNING is logged

#### Scenario: an invalid stored hash is still a 401
- **WHEN** the fingerprint lookup finds an active agent and the verify raises `argon2.exceptions.InvalidHashError`
- **THEN** the response is 401 with `INVALID_KEY_RESPONSE` and no WARNING is logged

#### Scenario: an unknown key stays a 401 whatever the dummy verify raises
- **WHEN** the fingerprint lookup finds no agent and the `DUMMY_HASH` verify raises `MemoryError`
- **THEN** the response is 401 with `INVALID_KEY_RESPONSE`

#### Scenario: a cancelled request is not turned into an answer
- **WHEN** the fingerprint lookup finds an active agent and the verify raises `asyncio.CancelledError`
- **THEN** `validate_agent_key` raises `asyncio.CancelledError` and returns no response

### Requirement: admin-api's memory limit fits its verify concurrency
Each admin-api definition below SHALL set a memory limit of at least `C x 64 + 256` MiB, C being its verify
concurrency, and each SHALL be 512 MiB after this change:
- `infra/compose/docker-compose.yml` and `infra/compose/docker-compose.ghcr.yml`: the string
  `services.admin-api.mem_limit` (today `256m`). C is `int()` of `services.admin-api.environment` (a mapping) at the
  key `MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY` when the key is there, else 4. Neither file sets it today.
- `deploy/helm/mintkey/values.yaml`: the string `adminApi.resources.limits.memory` (today `256Mi`). C is 4: the chart
  passes no `MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY` to admin-api (`global.extraEnv` reaches the Go services only).
  Only that value changes: `adminApi.resources` becomes `{requests: {cpu: "100m", memory: "128Mi"}, limits: {cpu:
  "500m", memory: "512Mi"}}`.

The module `admin_api.capacity` (`apps/admin-api/src/admin_api/capacity.py`) SHALL define these, and the test module
`tests/acceptance/test_admin_api_verify_capacity.py` SHALL use them:
- `to_mib(value: str) -> int`: an integer followed by `m`, `M` or `Mi` is that many MiB; followed by `g`, `G` or `Gi`,
  that many times 1024. Any other string SHALL raise `ValueError` whose message contains the string.
- `required_mib(concurrency: int) -> int`: `concurrency * 64 + 256`.
- `compose_concurrency(environment: Mapping[str, object] | None) -> int`: `int()` of the value at
  `MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY` when the mapping has that key, else 4.
- `capacity_problem(name: str, limit: str | None, concurrency: int) -> str | None`: `None` when `limit` is `None` or
  `to_mib(limit) >= required_mib(concurrency)`; else `"<name>: admin-api memory limit <limit> (<to_mib(limit)> MiB) is
  below the required <required_mib(concurrency)> MiB for <concurrency> concurrent verifies"`.

A missing file, a missing `admin-api` service or `adminApi` block, or a concurrency that is not an integer SHALL fail
the test with a message naming the file or the value; nothing is skipped.

#### Scenario: the three definitions fit the rule
- **WHEN** the test reads the three files
- **THEN** each limit converts to 512 MiB and `capacity_problem` returns `None` for each with concurrency 4

#### Scenario: a definition that does not fit is reported
- **WHEN** `capacity_problem("values.yaml", "512Mi", 8)` is called
- **THEN** it returns `"values.yaml: admin-api memory limit 512Mi (512 MiB) is below the required 768 MiB for 8
  concurrent verifies"`

#### Scenario: a definition without a limit is not checked
- **WHEN** `capacity_problem("x", None, 4)` is called
- **THEN** it returns `None`

#### Scenario: memory values convert, and others are refused
- **WHEN** `to_mib` is given `512m`, `512M`, `512Mi`, `1g`, `1G`, `1Gi`, then `512`, `512k`, `512 Mi`, `` and `abc`
- **THEN** the first six give 512, 512, 512, 1024, 1024 and 1024, and each of the others raises `ValueError` whose
  message contains it

#### Scenario: a broken definition fails the test, never skips it
- **WHEN** a compose environment sets `MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY: "four"`
- **THEN** `compose_concurrency` raises `ValueError` naming `four`

### Requirement: to_mib refuses 512mi, 1gi and non-ASCII digits — feedback FB-001
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: to_mib refuses 512mi, 1gi and non-ASCII digits
- **WHEN** to_mib is given 512mi, 1gi, or 512m written with non-ASCII digits (the full-width ５１２m)
- **THEN** it raises ValueError whose message contains the string, as it already does for 512, 512k, '512 Mi', '' and abc; only ASCII digits followed by exactly m, M, Mi, g, G or Gi convert
