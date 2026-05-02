# P‑003 — Token format and binding

**Status**: Open.

## Question
What is the format of the brokered token, what does it bind, and how does the proxy verify it?

## Context
Quality attribute scenarios:
- [S‑SEC‑3](../01-architecture/03-quality-attributes.md#ssec3--stolen-agent-api-key-has-bounded-blast-radius) — bounded blast radius of a stolen Agent API Key.
- [S‑PERF‑1](../01-architecture/03-quality-attributes.md#sperf1--proxy-latency-overhead-is-bounded) — proxy adds little latency.
- [S‑OPS‑1](../01-architecture/03-quality-attributes.md#sops1--operator-can-revoke-an-agent-in-seconds) — revoke in seconds.
- [S‑AVAIL‑1](../01-architecture/03-quality-attributes.md#savail1--control-plane-downtime-does-not-stop-inflight-agent-work) — control plane outage doesn't break in‑flight work.

Threats: token forgery, replay, theft, bind‑once‑use‑anywhere.

## Options

### Option A — JWS‑signed JWT, asymmetric key, JWKS‑distributed public key
- Claims: `sub` (agent), `aud` (service id), `scope` (action list), `jti`, `iat`, `exp`, optional `cnf` (key‑bound for replay protection).
- Proxy verifies signature locally using the cached JWKS.
- **Pros**: standard, library support everywhere, no per‑request broker call from the proxy → low latency; **survives short control‑plane outages** (S‑AVAIL‑1).
- **Cons**: revocation is not free — proxy must check a revocation signal (short JWKS TTL, key rotation, or a denylist).

### Option B — Opaque token + per‑request introspection
- Broker hands out an opaque random string; proxy calls broker to introspect on each request.
- **Pros**: instantaneous revocation; broker holds all state.
- **Cons**: every proxy hit adds a broker round‑trip → kills S‑PERF‑1; control‑plane outage breaks data plane → kills S‑AVAIL‑1.

### Option C — JWS‑signed JWT *plus* a fast revocation channel (best of both)
- JWT as in Option A.
- Proxy subscribes to a revocation stream (Redis pub/sub, NATS, or even a short‑poll endpoint) listing revoked `agent_id` and `jti`.
- **Pros**: low‑latency happy path *and* revoke‑in‑seconds.
- **Cons**: extra infra component on the data plane (a small one); failure mode if revocation channel is down (mitigated by graceful fallback to TTL‑based expiry).

## Recommendation
**Option C.** The latency and availability properties of Option A are non‑negotiable; the revocation channel adds one component but the failure mode is graceful (revocation channel down → tokens still expire on TTL, just slower revocation).

Specifics for v1:
- **Algorithm**: EdDSA (Ed25519) — small signatures, no curve choice ambiguity.
- **TTL**: default 10 minutes; configurable per service.
- **Binding**: JWT carries `aud=service_id`, `scope`, and a hash‑bound `cnf.jkt` to a per‑token client cert when high‑assurance mode is enabled. Default off in MVP.
- **JWKS**: served by the broker at a stable URL; cached by the proxy with a short TTL (e.g., 5 minutes) to allow quick key rotation.
- **Revocation channel**: a small in‑memory pub/sub initially (Redis or NATS — pick in iteration 2).

## JWT shape (preview)
```json
{
  "iss": "mintkey/broker",
  "sub": "agent_01HX…",
  "aud": "svc_crm",
  "scope": "read:contacts",
  "jti": "01HX…",
  "iat": 1715000000,
  "exp": 1715000600,
  "cnf": { "jkt": "…optional thumbprint…" }
}
```

## Implications
- Broker holds an EdDSA keypair; key rotation is supported (publish multiple keys in JWKS during overlap).
- Proxy is stateless except for cached JWKS and revocation state.
- Audit log links every proxy hit to the `jti`.
- The proxy never trusts any agent‑provided routing info — `aud` is the only authority.
