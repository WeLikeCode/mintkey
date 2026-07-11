# Email Proxy Implementation Tasks

## Overview
This document breaks down the email proxy implementation into concrete tasks organized by milestone. Each task includes dependencies, acceptance criteria, and estimated effort.

## Milestone 1: Architecture & Contracts (Week 1)

### Task 1.1: Create ADR-0024
**Status**: ✅ Complete  
**Effort**: 0.5 day  
**Dependencies**: None

**Description**: Document the architectural decision for email proxy support.

**Acceptance Criteria**:
- [x] ADR-0024 created in `docs/architecture/01-architecture/adr/0024-email-proxy-support.md`
- [x] Follows ADR template structure
- [x] Documents decision, context, consequences, and trade-offs
- [x] References related ADRs (0004, 0014.4, 0021, 0018)
- [x] Documents protocol multiplexing behavior

### Task 1.2: Update vault.proto
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.1

**Description**: Add email auth schemes to vault.proto.

**Acceptance Criteria**:
- [x] Add `AUTH_SCHEME_EMAIL_PASSWORD = 14`
- [x] Add `AUTH_SCHEME_EMAIL_OAUTH2 = 15`
- [x] Add `AUTH_SCHEME_EMAIL_APP_PASSWORD = 16`
- [x] Update comments with email-specific metadata
- [x] Proto compiles without errors

**Files**:
- `docs/architecture/contracts/vault-adapter/vault.proto`

### Task 1.3: Update OpenAPI Schema
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 1.2

**Description**: Add email service endpoints and schemas to OpenAPI.

**Acceptance Criteria**:
- [x] Add email auth schemes to AuthScheme enum
- [x] Add EmailService schema
- [x] Add EmailMessage schema with body_type field
- [x] Add Mailbox schema
- [x] Add Attachment schema
- [x] Add endpoints: GET /v1/email/mailboxes, GET /v1/email/messages, GET /v1/email/messages/{id}, POST /v1/email/send, DELETE /v1/email/messages/{id}, POST /v1/email/messages/{id}/move, POST /v1/email/messages/{id}/flags, POST /v1/email/search, GET /v1/email/attachments/{id}
- [x] OpenAPI validates without errors

**Files**:
- `docs/architecture/contracts/rest/openapi.yaml`

### Task 1.4: Update MCP Tools
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 1.3

**Description**: Add email MCP tools to tools.yaml.

**Acceptance Criteria**:
- [x] Add email auth schemes to auth_scheme enum
- [x] Add list_mailboxes tool (requires read:email)
- [x] Add list_emails tool (requires read:email)
- [x] Add read_email tool (requires read:email)
- [x] Add send_email tool (requires send:email)
- [x] Add search_emails tool (requires read:email)
- [x] Add delete_email tool (requires delete:email)
- [x] Add move_email tool (requires write:email)
- [x] Add download_attachment tool (requires read:email)
- [x] Add mark_email tool (requires write:email)
- [x] YAML validates without errors

**Files**:
- `docs/architecture/contracts/mcp/tools.yaml`

### Task 1.5: Update Audit Event Schema
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.1

**Description**: Add email audit events to schema.

**Acceptance Criteria**:
- [x] Add target_type enum values: `email_service`, `email_message`, `email_attachment`
- [x] Add auth_scheme enum values: `email_password`, `email_oauth2`, `email_app_password`
- [x] Add email event types: `email.mailboxes.listed`, `email.messages.listed`, `email.message.read`, `email.sent`, `email.messages.searched`, `email.message.deleted`, `email.message.moved`, `email.attachment.downloaded`, `email.service.registered`, `email.service.auth_expired`, `email.message.flags_updated`, `email.rate_limit.exceeded`, `email.domain.blocked`
- [x] JSON schema validates without errors

**Files**:
- `docs/architecture/contracts/events/audit-event.schema.json`

### Task 1.6: Update Change Event Schema
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.1

**Description**: Add email change events to schema.

**Acceptance Criteria**:
- [x] Add `email.service.registered` event
- [x] Add `email.service.updated` event
- [x] Add `email.service.deleted` event
- [x] Add events to `oneOf` array and `discriminator.mapping`
- [x] Add to `x-mintkey-channels` section
- [x] JSON schema validates without errors

**Files**:
- `docs/architecture/contracts/events/change-event.schema.json`

### Task 1.7: Update Span Attributes
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.1

**Description**: Add email proxy span attributes.

**Acceptance Criteria**:
- [x] Add span names: `mintkey.email.handle_request`, `mintkey.email.fetch_credential`, `mintkey.email.imap_operation`, `mintkey.email.smtp_send`
- [x] Add allowed attributes: `mintkey.email.operation`, `mintkey.email.provider`, `mintkey.email.mailbox`, `mintkey.email.message_count`, `mintkey.email.attachment_count`, `mintkey.email.attachment_size`
- [x] Update `mintkey/internal/otel/allowlist.go`
- [x] Update `mintkey_otel/allowlist.py`
- [x] Documentation updated

**Files**:
- `docs/architecture/contracts/events/span-attributes.md`
- `mintkey/internal/otel/allowlist.go`
- `mintkey_otel/allowlist.py`

### Task 1.8: Create Kiro Spec
**Status**: ✅ Complete  
**Effort**: 1 day  
**Dependencies**: Task 1.1

**Description**: Create Kiro spec for email proxy.

**Acceptance Criteria**:
- [x] requirements.md created with user stories and acceptance criteria
- [x] design.md created with architecture and sequence diagrams
- [x] tasks.md created with implementation tasks

**Files**:
- `.kiro/specs/email-proxy/requirements.md`
- `.kiro/specs/email-proxy/design.md`
- `.kiro/specs/email-proxy/tasks.md`

## Milestone 2: Backend Core (Weeks 2-4)

### Task 2.1: Create email-proxy Directory Structure
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.8

**Description**: Create directory structure for email-proxy service.

**Acceptance Criteria**:
- [x] Create `apps/email-proxy/` directory
- [x] Create `cmd/email-proxy/main.go`
- [x] Create `internal/config/config.go`
- [x] Create `internal/pool/` directory (IMAP connection pool)
- [x] Create `internal/imap/` directory
- [x] Create `internal/smtp/` directory
- [x] Create `internal/oauth2/` directory
- [x] Create `internal/api/` directory (REST API)
- [x] Create `internal/auth/` directory (JWT validation)
- [x] Create `internal/security/` directory (injection prevention, domain filtering, rate limiting)
- [x] Create `internal/audit/` directory
- [x] Create `internal/metrics/` directory
- [x] Create `internal/trace/` directory
- [x] Create `go.mod` with correct module path (`github.com/mintkey/mintkey/services/email-proxy`)
- [x] Create `Dockerfile`

**Files**:
- `apps/email-proxy/**`

### Task 2.2: Implement Configuration
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.1

**Description**: Implement configuration loading.

**Acceptance Criteria**:
- [x] Config struct defined with all fields (VaultIdentityID, VaultIdentityToken, OTelEndpoint, AuditWALPath)
- [x] Load from environment variables
- [x] Validate required fields
- [x] Set sensible defaults
- [x] Unit tests pass

**Files**:
- `apps/email-proxy/internal/config/config.go`
- `apps/email-proxy/internal/config/config_test.go`

### Task 2.3: Implement IMAP Client
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 2.2

**Description**: Implement IMAP client wrapper.

**Acceptance Criteria**:
- [x] Connect to IMAP server with password
- [x] Connect to IMAP server with OAuth2 token
- [x] List mailboxes
- [x] Select mailbox
- [x] Fetch message summaries (ENVELOPE)
- [x] Fetch full message with attachments
- [x] Search messages (parameterized, no injection)
- [x] Delete message (move to Trash)
- [x] Move message to mailbox
- [x] Mark message flags (read/unread/flagged)
- [x] Handle connection errors
- [x] Handle authentication errors
- [x] Unit tests pass with mock IMAP server

**Files**:
- `apps/email-proxy/internal/imap/client.go`
- `apps/email-proxy/internal/imap/mailbox.go`
- `apps/email-proxy/internal/imap/message.go`
- `apps/email-proxy/internal/imap/client_test.go`

### Task 2.4: Implement SMTP Client
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 2.2

**Description**: Implement SMTP client wrapper.

**Acceptance Criteria**:
- [x] Connect to SMTP server with password
- [x] Connect to SMTP server with OAuth2 token
- [x] Send email with text body
- [x] Send email with HTML body
- [x] Send email with attachments
- [x] Support multiple recipients (to, cc, bcc)
- [x] Validate recipient addresses with RFC 5322 parser
- [x] Sanitize headers (reject \r\n injection)
- [x] Handle connection errors
- [x] Handle authentication errors
- [x] Handle send errors
- [x] Unit tests pass with mock SMTP server

**Files**:
- `apps/email-proxy/internal/smtp/client.go`
- `apps/email-proxy/internal/smtp/send.go`
- `apps/email-proxy/internal/smtp/client_test.go`

### Task 2.5: Implement OAuth2 Handlers
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 2.2

**Description**: Implement OAuth2 flows for Gmail and Outlook.

**Acceptance Criteria**:
- [x] Gmail OAuth2 flow (authorization URL, token exchange, refresh)
- [x] Outlook OAuth2 flow (authorization URL, token exchange, refresh)
- [x] Provider interface for extensibility
- [x] Singleflight to prevent concurrent token refresh storms
- [x] Handle token refresh failures
- [x] Handle token expiration (emit `email.service.auth_expired` audit event)
- [x] Update service status to `error` on expiration
- [x] Unit tests pass with mock OAuth2 server

**Files**:
- `apps/email-proxy/internal/oauth2/provider.go`
- `apps/email-proxy/internal/oauth2/gmail.go`
- `apps/email-proxy/internal/oauth2/outlook.go`
- `apps/email-proxy/internal/oauth2/singleflight.go`
- `apps/email-proxy/internal/oauth2/provider_test.go`

### Task 2.6: Implement Connection Pool
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 2.3

**Description**: Implement IMAP connection pool.

**Acceptance Criteria**:
- [x] Per-service connection pool with configurable size (default: 5)
- [x] Idle timeout: 5 minutes (configurable)
- [x] Credentials fetched once per pool connection
- [x] UIDVALIDITY tracking (invalidate cached UIDs on change)
- [x] Thread-safe (concurrent access from multiple requests)
- [x] Connection health checks
- [x] Unit tests pass

**Files**:
- `apps/email-proxy/internal/pool/pool.go`
- `apps/email-proxy/internal/pool/pool_test.go`

### Task 2.7: Implement Security Measures
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 2.3, Task 2.4

**Description**: Implement security measures for injection prevention, domain filtering, and rate limiting.

**Acceptance Criteria**:
- [x] IMAP/SMTP injection prevention (parameterized queries, header sanitization)
- [x] RFC 5322 address parsing and validation
- [x] Domain filtering (configurable allowlist per service)
- [x] Rate limiting (per-agent, per-service, shared via Postgres advisory locks)
- [x] Search query sanitization (log length/mailbox, not query text)
- [x] Unit tests for injection prevention, address parsing, domain filtering, rate limiting

**Files**:
- `apps/email-proxy/internal/security/injection.go`
- `apps/email-proxy/internal/security/rfc5322.go`
- `apps/email-proxy/internal/security/ratelimit.go`
- `apps/email-proxy/internal/security/injection_test.go`
- `apps/email-proxy/internal/security/rfc5322_test.go`
- `apps/email-proxy/internal/security/ratelimit_test.go`

### Task 2.8: Implement JWT Validation
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 2.2

**Description**: Implement brokered JWT validation via JWKS.

**Acceptance Criteria**:
- [x] Validate JWT against broker JWKS (Ed25519)
- [x] Force-refresh JWKS on unknown `kid` (per ADR-0016.2)
- [x] Check JWT scope against required permission
- [x] Check JWT audience matches service_id
- [x] Handle JWKS fetch failures
- [x] Unit tests pass

**Files**:
- `apps/email-proxy/internal/auth/jwt.go`
- `apps/email-proxy/internal/auth/jwks.go`
- `apps/email-proxy/internal/auth/jwt_test.go`

### Task 2.9: Implement REST API Server
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 2.6, Task 2.7, Task 2.8

**Description**: Implement REST API server with all endpoints.

**Acceptance Criteria**:
- [x] HTTP server with chi router
- [x] JWT validation middleware
- [x] Logging middleware
- [x] GET /v1/email/mailboxes endpoint
- [x] GET /v1/email/messages endpoint
- [x] GET /v1/email/messages/{id} endpoint
- [x] POST /v1/email/send endpoint
- [x] DELETE /v1/email/messages/{id} endpoint
- [x] POST /v1/email/messages/{id}/move endpoint
- [x] POST /v1/email/messages/{id}/flags endpoint
- [x] POST /v1/email/search endpoint
- [x] GET /v1/email/attachments/{id} endpoint
- [x] POST /v1/health endpoint
- [x] POST /v1/ready endpoint
- [x] Error handling with JSON responses (sanitized)
- [x] Unit tests pass

**Files**:
- `apps/email-proxy/internal/api/server.go`
- `apps/email-proxy/internal/api/handlers.go`
- `apps/email-proxy/internal/api/middleware.go`
- `apps/email-proxy/internal/api/routes.go`
- `apps/email-proxy/internal/api/handlers_test.go`

### Task 2.10: Implement Audit Emitter
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 2.9

**Description**: Implement audit event emission via auditq.Queue.

**Acceptance Criteria**:
- [x] Emit email.mailboxes.listed event
- [x] Emit email.messages.listed event
- [x] Emit email.message.read event
- [x] Emit email.sent event
- [x] Emit email.messages.searched event
- [x] Emit email.message.deleted event
- [x] Emit email.message.moved event
- [x] Emit email.message.flags_updated event
- [x] Emit email.attachment.downloaded event
- [x] Emit email.service.auth_expired event
- [x] Sanitize search queries (log length/mailbox, not query text)
- [x] Sanitize recipients (log count, not addresses)
- [x] Truncate subject to 100 chars
- [x] Integrate with auditq.Queue (use auditq.Event struct)
- [x] Include prev_hash + hash for audit chain
- [x] Unit tests pass

**Files**:
- `apps/email-proxy/internal/audit/emit.go`
- `apps/email-proxy/internal/audit/emit_test.go`

### Task 2.11: Implement Metrics
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.9

**Description**: Implement Prometheus metrics.

**Acceptance Criteria**:
- [x] Track email operations by type
- [x] Track email operations by provider
- [x] Track operation duration
- [x] Track error rates
- [x] Track attachment sizes
- [x] Track rate limit violations
- [x] Track domain blocks
- [x] Expose /metrics endpoint
- [x] Unit tests pass

**Files**:
- `apps/email-proxy/internal/metrics/metrics.go`
- `apps/email-proxy/internal/metrics/metrics_test.go`

### Task 2.12: Implement Tracing
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.9

**Description**: Implement OpenTelemetry tracing.

**Acceptance Criteria**:
- [x] Create spans for all email operations
- [x] Add span attributes (operation, provider, mailbox, message_count)
- [x] Integrate with OTel SDK
- [x] Unit tests pass

**Files**:
- `apps/email-proxy/internal/trace/trace.go`
- `apps/email-proxy/internal/trace/trace_test.go`

### Task 2.13: Wire Everything Together
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 2.10, Task 2.11, Task 2.12

**Description**: Wire all components in main.go.

**Acceptance Criteria**:
- [x] Load configuration
- [x] Initialize Vault client with service identity
- [x] Initialize IMAP connection pool
- [x] Initialize SMTP client
- [x] Initialize OAuth2 handlers
- [x] Initialize JWT validation
- [x] Initialize security measures
- [x] Initialize audit emitter
- [x] Initialize metrics
- [x] Initialize tracing
- [x] Start HTTP server
- [x] Handle graceful shutdown
- [x] Integration test passes

**Files**:
- `apps/email-proxy/cmd/email-proxy/main.go`

## Milestone 3: Frontend (Week 4)

### Task 3.1: Create Email Service Resource
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 1.3

**Description**: Create AdminJS resource for email services.

**Acceptance Criteria**:
- [x] Email service list view
- [x] Email service detail view
- [x] Email service create form
- [x] Email service edit form
- [x] Email service delete action
- [x] Resource registered in AdminJS

**Files**:
- `apps/admin-ui/src/resources/email_services.ts`

### Task 3.2: Create Email Service Create Form
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 3.1

**Description**: Create form for registering email services.

**Acceptance Criteria**:
- [x] Provider selection (Gmail, Outlook, Custom)
- [x] For Gmail/Outlook: OAuth2 setup button
- [x] For Custom: IMAP/SMTP server fields
- [x] Username/password fields
- [x] Connection pool size configuration
- [x] Rate limit configuration
- [x] Domain restrictions configuration
- [x] Test connection button
- [x] Form validation
- [x] Success/error messages
- [x] Unit tests pass

**Files**:
- `apps/admin-ui/src/components/actions/EmailServiceCreateForm.tsx`
- `apps/admin-ui/src/components/actions/EmailServiceCreateForm.test.tsx`

### Task 3.3: Create OAuth2 Setup Component
**Status**: ⏳ Pending  
**Effort**: 1.5 days  
**Dependencies**: Task 3.2

**Description**: Create OAuth2 setup flow component with CSRF protection.

**Acceptance Criteria**:
- [x] Generate cryptographic state parameter
- [x] Store state in session
- [x] Display authorization URL
- [x] Handle OAuth2 callback with state validation
- [x] Exchange code for tokens
- [x] Store refresh token in Vault
- [x] Handle token expiration
- [x] Display success/error messages
- [x] Re-authorize button for expired tokens
- [x] Unit tests pass

**Files**:
- `apps/admin-ui/src/components/actions/EmailServiceOAuth2Setup.tsx`
- `apps/admin-ui/src/components/actions/EmailServiceOAuth2Setup.test.tsx`

### Task 3.4: Create Email Services Intro Section
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 3.1

**Description**: Create intro section for email services.

**Acceptance Criteria**:
- [x] Display overview of email proxy
- [x] Display setup instructions
- [x] Link to documentation
- [x] Unit tests pass

**Files**:
- `apps/admin-ui/src/components/sections/EmailServicesIntro.tsx`
- `apps/admin-ui/src/components/sections/EmailServicesIntro.test.tsx`

### Task 3.5: Add Email Service Endpoints to admin-api
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 1.3

**Description**: Add email service CRUD endpoints to admin-api.

**Acceptance Criteria**:
- [x] GET /v1/email/services endpoint
- [x] GET /v1/email/services/{id} endpoint
- [x] POST /v1/email/services endpoint
- [x] PATCH /v1/email/services/{id} endpoint
- [x] DELETE /v1/email/services/{id} endpoint
- [x] POST /v1/email/services/{id}/test endpoint
- [x] POST /v1/email/services/oauth2/authorize endpoint
- [x] POST /v1/email/services/oauth2/callback endpoint
- [x] Permission checks
- [x] Audit event emission
- [x] Unit tests pass

**Files**:
- `apps/admin-api/src/admin_api/api/email_services.py`
- `apps/admin-api/src/admin_api/api/email_services_test.py`

### Task 3.6: Add Email Service Database Schema
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 3.5

**Description**: Add email_services table to database.

**Acceptance Criteria**:
- [x] Create email_services table with foreign key to services table
- [x] Add indexes
- [x] Add RLS policies
- [x] Single transaction for services + email_services inserts
- [x] Create migration
- [x] Migration runs without errors

**Files**:
- `apps/admin-api/db/changelog/XXX-email-services.yaml`

## Milestone 4: Testing (Week 5)

### Task 4.1: Write Unit Tests
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 2.13

**Description**: Write comprehensive unit tests.

**Acceptance Criteria**:
- [x] IMAP client tests (80% coverage)
- [x] SMTP client tests (80% coverage)
- [x] OAuth2 handler tests (80% coverage)
- [x] Connection pool tests (80% coverage)
- [x] Security tests (injection prevention, domain filtering, rate limiting) (80% coverage)
- [x] JWT validation tests (80% coverage)
- [x] API handler tests (80% coverage)
- [x] Audit emitter tests (80% coverage)
- [x] Metrics tests (80% coverage)
- [x] Trace tests (80% coverage)
- [x] All tests pass

**Files**:
- `apps/email-proxy/**/*_test.go`

### Task 4.2: Write Integration Tests
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 4.1

**Description**: Write integration tests with mock email providers.

**Acceptance Criteria**:
- [x] Test email send flow
- [x] Test email receive flow
- [x] Test email search flow
- [x] Test OAuth2 flow with mock provider
- [x] Test attachment handling
- [x] Test connection pooling
- [x] Test error handling
- [x] Test OAuth2 token refresh with singleflight
- [x] Test UIDVALIDITY change detection
- [x] All tests pass

**Files**:
- `tests/integration/email_proxy/test_email_flow.py`

### Task 4.3: Write Acceptance Tests
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 4.2

**Description**: Write acceptance tests with full docker-compose stack.

**Acceptance Criteria**:
- [x] Test with real Gmail account (test account)
- [x] Test with real Outlook account (test account)
- [x] Test with custom IMAP/SMTP server
- [x] Test OAuth2 flows
- [x] Test attachment handling
- [x] Test rate limiting
- [x] Test domain filtering
- [x] Test audit hash chain
- [x] Test TLS termination
- [x] All tests pass

**Files**:
- `tests/acceptance/test_email_proxy.py`

### Task 4.4: Write Architecture Tests
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.1

**Description**: Write architecture tests to enforce security invariants.

**Acceptance Criteria**:
- [x] No plaintext credentials in logs
- [x] Audit events emitted for all operations
- [x] Rate limiting enforced via Postgres advisory locks
- [x] Domain filtering enforced via RFC 5322 parser
- [x] JWT validation via JWKS (not shared secret)
- [x] Search query sanitization in audit events
- [x] All tests pass

**Files**:
- `tests/architecture/test_email_proxy_security.py`

### Task 4.5: Write Security Red Team Tests
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.1

**Description**: Write red team tests for security vulnerabilities.

**Acceptance Criteria**:
- [x] Send email containing known credential fingerprint, verify it doesn't appear in logs, audit events, or span attributes
- [x] Attempt IMAP/SMTP injection via malformed search queries
- [x] Attempt IMAP/SMTP injection via malformed email headers
- [x] Attempt domain filtering bypass via malformed addresses
- [x] Attempt rate limiting bypass by distributing requests across instances
- [x] Concurrent OAuth2 token refresh (10 goroutines), verify singleflight prevents storms
- [x] All tests pass

**Files**:
- `tests/security/test_email_proxy_redteam.py`

### Task 4.6: Write Performance Tests
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.1

**Description**: Write performance tests.

**Acceptance Criteria**:
- [x] Load test with 100 concurrent operations
- [x] Measure latency percentiles (p50, p95, p99)
- [x] Verify connection pooling reduces overhead by 80%
- [x] Verify rate limiting works under load
- [x] Document performance characteristics

**Files**:
- `tests/performance/test_email_proxy_load.py`

## Milestone 5: Documentation & Deployment (Week 6)

### Task 5.1: Write User Documentation
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.3

**Description**: Write user-facing documentation.

**Acceptance Criteria**:
- [x] How to configure email services
- [x] How to use email MCP tools
- [x] OAuth2 setup guide
- [x] Troubleshooting guide
- [x] Examples

**Files**:
- `docs/user-guide/email-proxy.md`

### Task 5.2: Write API Documentation
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 4.3

**Description**: Write API reference documentation.

**Acceptance Criteria**:
- [x] REST API reference
- [x] MCP tools reference
- [x] Error codes reference
- [x] Examples

**Files**:
- `docs/api-reference/email-proxy.md`

### Task 5.3: Create Grafana Dashboard
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 2.8

**Description**: Create Grafana dashboard for email proxy metrics.

**Acceptance Criteria**:
- [x] Email operations per minute panel
- [x] OAuth2 token refresh rate panel
- [x] Error rates by provider panel
- [x] Attachment upload/download rates panel
- [x] Rate limit violations panel
- [x] Domain blocks panel
- [x] Dashboard imports without errors

**Files**:
- `grafana/dashboards/email-proxy.json`

### Task 5.4: Update Docker Compose
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.13

**Description**: Add email-proxy to docker-compose.yml.

**Acceptance Criteria**:
- [x] email-proxy service defined
- [x] Environment variables configured
- [x] Health checks configured
- [x] Port 993 exposed (IMAP)
- [x] Port 587 exposed (SMTP)
- [x] Port 8088 exposed (REST API + health/metrics)
- [x] Depends on vault-adapter and admin-api
- [x] docker-compose up starts email-proxy

**Files**:
- `docker-compose.yml`

### Task 5.5: Update CI/CD Pipeline
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 4.3

**Description**: Add email-proxy to CI/CD pipeline.

**Acceptance Criteria**:
- [x] Build email-proxy in CI
- [x] Run unit tests in CI
- [x] Run integration tests in CI
- [x] Run acceptance tests in nightly
- [x] Deploy email-proxy on merge to main

**Files**:
- `.github/workflows/ci.yml`

## Milestone 6: Adversarial Review & Hardening (Week 7)

### Task 6.1: Conduct Adversarial Review
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 5.5

**Description**: Conduct adversarial review of email proxy implementation.

**Acceptance Criteria**:
- [x] Security review completed
- [x] Architecture review completed
- [x] Performance review completed
- [x] Findings documented
- [x] Critical findings addressed

**Files**:
- `docs/architecture/contracts/_review-email-proxy.md`

### Task 6.2: Address Review Findings
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 6.1

**Description**: Address findings from adversarial review.

**Acceptance Criteria**:
- [x] All critical findings fixed
- [x] All high findings fixed or documented
- [x] Tests updated
- [x] Documentation updated

**Files**:
- Various based on findings

### Task 6.3: Performance Testing
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 6.2

**Description**: Conduct performance testing.

**Acceptance Criteria**:
- [x] Load test with 100 concurrent operations
- [x] Measure latency percentiles (p50, p95, p99)
- [x] Identify bottlenecks
- [x] Optimize critical paths
- [x] Document performance characteristics

**Files**:
- `tests/performance/test_email_proxy_load.py`

## Milestone 7: Release (Week 8)

### Task 7.1: Create Release Notes
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 6.3

**Description**: Create release notes for email proxy feature.

**Acceptance Criteria**:
- [x] Feature overview
- [x] Breaking changes (if any)
- [x] Migration guide (if needed)
- [x] Known issues
- [x] Changelog

**Files**:
- `RELEASE_NOTES.md`

### Task 7.2: Update Main Documentation
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 7.1

**Description**: Update main documentation to reference email proxy.

**Acceptance Criteria**:
- [x] Update README.md
- [x] Update architecture overview
- [x] Update deployment guide
- [x] Update user guide

**Files**:
- `README.md`
- `docs/architecture/README.md`
- `docs/deployment/README.md`

### Task 7.3: Merge to Main
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 7.2

**Description**: Merge email proxy feature to main branch.

**Acceptance Criteria**:
- [x] All tests pass
- [x] All documentation updated
- [x] Code review approved
- [x] Merge to main
- [x] Tag release

**Files**:
- None

## Summary

**Total Tasks**: 55  
**Total Effort**: ~9 weeks (1 developer)  
**Critical Path**: Task 1.1 → Task 2.1 → Task 2.13 → Task 4.3 → Task 6.3 → Task 7.3

**Key Dependencies**:
- ADR-0024 must be approved before implementation
- Contracts must be updated before backend implementation
- Backend must be complete before frontend implementation
- All tests must pass before release

**Risk Mitigation**:
- Start with MVP (basic IMAP/SMTP transparent proxy) and add REST API incrementally
- Use mock email providers for testing
- Conduct adversarial review before release
- Performance test with realistic load
- Follow SSH proxy integration patterns exactly (module path, import paths, config structure)

**Lessons from SSH Proxy Integration**:
- Use correct module path: `github.com/mintkey/mintkey/services/email-proxy`
- Use correct internal package paths: `github.com/mintkey/mintkey/packages/go/*`
- Follow exact config pattern (VaultIdentityID, VaultIdentityToken, OTelEndpoint, AuditWALPath)
- Use `auditq.Event` struct directly (not raw bytes)
- Use `ulid.New("email_")` with trailing underscore
- Wire module into `go.work` workspace
- Test that code builds before merging

**Hybrid Approach Benefits**:
- Maximum flexibility for agents (IMAP/SMTP or REST API)
- Consistent with SSH proxy pattern (transparent protocol)
- REST API provides simpler integration for basic operations
- Future-proofing for both current and future agent architectures
