# Email Proxy Requirements

## Overview
The email proxy enables agents to send and receive emails transparently via MCP tools, while humans configure email services through the Admin UI. The proxy handles IMAP/SMTP protocols internally and exposes a clean REST API to agents.

## User Stories

### Agent Email Operations

**Permission Model**: Agents are granted one or more of these permissions on an email service:
- `read:email` — list mailboxes, list messages, read message, search, download attachment
- `send:email` — send email
- `write:email` — move message, mark as read/unread
- `delete:email` — delete message

#### US-1: List Mailboxes
**As an** agent with `read:email` permission  
**I want to** list available mailboxes (INBOX, Sent, Drafts, etc.)  
**So that** I can navigate the email account structure

**Acceptance Criteria:**
- AC-1.1: Agent calls `list_mailboxes()` MCP tool with valid JWT (scope includes `read:email`)
- AC-1.2: Returns array of mailbox objects with name, message count, and unread count
- AC-1.3: Audit event `email.mailboxes.listed` emitted with agent_id and service_id
- AC-1.4: Operation completes within 5 seconds (p95)
- AC-1.5: Error returned if email service not configured, credentials invalid, or JWT lacks `read:email` scope
- AC-1.6: IMAP connection reused from pool (not created per-operation)

#### US-2: List Emails
**As an** agent with `read:email` permission  
**I want to** list recent emails in a mailbox  
**So that** I can see what emails are available

**Acceptance Criteria:**
- AC-2.1: Agent calls `list_emails(mailbox, limit, after)` MCP tool with valid JWT (scope includes `read:email`)
- AC-2.2: Returns array of email summaries (id, subject, from, date, unread status, size)
- AC-2.3: Supports pagination via `after` cursor
- AC-2.4: Default limit is 50, max is 200
- AC-2.5: Audit event `email.messages.listed` emitted with agent_id, service_id, mailbox, and count
- AC-2.6: Operation completes within 10 seconds (p95)
- AC-2.7: Error returned if mailbox doesn't exist or JWT lacks `read:email` scope
- AC-2.8: IMAP connection reused from pool

#### US-3: Read Email
**As an** agent with `read:email` permission  
**I want to** read a full email with attachments  
**So that** I can process email content

**Acceptance Criteria:**
- AC-3.1: Agent calls `read_email(id)` MCP tool with valid JWT (scope includes `read:email`)
- AC-3.2: Returns full email object (headers, body with format indicator, attachments)
- AC-3.3: Body includes `body_type` field: `"plain"` | `"html"` | `"both"`
- AC-3.4: For `body_type: "both"`, returns `{text: string, html: string}`
- AC-3.5: Attachments included as base64-encoded data with filename and MIME type
- AC-3.6: Audit event `email.message.read` emitted with agent_id, service_id, and message_id
- AC-3.7: Operation completes within 15 seconds (p95)
- AC-3.8: Error returned if message doesn't exist or JWT lacks `read:email` scope
- AC-3.9: IMAP connection reused from pool; UIDVALIDITY checked

#### US-4: Send Email
**As an** agent with `send:email` permission  
**I want to** send an email with optional attachments  
**So that** I can communicate via email

**Acceptance Criteria:**
- AC-4.1: Agent calls `send_email(to, subject, body, cc?, bcc?, attachments?)` MCP tool with valid JWT (scope includes `send:email`)
- AC-4.2: Supports multiple recipients (to, cc, bcc)
- AC-4.3: Supports attachments up to 25MB each, 50MB total message size (configurable)
- AC-4.4: Returns message ID on success
- AC-4.5: Audit event `email.sent` emitted with agent_id, service_id, recipients (count only, not addresses), and subject (truncated to 100 chars)
- AC-4.6: Operation completes within 30 seconds (p95)
- AC-4.7: Error returned if send fails (invalid recipient, quota exceeded, etc.) or JWT lacks `send:email` scope
- AC-4.8: Rate limit enforced (configurable per service, default 100/hour) via shared state (Postgres advisory locks)
- AC-4.9: Recipient addresses validated with RFC 5322 parser; domain filtering enforced
- AC-4.10: Subject and body validated for injection (no `\r\n` in headers)
- AC-4.11: SMTP connection created per-operation (not pooled)

#### US-5: Search Emails
**As an** agent with `read:email` permission  
**I want to** search emails by query  
**So that** I can find specific emails

**Acceptance Criteria:**
- AC-5.1: Agent calls `search_emails(query, mailbox?, limit?)` MCP tool with valid JWT (scope includes `read:email`)
- AC-5.2: Query supports subject, from, to, body text search
- AC-5.3: Optional mailbox filter
- AC-5.4: Returns array of matching email summaries
- AC-5.5: Audit event `email.messages.searched` emitted with agent_id, service_id, query_length (not query text), mailbox, and count
- AC-5.6: Operation completes within 15 seconds (p95)
- AC-5.7: Error returned if JWT lacks `read:email` scope
- AC-5.8: IMAP SEARCH uses parameterized query (no injection)
- AC-5.9: IMAP connection reused from pool

#### US-6: Delete Email
**As an** agent with `delete:email` permission  
**I want to** delete an email  
**So that** I can manage the mailbox

**Acceptance Criteria:**
- AC-6.1: Agent calls `delete_email(id)` MCP tool with valid JWT (scope includes `delete:email`)
- AC-6.2: Email moved to Trash (not permanently deleted)
- AC-6.3: Audit event `email.message.deleted` emitted with agent_id, service_id, and message_id
- AC-6.4: Operation completes within 5 seconds (p95)
- AC-6.5: Error returned if message doesn't exist or JWT lacks `delete:email` scope
- AC-6.6: IMAP connection reused from pool

#### US-7: Move Email
**As an** agent with `write:email` permission  
**I want to** move an email to a different folder  
**So that** I can organize the mailbox

**Acceptance Criteria:**
- AC-7.1: Agent calls `move_email(id, mailbox)` MCP tool with valid JWT (scope includes `write:email`)
- AC-7.2: Email moved to target mailbox
- AC-7.3: Audit event `email.message.moved` emitted with agent_id, service_id, message_id, from_mailbox, and to_mailbox
- AC-7.4: Operation completes within 5 seconds (p95)
- AC-7.5: Error returned if message or target mailbox doesn't exist, or JWT lacks `write:email` scope
- AC-7.6: IMAP connection reused from pool

#### US-8: Download Attachment
**As an** agent with `read:email` permission  
**I want to** download an email attachment  
**So that** I can process attached files

**Acceptance Criteria:**
- AC-8.1: Agent calls `download_attachment(id)` MCP tool with valid JWT (scope includes `read:email`)
- AC-8.2: Returns attachment data as base64-encoded string with filename and MIME type
- AC-8.3: Supports attachments up to 25MB (configurable)
- AC-8.4: Audit event `email.attachment.downloaded` emitted with agent_id, service_id, message_id, attachment_id, and size
- AC-8.5: Operation completes within 30 seconds (p95)
- AC-8.6: Error returned if attachment doesn't exist or JWT lacks `read:email` scope
- AC-8.7: IMAP connection reused from pool

#### US-9: Mark Email Flags
**As an** agent with `write:email` permission  
**I want to** mark an email as read/unread/flagged  
**So that** I can manage email state

**Acceptance Criteria:**
- AC-9.1: Agent calls `mark_email(id, flags)` MCP tool with valid JWT (scope includes `write:email`)
- AC-9.2: Flags is array of: `"\Seen"`, `"\Flagged"`, `"\Answered"`, `"\Deleted"`
- AC-9.3: Email flags updated on server
- AC-9.4: Audit event `email.message.flags_updated` emitted with agent_id, service_id, message_id, and flags
- AC-9.5: Operation completes within 5 seconds (p95)
- AC-9.6: Error returned if message doesn't exist or JWT lacks `write:email` scope
- AC-9.7: IMAP connection reused from pool

### Human Email Service Configuration

#### US-10: Register Email Service (Password)
**As an** operator  
**I want to** register an email service with username/password  
**So that** agents can use it

**Acceptance Criteria:**
- AC-10.1: Operator fills form in Admin UI (provider, username, password, IMAP/SMTP servers)
- AC-10.2: Password stored in Vault Adapter with envelope encryption (auth_scheme: `email_password`)
- AC-10.3: Test connection button validates credentials
- AC-10.4: Audit event `email.service.registered` emitted with operator_id and service_id
- AC-10.5: Service appears in email services list
- AC-10.6: Service also registered in `services` table (single transaction with `email_services` table)

#### US-11: Register Email Service (OAuth2)
**As an** operator  
**I want to** register an email service with OAuth2  
**So that** agents can use Gmail/Outlook securely

**Acceptance Criteria:**
- AC-11.1: Operator selects provider (Gmail, Outlook) in Admin UI
- AC-11.2: Admin UI generates cryptographic `state` parameter, stores in session
- AC-11.3: Admin UI redirects to provider with `state` for CSRF protection
- AC-11.4: Provider redirects back with authorization code and `state`
- AC-11.5: Admin UI validates `state` matches session
- AC-11.6: email-proxy exchanges code for refresh token
- AC-11.7: Refresh token stored in Vault Adapter (auth_scheme: `email_oauth2`)
- AC-11.8: Audit event `email.service.registered` emitted with operator_id and service_id
- AC-11.9: Service appears in email services list with OAuth2 badge
- AC-11.10: Service also registered in `services` table (single transaction with `email_services` table)

#### US-12: Configure Email Permissions
**As an** operator  
**I want to** configure which agents can use email services  
**So that** I can control access

**Acceptance Criteria:**
- AC-12.1: Operator grants `read:email` permission to agent (list, read, search, download)
- AC-12.2: Operator grants `send:email` permission to agent (send)
- AC-12.3: Operator grants `write:email` permission to agent (move, mark flags)
- AC-12.4: Operator grants `delete:email` permission to agent (delete)
- AC-12.5: Permissions enforced by email proxy via JWT scope validation
- AC-12.6: Audit event `email.permission.granted` emitted
- AC-12.7: Agent can only perform operations matching granted permissions

#### US-13: Configure Email Rate Limits
**As an** operator  
**I want to** configure rate limits for email services  
**So that** I can prevent abuse

**Acceptance Criteria:**
- AC-13.1: Operator sets rate limit (e.g., 100 emails/hour)
- AC-13.2: Rate limit enforced by email proxy via shared state (Postgres advisory locks)
- AC-13.3: Rate limit enforced across all proxy instances (not per-instance)
- AC-13.4: Audit event `email.rate_limit.exceeded` emitted when limit hit
- AC-13.5: Error returned to agent when limit exceeded

#### US-14: Configure Email Domain Restrictions
**As an** operator  
**I want to** restrict which domains agents can send to  
**So that** I can prevent spam

**Acceptance Criteria:**
- AC-14.1: Operator configures allowed domains (e.g., @company.com)
- AC-14.2: Domain restrictions enforced by email proxy using RFC 5322 address parser
- AC-14.3: Recipient addresses validated and domain extracted from `addr-spec`
- AC-14.4: Malformed addresses rejected
- AC-14.5: Audit event `email.domain.blocked` emitted when domain blocked
- AC-14.6: Error returned to agent when domain blocked

#### US-15: Monitor Email Usage
**As an** operator  
**I want to** monitor email usage per agent  
**So that** I can detect abuse

**Acceptance Criteria:**
- AC-15.1: Admin UI shows email usage dashboard
- AC-15.2: Dashboard shows messages sent/received per agent
- AC-15.3: Dashboard shows error rates
- AC-15.4: Dashboard shows recent activity
- AC-15.5: Data updated in near real-time (5-second lag)

#### US-16: Handle OAuth2 Token Expiration
**As an** operator  
**I want to** be notified when OAuth2 authorization expires  
**So that** I can re-authorize the email service

**Acceptance Criteria:**
- AC-16.1: Email proxy detects OAuth2 refresh token expiration on refresh failure
- AC-16.2: Audit event `email.service.auth_expired` emitted with service_id and error_reason
- AC-16.3: Service status updated to `error` in database
- AC-16.4: Admin UI displays error badge on email service
- AC-16.5: Admin UI shows "Re-authorize" button to restart OAuth2 flow
- AC-16.6: Operator can re-authorize without deleting and recreating service

## Non-Functional Requirements

### Performance
- NFR-1: List mailboxes completes within 5 seconds (p95)
- NFR-2: List emails completes within 10 seconds (p95)
- NFR-3: Read email completes within 15 seconds (p95)
- NFR-4: Send email completes within 30 seconds (p95)
- NFR-5: Search emails completes within 15 seconds (p95)
- NFR-6: Support 100 concurrent email operations per proxy instance
- NFR-7: IMAP connection pool reduces connection creation overhead by 80% (vs per-operation connections)

### Security
- NFR-8: Email credentials never logged or exposed in audit events
- NFR-9: OAuth2 tokens stored securely in Vault Adapter with envelope encryption
- NFR-10: All email operations authenticated via brokered JWT (JWS Ed25519, validated against broker JWKS)
- NFR-11: Rate limiting enforced per agent and per service via shared state (Postgres advisory locks)
- NFR-12: Domain restrictions enforced for outbound emails using RFC 5322 address parser
- NFR-13: TLS termination for port 8088 (Kong TCP route or mTLS between MCP server and email proxy)
- NFR-14: IMAP/SMTP injection prevention via parameterized queries and RFC 5322 validation
- NFR-15: OAuth2 CSRF protection via cryptographic `state` parameter
- NFR-16: Search query sanitization in audit events (log length and mailbox, not query text)
- NFR-17: Email body and attachment content never logged
- NFR-18: Service identity boot secret for Vault Adapter authentication

### Reliability
- NFR-19: Email proxy recovers from provider outages within 60 seconds of provider restoration (without manual intervention)
- NFR-20: OAuth2 token refresh failures retried with exponential backoff (max 3 attempts)
- NFR-21: OAuth2 token refresh uses singleflight to prevent concurrent refresh storms
- NFR-22: IMAP/SMTP connection failures retried up to 3 times
- NFR-23: Audit events emitted even on operation failure
- NFR-24: IMAP connection pool handles UIDVALIDITY changes (invalidate cached UIDs)

### Scalability
- NFR-25: Support horizontal scaling (multiple proxy instances)
- NFR-26: Rate limiting state shared across instances via Postgres advisory locks
- NFR-27: IMAP connection pool per service (configurable size, default 5 connections)
- NFR-28: Stateless design for request handling (credentials fetched per connection pool, not per request)

### Observability
- NFR-29: Prometheus metrics for all email operations
- NFR-30: OTel traces for all email operations with explicit span attribute allowlist
- NFR-31: Grafana dashboard for email proxy metrics
- NFR-32: Structured logs for all operations (no credentials, no email content)
- NFR-33: Audit hash chain participation via `auditq.Queue` → admin-api → Postgres

### Data Integrity
- NFR-34: Audit hash chain maintained per tenant (prev_hash + hash per event)
- NFR-35: Email service registration uses single transaction for `services` and `email_services` tables
- NFR-36: OAuth2 expiration detected and service status updated to `error`

## Glossary

- **Mailbox**: Email folder (INBOX, Sent, Drafts, Trash, etc.)
- **Message**: Email with headers, body, and attachments
- **Attachment**: File attached to email (base64-encoded)
- **OAuth2**: Authorization framework for delegated access
- **Refresh Token**: Long-lived token used to obtain access tokens
- **Access Token**: Short-lived token used for API calls
- **App Password**: Provider-specific password for accounts with 2FA

## Out of Scope (Phase 1)

- Email templates (Phase 2)
- Webhook notifications (Phase 2)
- Email rules (auto-forward, auto-reply) (Phase 2)
- Advanced search (full-text, date range) (Phase 2)
- Attachment virus scanning (Phase 2)
- Email encryption (PGP, S/MIME) (Phase 3)
