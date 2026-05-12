# Open architectural questions

A living register of architectural questions that have been **identified, deemed non‑blocking for the current state, and are tracked here until resolved**. Each entry has an ID, severity, source, owning phase, and status.

When an open question is resolved, it moves into an ADR (or amendment) and the entry here is marked **Resolved → ADR‑NNNN** with a pointer.

## Severity legend
- 🟡 **High** — should be resolved within the named phase to avoid implementation churn.
- 🟢 **Medium** — workable as a documentation note or implementation discipline.

## Index

| ID | Title | Severity | Source | Phase / Owner | Status |
|----|-------|:--------:|--------|----------------|--------|
| OQ‑001 | Hash‑chain semantics on tenant deletion | 🟡 | Adversarial pass 2 (#C) | Phase 2, when tenant deletion ships | Open |
| OQ‑002 | App‑layer tenant filter — concrete CI test | 🟡 | Adversarial pass 2 (#E) | Phase 1 milestone 1.0 + 1.12 | Open |
| OQ‑003 | Vault Adapter horizontal scaling | 🟢 | Adversarial pass 2 (#F) | Phase 2 | Open |
| OQ‑004 | Audit serialization at sustained per‑tenant volume | 🟢 | Adversarial pass 2 (#G) | Phase 1 benchmark; Phase 2 fix if hot | Open |
| OQ‑005 | Operator tenant‑switch race in AdminJS | 🟢 | Adversarial pass 2 (#H) | Phase 1 implementation | Open |
| OQ‑006 | Reconciliation endpoint fanout caching | 🟢 | Adversarial pass 2 (#J) | Phase 1 implementation | Open |
| OQ‑007 | Channel‑name documentation in change‑channel wrappers | 🟢 | Adversarial pass 2 (#K) | iteration 2 closeout doc | Open |
| OQ‑008 | JWT `iss` for per‑tenant signing keys | 🟢 | Subagent #1 / Adv pass 2 (#O) | Phase 2 | Open |
| OQ‑009 | AdminJS public‑key bootstrap mechanics | 🟢 | Adversarial pass 2 (#P) | Phase 1 seed‑job spec | Open |
| OQ‑010 | AdminJS form‑submit latency budget | 🟢 | Adversarial pass 2 (#Q) | Phase 1 documentation | Open |
| OQ‑011 | Per‑tenant rate limits split (Kong + FastAPI) | 🟢 | Adversarial pass 2 (#R) | Phase 1 documentation | Open |
| OQ‑012 | Liquibase changelog naming convention | 🟢 | Adversarial pass 2 (#S) | KIRO.md note | Open |
| OQ‑013 | Boot‑secret rotation operational mechanics | 🟢 | Adversarial pass 2 (#T) | Phase 1 implementation | Open |
| OQ‑014 | `AgentApiKey` declared in OpenAPI but unapplied to any endpoint | 🟢 | Subagent security review (F‑11) | Iteration 4 closeout | Open |
| OQ‑015 | Constant‑time compare guidance for Bearer Agent API Key in MCP tools docs | 🟢 | Subagent security review (F‑13) | Iteration 4 closeout | Open |
| OQ‑016 | `Tenant.settings` closed schema (currently open object) | 🟢 | Subagent security review (F‑15) | Phase 1 implementation | Open |
| OQ‑017 | `api_key_fingerprint` format consistency (full SHA‑256 vs 8‑hex) | 🟢 | Subagent security review (F‑18) | Iteration 4 closeout | Open |
| OQ‑018 | `username_attempted` length cap and salted hash in production | 🟢 | Subagent security review (F‑19) | Phase 2 hardening | Open |
| OQ‑019 | `redirect_uri` allowlist validation algorithm | 🟢 | Subagent security review (F‑20) | Phase 1 implementation | Open |
| OQ‑020 | Proto field `(mintkey_sensitive) = true` option for codegen | 🟢 | Subagent security review (F‑23) | Phase 1 implementation | Open |
| OQ‑021 | Change‑event envelope explicit no‑hash‑chain note | 🟢 | Subagent security review (F‑24) | Iteration 4 closeout | Open |
| OQ‑022 | Per‑service min/max/default TTL bounds exposed in MCP `service_full` | 🟢 | Subagent security review (F‑26) | Iteration 4 closeout | Open |
| OQ‑023 | `/.well-known/jwks.json` belongs to broker, not admin-api | 🟡 | P2G coverage audit | Phase 2 | Open |
| OQ‑024 | `/v1/services` and `/v1/agents` (tenant-prefix-less) — needed? | 🟢 | P2G coverage audit | Phase 2 | Open |
| OQ‑025 | `/v1/audit` (tenant-prefix-less) — redundant with `/v1/tenants/{id}/audit`? | 🟢 | P2G coverage audit | Phase 2 | Open |
| OQ‑026 | `/v1/tenants/{id}/changes` SSE feed — deferred; design needed | 🟡 | P2G coverage audit | Phase 2 | Open |

---

## Per‑question detail

### OQ‑001 — Hash‑chain semantics on tenant deletion 🟡
[ADR‑0014.7](adr/0014-iter-1-2-corrections.md) makes the audit hash chain mandatory and per‑tenant. [ADR‑0016.7](adr/0016-round-2-corrections.md) makes tenant deletion cascade with an audit `tenant.deleted` event in the chain. **Open**: when a tenant is hard‑purged for GDPR, does the chain go too, or is it retained as a compliance record? Today's posture: chain is the canonical record, retained; the GDPR right‑to‑erasure case needs a separate decision. **Phase 2** when deletion ships.

### OQ‑002 — App‑layer tenant filter — concrete CI test 🟡
[ADR‑0014.1](adr/0014-iter-1-2-corrections.md) replaces tenant‑scoped channel names with a global channel + application‑layer filter. The wrapper enforces a mandatory tenant‑scope config; an arch test asserts wrappers are correctly configured. **Open**: write the integration test that fuzzes events across tenants and asserts no leakage to a wrong‑tenant subscriber. Goes into Phase 1 milestone 1.0 (Foundation) and milestone 1.12 (Multi‑tenant smoke test) acceptance criteria.

### OQ‑003 — Vault Adapter horizontal scaling 🟢
After [ADR‑0014.4](adr/0014-iter-1-2-corrections.md) drops the proxy‑plugin plaintext cache, every proxy request hits the Vault Adapter. The v1 file backend (SQLite) is single‑writer. Phase 2 production needs a horizontal‑scaling story. Candidates: (a) bring HashiCorp Vault forward as v2 (already on the roadmap), (b) read‑mostly Vault Adapter replicas with file replication, (c) gRPC load balancer in front of stateless Vault Adapter instances sharing storage. **Phase 2** decision.

### OQ‑004 — Audit serialization at sustained per‑tenant volume 🟢
The mandatory hash chain serializes audit emission per tenant. At low‑hundreds events/sec per tenant, Postgres handles it. **Open**: at what point does it become hot? Plan: benchmark in Phase 1 with synthetic workload; if a tenant ever exceeds a threshold (TBD, likely ~500/sec sustained), shard the chain (per‑category sub‑chains within tenant). Phase 2 fix if a tenant is actually hot.

### OQ‑005 — Operator tenant‑switch race in AdminJS 🟢
Operator opens a service‑edit form for tenant A, switches to B, submits. The signed JWT to FastAPI ([ADR‑0014.6](adr/0014-iter-1-2-corrections.md)) carries `tnt`; FastAPI validates `tnt` matches the targeted resource's tenant. Pre‑existing form contents are submitted with the OLD tenant's resource id but the NEW session tenant — FastAPI rejects with `tenant_mismatch`. **Open**: implementation detail — does AdminJS proactively invalidate open forms on tenant switch, or do we rely on the FastAPI rejection + UI error? Phase 1 implementation choice.

### OQ‑006 — Reconciliation endpoint fanout caching 🟢
On a FastAPI restart, every change‑channel subscriber reconciles via `GET /v1/changes?since=`. N subscribers in flight = N concurrent identical‑shape queries. **Open**: add response cache with very short TTL (e.g., 1 s) keyed by `(tenant_filter, since, limit)`. Phase 1 implementation detail.

### OQ‑007 — Channel‑name documentation in wrappers 🟢
[ADR‑0014.1](adr/0014-iter-1-2-corrections.md) changed the channels from per‑tenant to global. The `mintkey/internal/changes` (Go) and `mintkey.changes` (Python) wrapper packages need their READMEs updated to describe the global channel naming. **iteration 2 closeout** doc work.

### OQ‑008 — JWT `iss` for per‑tenant signing keys 🟢
v1 uses a shared signing key; `iss = mintkey/broker`; key rotation via `kid`. **Phase 2** opt‑in is per‑tenant signing keys. Open: does `iss` become `mintkey/broker/<tenant_slug>` (more explicit but breaks consumers expecting fixed `iss`) or stay constant with `kid` carrying tenant context? **Lean: stay constant; `kid` encodes both `(tenant_id, key_version)`**. Phase 2 follow‑up to [ADR‑0006](adr/0006-token-format-and-binding.md).

### OQ‑009 — AdminJS public‑key bootstrap mechanics 🟢
[ADR‑0014.6](adr/0014-iter-1-2-corrections.md) has AdminJS hold a private key; FastAPI fetches the public key from the Vault Adapter on startup. **Open**: who writes the public key into the Vault Adapter on first deploy? The seed job. Specifics — keypair generated where (deploy‑time vs. seed‑time), public key stored under what credential type ID. Phase 1 seed‑job specification.

### OQ‑010 — AdminJS form‑submit latency budget 🟢
[ADR‑0014.5](adr/0014-iter-1-2-corrections.md) routes all AdminJS writes through FastAPI. Each submit: browser → AdminJS Express → FastAPI → DB. Empirical p50 estimate ~50–150 ms. **Open**: pin a budget and measure in Phase 1. Acceptable for an admin UI but worth a load test before declaring v1 done. Phase 1 documentation note.

### OQ‑011 — Per‑tenant rate limits split (Kong + FastAPI) 🟢
[S‑MT‑3](03-quality-attributes.md) demands per‑tenant noisy‑neighbor isolation. Two enforcement layers: Kong's stock `rate-limiting` plugin (data‑plane RPS); FastAPI's own per‑tenant `request_token` limiter (control plane). **Open**: documentation that the two layers are intentional and where each rule lives. Plus a small ADR if we ever unify them. Phase 1 documentation.

### OQ‑012 — Liquibase changelog naming convention 🟢
[ADR‑0015](adr/0015-liquibase-schema-source-of-truth.md) makes Liquibase the schema source of truth. **Open**: pin the file naming convention — `vNN-short-description.yaml` with monotonic `NN`; commit‑lint check that catches non‑monotonic numbering. Lives in `KIRO.md`.

### OQ‑013 — Boot‑secret rotation operational mechanics 🟢
[ADR‑0014.2](adr/0014-iter-1-2-corrections.md) introduces per‑service boot secrets to the Vault Adapter. Rotation: re‑run the seed job (or its rotation subcommand) with an overlap window. **Open**: hot‑reload mechanism — does the service watch the boot‑secret file (inotify‑style) and pick up rotation, or require a SIGHUP, or restart? **Lean: file watch with fallback to SIGHUP**. Phase 1 implementation detail.

---

### OQ‑023 — `/.well-known/jwks.json` belongs to broker, not admin-api 🟡
The OpenAPI contract lists `GET /.well-known/jwks.json` but the broker service (Go) owns JWT signing keys. The admin-api has no signing keys to publish. This endpoint must be served by the broker service and the OpenAPI contract should be split (or a note added clarifying the owning service). **Phase 2** — update OpenAPI contract ownership annotation or split the spec.

### OQ‑024 — `/v1/services` and `/v1/agents` (tenant-prefix-less) 🟢
OpenAPI lists `GET /v1/services`, `POST /v1/services`, `GET /v1/agents`, `POST /v1/agents` without a tenant prefix. These appear to be implicit shortcuts to the active tenant's resources (per the OpenAPI description text). It is unclear whether these are required for Phase 1 or are a convenience for the MCP server path. **Phase 2** — clarify whether these are genuine routes or spec artifacts; if genuine, implement in admin-api or as MCP-facing routes.

### OQ‑025 — `/v1/audit` (tenant-prefix-less) 🟢
OpenAPI lists `GET /v1/audit` without a tenant prefix, alongside the already-implemented `GET /v1/tenants/{id}/audit`. It is ambiguous whether the prefix-less route is a platform-wide audit view (PlatformAdmin only, all tenants) or a duplicate artifact. **Phase 2** — decide if needed and implement accordingly.

### OQ‑026 — `/v1/tenants/{id}/changes` SSE feed deferred 🟡
The OpenAPI contract defines `GET /v1/tenants/{id}/changes` as an SSE (Server-Sent Events) feed for per-tenant change events. This is architecturally distinct from the implemented `GET /v1/changes` (global feed with tenant filtering). The per-tenant SSE variant requires SSE response type support in FastAPI and a separate design decision on whether it duplicates or replaces the global feed. **Phase 2** — design the SSE response, decide on overlap with `/v1/changes`, then implement.

## Maintenance
- New issues found in adversarial reviews land here as `OQ‑NNN`.
- When an OQ is resolved by an ADR, change Status to `Resolved → ADR‑NNNN` and keep for history; remove from the index 30 days later.
- Severity is the editor's call; raise it in PR review if needed.
