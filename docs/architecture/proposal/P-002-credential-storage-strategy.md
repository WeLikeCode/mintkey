# P‑002 — Credential storage strategy

**Status**: Accepted (→ [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md)) — 2026-05-10.

> **Outcome**: Option C is adopted (pluggable Vault Adapter), but the v1 backend is **not** SQL+KMS as recommended below. Instead, v1 is an **encrypted file on an externally mounted volume**, with **HashiCorp Vault** as v2 and **SQL+KMS** as v3. See [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md) for the rationale.

## Question
Where and how do we store the real backend credentials, and what is the trust root?

## Context
Quality attribute scenarios that constrain this:
- [S‑SEC‑2](../01-architecture/03-quality-attributes.md#ssec2--credentials-at-rest-are-encrypted-with-a-kmsrooted-key) — credentials at rest encrypted with a KMS‑rooted key.
- [S‑OPS‑2](../01-architecture/03-quality-attributes.md#sops2--operator-can-rotate-a-backend-credential-without-agent-changes) — rotate without agent changes.
- [S‑MOD‑1](../01-architecture/03-quality-attributes.md#smod1--adding-a-new-backend-auth-scheme-is-small-and-local) — adding a new auth scheme stays small.
- [S‑PERF‑1](../01-architecture/03-quality-attributes.md#sperf1--proxy-latency-overhead-is-bounded) — proxy hot path stays under 10 ms p50 added latency.

Threats that constrain this:
- **Tampering** of ciphertext (need AEAD).
- **Information disclosure** via DB dump (need KMS‑rooted KEK).
- **Compromise of the proxy** (limit cache scope; fast credential zeroization).

## Options

### Option A — HashiCorp Vault as the only credential store
- Vault holds credentials; Vault Adapter is a thin client.
- **Pros**: mature, well‑audited, granular policies, dynamic secrets, native rotation engines, OAuth/OIDC and database secret engines built in.
- **Cons**: an additional production dependency to operate; overkill for the MVP self‑hoster who "just wants `docker compose up`"; per‑credential read latency adds to the proxy hot path.

### Option B — SQL + envelope encryption against an external KMS
- Credentials live as ciphertext in Postgres. DEKs are unique per credential, encrypted by a KEK that lives in an external KMS.
- **Pros**: no extra production dependency beyond Postgres + KMS (which we need anyway); simplest "single docker‑compose" story (KMS emulator for dev); DEK can be cached encrypted, so the hot path needs at most one KMS roundtrip on cache miss.
- **Cons**: we own the encryption code (small but security‑critical); we have to write rotation tooling.

### Option C — Pluggable Vault Adapter, ship A and B as alternative backends
- The Vault Adapter exposes one interface; one implementation is HashiCorp Vault, another is SQL+KMS.
- **Pros**: lets users pick; respects S‑MOD‑1; future‑proof.
- **Cons**: maintaining two implementations is more work; risks divergent semantics; feature‑surface bloat.

## Recommendation
**Option C as the architectural intent, with Option B as the default and only‑shipped backend for the MVP.**

The Vault Adapter abstraction ships now (so we don't repaint later), but only the SQL+KMS implementation is in v1. HashiCorp Vault arrives as a second adapter in a later release driven by demand.

## Outcome (supersedes the recommendation above)
**Accepted** on 2026-05-10 with a **different v1 backend than this proposal recommended**, captured in [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md):

- The pluggable Vault Adapter (Option C) is adopted, as recommended.
- **v1 backend is "encrypted file on an externally mounted volume"** (a fourth option, not in the original list above), chosen so the MVP needs no external KMS or Vault to run.
- **v2 backend is HashiCorp Vault** (Option A from above).
- **v3 backend is SQL + envelope encryption with external KMS** (Option B from above).

The decision rationale and the security caveats of the file backend are documented in ADR‑0003.

## Implications
- Vault Adapter is a real C&C container, not a library hidden in the Admin API.
- For dev: a KMS emulator (e.g., LocalStack KMS or a stub) runs in compose.
- For prod: cloud KMS is configured via env; the bring‑your‑own‑KMS contract is part of iteration 2.
- The DEK cache (encrypted) is per‑proxy‑instance, keyed by `(service_id, key_version)`, with TTL ≤ JWT TTL.

## Open follow‑ups
- OAuth2 token refresh — Vault Adapter responsibility or separate Token Manager? *Recommendation: Vault Adapter, with a credential‑type‑specific "refresh hook" interface.*
- Per‑credential KMS key vs. single tenant KEK? *Recommendation: single tenant KEK in v1; per‑credential KEK is a 2.x concern.*
- Hash chain on the audit log — bake into Audit Service or rely on KMS‑signed logs? *Recommendation: in‑service hash chain, periodic external anchor (later).*
