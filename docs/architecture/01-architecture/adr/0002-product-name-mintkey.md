# ADR‑0002: Adopt "Mintkey" as the product name

## Status
Accepted — 2026-05-10. Promoted from [`proposal/P-001-product-name-candidates.md`](../../proposal/P-001-product-name-candidates.md), Option A.

## Context
[`P‑001`](../../proposal/P-001-product-name-candidates.md) considered six naming options for the product (Mintkey, Brokerkey, Latch, Conduit, Keysmith, Vouch). The name needs to suggest credential brokering, be short and memorable, avoid trademark conflicts with adjacent products (Vault, Latchkey, Pomerium, Boundary, Auth0, Vouch Proxy, Conduit/Linkerd), and be Google‑able.

The naming choice cascades into:
- Repo and folder names.
- Container image namespace (`<name>/<container>`).
- MCP server identity string.
- Metric prefix (`<name>.*`).
- Documentation domain (eventually).

Continuing with no name forces every doc to say "the system" or "this product" and blocks iteration 2 deliverables (concrete `docker-compose.yml`, image tags, metric naming) which already need a real prefix.

## Decision
The product is named **Mintkey** (one word, capitalized at the start of a sentence, lowercase elsewhere — including in image names, metric names, and CLI tools).

The name is interpreted as evoking the *minting* of short‑lived keys — which is exactly what the Credential Broker does.

## Consequences
**Adopted immediately:**
- Repo namespace: `mintkey/`.
- Container image namespace: `mintkey/<container>` (e.g., `mintkey/proxy`, `mintkey/broker`, `mintkey/admin-api`).
- MCP server identity string: `mintkey`.
- Metric prefix: `mintkey.*` (already used in [`docs/04-observability/README.md`](../../04-observability/README.md)).
- Documentation references to "the system" *may* be progressively replaced with "Mintkey" as docs are touched, but no bulk rename is required — the system‑neutral phrasing in iteration 1 docs remains valid.

**Open follow‑ups:**
- A trademark / availability check (USPTO, EUIPO, npm, PyPI, Docker Hub, GitHub org) must complete before iteration 5 (implementation). If the check turns up a blocker, this ADR is superseded by a follow‑up ADR proposing a replacement name; image and metric namespaces will then change in lock‑step.
- A domain (`mintkey.dev` or similar) is not procured at this stage; deferred until first public release.

**Costs / risks:**
- "Mint" is overused in fintech; potential SEO collisions. Mitigated by always pairing with a descriptor in marketing material (e.g., "Mintkey — credential broker for agents").

## Related
- [`P‑001 product‑name‑candidates`](../../proposal/P-001-product-name-candidates.md) — Accepted (this ADR).
- [`ADR‑0001 record‑architecture‑decisions`](0001-record-architecture-decisions.md) — establishes the proposal → ADR pipeline this ADR follows.
