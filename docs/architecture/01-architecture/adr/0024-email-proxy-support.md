# ADR-0024: Email Proxy Support for Agent Email Operations

## Status
Proposed — 2026-06-01

## Context
Agents need to send and receive emails transparently without holding email credentials (passwords, OAuth2 tokens). The current egress proxy (ADR-0004) is HTTP-only and cannot proxy IMAP/SMTP traffic. Email protocols are stateful (IMAP) or transactional (SMTP), requiring a different approach than HTTP reverse proxying.

**Design Question: REST API vs Transparent Protocol Proxy**

The SSH proxy (ADR-0022) uses the actual SSH protocol transparently — agents connect with standard SSH tools and the bastion bridges the connection. Should the email proxy follow the same pattern?

Quality attributes affected:
- S-SEC-1: Agent never holds usable backend credential
- S-AUD-1: Every credential use is logged
- S-MOD-1: New auth scheme touches ≤3 files in proxy

## Decision

### D1: Email Proxy Architecture — Hybrid Approach (Transparent Protocol + REST API)

Deploy a **separate Go binary** (`apps/email-proxy/`) implementing both transparent IMAP/SMTP protocol handling AND REST API:

| Approach | How it works | When to use |
|----------|-------------|-------------|
| **Transparent IMAP/SMTP** | Agent connects with standard email client on ports 993/587 | Full email feature access |
| **REST API** | Agent calls REST endpoints on port 8088 | Simpler integration via MCP tools |

Both approaches share the same credential fetching, protocol handling, and audit infrastructure. Agents choose the approach that fits their needs.

### D2: New Auth Schemes

Add three new auth schemes to vault.proto, openapi.yaml, tools.yaml, and audit-event.schema.json:

- `AUTH_SCHEME_EMAIL_PASSWORD = 14` — username:password
- `AUTH_SCHEME_EMAIL_OAUTH2 = 15` — OAuth2 refresh token JSON
- `AUTH_SCHEME_EMAIL_APP_PASSWORD = 16` — app-specific password (e.g., Gmail 2FA)

### D3: Agent Authentication Flow

Agents authenticate via **brokered JWTs** (same pattern as HTTP proxy):
1. Agent requests JWT via MCP `request_token(service_id, action="send:email")`
2. Broker issues JWT with `aud=service_id`, `scope=action`, `tnt=tenant_id`
3. Agent uses JWT to authenticate to email proxy

**Permission model** (4 actions):
- `read:email` — list/read/search/download
- `send:email` — send email
- `write:email` — move, mark flags
- `delete:email` — delete

### D4: Transparent Protocol Authentication (IMAP/SMTP)

Agents authenticate to the email proxy using the **same pattern as SSH proxy** (ADR-0022):

**IMAP (port 993):** Agent presents JWT as password via `AUTHENTICATE PLAIN`
**SMTP (port 587):** Agent authenticates via `AUTH XOAUTH2` with JWT

The email proxy validates JWT, fetches backend credentials from Vault, and bridges the connection transparently. Agent uses standard email tools (Thunderbird, mutt, etc.).

### D5: Agent Interface (REST API)

Endpoints on port 8088:
- `GET /v1/email/mailboxes`
- `GET /v1/email/messages?mailbox=INBOX&limit=50`
- `GET /v1/email/messages/{id}`
- `POST /v1/email/send`
- `DELETE /v1/email/messages/{id}`
- `POST /v1/email/messages/{id}/move`
- `POST /v1/email/messages/{id}/flags`
- `POST /v1/email/search`
- `GET /v1/email/attachments/{id}`

### D6: MCP Tools

- `list_mailboxes()` — read:email
- `list_emails(mailbox, limit, after)` — read:email
- `read_email(id)` — read:email
- `send_email(to, subject, body, cc?, bcc?, attachments?)` — send:email
- `search_emails(query, mailbox?, limit?)` — read:email
- `delete_email(id)` — delete:email
- `move_email(id, mailbox)` — write:email
- `download_attachment(id)` — read:email
- `mark_email(id, flags)` — write:email

MCP server routes email tool calls via `email_proxy_url` config (global, tenant isolation via JWT `tnt` claim).

### D7: OAuth2 Support

Support Gmail (Google OAuth2), Outlook (Microsoft Graph OAuth2), and custom providers.

**OAuth2 Flow (CSRF-protected):**
1. Operator configures email service in Admin UI
2. admin-api generates cryptographic `state` parameter, stores in session
3. admin-ui redirects to provider with `state`
4. Provider redirects back with code + state
5. admin-ui validates `state` matches session
6. **admin-api** receives callback, validates `state`, performs token exchange (holds `client_secret`)
7. admin-api stores refresh token in Vault Adapter via gRPC
8. On each operation, email-proxy fetches refresh token from Vault, exchanges for access token

**Key decisions:**
- **admin-api holds `client_secret`** (consistent with Keycloak pattern in ADR-0020)
- **admin-api performs token exchange** (not email-proxy, not admin-ui)
- **Refresh token stored in Vault** (never in database or memory)
- **Singleflight** prevents concurrent refresh storms
- **Expiration handling**: emit `email.service.auth_expired` audit event, update service status to `error`

### D8: ID Scheme

Wire IDs for email resources:
- **Messages**: `uid:<imap_uid>` (opaque, not ULID — protocol-specific)
- **Attachments**: `att:<message_uid>:<part_number>`
- **Mailboxes**: IMAP mailbox names used directly (e.g., "INBOX", "Sent")

### D9: Attachment Support (Phase 1)

- Send via multipart/form-data
- Receive as base64-encoded JSON (small attachments) or streaming endpoint
- Download via `GET /v1/email/attachments/{id}` with `Content-Type: application/octet-stream`
- Size limit: 25MB per attachment, 50MB total (configurable)

### D10: TLS Termination

Port 8088 requires TLS termination:
- **Production**: Kong TCP route (preferred)
- **Alternative**: mTLS between MCP server and email proxy
- **Development**: Plain HTTP with documented trust boundary

### D11: Connection Pooling

IMAP connections pooled per `(tenant_id, service_id)`:
- Default 5 connections per pool, idle timeout 5 minutes
- **Tenant isolation**: connections never shared across tenants
- UIDVALIDITY tracking detects mailbox recreation
- Health checks via IMAP `NOOP` every 60s
- SMTP connections created per-operation (transactional, not pooled)

### D12: Security Measures

- **IMAP/SMTP injection prevention**: parameterized SEARCH, `go-message` for MIME, reject `\r\n` in headers
- **Domain filtering**: RFC 5322 parser, configurable allowlist per service
- **Rate limiting**: per (agent_id, service_id, hour) via Postgres advisory locks (shared across instances)
- **Audit sanitization**: log query length/mailbox only (not query text), truncate subject to 100 chars
- **Service identity**: Vault Adapter `ValidateServiceIdentity` with boot secret

### D13: Audit Integration

Email proxy participates in audit hash chain via `auditq.Queue` → admin-api → Postgres:
- `prev_hash` + `hash` per event, per-tenant chain (ADR-0014.7)
- **New target_type**: `email_service`, `email_message`, `email_attachment`
- **New event types**: `email.sent`, `email.received`, `email.deleted`, `email.moved`, `email.searched`, `email.attachment.downloaded`, `email.service.registered`, `email.service.auth_expired`, `email.rate_limit.exceeded`, `email.domain.blocked`

### D14: Service Discovery

Email services appear in MCP `list_services`:
- Registered in `services` table with `auth_scheme: email_*`
- Email-specific config in `email_services` table
- **Single transaction** for both writes
- MCP server config: `email_proxy_url` (global, tenant isolation via JWT)
- Email proxy reads config from Postgres directly (like kong-syncer)

## Consequences

### Positive
- Agents send/receive emails without holding credentials
- Full audit trail for all operations
- OAuth2 support with CSRF protection
- Both transparent protocol and REST API for maximum flexibility
- Connection pooling reduces provider rate limits
- TLS termination protects credentials and content
- Granular permission model (read/send/write/delete)
- Shared rate limiting across proxy instances

### Costs
- ~5500 lines of new Go code
- New binary to deploy (3 ports: 993 IMAP, 587 SMTP, 8088 REST)
- IMAP/SMTP protocol complexity (RFC 3501 + extensions)
- OAuth2 flow management (token refresh, expiration handling, CSRF protection)
- Connection pool management (idle timeout, UIDVALIDITY tracking)

### Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Credential leak in memory dump | Medium | Zero on connection recycle; ADR-0014.4 pattern |
| IMAP state corruption | Low | UIDVALIDITY tracking; invalidate on mismatch |
| OAuth2 token refresh failure | Medium | Singleflight; exponential backoff; audit event on failure |
| Attachment DoS | Low | Configurable limits; streaming download endpoint |
| Rate limiting bypass | Medium | Postgres advisory locks (shared state); per-instance fallback |
| IMAP/SMTP injection | High | Parameterized SEARCH; RFC 5322 validation; reject `\r\n` |
| Domain filtering bypass | High | RFC 5322 parser; reject malformed addresses |
| Audit chain break | High | `auditq.Queue` → admin-api → Postgres; same as SSH proxy |
| OAuth2 CSRF | High | Cryptographic `state` parameter; validate on callback |
| Concurrent token refresh | High | Singleflight pattern |

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Raw IMAP/SMTP proxy | Agent holds credentials (violates S-SEC-1) |
| Email API gateway (SendGrid, etc.) | Vendor lock-in; no receive support |
| Embed in proxy-plugin | Different lifecycles; increases complexity |
| Separate IMAP + SMTP binaries | Operational overhead |
| Symmetric JWT validation | Violates ADR-0006 (JWS Ed25519) |
| Per-operation IMAP connections | Prohibitively expensive; hits provider limits |

## Amends
- ADR-0004: Email proxy is a sibling data-plane component
- ADR-0014.4: Connection-scoped credential holding acceptable (pool recycled after 5 min idle)
- ADR-0006: Validates brokered JWTs via JWKS (Ed25519)
- ADR-0008: Sets `app.current_tenant` from JWT `tnt` claim
- ADR-0014.7: Participates in audit hash chain via `auditq.Queue`
- ADR-0016.2: Force-refreshes JWKS on unknown `kid`

## Open Follow-ups
- Email templates (Phase 2)
- Webhook notifications (Phase 2)
- Email rules — auto-forward, auto-reply (Phase 2)
- Advanced search — full-text, date range (Phase 2)
- Attachment virus scanning (Phase 2)
- Email encryption — PGP, S/MIME (Phase 3)
- Evaluate `go-imap/v2` when stable

## Related
- ADR-0004: Egress proxy (Kong)
- ADR-0014.4: No plaintext credential cache
- ADR-0022: SSH Bastion (similar architecture pattern)
- ADR-0018: Classical API keys (similar auth pattern)
