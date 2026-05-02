# ADR‑0004: Egress Proxy implementation — Kong Gateway (DB‑less) + Go plugin via go‑pdk

## Status
Accepted — 2026-05-10. Promoted from [`proposal/P-005-egress-proxy-implementation.md`](../../proposal/P-005-egress-proxy-implementation.md), Option G.

## Context
[P‑005](../../proposal/P-005-egress-proxy-implementation.md) compared ten implementation options for the Egress Proxy (D1 in [`02-container-view.md`](../02-container-view.md)) against the quality‑attribute scenarios (S‑PERF‑1, S‑OPS‑1/2, S‑MOD‑1, S‑AVAIL‑1) and the threat model. The proposal's primary recommendation was Option J (Envoy + ext_authz + xDS via go‑control‑plane), with Option G (Kong Gateway DB‑less + Go plugin) as a strong alternative and Option E (Caddy + module) as the simplest alternative.

After review, Option G is selected. The reasoning prioritizes:
- **Maximum off‑the‑shelf surface**: Kong is the most‑deployed OSS API gateway for the "JWT validation + credential injection + dynamic services" pattern. Stock plugins cover JWT, Prometheus, OTel, Jaeger, rate limiting, ACL, and request transformation. We get all of those without writing them.
- **Operational maturity**: Kong has a long track record at production scale; the documentation, troubleshooting guides, and community knowledge are deeper than for Caddy or APISIX.
- **Bounded custom code**: a Go plugin (~250 lines using `go-pdk`) plus a small Kong‑syncer (~150 lines) — about 400 lines we own. Smaller than the Envoy + ext_authz path (~550 lines) and a fraction of a from‑scratch implementation.
- **Lower operational complexity than Envoy + xDS**: a single Kong binary plus our plugin process, configured via declarative YAML pushed to Kong's `/config` endpoint. No xDS control plane to operate.
- **Acceptable trade on dependency surface**: Kong's Lua/OpenResty core is large but it has been stable and audited; the plaintext credential never lives in Lua memory because the Go plugin runs out‑of‑process and only returns the headers Kong should add.

## Decision

The Egress Proxy is realized by:

1. **Kong Gateway (DB‑less mode)** as the data plane. Image: `kong:latest` (version pinned in iteration 2). DB‑less reads a YAML manifest at startup and via the admin `/config` endpoint — Kong itself needs no Postgres.

2. **Stock Kong plugins** configured per service:
   - `jwt` — verifies the brokered JWT against the broker's JWKS.
   - `prometheus` and `opentelemetry` (or `zipkin`/`jaeger` plugins) — observability.
   - `rate-limiting` — per‑agent / per‑service throttling.
   - `request-termination` — fail‑closed on misconfiguration.

3. **A custom Go plugin**, distributed as a separate process and connected to Kong via Kong's external plugin protocol, running in the `access` phase:
   - Reads the JWT‑validated context Kong passes (claims `sub`, `aud`, `scope`, `jti`, `key_version`).
   - Looks up the service config from an in‑plugin cache keyed by `service_id`.
   - Calls the Vault Adapter (gRPC) to fetch the credential by `(service_id, key_version)`. Holds plaintext in a request‑scoped variable.
   - Sets the appropriate request header per the service's auth scheme (`Authorization: Bearer …`, `X-API-Key: …`, basic‑auth, etc.) using `kong.service.request.set_header`.
   - Strips the agent's inbound `Authorization` header before Kong forwards.
   - Emits an `mintkey.proxy.hit` audit event after the response (in `log` phase) with `(jti, agent_id, service_id, latency, outcome)`.
   - Maintains a small **plaintext credential cache** keyed by `(service_id, key_version)` with TTL ≤ JWT TTL (default 5 min), invalidated on `credential.rotated` events from the change channel.
   - Subscribes to the change channel for `service.*`, `credential.*`, and `agent.revoked` events.

4. **A small Kong‑syncer Go service** in the control plane that:
   - Subscribes to the same change channel.
   - Translates our service registry into Kong declarative YAML.
   - Pushes updates to Kong's `/config` endpoint on operator events (service registered, updated, removed; agent revoked → ACL update).
   - Exposes a health/ready endpoint.

5. **Response credential scrubbing** is implemented in the plugin's `body_filter`/`header_filter` phase as a defense‑in‑depth measure for backends that echo `Authorization` or known credential‑bearing fields. Defensive scrubbing list is maintained as part of the plugin config.

## Why not the proposal's primary recommendation (J — Envoy + ext_authz)
J is technically excellent, but in operational terms it asks more of an early‑stage project than its benefits return today:
- Two binaries on the data plane (Envoy + ext_authz) plus an xDS server in the control plane.
- Envoy YAML/xDS resources are verbose and require ops literacy that Kong does not.
- The marginal benefits (canonical pattern, multi‑cluster routing, HTTP/3) are not justified at our v1 scale.

J is preserved as the **documented upgrade path** if/when we hit a need only Envoy answers (sustained > 1k RPS per instance, service‑mesh integration, sophisticated traffic shaping).

## Consequences

### Positive
- ~400 lines of custom Go is everything we own for the data plane.
- Stock plugins give us: JWT, observability, rate limiting, ACL, response transformation — without writing them.
- Single, well‑documented runtime (Kong) for ops to learn.
- Mature plugin ecosystem covers most "what about X?" follow‑up requirements.
- No xDS control plane.

### Costs
- Kong's Lua/OpenResty core is large; the trusted‑memory dependency surface is larger than the Caddy or custom‑Go options.
- Two processes on the data plane node (Kong + plugin); UDS/loopback IPC adds a small per‑request latency hop.
- Declarative‑config push to `/config` is *eventually* consistent; rotation lag is bounded by the syncer's push latency plus Kong's reload time (typically sub‑second).
- Kong DB‑less limits some advanced features (e.g., per‑plugin DB‑backed state), which we don't currently need.

### Risks
- **Kong version churn**: Kong's plugin protocol and admin API are stable but not immutable. Mitigation: pin the Kong version per release; integration tests run against the pinned version.
- **`go-pdk` API stability**: less battle‑tested than Lua plugins. Mitigation: keep the plugin small; integration test against the pinned `go-pdk` version.
- **Plugin process crash**: if the Go plugin process dies, Kong fails closed for affected requests (correct behavior). Mitigation: supervised by the container orchestrator; readiness probe fails until plugin reconnects.

## Implications

### Container view ([`02-container-view.md`](../02-container-view.md))
D1 (Egress Proxy) is now realized by two co‑located processes: `kong` and `mintkey/proxy-plugin`. The container view will be updated to reflect this in iteration 2.

### Deployment ([`05-deployment/README.md`](../../05-deployment/README.md))
Compose adds a `kong` service (image `kong:latest`, DB‑less mode, mounted YAML config volume) and a `proxy-plugin` service (our Go plugin). Iteration 2 specifies the bootstrap YAML.

### Change channel ([P‑003](../../proposal/P-003-token-format-and-binding.md))
Carries three event families that the plugin and the Kong‑syncer consume:
- `service.registered`, `service.updated`, `service.removed` → Kong‑syncer pushes new YAML.
- `credential.rotated` → plugin invalidates `(service_id, *)` cache entries.
- `agent.revoked` → plugin invalidates JWT acceptance for that `agent_id` + Kong ACL plugin update.

### Vault Adapter contract
Exposes typed `get_credential(service_id, key_version) → (plaintext, auth_scheme, expires_at?)` over gRPC. Plugin caches by `(service_id, key_version)`.

## Alternatives considered (not adopted)
| Option | Why not |
|--------|---------|
| **J. Envoy + ext_authz + xDS** | Higher operational complexity than warranted at v1; preserved as upgrade path. |
| **E. Caddy + Go module** | Smaller ecosystem; fewer ready‑made plugins for advanced features we'll likely want. |
| **I. APISIX + plugin** | Requires etcd as an additional component; younger plugin ecosystem than Kong's. |
| **H. Tyk + Go plugin** | Corporate‑direction concerns about OSS feature gating. |
| **D. Custom Go proxy** | Operator preference is "off‑the‑shelf with config"; D requires us to own all HTTP edge handling. |

## Open follow‑ups (iteration 2)
- Kong version pinning (Kong 3.x stream).
- Decision on `kong-plugin-server` (the Go plugin process management) — supervised by Kong itself or by compose?
- Whether to use Kong's stock `request-transformer-advanced` for some auth schemes (it can interpolate values) — reduces plugin scope but Plus‑only in some cases.
- `go-pdk` API version pinning and a Renovate strategy.
- Bootstrap YAML for the docker‑compose MVP (one demo service, one demo agent).

## Related
- [P‑005 egress‑proxy‑implementation](../../proposal/P-005-egress-proxy-implementation.md) — Accepted (this ADR).
- [P‑003 token‑format‑and‑binding](../../proposal/P-003-token-format-and-binding.md) — change channel integration.
- [ADR‑0003 credential‑storage‑strategy](0003-credential-storage-strategy.md) — Vault Adapter contract.
- [ADR‑0001 record‑architecture‑decisions](0001-record-architecture-decisions.md).
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — plugin cache key gains `tenant_id`; JWT `tnt` claim enforced; audit emits `tenant_id`; Kong‑syncer scopes routes by tenant.
