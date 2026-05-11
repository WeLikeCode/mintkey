# ADR‑0018: Classical service API keys for non‑agent clients

## Status
Accepted — 2026-05-11. Drafted from [P‑010](../../proposal/P-010-extended-token-class.md) (Option E, selected). Amends [ADR‑0016](0016-round-2-corrections.md) §16.6 (`AdminSettings` schema) and [ADR‑0017](0017-round-3-corrections.md) §17.10 (`mintkey:code` enum). Does **not** amend [ADR‑0006](0006-token-format-and-binding.md) — brokered JWTs are unchanged; the proxy distinguishes the two credential kinds by prefix.

## Context

Mintkey's core invariant — call it the **credential‑indirection invariant** — is:

```
  Client  ──(Mintkey‑issued key)──▶  Mintkey  ──(real backend credential)──▶  Backend service
```

The client (an agent, or any other caller) only ever holds a **Mintkey‑issued key**. That key is *not* the real backend credential; it is an indirection handle that Mintkey resolves, then swaps for the real credential — which Mintkey holds in the Vault Adapter (ADR‑0003) and which never leaves Mintkey. Because the handle is Mintkey's, Mintkey can revoke it at any instant; in that sense the client's key is always *temporary relative to the real credential*, even when its nominal lifetime is long.

Today this invariant is realised for **agents** via the brokered JWT (ADR‑0006): the agent calls MCP `request_token`, gets a short‑lived JWT, presents it at `/v1/call/<service_id>/<path>`, and the proxy injects the real credential. The JWT *is* the agent's "temporary API key" in the diagram above.

But many real callers are **not agents** and cannot perform the MCP discovery + `request_token` exchange: a deploy script, a cron job, a CI pipeline, a third‑party webhook receiver, an off‑the‑shelf SaaS integration. They want what every API gateway offers: a key you paste into a config file and present like any REST credential. There is no such thing in Mintkey today.

[P‑010](../../proposal/P-010-extended-token-class.md) considered making the *agent's brokered JWT* long‑lived to serve this need (Option C — the "extended token class"); that was **rejected** as cost/benefit‑upside‑down and as inverting the "agents never hold a usable credential" property. P‑010's adopted answer for non‑agent callers is **Option E**: a *classical service API key* — a long‑lived opaque token that is still a Mintkey‑issued indirection handle (so the invariant above holds for non‑agent clients exactly as it does for agents), server‑resolved, instantly revocable, and never the real backend credential.

This ADR codifies Option E.

## Decision

### 1. The indirection invariant holds for classical clients too

A classical service API key is the **non‑agent flavour** of the diagram above:

```
  Non‑agent client  ──(mk_svckey_…)──▶  Mintkey egress proxy  ──(real backend credential)──▶  Backend service
                          │                       │
                          │                       └─ resolved server‑side via the Broker; the real
                          │                          credential is fetched from the Vault Adapter
                          │                          per request and never cached as plaintext
                          └─ a Mintkey‑issued handle; the client never sees the real credential;
                             Mintkey can revoke this handle at any instant
```

The key the client holds (`mk_svckey_…`) is **not** a backend credential and **not** something the client can use anywhere except at Mintkey's `/v1/call/<service_id>/<path>` route. Presenting it to the MCP server, the Admin REST API, or the backend directly does nothing.

### 2. Token format

- Wire form: `mk_svckey_<Crockford base32 of 32 random bytes>` (≈ 52 chars after the prefix). The `mk_svckey_` prefix is **reserved** and MUST NOT collide with any other Mintkey token prefix (`mk_agent_` for Agent API Keys, `svcid_*` for service‑identity boot secrets, `eyJ…` for brokered JWTs). The proxy's credential‑type dispatch is by prefix.
- At rest: only the **Argon2id hash** (same parameters as the Agent API Key) and an **8‑byte fingerprint** `hex(sha256(plaintext)[:8])` are stored. The plaintext is never stored; it is returned exactly once, in the 201 response at creation/rotation, and the Admin Console shows it once with a "store it now" warning.
- The fingerprint is the lookup index (O(1)); the Argon2id verify is the actual authentication. The fingerprint is a non‑reversible quasi‑identifier — safe in audit payloads and logs; **not** a span attribute.

### 3. Binding and authority

A classical service API key binds to:
- exactly **one existing Agent** (the *bound Agent*),
- exactly **one Service**,
- a non‑empty subset of that Agent's `(service, action)` permission grants for that Service (the key's `allowed_actions`),
- an optional `expires_at` (absent = no expiry),
- an optional `constraints` object — the **closed** `Constraints` schema (ADR‑0016.4): `request_path_prefix`, `source_ip_allowlist`, `time_window`, `rate_limit`; `additionalProperties: false`.

A key can never exceed its bound Agent's grants. **Revoking the bound Agent revokes all its classical keys** (the resolver checks `agents.status`). In v1, "service account that exists only to back API keys" is achieved by creating an Agent and not using its MCP key; a dedicated principal type is a future refinement (see Open follow‑ups).

### 4. Server‑side resolution (the Broker), with a short proxy cache

- The Broker exposes an **internal** endpoint `POST /v1/api-keys/resolve`, authenticated with `X-Mintkey-Service-Token: <svcid_proxy>` (ADR‑0014.2). It is not part of the public OpenAPI surface.
- Given `{key_fingerprint, presented_key, service_id, tenant_id}` it: sets `app.current_tenant` (bound parameter, never f‑string SQL); looks up the row by fingerprint (RLS‑scoped); does a **constant‑time Argon2id verify** of `presented_key` against the stored hash — and, for an unknown fingerprint, verifies against a fixed dummy hash so timing does not reveal fingerprint existence; checks revoked / bound‑agent‑revoked / expired / service‑match; returns `{api_key_id, agent_id, service_id, allowed_actions, constraints, expires_at}` on success, or `401` with one of the error codes in §7. It returns the **uniform** `api_key_invalid` for malformed / unknown‑fingerprint / verify‑failed (no existence oracle); it logs the precise reason in its own structured log only. It is rate‑limited per fingerprint and per caller; `429` on either. It emits **no audit event** per call (the proxy's `proxy.hit` records usage).
- The proxy caches a successful resolution **keyed by fingerprint** for `AdminSettings.api_key.proxy_cache_ttl_seconds` (default 60, range `[10, 300]`). A cache **hit** performs no Argon2id and no Broker call; a cache **miss** performs one Argon2id verify in the Broker (~50–100 ms by design — Argon2id is deliberately slow; with the default TTL each key incurs at most one such verify per minute regardless of request rate). The cache holds **only the binding metadata** above — never the real backend credential (still fetched from the Vault Adapter per request), never the plaintext key, never any DEK; it is analogous to the existing JWKS metadata cache and does not conflict with ADR‑0014.4 ("no plaintext credential cache in the proxy plugin"). The proxy discards the presented plaintext after computing the fingerprint and (on a miss) forwarding it to the Broker.

### 5. Per‑request checks at the proxy (every request, hit or miss)

In order: (a) the resolution's `service_id` equals the URL's `service_id` — else `api_key_wrong_service`; (b) `expires_at` (if present) is in the future — else `api_key_expired` and evict the cache entry; (c) the request's action (derived from `{method, path}` by the same service‑action mapping the brokered path uses to derive `scope`) is in `allowed_actions` — else `api_key_action_not_allowed`; (d) **every** present `Constraints` kind is satisfied for *this* request — `request_path_prefix`, `source_ip_allowlist`, `time_window` (in the constraint's timezone), `rate_limit` (per‑`api_key_id` per‑proxy‑instance token bucket) — else `api_key_constraint_failed` naming the failing kind. On all checks passing, the proxy fetches the real credential from the Vault Adapter and injects it per the service's auth scheme exactly as on the brokered path, strips the client's `Authorization` before forwarding, and runs the response scrubber.

**Note:** because the proxy does a server‑side lookup anyway, **all four `Constraints` kinds — including `time_window` and `rate_limit` — are enforced per request.** This is a genuine improvement over a brokered token (where `time_window`/`rate_limit` are evaluated once at issuance): a classical key with a `time_window` is usable *only* during that window, every time.

### 6. Revocation

Operator‑initiated revocation sets `revoked_at`/`revoked_by`/`revoke_reason`, emits the `api_key.revoked` audit event (on the per‑tenant hash chain), and publishes `api_key.revoked` on the global `mintkey:agent` channel (ADR‑0014.1), carrying `key_fingerprint` — all in one DB transaction. The proxy evicts the cache entry for that fingerprint within 5 s of the change‑channel event; absent the event, the entry expires naturally within the cache TTL. So a revoked key stops working within `min(5 s, AdminSettings.api_key.proxy_cache_ttl_seconds)`. Revoking the bound Agent (`agents.status = 'revoked'`) has the same effect via the existing `agent.revoked` handling plus a cache‑eviction‑by‑`agent_id` step. Rotation = create a new key with the same binding (new plaintext, shown once) + `api_key.rotated` audit + an operator‑controlled overlap before the old key is explicitly revoked.

### 7. New `mintkey:code` values (extends ADR‑0017.10's closed enum)

`api_key_invalid`, `api_key_expired`, `api_key_revoked`, `api_key_wrong_service`, `api_key_action_not_allowed`, `api_key_constraint_failed`, `api_key_resolution_unavailable` (the cache‑miss‑during‑resolver‑outage fail‑closed case), `api_key_actions_exceed_grant` (Admin REST API, 422), `api_key_policy_violation` (Admin REST API, 422 — an operator‑policy violation at creation).

### 8. Operator policies (extends ADR‑0016.6's closed `AdminSettings` schema)

A new `api_key` sub‑object: `proxy_cache_ttl_seconds` (int, default 60, `[10, 300]`), `require_expiry` (bool, default `false`), `allow_no_expiry` (bool, default `true`), `max_expiry_days` (int, default 365, `[1, 3650]`), `require_ip_allowlist` (bool, default `false`). An operator who wants classical keys to be "temporary" in the duration sense sets `require_expiry: true` and a small `max_expiry_days`; an operator who wants them source‑pinned sets `require_ip_allowlist: true`.

### 9. Identifiers, audit, OTel

- The key plaintext is `mk_svckey_<…>`. The `api_key_id` that appears on the wire (audit payloads, list responses) is a prefixed ULID `svckey_<ULID>` (ADR‑0017.11), with the DB column holding the 128‑bit body as `UUID` (the same treatment as `jti`).
- New audit events on the per‑tenant hash chain: `api_key.created` (`{api_key_id, key_fingerprint, agent_id, service_id, allowed_actions, expires_at, constraints, created_by}` — **never the plaintext**), `api_key.revoked`, `api_key.rotated`. `proxy.hit` gains `auth_method` (`"brokered_jwt"` | `"api_key"`), and for `api_key`: `api_key_id`, `key_fingerprint`, and (on denial) `reason_code` — never the plaintext.
- OTel: the `/v1/call/...` span gets `mintkey.auth_method` (the enum value only — never the key or fingerprint); added to the span‑attribute allowlist (ADR‑0017.6). The architecture red‑team grep (mintkey‑mvp T‑1.3.3) is extended to assert zero `mk_svckey_…` strings in any log, span export, or `audit_events.payload`.

### 10. Persistence (Liquibase is the source of truth — ADR‑0015)

A new Liquibase changeset creates `service_api_keys` (`id UUID PK`, `tenant_id`, `agent_id`, `service_id`, `key_hash`, `key_fingerprint CHAR(16)`, `allowed_actions TEXT[]`, `constraints JSONB`, `expires_at`, `last_used_at`, `revoked_at`, `revoked_by`, `revoke_reason`, `created_at`, `created_by`), with a `UNIQUE` on `key_fingerprint`, `CHECK`s (`allowed_actions` non‑empty; `expires_at IS NULL OR expires_at > created_at`), and partial indexes whose predicates are **IMMUTABLE only** — `WHERE revoked_at IS NULL`, never `now()` (which would fail the migration); "active" is a query‑time filter. The table gets the byte‑for‑byte standard tenant‑isolation RLS policy (ADR‑0014.8, ADR‑0016.3) in the same changeset; it is a tenant‑scoped table, not on the platform‑scoped RLS‑exclusion allowlist. The changeset includes an explicit `rollback` block. The SQLAlchemy mirror is regenerated from the post‑migration schema (CI mirror‑diff gate). `last_used_at` is updated by the Admin REST API inside the `proxy.hit` audit transaction (the proxy never writes the DB — ADR‑0014.4), coalesced to ≤ 1 write per `api_key_id` per minute.

### 11. What this ADR does NOT do

- It does **not** change brokered JWTs (ADR‑0006). Agents continue to use short‑lived JWTs (plus the `refresh_at` ergonomic hint adopted as P‑010 Option A — that is a separate ADR‑0006 follow‑up note, not this ADR).
- It does **not** introduce the rejected "extended token class" (P‑010 Option C). No `token_class`/`reval`/mandatory‑`cnf.jkt` claims; no `token-reaper` container; no container‑count change.
- It does **not** add an MCP surface. Classical keys are operator‑issued (Admin Console / Admin REST API) and used only by non‑agent clients at the proxy. Agents cannot create, list, or use them via MCP.

## Consequences

### Positive
- The credential‑indirection invariant (`Client → Mintkey key → Mintkey → real credential → Backend`) now covers **non‑agent clients**, not just agents — the real backend credential still never leaves Mintkey.
- Non‑agent clients get the familiar API‑gateway UX: a key in a config file, used like any REST credential.
- Because resolution is server‑side, **all four `Constraints` kinds are enforced per request** — a classical key can be *more* tightly scoped (path, source IP, time window, rate) than a brokered token ever was.
- Revocation is effectively instant (`min(5 s, cache TTL)`); revoking the bound Agent cascades.
- Reuses existing RBAC (a key ⊆ its bound Agent's grants), the existing Vault‑Adapter credential‑injection path, the existing audit chokepoint + hash chain, the existing change channel.
- **No new long‑running container.** The 17‑container compose count is unchanged.

### Costs
- A leaked classical key grants its `(service, allowed_actions)` until revoked — the standard API‑key tradeoff. Mitigated by: short cache TTL ⇒ fast revoke; optional and optionally‑mandatory expiry (`require_expiry`, `max_expiry_days`); optional and optionally‑mandatory `source_ip_allowlist`; fingerprint‑only audit/logs/OTel; can't exceed the bound Agent's grants; bound‑Agent revocation cascades.
- A new credential type with CRUD endpoints, an AdminJS surface, a Broker resolution endpoint, and a proxy resolution cache + prefix‑dispatch branch.
- A resolution‑cache **miss** costs the Argon2id verify (~50–100 ms, by design). The cache amortises this to ≤ 1 verify per key per `proxy_cache_ttl_seconds`; high‑rate distinct API‑key clients may warrant a larger TTL or a scaled Broker — an ordinary scaling lever.
- A schema change spanning Liquibase + SQLAlchemy mirror + Pydantic + OpenAPI + audit/change‑event schemas + OTel allowlist (the standard fan‑out for any wire change, per ADR‑0014.3 / ADR‑0015).

### Risks
- **Resolution‑endpoint outage during a cache miss** ⇒ fail‑closed for that key (`api_key_resolution_unavailable`, HTTP 503). Cache hits are served normally throughout the outage; the exposure window for a revocation during an outage is `min(cache TTL, outage)`. Accepted.
- **`rate_limit` is per‑proxy‑instance** (token buckets aren't shared across replicas) — as for permission‑grant rate limits. Exact global rate limiting is out of scope.
- **Prefix collision** — `mk_svckey_` must never collide with `mk_agent_`, `svcid_*`, or the JWT shape. Enforced by an architecture test that asserts the prefixes are pairwise non‑overlapping.
- **Fingerprint truncation** — an 8‑byte fingerprint has a ~50% collision chance at ~2³² keys; the `UNIQUE` constraint forces a regenerate‑and‑retry at creation, so in practice this is a non‑issue at any realistic scale. If a deployment ever approached that scale, the fingerprint width is a one‑column migration.

## Implications
- **Amends ADR‑0016.6** — the closed `AdminSettings` schema gains an `api_key` sub‑object (§8). A Status‑line corrigendum on ADR‑0016 points here.
- **Amends ADR‑0017.10** — the closed `mintkey:code` enum gains the codes in §7. A Status‑line corrigendum on ADR‑0017 points here.
- **Does not amend ADR‑0006** — brokered JWTs are untouched; the proxy distinguishes credential kinds by prefix. The Option‑A agent‑refresh ergonomics (`refresh_at`, `services.max_standard_ttl`) are a separate, smaller ADR‑0006 follow‑up note, not part of this ADR.
- The `long-lived-api-keys` Kiro spec (`requirements.md` + `design.md`, already rewritten for Option E) is **unblocked once this ADR is Accepted** and may then generate `tasks.md` (~10–14 tasks: schema, proxy classical‑key branch + cache, Broker resolve endpoint, Admin REST API CRUD, AdminJS resource, contract propagation, tests).
- The threat model (`05-threat-model.md`) MUST gain an entry for "leaked classical service API key" and its mitigations before this feature ships.
- KIRO.md / AGENTS.md / CLAUDE.md guardrails gain: "classical API keys (`mk_svckey_…`) are operator‑issued, server‑resolved, never the real credential; the proxy distinguishes them from brokered JWTs by prefix; the resolution cache holds binding metadata only, not secrets."

## Open follow‑ups
- **Service‑account principal type** — an identity that has classical API keys but no MCP key (an `agents.mcp_enabled` flag, or a separate `service_accounts` table). v1 binds a key to an existing Agent; this is a noted refinement, not v1 scope.
- **Global (cross‑replica) rate limiting** for the `rate_limit` constraint — a separate concern, shared with permission‑grant rate limits.
- **`describe_service` exposure** — whether (and how) an operator‑facing discovery surface should advertise "this service accepts classical API keys". Out of scope here; a small future decision.
- **Fingerprint width / hashing** — keep 8 bytes of SHA‑256, or move to a wider/parameterised digest. 8 bytes is fine at any realistic scale; revisit only if a deployment proves otherwise.
- **Negative caching** at the proxy (caching a `401` briefly to absorb a flood of a known‑bad key) — v1 relies on the Broker's per‑fingerprint rate limit plus a brief per‑fingerprint backoff in the proxy; a short negative cache is a possible later optimisation.

## Related
- [P‑010 — long‑lived agent access: extended token class vs. the alternatives](../../proposal/P-010-extended-token-class.md) — the option set; Option E (this ADR) and Option A (ADR‑0006 follow‑up) adopted, Options B and C rejected.
- [ADR‑0006 — token format and binding](0006-token-format-and-binding.md) — the brokered JWT; the **agent‑path counterpart** of this ADR. Unchanged here.
- [ADR‑0003 — credential storage strategy](0003-credential-storage-strategy.md) — the Vault Adapter; the real backend credential lives there and is fetched per request.
- [ADR‑0008 — multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md), [ADR‑0014 §14.8 — RLS architecture test](0014-iter-1-2-corrections.md), [ADR‑0016 §16.3 — PlatformAdmin RLS escape](0016-round-2-corrections.md) — the RLS template `service_api_keys` uses.
- [ADR‑0015 — Liquibase is the schema source of truth](0015-liquibase-schema-source-of-truth.md) — the `service_api_keys` table is a Liquibase changeset.
- [ADR‑0016 §16.4 — closed `Constraints` schema](0016-round-2-corrections.md) — the constraints a classical key may carry.
- [ADR‑0016 §16.6 — admin‑settings endpoint](0016-round-2-corrections.md) — amended here (the `api_key` sub‑object).
- [ADR‑0017 §17.10 — REST↔MCP error‑code mapping / closed `mintkey:code`](0017-round-3-corrections.md) — amended here (the new codes). [§17.11 — ULID‑with‑prefix wire form](0017-round-3-corrections.md) — `svckey_<ULID>`.
- [ADR‑0014 §14.2 — service identity boot secrets](0014-iter-1-2-corrections.md) — the `svcid_proxy` identity the Broker resolve endpoint authenticates. [§14.4 — no plaintext cache in the proxy plugin](0014-iter-1-2-corrections.md) — the resolution cache holds metadata only, consistent with this. [§14.7 — audit hash chain mandatory](0014-iter-1-2-corrections.md) — the new audit events are on the chain.
