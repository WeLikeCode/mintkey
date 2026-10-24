# Agent key authentication

## Purpose

How the MCP server and admin-api answer a request authenticated by an agent key when the key is valid, rejected, or
could not be checked, and the capacity admin-api needs to check keys without timing out.

## ADDED Requirements

### Requirement: A REST request whose agent key could not be checked gets 503 auth_unavailable
The MCP server's HTTP middleware SHALL answer a request on a path outside its auth bypass list that carries an
`mk_agent_` key (`Authorization: Bearer` or `X-API-Key`) with status 503, the body `{"code": "mintkey:auth_unavailable"}`
and the header `Retry-After: 1`, without running the route, when `validate_agent_key` returns the reason
`service_unavailable`. The body SHALL be the same for every cause and SHALL NOT contain the key. Every other case SHALL
behave as before.

#### Scenario: admin-api cannot judge the key on list_services
- **WHEN** `GET /v1/tools/list_services` carries `Authorization: Bearer mk_agent_<key>` and `validate_agent_key`
  returns `(None, "service_unavailable")`
- **THEN** the response is 503 with the body `{"code": "mintkey:auth_unavailable"}` and `Retry-After: 1`, and the
  route's database session is never used

#### Scenario: the same answer on request_token and with X-API-Key
- **WHEN** `POST /v1/tools/request_token` carries `X-API-Key: mk_agent_<key>` and `validate_agent_key` returns
  `(None, "service_unavailable")`
- **THEN** the response is the same 503 with the same body and `Retry-After: 1`, and the body does not contain the key

#### Scenario: a rejected key still gets 401
- **WHEN** `GET /v1/tools/list_services` carries an `mk_agent_` key and `validate_agent_key` returns
  `(None, "invalid_key")`
- **THEN** the response is 401 with the body `{"code": "mintkey:auth_required"}`

#### Scenario: a valid key still gets through
- **WHEN** `GET /v1/tools/list_services` carries an `mk_agent_` key and `validate_agent_key` returns an agent context
- **THEN** the response is 200

#### Scenario: no agent key, no validation
- **WHEN** `GET /v1/tools/list_services` carries no `mk_agent_` key
- **THEN** `validate_agent_key` is not called and the response is 401 `{"code": "mintkey:auth_required"}`

#### Scenario: a bypass path is served while admin-api is down
- **WHEN** `GET /health` carries an `mk_agent_` key and `validate_agent_key` would return
  `(None, "service_unavailable")`
- **THEN** `validate_agent_key` is not called and the response is 200

### Requirement: admin-api answers 503 when the verify fails for a reason other than the key
`POST /v1/internal/validate-agent-key` SHALL answer 503 with the body `{"mintkey:code": "mintkey:verify_unavailable"}`
when the Argon2id verify of a known agent's stored hash raises an exception that is neither
`argon2.exceptions.VerificationError` nor `argon2.exceptions.InvalidHashError`. A mismatch, an invalid stored hash, an
unknown key, a status other than `active` and an expired key SHALL keep the 401 `INVALID_KEY_RESPONSE`.

#### Scenario: an unexpected error in the verify of a known agent
- **WHEN** the fingerprint lookup finds an active agent and the verify raises `MemoryError`
- **THEN** the response is 503 with the body `{"mintkey:code": "mintkey:verify_unavailable"}`

#### Scenario: a mismatch is still a 401
- **WHEN** the fingerprint lookup finds an active agent and the verify raises `argon2.exceptions.VerifyMismatchError`
- **THEN** the response is 401 with `INVALID_KEY_RESPONSE`

#### Scenario: an invalid stored hash is still a 401
- **WHEN** the fingerprint lookup finds an active agent and the verify raises `argon2.exceptions.InvalidHashError`
- **THEN** the response is 401 with `INVALID_KEY_RESPONSE`

#### Scenario: an unknown key stays a 401 whatever the dummy verify raises
- **WHEN** the fingerprint lookup finds no agent and the `DUMMY_HASH` verify raises `MemoryError`
- **THEN** the response is 401 with `INVALID_KEY_RESPONSE`

### Requirement: admin-api's memory limit fits its verify concurrency
Every admin-api definition in the repository that sets a memory limit (the `admin-api` service's `mem_limit` in
`infra/compose/docker-compose.yml` and `infra/compose/docker-compose.ghcr.yml`, and `adminApi.resources.limits.memory`
in `deploy/helm/mintkey/values.yaml`) SHALL be at least `C x 64 MiB + 256 MiB`, where C is
`MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY` in that definition's environment, else 4. Each of the three SHALL be 512 MiB.

#### Scenario: the three definitions fit the rule
- **WHEN** the test reads the three files
- **THEN** each admin-api memory limit is 512 MiB, at least `4 x 64 + 256` MiB

#### Scenario: a definition that does not fit is reported
- **WHEN** the rule is applied to a definition with `MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY: "8"` and a 512 MiB limit
- **THEN** it fails, naming the file, the limit and the required 768 MiB

#### Scenario: a definition without a limit is not checked
- **WHEN** an admin-api definition sets no memory limit
- **THEN** the rule does not apply to it and the test does not fail on it
