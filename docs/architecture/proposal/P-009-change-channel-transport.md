# P‑009 — Change channel transport

**Status**: Accepted (→ [ADR‑0010](../01-architecture/adr/0010-change-channel-postgres-listen-notify.md)) — 2026-05-10. Selected the recommended **Option A** (Postgres `LISTEN/NOTIFY`).

> **Outcome**: Accepted as recommended. The change channel runs on Postgres `LISTEN/NOTIFY` — zero extra container, transactional with state changes, tenant‑scoped channel names (`mintkey:<tenant_slug>:{service,credential,agent}`). At‑most‑once delivery is acceptable because the reconciliation endpoint (`GET /v1/changes?since=...`) handles disconnects. **Redis is removed from the Phase 1 compose set** — one fewer container. Behind a small `mintkey/packages/go/changes` (Go) / `mintkey.changes` (Python) abstraction so a future swap to Redis or NATS is a one‑file change. See [ADR‑0010](../01-architecture/adr/0010-change-channel-postgres-listen-notify.md).

## Question
What runtime carries the change channel — the cache‑invalidation / revocation pub/sub used by the Egress Proxy plugin, the Kong‑syncer, the MCP Server, and (potentially) the Admin REST API?

## Context

### What flows over the channel
Three event families ([ADR‑0006](../01-architecture/adr/0006-token-format-and-binding.md), [ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md), [ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md)):
- **`service.*`** — `service.registered`, `service.updated`, `service.removed`. Consumed by the Kong‑syncer (to push declarative YAML) and by the MCP Server (to invalidate discovery cache).
- **`credential.*`** — `credential.rotated`, `credential.revoked`. Consumed by the Egress Proxy plugin (to invalidate `(tenant_id, service_id, *)` cache entries).
- **Agent / token revocation** — `agent.revoked`, `token.revoked`. Consumed by the Egress Proxy plugin and the MCP Server.

Every event carries `tenant_id`. Subscribers filter as needed.

### Forces
- **Volume**: low. A busy single‑tenant deployment might emit 10–100 events/day; a multi‑tenant deployment with 100 tenants might emit a few thousand. The channel is *not* hot.
- **Latency budget**: sub‑second propagation is desirable for revocation ([S‑OPS‑1](../01-architecture/03-quality-attributes.md)) but not critical for service updates.
- **Reliability**: at‑most‑once is acceptable because we already plan a periodic reconciliation endpoint ([ADR‑0006](../01-architecture/adr/0006-token-format-and-binding.md)). At‑least‑once would be preferred but introduces dedupe complexity for subscribers.
- **Operational footprint**: the user prefers off‑the‑shelf with low custom code ([ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md)). Adding another infra component should pay for itself.
- **Transactional with state changes**: it would be valuable for the publish to happen atomically with the DB write. (Otherwise the DB has a service that no subscriber knows about until the next reconciliation tick.)

## Options

### Option A — Postgres `LISTEN/NOTIFY`
Subscribers `LISTEN <channel>` on a long‑lived connection; publishers call `NOTIFY <channel>, '<json>'` inside the same DB transaction as the state change.
- **Pros**:
  - **Zero extra container.** Postgres is already in compose.
  - **Transactional with state changes** — publish happens iff the row commits. No "DB has it but channel didn't fire" case.
  - Simple client code in every language (every Postgres driver supports it).
  - No memory pressure on a separate broker.
- **Cons**:
  - Payload size limit ~8 kB. We send references (IDs), not full payloads — fine for our use case.
  - At‑most‑once: subscribers must reconnect and reconcile if disconnected.
  - Long‑lived connections per subscriber consume one Postgres connection each.
  - Postgres has a global lock during NOTIFY; not a problem at our scale.

### Option B — Redis pub/sub
Subscribers connect to Redis and `SUBSCRIBE <channel>`; publishers `PUBLISH <channel> <json>`.
- **Pros**:
  - Simple, ubiquitous, well understood.
  - Decoupled from Postgres (no DB connection contention).
  - Larger payload size; faster fan‑out.
- **Cons**:
  - **Adds a Redis container** to compose, with its own backup/HA story (even in v1).
  - **Not transactional with the DB write** — you can have "DB has it, Redis didn't fan out" if the publisher crashes between commit and publish. Reconciliation handles this but adds windows of inconsistency.
  - At‑most‑once like LISTEN/NOTIFY (Redis pub/sub is fire‑and‑forget; Streams add at‑least‑once but more complexity).
  - Redis is one more thing to operate.

### Option C — NATS (with JetStream)
Subscribers connect to NATS; publishers publish to a subject; JetStream provides at‑least‑once with replay.
- **Pros**:
  - **At‑least‑once delivery** with replay; subscribers can catch up after disconnect without polling our reconciliation endpoint.
  - Better guarantees than A or B.
  - Strong multi‑tenancy story (subjects can be tenant‑scoped).
- **Cons**:
  - **Adds a NATS container** with its own ops story (more complex than Redis).
  - Most engineers don't know NATS; learning curve.
  - Overkill for our event volume.

### Option D — Apache Kafka
At‑least‑once, durable, replayable, well known.
- **Cons**: very heavy for our volume; requires ZooKeeper/KRaft; significant ops cost. **Rejected.**

## Comparison matrix

| Dimension                                  | **A. Postgres LISTEN/NOTIFY** | B. Redis pub/sub | C. NATS+JetStream | D. Kafka |
|--------------------------------------------|:------------------------------:|:----------------:|:-----------------:|:--------:|
| Extra containers in compose                | **0**                         | 1                | 1 or 3 (cluster)  | 3+ (ZK/KRaft + brokers) |
| Transactional with DB state change         | ✓✓                            | ✗                | ✗                 | ✗        |
| Delivery guarantee (default)               | at‑most‑once                  | at‑most‑once     | at‑least‑once     | at‑least‑once |
| Ops complexity                             | minimal                       | low              | medium            | high     |
| Throughput headroom                        | enough for ≪ 10k/sec          | high             | very high         | very high |
| Payload size                               | ≤ 8 kB                        | unlimited        | large             | large    |
| Engineer familiarity                       | wide                          | very wide        | medium            | wide     |
| Suits our actual volume                    | ✓✓                            | ✓                | ✓ (overkill)      | ✗ overkill |

## Recommendation

**Option A — Postgres `LISTEN/NOTIFY` for v1.**

Reasoning:
1. **Zero extra container.** Self‑hosters get the change channel "for free" with the DB they already run. This matches the operator preference established in [ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md) and [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md).
2. **Transactional with state changes** is a real win for *correctness*. When the Admin REST API commits a `services` row insert, the `service.registered` notification fires iff the commit succeeds. No publisher‑crash window.
3. **Reconciliation endpoint** is already on the books (ADR‑0006 open follow‑ups) regardless of transport, so at‑most‑once delivery is acceptable.
4. **Volume is low.** Even if we 100× the projected event rate, LISTEN/NOTIFY handles it without trouble.
5. **Behind a small abstraction**: the channel client is a Go (or Python) interface; swapping to Redis or NATS later is a one‑file change in a half dozen places.

### Honest alternative
**Redis pub/sub (Option B)** if we ever need:
- Larger payloads than 8 kB (we don't today; we send IDs).
- Decoupling from the DB (e.g., the channel must keep working when Postgres is reconciliation‑only).
- Higher fan‑out than Postgres can comfortably handle.

**NATS (Option C)** is overkill for v1 but a credible upgrade if we ever want at‑least‑once delivery with replay built into the transport.

## Tech stack pinning (if accepted)

| Concern                | Choice                                                          |
|------------------------|-----------------------------------------------------------------|
| Transport              | Postgres `LISTEN/NOTIFY` on dedicated channels                   |
| Channels               | One per event family per tenant: `mintkey:<tenant_slug>:service`, `:credential`, `:agent`. (Subscribers can filter or subscribe to a wildcard pattern via multiple LISTENs.) |
| Payload                | JSON with `event_id` (ULID), `event_type`, `tenant_id`, `actor_id`, `target_id`, `key_version?`, `at` (RFC3339). Body fields are references, not full payloads. |
| Publisher (Python)     | `asyncpg` `connection.execute("NOTIFY ...")` inside the same transaction as the state change |
| Publisher (Go)         | `pgx` `conn.Exec(ctx, "NOTIFY ...")` inside the same `pgx.Tx` |
| Subscriber (Go)        | `pgx` `conn.Listen(ctx, "...")` on a dedicated connection from a small reconnecting wrapper |
| Subscriber (Python)    | `asyncpg` `connection.add_listener(...)` |
| Reconciliation         | `GET /v1/changes?since=<event_id>` on the Admin REST API; subscribers call this on startup and after disconnect, paginated |
| Heartbeat              | A `mintkey:heartbeat` notification every 30 s so subscribers detect stale connections |

## Implications
- The change channel client is **a small Go package** (`mintkey/packages/go/changes`) and **a small Python package** (`mintkey.changes`) — same wire format, same channel names.
- The `mintkey/admin-api` is the **single publisher**: every state change goes through its handlers (or audit chokepoint), and each handler publishes from within the DB transaction.
- The proxy plugin, the Kong‑syncer, and the MCP Server are **subscribers**.
- **Multi‑tenant scoping** is in the channel name; subscribers can choose to listen to all tenants (Kong‑syncer) or to one tenant (an MCP Server instance dedicated to one tenant in the high‑isolation tier).
- **Reconciliation contract** — `GET /v1/changes?since=<event_id>&limit=<n>` returns events in (event_id, at) order. Iteration 4 publishes the schema.

## Threat model considerations
- A subscriber receives only events for the channels it `LISTEN`s on. Cross‑tenant leakage is impossible by construction *if* channel names are tenant‑scoped — which they are.
- The Postgres role used by subscribers has only the LISTEN privilege; cannot publish. Publishers use the application role.
- Channel payload is small and references‑only; no PII or credential material flows over the channel.

## Open follow‑ups (iteration 2)
- Channel name conventions (final form vs. above proposal).
- Reconciliation pagination size and cadence on disconnect.
- Whether to add a Redis‑based "fast lane" for token revocation specifically (sub‑100ms target) if Postgres LISTEN/NOTIFY ever proves too slow. Default: defer.
- Heartbeat detection algorithm in subscribers (timeout, backoff, alarm).

## Related
- [ADR‑0006 token format](../01-architecture/adr/0006-token-format-and-binding.md) — defines what flows over the channel.
- [ADR‑0004 egress proxy](../01-architecture/adr/0004-egress-proxy-kong.md) — the proxy plugin is the primary subscriber.
- [ADR‑0008 multi‑tenancy](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md) — channels are tenant‑scoped.
