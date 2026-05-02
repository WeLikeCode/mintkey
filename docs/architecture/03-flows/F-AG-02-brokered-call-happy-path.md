# F‑AG‑02 — Agent: brokered call (happy path)

## Goal
With a valid JWT in hand, the agent calls the backend service through Kong; the proxy plugin validates the token, fetches the credential, injects it, forwards to the backend, scrubs the response, and emits audit + OTel data.

## Actors
- **Agent** (machine).
- **Kong Gateway** (DB‑less, with the JWT plugin and our custom Go plugin).
- **Egress Proxy plugin** (Go, `go-pdk`).
- **Credential Broker** — JWKS endpoint only (consulted on cache miss).
- **Vault Adapter** (Go) — `GetCredential` over gRPC.
- **Backend service** — the registered API.
- **Audit Service** — emits `proxy.hit`.

## Pre‑conditions
- [F‑AG‑01](F-AG-01-discover-and-request-token.md) complete: agent has a valid JWT.
- Service is registered (F‑OP‑02) with a current credential (F‑OP‑03).
- Permission grant covers the `(service, action)` and ABAC constraints.
- Kong's declarative config has the route for the service (Kong‑syncer pushed it after F‑OP‑02).

## Post‑conditions
- The backend service received the request with the **real credential injected** per its `auth_scheme` and **without** the agent's JWT.
- The agent received the backend's response, scrubbed of any echoed credential.
- One `proxy.hit` audit event with `(jti, agent_id, service_id, action, latency_ms, status, outcome)`.
- One end‑to‑end OTel trace from the agent's request through the Kong plugin, vault decrypt, backend call, and scrubber.

## Sequence diagram

```mermaid
sequenceDiagram
    actor Ag as Agent
    participant Kg as Kong
    participant Plg as Proxy plugin (Go)
    participant Br as Broker (JWKS)
    participant Va as Vault Adapter
    participant Be as Backend
    participant Au as Audit (Admin API)

    Ag->>Kg: GET https://localhost/v1/call/svc_demo/health<br/>Authorization Bearer agentJwt
    Kg->>Plg: access phase
    Plg->>Plg: parse JWT, look up kid in cached JWKS
    alt unknown kid
        Plg->>Br: GET /.well-known/jwks.json (force refresh per ADR-0016.2)
        Br-->>Plg: refreshed JWKS
    end
    Plg->>Plg: verify signature, exp, iss=mintkey/broker, aud=svc_demo, tnt matches service tenant, scope=read:health
    Plg->>Plg: check jti not in revocation set, agent not in revoked-agent set
    Plg->>Va: GetCredential(tenant_id, svc_demo, current key_version) over gRPC
    Va->>Va: fetch encrypted DEK from cache (encrypted DEK only)
    Va->>Va: AES-256-GCM decrypt with KEK (cached)
    Va-->>Plg: plaintext credential, auth_scheme
    Plg->>Plg: build outbound headers: strip agent Authorization, inject per auth_scheme
    Plg->>Plg: enforce egress allowlist (registered base_url, reject cross-origin redirect follow per ADR-0007)
    Kg->>Be: GET base_url + /health (with injected auth)
    Be-->>Kg: 200 OK + body
    Kg->>Plg: response phase (header_filter, body_filter)
    Plg->>Plg: response scrubber strips Authorization, Cookie, Set-Cookie if present, then scans body for known credential fingerprint (defense in depth)
    Plg->>Au: emit proxy.hit (jti, latency_ms, status=200, outcome=ok)
    Plg->>Plg: zero plaintext credential from request scope (per ADR-0014.4)
    Kg-->>Ag: 200 OK + body
```

## Quality attribute scenarios touched
- [S‑PERF‑1](../01-architecture/03-quality-attributes.md) — proxy added p50 ≤ 10 ms, p99 ≤ 30 ms.
- [S‑SEC‑1](../01-architecture/03-quality-attributes.md) — agent never sees the real credential.
- [S‑SEC‑3](../01-architecture/03-quality-attributes.md) — bounded blast radius.
- [S‑AUD‑1](../01-architecture/03-quality-attributes.md) — every proxy hit audited.
- [S‑OBS‑1](../01-architecture/03-quality-attributes.md) — end‑to‑end OTel trace.
- [S‑MT‑1](../01-architecture/03-quality-attributes.md) — `tnt` mismatch denies; cross‑tenant token replay impossible.
- [S‑AVAIL‑1](../01-architecture/03-quality-attributes.md) — control plane outage doesn't break in‑flight tokens.

## Failure modes (for the happy‑path doc; deeper coverage in F‑AG‑03 / F‑AG‑04 future)
| Failure | Detection | Behavior |
|---------|-----------|----------|
| JWT expired | exp check | 401 with `token_expired`; agent SDK refreshes (per [ADR‑0014.9](../01-architecture/adr/0014-iter-1-2-corrections.md)) |
| JWT revoked (jti or agent) | revocation set in plugin | 401 with `token_revoked` |
| `tnt` mismatch with service tenant | claim check | 401 with `tenant_mismatch` |
| `aud` mismatch with route service | claim check | 401 with `audience_mismatch` |
| `scope` doesn't cover requested action | path‑to‑action mapping | 403 with `action_not_granted` |
| Vault Adapter unreachable | gRPC error | 503; agent retries |
| Backend 5xx | upstream | passed through to agent |
| Backend 401 (real credential rejected) | upstream | passed through; operator sees `service.credential_rejected` audit (separate flow) |
| Cross‑origin redirect from backend | Kong follow‑redirect policy off | redirect returned to agent unchanged |
| Response body contains credential signature | response scrubber match | scrubber strips known fields + emits high‑severity audit `proxy.credential_echo_detected` |

## Test plan

### Unit tests
- `proxy_plugin.verify_jwt` — every claim check (iss, aud, scope, tnt, exp, jti); JWKS cache hit + miss + force‑refresh.
- `proxy_plugin.build_outbound_request` — every auth_scheme variant; redirect policy; header smuggling protection.
- `proxy_plugin.scrub_response` — known credential fingerprints in headers and body; idempotent.
- `proxy_plugin.zero_plaintext` — best‑effort zero of byte slices.

### Integration tests (testcontainers — Postgres + Kong + plugin + Vault Adapter + a stub backend)
- Happy path: JWT issued by broker → Kong → plugin → backend → response. Assert backend log shows the real API key (not the JWT); audit row has matching `jti`; OTel pipeline shows the trace.
- Latency benchmark: 100 RPS sustained, measure p50 and p99 added latency. Assert ≤ 10 ms p50, ≤ 30 ms p99 ([S‑PERF‑1](../01-architecture/03-quality-attributes.md)).
- Each `auth_scheme`: api_key_header, api_key_query, bearer_token, basic_auth, oauth2_client_credentials, oidc_client_secret, mtls. Each gets its own integration test against a stub that asserts the expected header/query was injected.
- Force JWKS refresh: rotate broker key during test; assert plugin recovers within one request.
- `tnt` mismatch: forge a JWT with wrong `tnt` (impossible normally; manufactured in test) → 401.
- Response scrubber: stub backend echoes `Authorization: Bearer <real-cred>` in response; assert scrubber strips it AND emits `proxy.credential_echo_detected` audit.

### Live smoke
- Part of E2E‑01 Phase 8.

### Red‑team / security tests
- Plaintext credential search across plugin's logs and stdout: zero matches.
- Plaintext in OTel span attributes: assert redaction policy (per [`docs/contracts/events/span-attributes.md`](../contracts/events/span-attributes.md)) catches any disallowed attribute.
- Coredump simulation: trigger SIGABRT in the plugin during a request; assert no plaintext appears in the dumped memory beyond a bounded set of single‑request bytes (informational; not a hard guarantee given Go GC).

## Kiro spec inputs
- **Components**: `proxy-plugin/internal/...` (Go go‑pdk), `vault-adapter/internal/...` (Go), `kong-syncer/internal/...` (Go), `broker/internal/jwks_endpoint.go`.
- **Contracts**: Kong route shape (declarative YAML produced by Kong‑syncer); `vault.proto` `GetCredential`; `proxy.hit` audit event; OTel span attributes.
- **Tasks** (TDD):
  1. Write integration test for the happy path against a stub backend; implement plugin until pass.
  2. Write each auth_scheme test; implement injection.
  3. Write JWKS force‑refresh test; implement.
  4. Write `tnt` mismatch test; implement (already in claim verifier).
  5. Write response‑scrubber test for each known echo location.
  6. Write latency benchmark test as a CI threshold check.
  7. Write red‑team plaintext‑in‑logs test; tighten redaction.
  8. Write OTel attribute redaction test; integrate with the contract's allowlist.
