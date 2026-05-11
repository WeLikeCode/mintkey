# P‑010 — Long‑lived agent access: extended token class vs. the alternatives

**Status**: Accepted — 2026-05-11. See § "Outcome". **Option A** (automatic token refresh) is adopted for agents; **Option E** (classical static service API keys, added during discussion) is adopted for non‑agent clients; Options **B** and **C** are rejected. ADR‑0018 will cover Option E (classical API keys), *not* the extended‑JWT class. The `long-lived-api-keys` Kiro spec is **re‑scoped to Option E**.

> Upstream of the `long-lived-api-keys` Kiro feature spec (`.kiro/specs/long-lived-api-keys/`). The spec originally described **Option C** below; this proposal exists because Option C changes a settled architectural decision (ADR‑0006's TTL ceiling) and inverts a stated product invariant ("agents never hold a usable credential"). The deliberation below surfaced a fifth option — classical static API keys for non‑agent clients — which addresses the underlying need more honestly than C. See § "Outcome" for the decision.

## Question

When an agent runs a workflow that outlives a standard brokered token's TTL (default 10 min, max 1 hour per ADR‑0006), how does it keep access — and which of those mechanisms, if any, do we build?

## Context

### The actual need

The driver is ergonomic, not functional: a long‑running agent workflow must re‑obtain a token before the current one expires. Today an agent does this by re‑calling MCP `request_token` (authenticating with its durable Agent API Key) — a single ~50 ms call the agent runtime makes. The complaint is "I have to implement a refresh loop in my agent runtime." There are two sharper sub‑cases worth separating out:

1. **Suspended‑and‑resumed workflows** — a workflow serialized to disk and resumed days later in a fresh process. On resume its token has expired; it must re‑authenticate to MCP with its Agent API Key and re‑request. (This works fine today as long as the runtime knows to do it on resume — the Agent API Key is the durable identity.)
2. **Single long‑lived upstream operation** — the agent's workload is one long HTTP request, a streaming response, or a websocket that can't tolerate a mid‑stream `Authorization` header swap. Refresh‑before‑expiry doesn't help here, because the agent can't rotate the credential mid‑request.

### Quality‑attribute scenarios in tension

- [S‑SEC‑3](../01-architecture/03-quality-attributes.md) — *bounded blast radius of a stolen credential*. A short‑TTL token's blast radius is its TTL; a 7‑day token's is 7 days (minus revocation latency).
- [S‑PERF‑1](../01-architecture/03-quality-attributes.md) / [S‑PERF‑2](../01-architecture/03-quality-attributes.md) — proxy hot path ≤ 30 ms p99 added latency; token issuance ≤ 50 ms p99 at 100/s. A refresh‑every‑10‑min model raises issuance volume; a per‑request revalidation callback adds proxy hot‑path latency.
- [S‑OPS‑1](../01-architecture/03-quality-attributes.md) — revoke an agent in ≤ 5 s. With a long‑lived token this becomes "revoke within `min(5 s change‑channel, revalidation interval)`" rather than "within 5 s and anyway the token dies in 10 min."
- [S‑AVAIL‑1](../01-architecture/03-quality-attributes.md) — control‑plane outage doesn't stop in‑flight work. A fail‑closed degradation for long‑lived tokens is a deliberate departure from this (the proposed new `S‑AVAIL‑2`).

### Threats

- **Credential theft from a compromised agent host** — the agent already holds its Agent API Key long‑term, so the host is already a trust anchor; the question is whether a *long‑lived access token* is a meaningfully worse thing to also leak. It is, for two reasons: (a) per‑request authorization constraints (`time_window`, `rate_limit`) are evaluated at issuance for standard tokens and do **not** survive a multi‑hour token; (b) instant revocation of the *agent* (ADR‑0008 `agents.status`) stops new `request_token` calls immediately, but a previously‑issued long‑lived token keeps working until the change channel propagates the `jti` revocation.
- **Token theft in transit / from logs** — mitigated for any token by short TTL; for a long‑lived token only mandatory proof‑of‑possession (`cnf.jkt`) reduces it (a leaked token alone is then unusable).
- **Replay** — `jti` denylist; for long‑lived tokens the denylist entry must persist for the token's whole life (memory growth — bounded, but real).

## Options

### Option A — Automatic token refresh (no new credential class)

The agent runtime transparently re‑calls `request_token` (with its Agent API Key) before `exp`. Mintkey's only change is ergonomic: `request_token` returns a `refresh_at` hint (e.g. `iat + 0.8·ttl`), and the MCP `describe_service` / docs spell out the refresh pattern. **Variant A′:** additionally raise the *standard* per‑service max TTL from 1 hour to an operator‑configurable cap of up to ~4 hours for services where the operator accepts the slightly larger blast radius — still a "standard" token, no new class, no new claims, no new components.

- **Pros**: zero new architecture; perfect alignment with the "agents never hold a usable long‑lived credential" thesis; smallest blast radius (≤ TTL); revocation stays trivially fast (token dies on TTL anyway); handles the suspended‑and‑resumed case (the Agent API Key is the durable identity, re‑request on resume); A′ buys 4× headroom for the issuance‑volume concern without any of Option C's machinery.
- **Cons**: the agent runtime must implement a refresh loop (one‑time cost per runtime, not per workflow); does nothing for sub‑case 2 (single long‑lived upstream operation); at very large scale (≳ 100 k concurrently‑active agent‑service pairs refreshing every 10 min ⇒ ≳ 170 issuances/s) you exceed S‑PERF‑2's tested 100/s and must either use A′ or scale the Broker — a known, ordinary scaling problem.
- **Cost**: tiny. A `refresh_at` field in the `request_token` output schema; doc updates; (A′) one Liquibase column `services.max_standard_ttl` + a validation bound + the Broker honoring it. ~1–2 small tasks.

### Option B — Refresh‑token pattern (long‑lived *request* capability, not a long‑lived *access* credential)

The agent obtains a long‑lived **refresh token** that is *not* a bearer credential for any backend — it can only be exchanged (at MCP, bound to a `cnf.jkt` key and/or the agent's registered session) for a short‑lived access token. The agent thus never holds a long‑lived *use* capability; it holds a long‑lived *request* capability that is narrower than its Agent API Key (e.g. scoped to one `(service, action)`).

- **Pros**: keeps the access token short‑lived (S‑SEC‑3 preserved for the thing that actually touches backends); the refresh token, if scoped, is a least‑privilege improvement over re‑using the Agent API Key for everything; no per‑request proxy revalidation (the proxy still sees only short‑lived access tokens); no new long‑running component.
- **Cons**: the refresh token's *only* advantage over the existing Agent‑API‑Key‑plus‑`request_token` flow is the scoping — and that scoping is also obtainable, more cheaply, by issuing **scoped Agent API Keys** (a smaller, separable feature); a new credential type with its own issuance/exchange/storage/revocation surface; still does nothing for sub‑case 2.
- **Cost**: medium — comparable wire/contract surface to Option C but no reaper, no proxy revalidation callback, no client‑mTLS plumbing. ~8–12 tasks.

### Option C — Source‑bound long‑lived access token (`token_class: "extended"` — the current Kiro spec)

A brokered JWT with `token_class: "extended"`, TTL 1 h – 7 d (operator‑configurable per service), **mandatory** `cnf.jkt` proof‑of‑possession, **mandatory** periodic proxy revalidation against the Broker every `reval` seconds, fail‑closed when the change channel is down > 30 s, a per‑(agent, service) concurrency cap, idle auto‑revocation, a dedicated registry table, and a new long‑running `token-reaper` container. Fully specified in `.kiro/specs/long-lived-api-keys/{requirements,design}.md`.

- **Pros**: directly addresses both sub‑cases (the agent can hold one token for the life of a long upstream operation); the mandatory `cnf.jkt` means a leaked *token* alone is unusable; the revalidation callback bounds revocation latency to `reval` even if a change‑channel event is dropped.
- **Cons**: highest cost and operational burden of any option (new credential class, ~5 new wire surfaces, a new container with leader election, a new alert, a rollback security‑regression runbook, client‑mTLS plumbing whose feasibility through Kong→go‑pdk is itself an open question — see design §11); worst thesis alignment (the requirements doc concedes "this feature does NOT preserve the 'agent never holds a usable credential' property in its pure form"); the agent now holds *both* the token *and* the PoP key for up to 7 days, so a compromised agent host yields 1 h–7 d of access throttled only by revocation latency; strictly worse than the status quo for `time_window`/`rate_limit`‑constrained grants (which the spec therefore forbids extended tokens for); the elaborate mitigation apparatus (mandatory PoP + revalidation + fail‑closed + reaper + concurrency cap + idle auto‑revoke) exists *to make a fundamentally riskier design tolerable* — effort that Option A avoids by not creating the risk.
- **Cost**: high — ~7 milestones, ~20–25 tasks, one new container, contract changes across OpenAPI/MCP/proto/JSON‑Schema/SQLAlchemy.

### Option D — Do nothing (reject the feature)

Keep the status quo: standard tokens only, agents refresh via `request_token`. (Differs from Option A only in that A adds a small `refresh_at` ergonomic hint; D adds literally nothing.)

- **Pros**: zero cost; smallest blast radius; perfect thesis alignment.
- **Cons**: ignores the ergonomic ask entirely; nothing for sub‑case 2.
- **Cost**: none.

### Option E — Classical (static) service API keys for non‑agent clients (added during discussion)

A long‑lived **opaque** token (`mk_svckey_…`, Argon2id‑hashed at rest, fingerprinted) that an operator issues from the Admin Console, bound to an existing Agent + a Service + a subset of that Agent's `(service, action)` grants + an optional expiry + optional `Constraints`. A non‑agent client (a script, cron job, CI pipeline, third‑party integration) presents it directly at the proxy — `Authorization: Bearer mk_svckey_…` to `/v1/call/<service_id>/<path>` — with **no MCP discovery and no `request_token` dance**. The proxy recognises the `mk_svckey_` prefix, resolves the key **server‑side** against the Broker on a cache miss (short cache, default 60 s), re‑checks the requested action and all four `Constraints` kinds **on every request**, and injects the real backend credential. Revocation is instant (evict the cache via the change channel; bounded anyway by the cache TTL). The audit / OTel record only the fingerprint, never the plaintext.

This is *not* a competitor to A — it serves a different audience. A is for **agents** (which have a live MCP connection and a durable Agent API Key); E is for **classical clients** (which want a credential they can paste into a config file).

- **Pros**: it is what "I want an API key" actually means — the well‑understood API‑gateway primitive, honest about what it is (a bearer key, server‑side‑resolved, fast‑revocable) rather than dressing up a long‑lived JWT; because the proxy does a server‑side lookup anyway, **all four `Constraints` kinds (incl. `time_window` and `rate_limit`) are enforced per request** — so a classical key can be *more* tightly scoped than an extended JWT ever could; revocation is effectively instant; no new credential *class* on the JWT (the JWT path is untouched); reuses existing RBAC (a key can never exceed its bound Agent's grants); no per‑request proxy→broker call on the happy path (cache hit), so S‑PERF‑1 holds; no fail‑closed departure from S‑AVAIL‑1 needed for the cache‑hit path (a brief resolver outage is absorbed by the cache; only a cache miss during a resolver outage fails closed — and that's a `min(cache TTL, outage)` window).
- **Cons**: a leaked classical key grants its `(service, actions)` until revoked — the classic API‑key tradeoff (mitigated by short cache TTL ⇒ fast revoke, optional expiry, optional mandatory `source_ip_allowlist`, fingerprint‑only audit); a new credential type with CRUD + an Admin Console surface + a resolution endpoint + a proxy cache; binds to an Agent in v1, which means a "pure API‑key client" Agent also has an MCP key (a small future flag — "disable MCP for this Agent" — fixes that).
- **Cost**: medium — ~one new table, a Broker `POST /v1/api-keys/resolve` endpoint, proxy prefix‑recognition + resolution cache + per‑request constraint re‑check, Admin REST API CRUD, an AdminJS resource, a change‑channel event. No new long‑running container (no reaper — a classical key has an explicit expiry or runs until revoked; nothing periodic to do). ~10–14 tasks.

## Recommendation

**Adopt Option A (with variant A′ available per operator), and reject Option C.**

Rationale:

1. **The need is ergonomic and Option A meets it at near‑zero cost.** "Refresh before expiry" is a one‑time implementation in the agent runtime, not a per‑workflow burden; a `refresh_at` hint makes it trivial. The suspended‑and‑resumed case (sub‑case 1) already works — the Agent API Key is the durable identity.
2. **Option C's cost/benefit is upside‑down.** It is the most expensive, most operationally heavy, worst‑thesis‑aligned option, and its security story is "build an elaborate apparatus so that a long‑lived bearer credential is tolerable." The cheaper, safer move is to not hand the agent a long‑lived bearer credential.
3. **Sub‑case 2 (a single long‑lived upstream operation) is the only real gap, and it shouldn't be solved with an agent‑held credential.** The proxy already holds the real backend credential; if a backend operation must outlive a 10‑min token, the right design is for the *proxy* to keep the upstream connection alive and re‑inject the credential as needed, while the agent's token continues to rotate normally. That is a proxy‑side feature (a future proposal, if a concrete backend demands it), not a new credential class.
4. **If a scoped‑long‑lived‑request need ever materializes, Option B's value is the scoping — and scoped Agent API Keys deliver that more cheaply.** Defer Option B until that need is concrete; prefer scoped Agent API Keys when it is.

**Concretely for v1:**
- `request_token` output gains `refresh_at` (RFC 3339), advisory, `≈ iat + 0.8·ttl`.
- MCP `describe_service` and the agent‑developer docs document the refresh pattern (including "on workflow resume, re‑authenticate with the Agent API Key and re‑request").
- (A′, optional, gated on operator opt‑in per service) a `services.max_standard_ttl` column, default 3600, validated `[60, 14400]`; the Broker clamps standard‑token requests to it. No new claims, no new components. This is the *only* concession toward "longer tokens," and it stays within the "standard" class with all its existing constraint enforcement.

## Outcome

**Decided 2026-05-11:**

- **Option A is adopted** for the agent‑refresh case: `request_token` gains an advisory `refresh_at` field; the MCP / agent‑developer docs document the refresh pattern (including re‑authenticating with the Agent API Key on workflow resume). Variant **A′** (`services.max_standard_ttl`, default 3600, validated `[60, 14400]`, operator opt‑in) is available. This stays entirely within ADR‑0006 — recorded as a one‑line ADR‑0006 follow‑up note, not a new ADR. ~2–3 tasks.
- **Option E is adopted** for the non‑agent‑client case: classical static service API keys (`mk_svckey_…`), operator‑issued, bound to an existing Agent + Service + a subset of that Agent's grants + optional expiry + optional `Constraints`, resolved server‑side at the proxy with a short cache, fast‑revocable. This is the substantive new feature. It is what "support API keys in classical terms" means: the standard API‑gateway primitive, with all four `Constraints` kinds enforced per request (the proxy does a server‑side lookup anyway).
- **Option C is rejected** — cost/benefit upside‑down; its mitigation apparatus exists only to make a long‑lived bearer JWT tolerable when Option A avoids the risk and Option E meets the "I want an API key" need honestly.
- **Option B is deferred** — its only edge over the status quo is scoping, and *scoped Agent API Keys* (a separate, smaller feature) deliver that more cheaply; revisit only if a concrete scoped‑long‑lived‑request need appears.
- **`ADR-0018` will be `ADR-0018-classical-service-api-keys`** (covering Option E), *not* the extended‑JWT class.
- The `long-lived-api-keys` Kiro spec is **re‑scoped to Option E**: `requirements.md` and `design.md` are rewritten for classical service API keys. The extended‑JWT versions are superseded (retained in git history as the rejected‑Option‑C record).

## Implications

- **Option A (agent refresh):** `request_token` output schema gains `refresh_at` (RFC 3339, advisory, `≈ iat + 0.8·ttl`); MCP/docs updated. (A′, if taken) Liquibase column `services.max_standard_ttl` (default 3600, `[60, 14400]`), Broker clamps standard requests to it. No new claims, no new components, no container‑count change. Captured as an ADR‑0006 follow‑up note. Tracked separately from the `long-lived-api-keys` spec — likely a tiny `token-refresh-ergonomics` Kiro spec or just folded into mintkey‑mvp's M1.5 (token issuance) tasks.
- **Option E (classical API keys) — `ADR-0018` agenda:** token format and prefix (`mk_svckey_…`, Argon2id‑hashed, fingerprinted); the server‑side‑resolution model + the proxy resolution‑cache TTL bound (default 60 s, max 300 s); that keys bind to an existing Agent in v1 (vs a dedicated service‑account principal — a noted future refinement); the resolution endpoint owner (Broker, consistent with it being the token authority and already running an HTTP server) and its `svcid_proxy` authentication; the `mintkey:code` enum delta (added to ADR‑0017.10); the change‑channel event (`api_key.revoked` on `mintkey:agent`); whether a `source_ip_allowlist` (or expiry) can be made mandatory via an `AdminSettings` policy. Once Accepted, the re‑scoped `long-lived-api-keys` design generates `tasks.md` (~10–14 tasks; no new long‑running container).
- **mintkey‑mvp impact:** Option A is within ADR‑0006 (no impact beyond the `refresh_at` field). Option E adds a `service_api_keys` table, a Broker resolve endpoint, a proxy resolution cache + prefix recognition, Admin REST API CRUD, an AdminJS resource, OpenAPI/SQLAlchemy/audit‑schema/OTel‑allowlist updates — but **no new container**, so the 17‑container count is unchanged.
- **Rejected‑C cleanup:** the extended‑JWT `requirements.md`/`design.md` are overwritten by the re‑scope; if anyone wants the Option‑C draft back, it's in git history at the commit before the re‑scope.

## Open follow‑ups

- **Proxy‑held long‑lived upstream sessions** — the proper answer to sub‑case 2. Out of scope here; spin up a proposal if a concrete backend requires it. Note this needs no agent‑credential change at all — the proxy already holds the real credential.
- **Scoped Agent API Keys** — a small feature (an Agent API Key restricted to a subset of the agent's `(service, action)` grants) that delivers Option B's least‑privilege benefit without a refresh‑token layer. Worth its own proposal if least‑privilege‑for‑long‑lived‑request becomes a requirement.
- **Issuance‑volume monitoring** — whichever option wins, add a `mintkey_token_issued_total` rate panel and an alert if it approaches the Broker's tested ceiling, so the "scale the Broker vs. raise `max_standard_ttl`" decision is data‑driven.
