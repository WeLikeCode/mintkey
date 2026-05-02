# ADR‑0006: Token format and binding — JWS (Ed25519) JWT + fast revocation channel

## Status
Accepted — 2026-05-10. Promoted from [`docs/proposal/P-003-token-format-and-binding.md`](../../proposal/P-003-token-format-and-binding.md), Option C (the proposal's recommendation).

## Context
[P‑003](../../proposal/P-003-token-format-and-binding.md) compared three options for the brokered token (full JWS JWT with revocation, opaque introspection, hybrid). The decision is driven by:
- [S‑PERF‑1](../03-quality-attributes.md) — proxy adds little latency.
- [S‑OPS‑1](../03-quality-attributes.md) — revoke ≤ 5 s.
- [S‑AVAIL‑1](../03-quality-attributes.md) — control‑plane outage doesn't break in‑flight work.
- [S‑SEC‑3](../03-quality-attributes.md) — bounded blast radius of a stolen Agent API Key.

Opaque introspection on every request fails S‑PERF‑1 and S‑AVAIL‑1; pure JWT fails S‑OPS‑1. The hybrid (Option C) gets us low‑latency local verification *and* sub‑5 s revoke.

## Decision

### Token shape
- **Format**: JWS over a JWT payload.
- **Algorithm**: **EdDSA (Ed25519)**. Small signatures, no curve‑choice ambiguity, fast verification.
- **Issuer (`iss`)**: `mintkey/broker`.
- **Subject (`sub`)**: agent identifier (e.g., `agent_01HX…`).
- **Audience (`aud`)**: service identifier (e.g., `svc_crm`). The proxy treats `aud` as the **only** routing authority; agent‑provided routing data is ignored.
- **Scope (`scope`)**: a single action string per token (e.g., `read:contacts`). Multiple scopes are not supported in v1; agents request one token per action.
- **JWT ID (`jti`)**: ULID. Used to link audit events for the request.
- **Issued at / Expiry (`iat`, `exp`)**: standard.
- **Confirmation (`cnf`, optional)**: `cnf.jkt` (RFC 7800) — thumbprint of a per‑token client cert when **high‑assurance mode** is enabled. Default off in MVP; opt‑in per service for cases where an additional client‑bound key is required.

Example token payload:
```json
{
  "iss": "mintkey/broker",
  "sub": "agent_01HX5J9F8V8H8V0CG3F2Y5J6M3",
  "aud": "svc_crm",
  "scope": "read:contacts",
  "jti": "01HX5J9F8V8H8V0CG3F2Y5J6Q1",
  "iat": 1715000000,
  "exp": 1715000600
}
```

### TTL
- **Default 10 minutes**. Configurable per service (`min` 60 s, `max` 60 min).
- The agent receives `expires_at` and can refresh by calling `request_token` again before expiry.

### Key management (signing keys)
- The Credential Broker holds an **EdDSA keypair** in process memory. The private key is loaded at startup from a Vault‑Adapter‑managed credential of type `signing_key`.
- **JWKS distribution**: the Broker exposes a stable `GET /.well-known/jwks.json` returning the public key(s). The Egress Proxy plugin caches this with a **5‑minute TTL** to allow quick key rotation.
- **Key rotation**: support for overlapping keys — the JWKS publishes the new and old public keys for a configurable overlap window (default 1 hour). After overlap, the old key is removed.

### Revocation channel
- A small **pub/sub channel** runs alongside the control plane. Initial implementation uses **Redis pub/sub**; alternatives (NATS, Postgres `LISTEN/NOTIFY`) are revisited in iteration 2. The choice is encapsulated behind a small Go interface in the proxy plugin and the broker.
- The channel carries three event families consumed by the proxy plugin (per [ADR‑0004](0004-egress-proxy-kong.md)):
  - `agent.revoked` — `{agent_id}`. Plugin denies all subsequent requests bearing tokens with that `sub`.
  - `token.revoked` — `{jti}`. Plugin denies the specific token.
  - `service.*` and `credential.*` — propagation handled by the Kong‑syncer and the plugin's credential cache.
- **Failure mode**: if the revocation channel is down, the system **degrades gracefully** to TTL‑based expiry (default 10 min). Revocation is slower but no token is honored beyond `exp`.

### Verification flow on the proxy
1. Parse token; reject malformed.
2. Verify signature against cached JWKS; refresh JWKS if `kid` is unknown.
3. Check `exp` (with a small clock skew tolerance, e.g., 30 s).
4. Check `iss == "mintkey/broker"`.
5. Check `aud == service_id` derived from the request URL.
6. Check `scope` matches the action implied by the request (path/method).
7. Check `jti` is not in the local revocation set.
8. Check `sub` is not in the local revoked‑agent set.
9. If `cnf.jkt` is present, verify the inbound client certificate thumbprint matches.
10. If all pass, proceed to credential lookup.

## Consequences

### Positive
- The proxy verifies tokens **locally** — no per‑request broker call. Meets S‑PERF‑1 and S‑AVAIL‑1.
- Revocation propagates within seconds via the channel; meets S‑OPS‑1.
- Standard JWT format works with off‑the‑shelf libraries everywhere (Go, Python, TypeScript).
- Key rotation has overlap support; rolling without downtime is straightforward.

### Costs
- The change channel is an additional infrastructure component. Initial Redis pub/sub is small but must be in compose and observed.
- Plugin must maintain two in‑memory revocation sets (`{agent_id}` and `{jti}`) with bounded size; iteration 2 specifies the eviction policy.

### Risks
- **Lost revocation event**: Redis pub/sub is at‑most‑once. Mitigation: periodic full‑state reconciliation (the plugin polls a `/v1/revocations?since=<ts>` endpoint every N seconds for catch‑up). At‑least‑once delivery via a queue is a future option.
- **Signing key compromise**: catastrophic if it occurs. Mitigation: short‑lived keys (rotation cadence to be set in iteration 2; recommend daily), JWKS public‑key distribution, optional HSM backing as a future enhancement.

## Implications
- **[Container view](../02-container-view.md)** — the change channel becomes an explicit component. Will be reflected when the container view is regenerated.
- **[ADR‑0004](0004-egress-proxy-kong.md)** — Kong Go plugin consumes the change channel; this ADR formalizes what flows over it.
- **[`05-threat-model.md`](../05-threat-model.md)** — the JWT‑forgery and replay mitigations summarized above are reflected in the model; iteration 2 will add explicit notes on `cnf.jkt` and key rotation.
- **[Contracts: MCP](../../contracts/mcp/)** — `request_token(service_id, action, ttl_seconds?)` returns the JWT and its `expires_at`. The exact shape is finalized in iteration 4.
- **[Contracts: REST](../../contracts/rest/)** — `GET /.well-known/jwks.json` is part of the public surface.

## Open follow‑ups (iteration 2)
- Concrete change‑channel transport: Redis pub/sub vs. NATS vs. Postgres `LISTEN/NOTIFY`. Trade Redis‑memory‑footprint for `LISTEN/NOTIFY`'s zero‑extra‑container or NATS's better‑guarantees.
- Key rotation cadence — default daily, with overlap windows. Whether to adopt short‑lived keys (e.g., 1 h with overlap).
- Eviction policy for the proxy plugin's revocation set (LRU, time‑bounded).
- Periodic reconciliation endpoint and cadence.
- Decision: support multi‑audience tokens later, or keep one `aud` per token forever.

## Related
- [P‑003 token‑format‑and‑binding](../../proposal/P-003-token-format-and-binding.md) — Accepted (this ADR).
- [ADR‑0004 egress‑proxy‑kong](0004-egress-proxy-kong.md) — change‑channel consumer.
- [ADR‑0003 credential‑storage‑strategy](0003-credential-storage-strategy.md) — Vault Adapter holds the broker's signing key.
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — JWT gains a `tnt` (tenant) claim; broker reads tenant from agent record; proxy enforces `tnt` matches service's tenant.
