# Stub Services Plan

> **Status: plan-only.** These stubs are designed but not yet implemented.
> This document is the authoritative plan for the three priority stub services
> needed to make Kiro-generated code testable in CI without external services.

---

## Purpose

Integration and acceptance tests require real service interfaces. Running the full stack
(Keycloak, Kong, the Go vault adapter) adds Docker startup latency and flakiness. Stubs
replace these services in unit and integration test suites with in-memory implementations
that are fast, deterministic, and resetable between tests.

---

## Priority Stubs

### 1. Vault Adapter Stub (in-memory, Go)

**Interface:** Same gRPC surface as `services/vault-adapter`, defined in
`docs/architecture/contracts/vault-adapter/vault.proto`. Required operations:
- `GetCredential(CredentialId, TenantId) → Envelope`
- `StoreCredential(TenantId, Envelope) → CredentialId`
- `RotateCredential(CredentialId, TenantId, NewEnvelope) → CredentialId`

**Location:** `tests/stubs/vault-adapter-stub/`

**Minimum viable scope:**
- In-memory `map[string]Envelope` keyed on credential ID.
- Returns the envelope as-is (no AES-GCM; the `ciphertext` field holds the raw test value).
- Generates deterministic credential IDs (sequential or UUID-seeded).
- State is reset between tests via `POST /reset` (see Uniform Conventions below).
- No key rotation cryptography — accept the new envelope and update the map.

**Language:** Go (matches the production `services/vault-adapter`; ensures interface fidelity).

---

### 2. Kong / Proxy Recorder Stub (HTTP, Go)

**Interface:** HTTP server that records every inbound request and returns a configurable
canned response. Used to verify that the Egress Proxy plugin injected the correct headers
before forwarding to the backend.

**Location:** `tests/stubs/proxy-recorder/`

**Minimum viable scope:**
- Listens on a configurable port (default: 9001 per uniform conventions).
- Records all inbound HTTP requests (method, path, headers, body) to an in-memory slice.
- Responds with a configurable canned response body and status code (default: 200 + `{}`).
- Exposes `GET /recorder/requests` returning the recorded request list as JSON for test
  assertions.
- Resets via `POST /reset` (clears the recorded request list).

**Language:** Go (`net/http` stdlib; no external dependencies).

---

### 3. OIDC / Keycloak Mock (Python, FastAPI)

**Interface:** Subset of Keycloak's OIDC endpoints needed by the admin-api and mcp-server:
- `GET /.well-known/openid-configuration` — discovery document
- `POST /realms/<realm>/protocol/openid-connect/token` — token endpoint (client credentials +
  authorization code flows)
- `GET /realms/<realm>/protocol/openid-connect/userinfo` — userinfo endpoint

**Location:** `tests/stubs/keycloak-mock/`

**Minimum viable scope:**
- Static Ed25519 signing key pair (generated at startup; public key served via JWKS endpoint
  `GET /realms/<realm>/protocol/openid-connect/certs`).
- Canned user fixtures: one `Admin` operator, one `Auditor` operator, one `AgentOwner` operator
  (loaded from a YAML fixture file at startup).
- Issues real JWTs signed with the stub key; includes `sub`, `email`, `realm_access.roles`.
- No admin API, no realm management, no token introspection.
- Resets (reloads fixtures) via `POST /reset`.

**Language:** Python (FastAPI) — matches the admin-api test infrastructure; allows sharing
`pytest` fixtures and `httpx.AsyncClient` patterns from the existing test suite.

---

## Uniform Conventions

All stubs follow these conventions so test harnesses can treat them uniformly:

| Convention | Rule |
|---|---|
| **Port range** | Stubs use ports 9000–9099: vault-adapter-stub on 9000, proxy-recorder on 9001, keycloak-mock on 9002 |
| **Health endpoint** | Every stub exposes `GET /health` → `{"status": "ok"}` |
| **Reset endpoint** | Every stub exposes `POST /reset` with no body → `204 No Content`; clears all recorded state |
| **Configuration** | All ports and behaviour are configurable via environment variables |
| **No external deps** | Stubs use only stdlib + test framework (no DB, no network calls) |
| **Interface fidelity** | Each stub implements the exact same interface as the real service; no shortcuts on the wire surface |

---

## CI Integration Plan

### Unit and integration tests

`tests/integration/` tests that previously required the full Docker stack will mount stubs
directly in the pytest session (Python stubs as `pytest` fixtures; Go stubs launched as
subprocesses via `subprocess.Popen` with a startup health-check poll).

### docker-compose.test.yml

`docker-compose.test.yml` (already exists in the repo root) will gain three stub services:
```yaml
vault-adapter-stub:
  build: tests/stubs/vault-adapter-stub/
  ports: ["9000:9000"]
proxy-recorder:
  build: tests/stubs/proxy-recorder/
  ports: ["9001:9001"]
keycloak-mock:
  build: tests/stubs/keycloak-mock/
  ports: ["9002:9002"]
```

### CI job changes

The `Integration Tests` CI job will switch its `docker-compose` profile from the full Keycloak
and vault-adapter images to the stub images when `MINTKEY_USE_STUBS=true` is set. This reduces
cold-start time from ~90 s to ~5 s for most integration test scenarios.

---

## Implementation priority

Implement in this order (each unblocks the next):

1. **Vault Adapter Stub** — unblocks Credential Broker and Egress Proxy plugin unit tests.
2. **OIDC / Keycloak Mock** — unblocks admin-api auth integration tests (currently require
   a real Keycloak container).
3. **Kong / Proxy Recorder** — unblocks end-to-end Egress Proxy tests that don't need the
   full Kong image.
