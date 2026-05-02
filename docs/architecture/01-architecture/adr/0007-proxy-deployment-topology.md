# ADR‑0007: Proxy deployment topology — explicit forward proxy with per‑service virtual‑host alias

## Status
Accepted — 2026-05-10. Promoted from [`docs/proposal/P-004-proxy-deployment-topology.md`](../../proposal/P-004-proxy-deployment-topology.md). Combines Option A (explicit forward proxy) as the API contract with Option C (per‑service virtual‑host alias) as the developer‑experience layer.

## Context
[P‑004](../../proposal/P-004-proxy-deployment-topology.md) compared three patterns for how the agent reaches the Egress Proxy and how the proxy reaches backends. Option A is the simplest mental model and works the same in compose, Kubernetes, and production. Option B (transparent intercept) is a deployment‑environment concern, not an architectural one. Option C is a usability sugar on top of Option A.

The proxy must:
- Be on the agent's egress path for brokered calls.
- Authenticate the agent via JWT.
- Reach backends on the public internet *and* (sometimes) on internal networks.
- Run with low latency and survive control‑plane outages.

## Decision

### API contract — explicit forward proxy (Option A)
The agent calls the Egress Proxy at one of two equivalent forms, both routed to the same handler:

1. **Path‑based form**:
   `https://proxy.local/v1/call/<service_id>/<path>`
2. **Virtual‑host form** (DX sugar, Option C):
   `https://<service-slug>.proxy.local/<path>`

The agent **never sends the backend URL**. The proxy derives the backend URL from the JWT's `aud` (`service_id`) by looking up the registered service. The agent's only structural data is which **service** and which **path within the service** to call.

### Egress allowlisting
- The proxy resolves the backend's **base URL** from the registered service config (in‑plugin cache, refreshed via change channel — see [ADR‑0004](0004-egress-proxy-kong.md), [ADR‑0006](0006-token-format-and-binding.md)).
- The agent‑supplied path is appended verbatim **except** that:
  - `..` segments are rejected (path traversal).
  - Absolute URLs in the path are rejected.
  - Schemes other than `http`/`https` are rejected.
- Backends that issue redirects to a different origin are **not followed**. The proxy returns the redirect to the agent unchanged; if the agent intends to follow a cross‑origin redirect, it must request a token for the new service.
- RFC 1918, link‑local, loopback, and metadata‑service IPs are **rejected by default**. An operator may explicitly allowlist internal hostnames per service for legitimate internal API access.

### Forwarding semantics
- **Method**: passed through.
- **Body**: streamed through (no buffering for non‑idempotent methods).
- **Headers**:
  - The agent's `Authorization` header is **always stripped**.
  - Headers we inject per the service's auth scheme override anything the agent sent that conflicts.
  - Hop‑by‑hop headers (`Connection`, `Keep-Alive`, `Proxy-*`, `TE`, `Trailers`, `Transfer-Encoding`, `Upgrade`) are stripped.
  - `Host` is set to the registered base URL's host.
  - `X-Forwarded-*` are NOT forwarded from the agent (the agent does not get to spoof IPs to the backend); the proxy may add its own.
- **Query string**: passed through verbatim.
- **TLS to backend**: required by default. HTTP backends are rejected unless the operator explicitly opts the service into HTTP (dev mode only).
- **Response**:
  - Status, headers, body streamed back to the agent.
  - **Response credential scrubber** strips known credential locations (`Authorization`, `Cookie`, `Set-Cookie`, and per‑service additional fields) from the response, per [ADR‑0004](0004-egress-proxy-kong.md). A high‑severity audit event is emitted if a known credential signature is detected in the response.

### Protocols supported in v1
- **HTTP/1.1** and **HTTP/2** request/response.
- **HTTP/3** deferred (Kong supports it; we just don't commit to it in v1).
- **WebSockets, SSE, long‑lived streams** deferred to a follow‑up iteration (will need session‑bound JWT renewal).
- **gRPC** deferred (Kong supports it; metadata‑level credential injection is a follow‑up — Phase 3 of the [roadmap](../../00-vision/06-roadmap.md)).

### Deployment models
- **`docker compose up` (MVP)**: Kong runs as one container; the proxy plugin runs as a sibling; the agent points its HTTP client at `http://localhost:8080`.
- **Kubernetes (Phase 2)**: Kong runs as a Deployment behind a LoadBalancer or Ingress; agents call the LoadBalancer URL.
- **Transparent intercept (Option B)**: explicitly **deferred** and called out as a deployment concern, not an architectural one. If a deployment wants transparent intercept (e.g., via `iptables` rules in an agent's network namespace), it can be added without changing the proxy.

## Consequences

### Positive
- One simple mental model (explicit proxy with deterministic routing) that works the same in compose, Kubernetes, and production.
- The proxy never trusts agent‑supplied routing — JWT `aud` is the only authority. Closes the entire class of "agent re‑routes to a different backend" attacks.
- Egress allowlist is anchored to the registered base URL, eliminating SSRF via "register internal service" by default.
- The DX‑friendly virtual‑host form means service identity shows up in the request's `Host` header, which is helpful for debugging and tracing.

### Costs
- Agents must be configured to call the proxy URL deliberately. This is by design and consistent with the threat model — agent code knows it is calling a brokered endpoint.
- Backends that depend on receiving the agent's `X-Forwarded-For` get the proxy's, not the agent's. An audit event in our log preserves the agent identity if needed for forensic correlation.

### Risks
- **Path normalization edge cases**: many SSRF/traversal vulnerabilities historically come from path normalization differences. Mitigation: use a strict, minimal path resolver that rejects ambiguous inputs (e.g., URL‑encoded `..`, double slashes); fuzz‑tested in CI.
- **TLS pinning vs. mainstream backends**: production backends rotate certs frequently; over‑strict pinning breaks. Mitigation: standard Web PKI verification by default; explicit per‑service pinning is opt‑in.

## Implications
- [Container view](../02-container-view.md): D1 (Egress Proxy) is reachable at two equivalent URL forms; both resolve to the same Kong route + plugin chain.
- [Threat model](../05-threat-model.md): the SSRF and routing‑spoof mitigations are made explicit by this ADR.
- [Roadmap](../../00-vision/06-roadmap.md): WebSockets, SSE, and gRPC are Phase 3 deliverables.

## Open follow‑ups (iteration 2 / Phase 2)
- Path normalization specification (which normalization rules apply, in which order).
- Whether to support a third URL form for backwards compatibility with raw forward‑proxy clients (`HTTPS_PROXY=http://proxy.local`). *Lean: deferred unless an operator asks.*
- Per‑service hostname allowlist when the registered base URL is internal.
- TLS termination at Kong vs. mTLS pass‑through to the backend (relevant for high‑assurance backends).
- Body size limits and request/response timeouts (default 30 s; configurable per service).

## Related
- [P‑004 proxy‑deployment‑topology](../../proposal/P-004-proxy-deployment-topology.md) — Accepted (this ADR).
- [ADR‑0004 egress‑proxy‑kong](0004-egress-proxy-kong.md) — proxy implementation.
- [ADR‑0006 token‑format‑and‑binding](0006-token-format-and-binding.md) — JWT `aud` is the routing authority.
- [`05-threat-model.md`](../05-threat-model.md) — SSRF, open redirect, header smuggling.
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — optional virtual‑host alias becomes `<service-slug>.<tenant-slug>.proxy.local`; URL conventions support `/v1/tenants/{tid}/...`.
