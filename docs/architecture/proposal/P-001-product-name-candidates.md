# P‑001 — Product name

**Status**: Accepted (→ [ADR‑0002](../01-architecture/adr/0002-product-name-mintkey.md)) — 2026-05-10.

## Question
What do we call this thing?

## Context
Naming a credential broker is harder than naming a CRUD app: the name has to suggest *brokering*, *credentials*, *agents*, or *gating*, without (a) infringing existing trademarks (Vault, Latchkey, Pomerium, Boundary, Auth0, …) and (b) being so generic it's un‑Googleable.

Naming feeds: repo name, container image namespace, Helm chart, MCP server identifier, docs domain, marketing.

## Options

### Option A — `Mintkey`
- Suggests the *minting* of short‑lived keys.
- 1‑word, 7 letters, easy to say.
- Minor: "mint" is overused in fintech.

### Option B — `Brokerkey`
- Most literal: it brokers keys.
- Easy to grok in the README.
- A bit clunky; sounds like a noun and a verb fighting.

### Option C — `Latch`
- Short. Suggests gating ("latch the door").
- Echoes the Latchkey reference (deliberately tributary, not a knock‑off).
- Risk of conflict with similarly‑named projects.

### Option D — `Conduit`
- Suggests the *path* the agent takes through us.
- Used elsewhere (Buoyant Conduit/Linkerd, Conduit data movement). Likely unavailable.

### Option E — `Keysmith`
- Evokes both *making* keys and craftsmanship.
- 8 letters. Likely available.

### Option F — `Vouch`
- We *vouch* for the agent to the backend. Short.
- Probably collides with Vouch Proxy.

## Recommendation
**Option A — `Mintkey`** for the working title. Short, evocative of short‑lived token minting, and straightforward to register. Revisit before iteration 5 (implementation) if a trademark check turns up a blocker.

## Outcome
**Accepted** on 2026-05-10. Promoted to [ADR‑0002](../01-architecture/adr/0002-product-name-mintkey.md). The product is **Mintkey**.

## Implications
- Repo: `mintkey/`.
- Image namespace: `mintkey/<container>` (e.g., `mintkey/proxy`, `mintkey/broker`).
- MCP server identity: `mintkey`.
- Docs site (eventually): `mintkey.dev` or similar.

## Discussion
*(empty — please add comments inline.)*
