# ADR‑0010: Change channel transport — Postgres `LISTEN/NOTIFY`

## Status
Accepted — 2026-05-10. Promoted from [`docs/proposal/P-009-change-channel-transport.md`](../../proposal/P-009-change-channel-transport.md), Option A (the proposal's recommendation).

## Context
[P‑009](../../proposal/P-009-change-channel-transport.md) compared four options for the change‑channel transport. The decisive forces:
- **No extra container if avoidable** — operator preference (matches [ADR‑0004](0004-egress-proxy-kong.md), [ADR‑0005](0005-admin-tech-stack.md)).
- **Transactional with state changes** — the publish should fire iff the DB row commits (eliminates the publisher‑crash window).
- **Volume is low** — tens to thousands of events per day even in multi‑tenant deployments.
- **At‑most‑once is acceptable** — a reconciliation endpoint is already on the books from [ADR‑0006](0006-token-format-and-binding.md).

## Decision

### Transport
- **Postgres `LISTEN/NOTIFY`** is the change‑channel transport for v1.
- Publishers `NOTIFY <channel>, '<json>'` **inside the same DB transaction** as the state change. The notification fires iff the commit succeeds.
- Subscribers `LISTEN <channel>` on a long‑lived dedicated connection from a small reconnecting wrapper. On disconnect, they reconcile via `GET /v1/changes?since=<event_id>` (defined by [ADR‑0006](0006-token-format-and-binding.md) follow‑ups; finalized in iteration 4 contracts).

### Channel naming (tenant‑scoped per [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md))
| Channel                               | Purpose                                                |
|---------------------------------------|--------------------------------------------------------|
| `mintkey:<tenant_slug>:service`       | `service.registered`, `service.updated`, `service.removed` |
| `mintkey:<tenant_slug>:credential`    | `credential.rotated`, `credential.revoked`             |
| `mintkey:<tenant_slug>:agent`         | `agent.revoked`, `token.revoked`                       |
| `mintkey:heartbeat`                   | A periodic notification (every 30 s) so subscribers detect stale connections |

Cross‑tenant leakage at the channel layer is impossible by construction — channel names contain the tenant slug, and a subscriber listens only to channels for the tenants it cares about. The Kong‑syncer subscribes to all tenants' channels (it operates above tenants); per‑tenant MCP Server instances (high‑isolation tier) subscribe to one tenant only.

### Payload format
```json
{
  "event_id":   "01HX5J9F8V8H8V0CG3F2Y5J6Q1",
  "event_type": "credential.rotated",
  "tenant_id":  "t_acme",
  "actor_id":   "operator_01HX…",
  "target_id":  "cred_01HX…",
  "key_version": 7,
  "at":         "2026-05-10T14:23:45Z"
}
```
Body fields are **references**, not full payloads. Subscribers fetch full state from the Admin REST API or DB on demand. The 8 kB Postgres NOTIFY payload limit is plenty.

### Library abstraction
- A small Go package `mintkey/internal/changes` and a small Python package `mintkey.changes`. Same wire format, same channel names, same reconnect / heartbeat behavior across both.
- The interface is **transport‑agnostic** so a future swap to Redis or NATS is a one‑file change in a half dozen places.

### Subscribers
- **Egress Proxy plugin** (Go, [ADR‑0004](0004-egress-proxy-kong.md)) — listens on `mintkey:*:credential`, `mintkey:*:agent` for cache invalidation.
- **Kong‑syncer** (Go, [ADR‑0004](0004-egress-proxy-kong.md)) — listens on `mintkey:*:service` for declarative‑YAML pushes.
- **MCP Server** (Python, [ADR‑0009](0009-mcp-server-stack-python.md)) — listens on its tenants' channels for discovery cache invalidation.

### Publishers
- **Admin REST API** (Python, [ADR‑0005](0005-admin-tech-stack.md)) — the only publisher. Every state change goes through its handlers; the audit chokepoint and the publish are in the same transaction.

### Reconciliation
- On startup or after a disconnect, every subscriber calls `GET /v1/changes?since=<last_event_id>&limit=<n>` on the Admin REST API and processes the events in order before resuming live consumption.
- The endpoint is paginated and returns events in `(at, event_id)` order.
- The reconciliation contract is finalized in iteration 4 (`docs/contracts/rest/openapi.yaml`).

### Heartbeat / connection liveness
- Publishers also fire `mintkey:heartbeat` every 30 s.
- Subscribers that don't see a heartbeat for `60 s` mark the connection dead, reconnect, and run reconciliation.

## Consequences

### Positive
- **Zero extra container.** Self‑hosters get the change channel "for free" with the Postgres they already run.
- **Transactional correctness**: no "DB has it, channel didn't fan out" window.
- **Tenant‑scoped channel names**: cross‑tenant leakage impossible by construction at the transport layer.
- **Behind a small abstraction** — swappable to Redis or NATS later if scale ever demands.

### Costs
- One long‑lived Postgres connection per subscriber per process. At our scale this is fine; we cap subscriber connections per service.
- Subscribers must implement reconnect + reconciliation themselves (pattern is shared in `mintkey/internal/changes` / `mintkey.changes`).
- 8 kB payload limit forces references‑only payloads. Acceptable; documented in payload format above.

### Risks
- **Postgres global lock during NOTIFY**: not a problem at our event volume (low thousands per day across all tenants).
- **Subscriber lag** during a Postgres restart: mitigated by reconciliation on reconnect.
- **A subscriber that fails reconciliation** silently lags. Mitigated by an OTel metric `mintkey.changes.subscriber_lag_seconds` that pages SRE if it exceeds threshold.

## Multi‑tenancy and security
- A subscriber that LISTENs only on `mintkey:t_acme:*` cannot receive events for other tenants. The application enforces this at startup based on the operator's or process's tenant scope.
- The Postgres role used by subscribers has only `LISTEN` privileges on these channels; cannot publish. Publishers use the application role.
- Channel payloads are reference‑only — no PII or credential material flows over the channel itself.

## Implications
- [`02-container-view.md`](../02-container-view.md) — the change channel is implicit (it's just Postgres). No new container.
- [`05-deployment/README.md`](../../05-deployment/README.md) — Redis is **removed** from the Phase 1 compose set; one fewer container.
- [`07-kiro-readiness.md`](../../00-vision/07-kiro-readiness.md) — the change‑channel stub is part of the test fixture library; integration tests use a real Postgres.
- [`docs/contracts/rest/`](../../contracts/rest/) — `GET /v1/changes?since=<event_id>` is part of the iteration‑4 OpenAPI surface.

## Honest alternative kept on file
**Redis pub/sub** if we ever need:
- Larger payloads than 8 kB (we don't today).
- Decoupling from Postgres (e.g., the channel must keep working when Postgres is reconciliation‑only).
- Higher fan‑out than Postgres can handle.

**NATS+JetStream** if we ever want at‑least‑once delivery with replay built into the transport.

Both are swappable behind the `mintkey/internal/changes` and `mintkey.changes` packages.

## Open follow‑ups (iteration 2 closeout)
- Final channel‑name conventions (the proposed form is above; a vote in iteration‑2 closeout).
- Reconciliation pagination size and cadence on disconnect.
- Whether to add a Redis "fast lane" for token revocation specifically if Postgres LISTEN/NOTIFY ever proves too slow. Default: defer.
- Heartbeat detection algorithm — `60 s` is the default; tunable per environment.

## Related
- [P‑009 change‑channel‑transport](../../proposal/P-009-change-channel-transport.md) — Accepted (this ADR).
- [ADR‑0004 egress‑proxy‑kong](0004-egress-proxy-kong.md) — proxy plugin and Kong‑syncer are the primary subscribers.
- [ADR‑0006 token‑format‑and‑binding](0006-token-format-and-binding.md) — defines what flows over the channel.
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — channels are tenant‑scoped.
- [ADR‑0009 mcp‑server‑stack‑python](0009-mcp-server-stack-python.md) — MCP Server is a subscriber.
