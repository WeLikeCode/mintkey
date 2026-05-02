# P‑004 — Proxy deployment topology

**Status**: Open.

## Question
How does the agent reach the Egress Proxy, and how does the proxy reach backends? What's the right pattern that scales from "laptop docker‑compose" to "real prod"?

## Context
The proxy must:
- Be on the agent's egress path for brokered calls.
- Authenticate the agent via JWT.
- Reach backends on the public internet *and* (sometimes) on internal networks.
- Run with low latency and survive control‑plane outages.

The MVP target is `docker compose up` on a laptop. We must not paint ourselves into a corner against a production deployment we already know is coming (Kubernetes, dedicated network).

## Options

### Option A — Explicit forward proxy
The agent points its HTTP client at `https://proxy.local/v1/call/<service_id>/<path>` (or, in HTTP‑CONNECT mode, sets `HTTPS_PROXY=…`). Backend URL is *not* sent by the agent; the proxy resolves it from the JWT's `aud`.
- **Pros**: simplest mental model; works the same in compose, k8s, and prod.
- **Cons**: agent has to know the proxy URL and call it deliberately (this is fine — it's exactly what we want).

### Option B — Transparent intercept
Agent network namespace's egress is routed through the proxy via `iptables` / `eBPF` / sidecar mesh.
- **Pros**: agent code does not change; impossible to bypass.
- **Cons**: deployment‑environment‑specific; doesn't fit a laptop docker‑compose; brittle in dev.

### Option C — Per‑service‑named virtual hosts on the proxy
Agent calls `https://<service-slug>.proxy.local/<path>`; proxy resolves service from the host header.
- **Pros**: easy debugging ("which service was called" is in the host header); friendly with off‑the‑shelf HTTP clients and tracing libs.
- **Cons**: requires DNS or Host header trickery in compose.

## Recommendation
**Option A as the API contract, with Option C as a developer‑experience layer on top of the same endpoint.** I.e., the proxy accepts both `https://proxy.local/v1/call/<service_id>/<path>` and `https://<service-slug>.proxy.local/<path>`; both resolve to the same underlying handler; both ignore any backend URL the agent might try to send.

Option B (transparent intercept) is explicitly **deferred** and called out as a deployment concern, not an architecture concern.

## Implications
- Egress allowlisting is anchored to the *registered base URL* of the service in the proxy's configuration cache, never to the agent's request.
- The path the agent sends is appended to the registered base URL, with no `..` traversal allowed.
- Method and body pass through; headers are passed through except the auth header(s) we inject.
- Response is streamed back; the response scrubber inspects standard credential locations (`Authorization`, `Cookie`, body fields known to echo).

## Open follow‑ups
- WebSockets / SSE / long‑lived streams: handled or deferred? *Recommendation: deferred to a follow‑up iteration; v1 supports request/response.*
- gRPC / non‑HTTP: deferred; v1 is HTTP/1.1 + HTTP/2.
- TLS termination at the proxy vs. mTLS pass‑through: terminate at proxy in v1; revisit when we add mTLS as an inbound auth mode for high‑assurance agents.
