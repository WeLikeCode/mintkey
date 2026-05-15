# Acceptance Tests

End-to-end acceptance tests for the Mintkey stack. All tests in this directory
target the real running docker-compose stack unless marked otherwise.

## Prerequisites

```bash
make dev          # starts all services
```

Set `MINTKEY_INTEGRATION_TEST=true` to run any test that hits live services.

---

## WS-4: Data-Plane Smoke + Resilience Tests

Added in WS-4. These tests harden the data-plane (broker, vault-adapter,
proxy-plugin, Kong) with per-service smoke tests and failure-injection scenarios.

### How to run

```bash
# Smoke tests only
make test-data-plane-smoke

# Resilience tests only
make test-data-plane-resilience

# Both (the full data-plane suite)
make test-data-plane
```

Or directly:

```bash
MINTKEY_INTEGRATION_TEST=true pytest tests/acceptance/test_data_plane_smoke.py -v
MINTKEY_INTEGRATION_TEST=true pytest tests/acceptance/test_data_plane_resilience.py -v
```

---

### Smoke Tests (`test_data_plane_smoke.py`)

Each smoke test does the smallest meaningful interaction with one data-plane
component to confirm it is running and responding correctly.

| Test | Component | What it covers |
|------|-----------|---------------|
| `test_broker_smoke` | Broker (`localhost:8083`) | POST `/v1/issue` with `X-Mintkey-Service-Token`; asserts JWT shape: `alg=EdDSA`, `kid` present, `iss=mintkey/broker`, `jti_` prefix, `exp` in future. Source: ADR-0006. |
| `test_vault_adapter_smoke` | Vault Adapter (`localhost:8084` gRPC) | gRPC `PutCredential` → `GetCredential` round-trip; asserts returned plaintext matches stored value; second `PutCredential` increments `key_version` by exactly 1. Source: ADR-0011, T-1.3.1. |
| `test_proxy_plugin_smoke` | Proxy Plugin (via Kong `localhost:8000`) | Creates agent + service + credential + permission; obtains JWT via MCP; calls Kong `/v1/call/{svc_id}/api-key-header`; asserts mock-backend `received_key` == registered secret and JWT is stripped from response. Source: ADR-0004, WS-9. |
| `test_kong_smoke` | Kong (`localhost:8001` admin) | Kong admin root returns `200` with `version`; route table contains at least one `/v1/call/<uuid>` entry pushed by kong-syncer. Source: ADR-0007. |

---

### Resilience Scenarios (`test_data_plane_resilience.py`)

Failure-injection tests. Each scenario sets up a bad state, acts, and asserts
safe failure — no credential leaks, no unexpected HTTP codes.

#### Scenario A: Revoked agent (`test_revoked_agent_cannot_issue_jwt`)

- **Setup**: creates an agent + service + permission; verifies MCP `request_token`
  succeeds (baseline).
- **Action**: calls `POST /v1/tenants/{tid}/agents/{aid}/revoke` to revoke the agent.
- **Assertion**: MCP `request_token` returns `401`/`403` within the revocation
  propagation window (≤6s polling; ADR-0014.1 SLA is ≤5s).
- **Assertion**: rejection response does not contain a JWT-shaped string (`eyJ…`).
- **Idempotency**: each run creates a unique agent by timestamp; revocation is
  permanent for that agent; does not affect other tests.

#### Scenario B: Expired JWT at proxy (`test_expired_jwt_rejected_by_proxy`)

- **Setup**: creates a service; obtains a real JWT to extract the `kid` from its
  header; builds a forged JWT with `exp = now - 120` (2 minutes ago) and an
  invalid signature.
- **Action**: calls `GET /v1/call/{svc_id}/api-key-header` with the forged JWT.
- **Assertion**: proxy returns `401` (the proxy verifier rejects on
  signature/exp before ever reaching vault).
- **Assertion**: `401` body does not contain the credential plaintext.
- **Design note**: the broker's signing key is ephemeral (generated at startup),
  so the forged signature will always be invalid even if `exp` is in the future.

#### Scenario C: Vault-adapter unavailable (`test_vault_down_returns_502_no_cred_leak`)

- **Setup**: creates agent + service + credential; confirms baseline proxy call
  returns `200` (stack fully healthy); issues a fresh JWT immediately before pausing.
- **Action**: `docker compose pause vault-adapter`.
- **Assertion**: proxy returns `502 Bad Gateway`.
- **SECURITY assertion**: `502` body does NOT contain the credential plaintext.
- **SECURITY assertion**: `502` body does NOT contain the JWT.
- **SECURITY assertion**: `502` body is < 512 bytes (no verbose error dump).
- **Teardown**: `docker compose unpause vault-adapter`; waits for
  `vault-adapter:8087/metrics` to respond `200` before returning.
- **Idempotency**: `finally` block ensures vault-adapter is always unpaused,
  even on test failure. Each run creates unique service/credential by timestamp.

#### Scenario D: Wrong scope / cross-service JWT (`test_wrong_scope_jwt_rejected`)

- **Setup**: creates service A + agent + permission + credential; creates service B
  + credential; issues a JWT scoped for service A (`aud = [svc_uuid_a]`).
- **Action**: calls Kong route for service B (`/v1/call/{svc_uuid_b}/...`) using
  service A's JWT.
- **Assertion**: service B's credential is NOT served (the proxy extracts
  `service_id` from JWT `aud`, not from the URL path). If `200` is returned, the
  `received_key` must be service A's credential, never service B's.
- **Design note**: this confirms the proxy-plugin's aud-based routing is
  authoritative and cannot be overridden by URL path manipulation.

---

### Setup / teardown pattern

All tests create unique resources keyed by `int(time.time())` so multiple runs
never collide. No teardown of admin-api state is performed (seeds are disposable).

Scenario C is the only test that mutates infrastructure (vault-adapter pause).
Its `finally` block always runs `docker compose unpause vault-adapter` so
subsequent tests in the same suite are not affected.

---

## Other acceptance tests

See `ENDPOINT_COVERAGE.md` for full endpoint coverage mapping.

Key tests:
- `test_golden_path.py` — WS-8 full cross-stack E2E (agent → MCP → broker → Kong → vault → mock-backend)
- `test_revocation_timing.py` — ADR-0014.1 revocation propagation SLA (≤5s)
- `test_rotation_propagation.py` — credential rotation end-to-end
- `test_audit_chain.py` — audit log hash-chain integrity
- `test_no_plaintext_in_audit.py` — credential hygiene in audit events
