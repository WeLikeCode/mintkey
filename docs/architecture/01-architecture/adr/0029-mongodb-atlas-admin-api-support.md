# ADR-0029: MongoDB Atlas Administration API Support

## Status
Proposed — 2026-06-28

## Context

Agents need to perform MongoDB Atlas **administrative** operations (manage projects, clusters, database users, network access, backups, alerts) through Mintkey. The Atlas Administration API (`https://cloud.mongodb.com/api/atlas/v2`) authenticates only via two schemes Mintkey does not support end-to-end:

- **Service Accounts** — OAuth 2.0 **client-credentials**. `client_id`/`client_secret` are exchanged at `https://cloud.mongodb.com/api/oauth/token` (`grant_type=client_credentials`, HTTP Basic, form body) for a **1-hour** Bearer access token. The `oauth2_client_credentials` enum value (5) is declared in `vault.proto`/OpenAPI/MCP but has no token-exchange implementation, payload schema, or admin-api validation.
- **Programmatic API Keys** — HTTP **Digest** (RFC 2617) challenge-response: public key as username, private key as password. Mintkey has no Digest support.

Two Atlas facts constrain the design:

1. The Administration API is **control-plane only** — it cannot read collection documents. The former Atlas Data API (HTTP document access) has been **retired**; reading documents requires the MongoDB wire protocol, which the HTTP egress proxy (ADR-0004) cannot carry. **Document reads are out of scope.**
2. Atlas v2 **requires** a dated `Accept: application/vnd.atlas.<yyyy-mm-dd>+json` header on every request, else **406**.

Quality attributes affected:
- **S-SEC-1**: Agent never holds a usable backend credential; no plaintext in logs/audit/spans.
- **S-AUD-1**: Every credential use is audited.
- **S-MOD-1**: A new auth scheme touches ≤3 files in the proxy (see D5).

This supersedes nothing; it extends the auth-scheme catalog established by ADR-0011 and the email-proxy precedent (ADR-0024).

## Decision

### D1: Scope — Administration API only

Mintkey supports the Atlas **Administration** API over the existing HTTP egress proxy. No MongoDB-wire data path, no document reads, no new proxy component.

### D2: OAuth2 client-credentials becomes a live-exchange scheme (enum 5, unchanged number)

The proxy performs the client-credentials exchange on demand, reusing — without modifying — the password-grant token-exchange engine (SSRF-hardened HTTP client, JSONPath/`expires_in` extraction, token cache, singleflight coalescing, graceful degradation, host-only `token.exchanged` audit). The exchange differs from password-grant in transport only: **form-encoded** `grant_type=client_credentials` (+ optional `scope`) with **HTTP Basic** `client_id:client_secret`. Credential payload:

```json
{ "token_url": "https://cloud.mongodb.com/api/oauth/token",
  "client_id": "...", "client_secret": "...",
  "scope": "(optional)", "token_response_path": "$.access_token" }
```

The exchanged token is injected as `Authorization: Bearer <token>` (the injector's existing scheme-5 case). A scheme-5 payload that is not exchange-shaped falls through to the existing pre-fetched-bearer behavior (backward-compatible).

### D3: New `http_digest` auth scheme (enum 18; 17 reserved)

Add `AUTH_SCHEME_HTTP_DIGEST = 18` to `vault.proto`, mirrored as `http_digest` in the OpenAPI and MCP enums and a Go `AuthScheme` constant. Credential payload `{public_key, private_key}`. The proxy performs RFC 2617 Digest via a **per-request Digest transport** on the reverse proxy (vetted `github.com/icholy/digest`), not a static header: the agent's `Authorization` is stripped and the Digest handshake supplies the upstream `Authorization`.

Integer **17 is reserved**, not assigned: the admin-api-only synthetic scheme `email_oauth2_client` (from feat/oauth2-providers-per-tenant-vault) already stores per-tenant OAuth2 client secrets in the vault at integer 17 without a canonical `vault.proto` entry. Rather than disturb that live feature (and risk its stored credentials), `http_digest` takes the next free canonical value 18, and `vault.proto` marks 17 `reserved` so no future canonical scheme collides. Regularizing `email_oauth2_client` into the canonical enum is a separate follow-up.

### D4: Read-scoped proxy actions — `read:atlas` and `admin:atlas`

Operators grant agents `read:atlas` (read-only) and/or `admin:atlas` (full). The proxy enforces a minimal, backward-compatible method gate: when the JWT `scope` is `read:atlas`, only `GET`/`HEAD`/`OPTIONS` are allowed (else `403`). `admin:atlas` and all pre-existing actions (`call`, email scopes) are unaffected. The broker continues to issue a scoped token only when a matching `permission_grants.action` row exists (defense in depth). This mirrors the email permission model (ADR-0024 D3) but is enforced in the HTTP proxy by method rather than by endpoint.

### D5: Version header is explicit, never injected

Mintkey does **not** add the Atlas `Accept` version header. Both Atlas service templates carry — in the agent-visible service `description` and operator `config_notes` — an explicit instruction to send `Accept: application/vnd.atlas.<yyyy-mm-dd>+json` on every request. The proxy already forwards agent request headers unchanged (only `Authorization` and `X-Mintkey-*` are stripped/replaced), so the agent-supplied header reaches MongoDB. No schema change; no per-service default-header mechanism.

### D6: S-MOD-1 file-count

The ≤3-files-in-proxy guidance fits injector-style schemes. Token-exchange schemes inherently need {payload struct, exchange, orchestration, dispatch}; `oauth2_client_credentials` follows the **existing** `oauth2_password_grant` footprint (`types.go`, `exchanger.go`, an egress handler, `main.go`). `http_digest` stays injector-style (`digest.go`, scheme const, `main.go`). This is a conscious, precedent-consistent choice, not new modularity debt.

### D7: Two service templates

`mongodb-atlas-service-account` (oauth2_client_credentials) and `mongodb-atlas-api-key` (http_digest), both `base_url: https://cloud.mongodb.com/api/atlas/v2`, Atlas v2 OpenAPI URL, `test_path: /groups`, scheme-appropriate credential hints, and the D5 version-header instruction.

## Consequences

**Positive**
- Agents get clean, audited access to the full Atlas Administration API via either MongoDB credential type.
- `oauth2_client_credentials` becomes generally usable (any client-credentials API), not just MongoDB.
- Read-only grants give operators least-privilege control independent of MongoDB-side roles.
- No new tables/columns; reuses the hardened token-exchange and credential-injection paths.

**Negative / trade-offs**
- Adds a third-party Go dependency (`github.com/icholy/digest`) to the proxy module.
- Two token-exchange schemes share similar-but-separate orchestration (accepted per D6).
- The agent must remember the Atlas version header; a forgotten header yields MongoDB's 406 (accepted per D5 — explicit over implicit, by operator/user choice).

**Out of scope (future)**
- MongoDB-wire data proxy / collection document reads.
- A per-service `default_headers` / `usage_notes` column to carry agent guidance more structurally.
- mTLS.

## References
- ADR-0004 (Kong egress proxy), ADR-0011 (shared Go stack), ADR-0014.4 (per-request plaintext), ADR-0017.6 (span redaction), ADR-0024 (email proxy — new-auth-scheme + permission-action precedent).
- OpenSpec change: `openspec/changes/mongodb-atlas-admin-api/`.
- MongoDB Atlas: Administration API v2 (`/api/atlas/v2`), Service Accounts (client-credentials, 1-hour tokens, `/api/oauth/token`), versioned API overview (`Accept: application/vnd.atlas.<date>+json`).
