# ADR-0024: Email Proxy Support for Agent Email Operations

## Status
Proposed — 2026-06-01

## Context
Agents need to send and receive emails transparently without holding email credentials (passwords, OAuth2 tokens). The current egress proxy (ADR-0004) is HTTP-only and cannot proxy IMAP/SMTP traffic. Email protocols are stateful (IMAP) or transactional (SMTP), requiring a different approach than HTTP reverse proxying.

Quality attributes affected:
- S-SEC-1: Agent never holds usable backend credential
- S-AUD-1: Every credential use is logged
- S-MOD-1: New auth scheme touches ≤3 files in proxy

## Decision

### D1: Email Proxy Architecture
Deploy a **separate Go binary** (`apps/email-proxy/`) that implements an email proxy service with **protocol multiplexing**:

- **Transparent protocol handling**: Agents call REST API endpoints without knowing the underlying protocol (IMAP/SMTP/OAuth2)
- **Protocol multiplexing**: Email proxy automatically selects the correct protocol and credentials based on the service configuration
- **Provider abstraction**: Gmail, Outlook, and custom IMAP/SMTP providers are handled transparently
- **Multi-service support**: Multiple email services (Gmail, Outlook, custom) can be configured simultaneously; agents access them via different service_ids
- **Credential isolation**: Email credentials (passwords, OAuth2 tokens) are fetched from Vault Adapter per-operation, never exposed to agents

**Multiplexing flow:**
1. Agent calls REST API (e.g., `POST /v1/email/send`)
2. Email proxy looks up service configuration for the agent's `service_id`
3. Email proxy determines provider type (Gmail/Outlook/Custom) from config
4. Email proxy fetches appropriate credentials (OAuth2 token or password) from Vault
5. Email proxy connects using the correct protocol (IMAP/SMTP with appropriate auth)
6. Email proxy returns result to agent

**Key architectural decisions:**
- Exposes REST API for agents (not raw IMAP/SMTP)
- Authenticates agents via **brokered JWT** (JWS Ed25519, validated against broker JWKS per ADR-0006)
- Fetches email credentials from Vault Adapter per-operation
- Handles IMAP/SMTP protocols internally using `go-imap` and `go-smtp`
- Bridges agent REST requests to email provider operations
- Emits audit events for all email operations
- **Connection pooling** for IMAP (per-service pool with 5-minute idle timeout)
- **TLS termination** via Kong TCP route or mTLS between MCP server and email proxy

### D2: New Auth Schemes
Add three new auth schemes to support email:
- `AUTH_SCHEME_EMAIL_PASSWORD = 14` — Vault stores email password (username:password format)
- `AUTH_SCHEME_EMAIL_OAUTH2 = 15` — Vault stores OAuth2 refresh token (JSON with client_id, client_secret, refresh_token)
- `AUTH_SCHEME_EMAIL_APP_PASSWORD = 16` — Vault stores app-specific password (for providers like Gmail with 2FA)

All three schemes must be added to:
- `vault.proto` AuthScheme enum
- `openapi.yaml` AuthScheme enum
- `tools.yaml` auth_scheme enum
- `audit-event.schema.json` auth_scheme enum

### D3: Agent Authentication Flow
Agents authenticate to the email proxy using **brokered JWTs** (same as HTTP proxy):
1. Agent discovers email service via MCP `list_services` (service appears with `auth_scheme: email_*`)
2. Agent requests JWT via MCP `request_token(service_id, action="send:email" | "read:email" | "write:email" | "delete:email")`
3. Broker issues JWT with `aud=email_service_id`, `scope=action`, `tnt=tenant_id`
4. Agent calls email proxy REST API with `Authorization: Bearer <JWT>`
5. Email proxy validates JWT against broker JWKS (Ed25519, force-refresh on unknown `kid` per ADR-0016.2)
6. Email proxy checks JWT `scope` against required permission for operation
7. Email proxy fetches credentials from Vault Adapter and performs operation

**Permission model** (4 actions):
- `read:email` — list mailboxes, list messages, read message, search, download attachment
- `send:email` — send email
- `write:email` — move message, mark as read/unread
- `delete:email` — delete message

### D4: Agent Interface (REST API)
Agents interact with email via REST API endpoints:
- `GET /v1/email/mailboxes` — List mailboxes (INBOX, Sent, Drafts, etc.)
- `GET /v1/email/messages?mailbox=INBOX&limit=50` — List messages
- `GET /v1/email/messages/{id}` — Read message with attachments
- `POST /v1/email/send` — Send email
- `DELETE /v1/email/messages/{id}` — Delete message
- `POST /v1/email/messages/{id}/move` — Move to folder
- `POST /v1/email/search` — Search messages
- `GET /v1/email/attachments/{id}` — Download attachment
- `POST /v1/email/messages/{id}/flags` — Mark as read/unread

### D5: MCP Tools
Expose email operations as MCP tools:
- `list_mailboxes()` — List available mailboxes (requires `read:email`)
- `list_emails(mailbox, limit, after)` — List recent emails (requires `read:email`)
- `read_email(id)` — Read full email with attachments (requires `read:email`)
- `send_email(to, subject, body, cc?, bcc?, attachments?)` — Send email (requires `send:email`)
- `search_emails(query, mailbox?, limit?)` — Search emails (requires `read:email`)
- `delete_email(id)` — Delete email (requires `delete:email`)
- `move_email(id, mailbox)` — Move email to folder (requires `write:email`)
- `download_attachment(id)` — Download attachment (requires `read:email`)
- `mark_email(id, flags)` — Mark as read/unread/flagged (requires `write:email`)

MCP server routes email tool calls to email proxy via `email_proxy_url` config.

### D6: OAuth2 Support
Support OAuth2 for major email providers:
- **Gmail**: Google OAuth2 flow with `mail.google.com` scope
- **Outlook**: Microsoft Graph OAuth2 flow with `Mail.ReadWrite` scope
- **Custom**: Username/password or app password for other providers

OAuth2 flow:
1. Operator configures email service in Admin UI
2. Admin UI generates cryptographic `state` parameter, stores in session
3. Admin UI redirects to provider with `state` for CSRF protection
4. Provider redirects back with authorization code and `state`
5. Admin UI validates `state` matches session
6. email-proxy exchanges code for refresh token
7. Refresh token stored in Vault Adapter
8. On each operation, email-proxy exchanges refresh token for access token
9. **Token refresh uses singleflight** to prevent concurrent refresh storms
10. **Expiration handling**: emit `email.service.auth_expired` audit event on refresh failure, update service status to `error`, notify operator via Admin UI

### D7: Attachment Support
Support email attachments in Phase 1:
- Send attachments via multipart/form-data
- Receive attachments as base64-encoded in JSON response
- Download attachments via dedicated endpoint
- Size limit: 25MB per attachment, 50MB total message (configurable)

### D8: TLS Termination
Email proxy port 8088 requires TLS termination:
- **Production**: Kong TCP route with TLS termination (preferred)
- **Alternative**: mTLS between MCP server and email proxy
- **Development**: Plain HTTP acceptable with documented trust boundary
- All agent JWTs and email content encrypted in transit

### D9: Connection Pooling
IMAP connections are expensive (TCP + TLS + LOGIN + SELECT):
- **Per-service connection pool** with configurable size (default: 5 connections)
- **Idle timeout**: 5 minutes (configurable)
- **Credentials fetched once per pool connection**, zeroed when connection recycled
- **UIDVALIDITY tracking**: detect mailbox recreation, invalidate cached UIDs
- Compatible with ADR-0014.4 (no persistent credential cache beyond connection lifetime)

### D10: Security Measures

**IMAP/SMTP Injection Prevention**:
- Use parameterized IMAP SEARCH via `go-imap`'s `imap.NewSearchCriteria()` with proper escaping
- Use `go-message` to construct MIME messages with proper header encoding
- Validate and reject `\r\n` in header values (subject, from, to, cc, bcc)
- Reject malformed RFC 5322 addresses

**Domain Filtering**:
- Parse recipient addresses with RFC 5322 parser
- Extract domain from parsed `addr-spec` (part after `@` in `mailbox` production)
- Reject addresses that don't parse cleanly
- Configurable allowlist per service

**Rate Limiting**:
- Per-agent and per-service rate limits
- **Shared state via Postgres advisory locks** (already in stack) for cross-instance enforcement
- Emit `email.rate_limit.exceeded` audit event on limit

**Audit Sanitization**:
- Search queries: log length and mailbox, not query text (prevent PII/credential leakage)
- Email content: never log body or attachment data
- Error messages: sanitize provider-specific errors before logging

**Service Identity**:
- Email proxy authenticates to Vault Adapter via `ValidateServiceIdentity`
- Config includes `ServiceIdentityID` and `ServiceIdentitySecret`
- Boot secret provisioned via same mechanism as other data-plane components

### D11: Audit Integration
Email proxy participates in audit hash chain:
- Write audit events via `auditq.Queue` → admin-api → Postgres (same as SSH proxy)
- Include `prev_hash` + `hash` per event, per-tenant chain (ADR-0014.7)
- **New target_type enum values**: `email_service`, `email_message`, `email_attachment`
- **New event types**: `email.sent`, `email.received`, `email.deleted`, `email.moved`, `email.searched`, `email.attachment.downloaded`, `email.service.registered`, `email.service.auth_expired`, `email.rate_limit.exceeded`, `email.domain.blocked`

### D12: Service Discovery
Email services appear in MCP `list_services`:
- Email service registered in `services` table with `auth_scheme: email_*`
- Email-specific config stored in `email_services` table (IMAP/SMTP hosts, ports, etc.)
- **Single transaction** for both table writes (consistency guarantee)
- MCP server config includes `email_proxy_url` for routing email tool calls
- Email proxy reads config from Postgres directly (like kong-syncer), not via admin-api

## Consequences

### Positive
- Agents can send/receive emails without holding email credentials
- Full audit trail for all email operations (send, receive, delete, move, search)
- OAuth2 support for major providers (Gmail, Outlook) with CSRF protection
- Attachment support for file sharing with size limits
- Consistent with existing proxy architecture (brokered JWT → Vault fetch → inject → audit)
- REST API is simpler for agents than raw IMAP/SMTP
- Connection pooling reduces provider rate limiting
- TLS termination protects credentials and content in transit
- Granular permission model (read/send/write/delete)
- Shared rate limiting across proxy instances

### Costs
- ~5500 lines of new Go code (increased from 4400 due to connection pooling, security measures)
- New binary to deploy and operate
- Additional port to expose (8088) with TLS termination requirement
- IMAP/SMTP protocol handling adds complexity
- OAuth2 flow management (token refresh, expiration handling, CSRF protection)
- Connection pool management (idle timeout, UIDVALIDITY tracking)
- Postgres advisory locks for shared rate limiting

### Risks
- Email credentials held in memory for connection pool lifetime (acceptable per ADR-0014.4 relaxation, zeroed on recycle)
- IMAP state management complexity (selected mailbox, UIDs, sequence numbers, UIDVALIDITY)
- OAuth2 token refresh failures (mitigate with singleflight, retry logic, expiration audit events)
- Attachment size limits (mitigate with streaming and configurable limits)
- Provider-specific quirks (mitigate with provider abstraction layer)
- IMAP/SMTP injection attacks (mitigate with parameterized queries, RFC 5322 validation)
- Domain filtering bypass (mitigate with proper address parsing)
- Rate limiting bypass (mitigate with shared state via Postgres advisory locks)

## Trade-offs

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Memory dump exposes email credentials | Medium | Zero credentials on connection recycle; same pattern as ADR-0014.4 |
| IMAP state corruption | Low | Connection pool with UIDVALIDITY tracking; invalidate on mismatch |
| OAuth2 token refresh failure | Medium | Singleflight to prevent storms; retry with exponential backoff; emit `email.service.auth_expired` audit event |
| Attachment size DoS | Low | Configurable size limit (25MB per attachment, 50MB total); streaming upload/download |
| Provider rate limiting | Medium | Per-agent and per-service rate limits with shared state (Postgres advisory locks); emit audit event on limit |
| IMAP/SMTP injection | High | Parameterized IMAP SEARCH; RFC 5322 address validation; reject `\r\n` in headers |
| Domain filtering bypass | High | RFC 5322 parser for address extraction; reject malformed addresses |
| Rate limiting bypass | Medium | Shared state via Postgres advisory locks; per-instance limits as fallback |
| TLS termination missing | Critical | Kong TCP route or mTLS; document trust boundary for dev |
| Audit hash chain break | High | Use `auditq.Queue` → admin-api → Postgres; same as SSH proxy |
| Search query PII leakage | Medium | Log query length and mailbox, not query text |
| OAuth2 CSRF | High | Cryptographic `state` parameter; validate on callback |
| Concurrent token refresh | High | Singleflight pattern; one refresh per service at a time |

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Raw IMAP/SMTP proxy | Agent holds credentials (violates S-SEC-1); complex for agents |
| Email API gateway (SendGrid, etc.) | Vendor lock-in; doesn't support receiving emails |
| Embed in proxy-plugin | IMAP/SMTP and HTTP have different lifecycles; increases complexity |
| Separate IMAP proxy + SMTP proxy | Two binaries instead of one; operational overhead |
| Symmetric JWT validation | Violates ADR-0006 (JWS Ed25519); allows JWT forgery |
| Per-operation IMAP connections | Prohibitively expensive; hits provider connection limits |
| In-memory rate limiting | Bypassed by distributing requests across instances |
| Admin API dependency for config | Circular dependency; different trust model than other data-plane components |
| Agent API Key auth (like MCP) | Breaks uniform security model; broker doesn't know about email operations |
| Base64 attachments in JSON only | Not streaming; memory spikes for large attachments |

## Amends
- ADR-0004: Email proxy is a sibling data-plane component, not an extension of Kong
- ADR-0014.4: Connection-scoped credential holding is acceptable (pool connections recycled after 5 min idle, credentials zeroed on recycle)
- ADR-0006: Email proxy validates brokered JWTs via JWKS (Ed25519), same as HTTP proxy
- ADR-0008: Email proxy sets `app.current_tenant` from JWT `tnt` claim for RLS
- ADR-0014.7: Email proxy participates in audit hash chain via `auditq.Queue`
- ADR-0016.2: Email proxy force-refreshes JWKS on unknown `kid` before rejecting
- ADR-0017.6: Email proxy span attributes follow explicit allowlist (no credentials)

## Implications
- Update `vault.proto` with new auth schemes (email_password=14, email_oauth2=15, email_app_password=16)
- Update `openapi.yaml` with email proxy endpoints and admin-api email service management endpoints
- Update `tools.yaml` with email operations and permission requirements
- Update `audit-event.schema.json` with new event types and `target_type` enum values (email_service, email_message, email_attachment)
- Update `change-event.schema.json` with email service events
- Update `span-attributes.md` with email proxy span names and attributes
- New Kiro spec: `.kiro/specs/email-proxy/`
- New docker-compose service: `email-proxy` with TLS termination (Kong TCP route)
- New Grafana dashboard: Email operation metrics
- Admin UI additions: Email service configuration, OAuth2 setup with CSRF protection
- MCP server config: Add `email_proxy_url` for routing email tool calls
- Postgres schema: Add `email_services` table with foreign key to `services` table
- **Module path**: `github.com/mintkey/mintkey/services/email-proxy` (follows SSH proxy pattern)
- **Internal packages**: `github.com/mintkey/mintkey/packages/go/auditq`, `/ulid`, `/vault/v1`
- **Go version**: 1.26.0+ (matches workspace)
- **Vault client**: Per-service client with `ValidateServiceIdentity` boot secret
- **Audit emission**: Use `auditq.Event` struct directly (not raw bytes)
- **OTel config**: Use `OTelEndpoint` string field, not `otelinit.Config`
- **ulid.New()**: Must include trailing underscore per ADR-0017.11 (`"audit_"`, `"email_"`)

## Open Follow-ups
- Email templates (Phase 2)
- Webhook notifications for new emails (Phase 2)
- Email rules (auto-forward, auto-reply, filtering) (Phase 2)
- Advanced search (full-text, date range, sender/recipient) (Phase 2)
- Attachment virus scanning (Phase 2)
- Email encryption (PGP, S/MIME) (Phase 3)
- Evaluate `go-imap/v2` when stable (currently v1 in maintenance mode)

## Related
- ADR-0004: Egress proxy (Kong)
- ADR-0014.4: No plaintext credential cache
- ADR-0021: SSH proxy (similar architecture pattern)
- ADR-0018: Classical API keys (similar auth pattern)
