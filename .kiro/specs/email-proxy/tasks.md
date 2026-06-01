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
- [ ] Add `AUTH_SCHEME_EMAIL_PASSWORD = 14`
- [ ] Add `AUTH_SCHEME_EMAIL_OAUTH2 = 15`
- [ ] Add `AUTH_SCHEME_EMAIL_APP_PASSWORD = 16`
- [ ] Update comments with email-specific metadata
- [ ] Proto compiles without errors

**Files**:
- `docs/architecture/contracts/vault-adapter/vault.proto`

### Task 1.3: Update OpenAPI Schema
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 1.2

**Description**: Add email service endpoints and schemas to OpenAPI.

**Acceptance Criteria**:
- [ ] Add email auth schemes to AuthScheme enum
- [ ] Add EmailService schema
- [ ] Add EmailMessage schema with body_type field
- [ ] Add Mailbox schema
- [ ] Add Attachment schema
- [ ] Add endpoints: GET /v1/email/mailboxes, GET /v1/email/messages, GET /v1/email/messages/{id}, POST /v1/email/send, DELETE /v1/email/messages/{id}, POST /v1/email/messages/{id}/move, POST /v1/email/messages/{id}/flags, POST /v1/email/search, GET /v1/email/attachments/{id}
- [ ] OpenAPI validates without errors

**Files**:
- `docs/architecture/contracts/rest/openapi.yaml`

### Task 1.4: Update MCP Tools
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 1.3

**Description**: Add email MCP tools to tools.yaml.

**Acceptance Criteria**:
- [ ] Add email auth schemes to auth_scheme enum
- [ ] Add list_mailboxes tool (requires read:email)
- [ ] Add list_emails tool (requires read:email)
- [ ] Add read_email tool (requires read:email)
- [ ] Add send_email tool (requires send:email)
- [ ] Add search_emails tool (requires read:email)
- [ ] Add delete_email tool (requires delete:email)
- [ ] Add move_email tool (requires write:email)
- [ ] Add download_attachment tool (requires read:email)
- [ ] Add mark_email tool (requires write:email)
- [ ] YAML validates without errors

**Files**:
- `docs/architecture/contracts/mcp/tools.yaml`

### Task 1.5: Update Audit Event Schema
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.1

**Description**: Add email audit events to schema.

**Acceptance Criteria**:
- [ ] Add target_type enum values: `email_service`, `email_message`, `email_attachment`
- [ ] Add auth_scheme enum values: `email_password`, `email_oauth2`, `email_app_password`
- [ ] Add email event types: `email.mailboxes.listed`, `email.messages.listed`, `email.message.read`, `email.sent`, `email.messages.searched`, `email.message.deleted`, `email.message.moved`, `email.attachment.downloaded`, `email.service.registered`, `email.service.auth_expired`, `email.message.flags_updated`, `email.rate_limit.exceeded`, `email.domain.blocked`
- [ ] JSON schema validates without errors

**Files**:
- `docs/architecture/contracts/events/audit-event.schema.json`

### Task 1.6: Update Change Event Schema
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.1

**Description**: Add email change events to schema.

**Acceptance Criteria**:
- [ ] Add `email.service.registered` event
- [ ] Add `email.service.updated` event
- [ ] Add `email.service.deleted` event
- [ ] Add events to `oneOf` array and `discriminator.mapping`
- [ ] Add to `x-mintkey-channels` section
- [ ] JSON schema validates without errors

**Files**:
- `docs/architecture/contracts/events/change-event.schema.json`

### Task 1.7: Update Span Attributes
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 1.1

**Description**: Add email proxy span attributes.

**Acceptance Criteria**:
- [ ] Add span names: `mintkey.email.handle_request`, `mintkey.email.fetch_credential`, `mintkey.email.imap_operation`, `mintkey.email.smtp_send`
- [ ] Add allowed attributes: `mintkey.email.operation`, `mintkey.email.provider`, `mintkey.email.mailbox`, `mintkey.email.message_count`, `mintkey.email.attachment_count`, `mintkey.email.attachment_size`
- [ ] Update `mintkey/internal/otel/allowlist.go`
- [ ] Update `mintkey_otel/allowlist.py`
- [ ] Documentation updated

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
- [ ] Create `apps/email-proxy/` directory
- [ ] Create `cmd/email-proxy/main.go`
- [ ] Create `internal/config/config.go`
- [ ] Create `internal/pool/` directory (IMAP connection pool)
- [ ] Create `internal/imap/` directory
- [ ] Create `internal/smtp/` directory
- [ ] Create `internal/oauth2/` directory
- [ ] Create `internal/api/` directory (REST API)
- [ ] Create `internal/auth/` directory (JWT validation)
- [ ] Create `internal/security/` directory (injection prevention, domain filtering, rate limiting)
- [ ] Create `internal/audit/` directory
- [ ] Create `internal/metrics/` directory
- [ ] Create `internal/trace/` directory
- [ ] Create `go.mod` with correct module path (`github.com/mintkey/mintkey/services/email-proxy`)
- [ ] Create `Dockerfile`

**Files**:
- `apps/email-proxy/**`

### Task 2.2: Implement Configuration
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.1

**Description**: Implement configuration loading.

**Acceptance Criteria**:
- [ ] Config struct defined with all fields (VaultIdentityID, VaultIdentityToken, OTelEndpoint, AuditWALPath)
- [ ] Load from environment variables
- [ ] Validate required fields
- [ ] Set sensible defaults
- [ ] Unit tests pass

**Files**:
- `apps/email-proxy/internal/config/config.go`
- `apps/email-proxy/internal/config/config_test.go`

### Task 2.3: Implement IMAP Client
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 2.2

**Description**: Implement IMAP client wrapper.

**Acceptance Criteria**:
- [ ] Connect to IMAP server with password
- [ ] Connect to IMAP server with OAuth2 token
- [ ] List mailboxes
- [ ] Select mailbox
- [ ] Fetch message summaries (ENVELOPE)
- [ ] Fetch full message with attachments
- [ ] Search messages (parameterized, no injection)
- [ ] Delete message (move to Trash)
- [ ] Move message to mailbox
- [ ] Mark message flags (read/unread/flagged)
- [ ] Handle connection errors
- [ ] Handle authentication errors
- [ ] Unit tests pass with mock IMAP server

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
- [ ] Connect to SMTP server with password
- [ ] Connect to SMTP server with OAuth2 token
- [ ] Send email with text body
- [ ] Send email with HTML body
- [ ] Send email with attachments
- [ ] Support multiple recipients (to, cc, bcc)
- [ ] Validate recipient addresses with RFC 5322 parser
- [ ] Sanitize headers (reject \r\n injection)
- [ ] Handle connection errors
- [ ] Handle authentication errors
- [ ] Handle send errors
- [ ] Unit tests pass with mock SMTP server

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
- [ ] Gmail OAuth2 flow (authorization URL, token exchange, refresh)
- [ ] Outlook OAuth2 flow (authorization URL, token exchange, refresh)
- [ ] Provider interface for extensibility
- [ ] Singleflight to prevent concurrent token refresh storms
- [ ] Handle token refresh failures
- [ ] Handle token expiration (emit `email.service.auth_expired` audit event)
- [ ] Update service status to `error` on expiration
- [ ] Unit tests pass with mock OAuth2 server

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
- [ ] Per-service connection pool with configurable size (default: 5)
- [ ] Idle timeout: 5 minutes (configurable)
- [ ] Credentials fetched once per pool connection
- [ ] UIDVALIDITY tracking (invalidate cached UIDs on change)
- [ ] Thread-safe (concurrent access from multiple requests)
- [ ] Connection health checks
- [ ] Unit tests pass

**Files**:
- `apps/email-proxy/internal/pool/pool.go`
- `apps/email-proxy/internal/pool/pool_test.go`

### Task 2.7: Implement Security Measures
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 2.3, Task 2.4

**Description**: Implement security measures for injection prevention, domain filtering, and rate limiting.

**Acceptance Criteria**:
- [ ] IMAP/SMTP injection prevention (parameterized queries, header sanitization)
- [ ] RFC 5322 address parsing and validation
- [ ] Domain filtering (configurable allowlist per service)
- [ ] Rate limiting (per-agent, per-service, shared via Postgres advisory locks)
- [ ] Search query sanitization (log length/mailbox, not query text)
- [ ] Unit tests for injection prevention, address parsing, domain filtering, rate limiting

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
- [ ] Validate JWT against broker JWKS (Ed25519)
- [ ] Force-refresh JWKS on unknown `kid` (per ADR-0016.2)
- [ ] Check JWT scope against required permission
- [ ] Check JWT audience matches service_id
- [ ] Handle JWKS fetch failures
- [ ] Unit tests pass

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
- [ ] HTTP server with chi router
- [ ] JWT validation middleware
- [ ] Logging middleware
- [ ] GET /v1/email/mailboxes endpoint
- [ ] GET /v1/email/messages endpoint
- [ ] GET /v1/email/messages/{id} endpoint
- [ ] POST /v1/email/send endpoint
- [ ] DELETE /v1/email/messages/{id} endpoint
- [ ] POST /v1/email/messages/{id}/move endpoint
- [ ] POST /v1/email/messages/{id}/flags endpoint
- [ ] POST /v1/email/search endpoint
- [ ] GET /v1/email/attachments/{id} endpoint
- [ ] POST /v1/health endpoint
- [ ] POST /v1/ready endpoint
- [ ] Error handling with JSON responses (sanitized)
- [ ] Unit tests pass

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
- [ ] Emit email.mailboxes.listed event
- [ ] Emit email.messages.listed event
- [ ] Emit email.message.read event
- [ ] Emit email.sent event
- [ ] Emit email.messages.searched event
- [ ] Emit email.message.deleted event
- [ ] Emit email.message.moved event
- [ ] Emit email.message.flags_updated event
- [ ] Emit email.attachment.downloaded event
- [ ] Emit email.service.auth_expired event
- [ ] Sanitize search queries (log length/mailbox, not query text)
- [ ] Sanitize recipients (log count, not addresses)
- [ ] Truncate subject to 100 chars
- [ ] Integrate with auditq.Queue (use auditq.Event struct)
- [ ] Include prev_hash + hash for audit chain
- [ ] Unit tests pass

**Files**:
- `apps/email-proxy/internal/audit/emit.go`
- `apps/email-proxy/internal/audit/emit_test.go`

### Task 2.11: Implement Metrics
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.9

**Description**: Implement Prometheus metrics.

**Acceptance Criteria**:
- [ ] Track email operations by type
- [ ] Track email operations by provider
- [ ] Track operation duration
- [ ] Track error rates
- [ ] Track attachment sizes
- [ ] Track rate limit violations
- [ ] Track domain blocks
- [ ] Expose /metrics endpoint
- [ ] Unit tests pass

**Files**:
- `apps/email-proxy/internal/metrics/metrics.go`
- `apps/email-proxy/internal/metrics/metrics_test.go`

### Task 2.12: Implement Tracing
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.9

**Description**: Implement OpenTelemetry tracing.

**Acceptance Criteria**:
- [ ] Create spans for all email operations
- [ ] Add span attributes (operation, provider, mailbox, message_count)
- [ ] Integrate with OTel SDK
- [ ] Unit tests pass

**Files**:
- `apps/email-proxy/internal/trace/trace.go`
- `apps/email-proxy/internal/trace/trace_test.go`

### Task 2.13: Wire Everything Together
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 2.10, Task 2.11, Task 2.12

**Description**: Wire all components in main.go.

**Acceptance Criteria**:
- [ ] Load configuration
- [ ] Initialize Vault client with service identity
- [ ] Initialize IMAP connection pool
- [ ] Initialize SMTP client
- [ ] Initialize OAuth2 handlers
- [ ] Initialize JWT validation
- [ ] Initialize security measures
- [ ] Initialize audit emitter
- [ ] Initialize metrics
- [ ] Initialize tracing
- [ ] Start HTTP server
- [ ] Handle graceful shutdown
- [ ] Integration test passes

**Files**:
- `apps/email-proxy/cmd/email-proxy/main.go`

## Milestone 3: Frontend (Week 4)

### Task 3.1: Create Email Service Resource
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 1.3

**Description**: Create AdminJS resource for email services.

**Acceptance Criteria**:
- [ ] Email service list view
- [ ] Email service detail view
- [ ] Email service create form
- [ ] Email service edit form
- [ ] Email service delete action
- [ ] Resource registered in AdminJS

**Files**:
- `apps/admin-ui/src/resources/email_services.ts`

### Task 3.2: Create Email Service Create Form
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 3.1

**Description**: Create form for registering email services.

**Acceptance Criteria**:
- [ ] Provider selection (Gmail, Outlook, Custom)
- [ ] For Gmail/Outlook: OAuth2 setup button
- [ ] For Custom: IMAP/SMTP server fields
- [ ] Username/password fields
- [ ] Connection pool size configuration
- [ ] Rate limit configuration
- [ ] Domain restrictions configuration
- [ ] Test connection button
- [ ] Form validation
- [ ] Success/error messages
- [ ] Unit tests pass

**Files**:
- `apps/admin-ui/src/components/actions/EmailServiceCreateForm.tsx`
- `apps/admin-ui/src/components/actions/EmailServiceCreateForm.test.tsx`

### Task 3.3: Create OAuth2 Setup Component
**Status**: ⏳ Pending  
**Effort**: 1.5 days  
**Dependencies**: Task 3.2

**Description**: Create OAuth2 setup flow component with CSRF protection.

**Acceptance Criteria**:
- [ ] Generate cryptographic state parameter
- [ ] Store state in session
- [ ] Display authorization URL
- [ ] Handle OAuth2 callback with state validation
- [ ] Exchange code for tokens
- [ ] Store refresh token in Vault
- [ ] Handle token expiration
- [ ] Display success/error messages
- [ ] Re-authorize button for expired tokens
- [ ] Unit tests pass

**Files**:
- `apps/admin-ui/src/components/actions/EmailServiceOAuth2Setup.tsx`
- `apps/admin-ui/src/components/actions/EmailServiceOAuth2Setup.test.tsx`

### Task 3.4: Create Email Services Intro Section
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 3.1

**Description**: Create intro section for email services.

**Acceptance Criteria**:
- [ ] Display overview of email proxy
- [ ] Display setup instructions
- [ ] Link to documentation
- [ ] Unit tests pass

**Files**:
- `apps/admin-ui/src/components/sections/EmailServicesIntro.tsx`
- `apps/admin-ui/src/components/sections/EmailServicesIntro.test.tsx`

### Task 3.5: Add Email Service Endpoints to admin-api
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 1.3

**Description**: Add email service CRUD endpoints to admin-api.

**Acceptance Criteria**:
- [ ] GET /v1/email/services endpoint
- [ ] GET /v1/email/services/{id} endpoint
- [ ] POST /v1/email/services endpoint
- [ ] PATCH /v1/email/services/{id} endpoint
- [ ] DELETE /v1/email/services/{id} endpoint
- [ ] POST /v1/email/services/{id}/test endpoint
- [ ] POST /v1/email/services/oauth2/authorize endpoint
- [ ] POST /v1/email/services/oauth2/callback endpoint
- [ ] Permission checks
- [ ] Audit event emission
- [ ] Unit tests pass

**Files**:
- `apps/admin-api/src/admin_api/api/email_services.py`
- `apps/admin-api/src/admin_api/api/email_services_test.py`

### Task 3.6: Add Email Service Database Schema
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 3.5

**Description**: Add email_services table to database.

**Acceptance Criteria**:
- [ ] Create email_services table with foreign key to services table
- [ ] Add indexes
- [ ] Add RLS policies
- [ ] Single transaction for services + email_services inserts
- [ ] Create migration
- [ ] Migration runs without errors

**Files**:
- `apps/admin-api/db/changelog/XXX-email-services.yaml`

## Milestone 4: Testing (Week 5)

### Task 4.1: Write Unit Tests
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 2.13

**Description**: Write comprehensive unit tests.

**Acceptance Criteria**:
- [ ] IMAP client tests (80% coverage)
- [ ] SMTP client tests (80% coverage)
- [ ] OAuth2 handler tests (80% coverage)
- [ ] Connection pool tests (80% coverage)
- [ ] Security tests (injection prevention, domain filtering, rate limiting) (80% coverage)
- [ ] JWT validation tests (80% coverage)
- [ ] API handler tests (80% coverage)
- [ ] Audit emitter tests (80% coverage)
- [ ] Metrics tests (80% coverage)
- [ ] Trace tests (80% coverage)
- [ ] All tests pass

**Files**:
- `apps/email-proxy/**/*_test.go`

### Task 4.2: Write Integration Tests
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 4.1

**Description**: Write integration tests with mock email providers.

**Acceptance Criteria**:
- [ ] Test email send flow
- [ ] Test email receive flow
- [ ] Test email search flow
- [ ] Test OAuth2 flow with mock provider
- [ ] Test attachment handling
- [ ] Test connection pooling
- [ ] Test error handling
- [ ] Test OAuth2 token refresh with singleflight
- [ ] Test UIDVALIDITY change detection
- [ ] All tests pass

**Files**:
- `tests/integration/email_proxy/test_email_flow.py`

### Task 4.3: Write Acceptance Tests
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 4.2

**Description**: Write acceptance tests with full docker-compose stack.

**Acceptance Criteria**:
- [ ] Test with real Gmail account (test account)
- [ ] Test with real Outlook account (test account)
- [ ] Test with custom IMAP/SMTP server
- [ ] Test OAuth2 flows
- [ ] Test attachment handling
- [ ] Test rate limiting
- [ ] Test domain filtering
- [ ] Test audit hash chain
- [ ] Test TLS termination
- [ ] All tests pass

**Files**:
- `tests/acceptance/test_email_proxy.py`

### Task 4.4: Write Architecture Tests
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.1

**Description**: Write architecture tests to enforce security invariants.

**Acceptance Criteria**:
- [ ] No plaintext credentials in logs
- [ ] Audit events emitted for all operations
- [ ] Rate limiting enforced via Postgres advisory locks
- [ ] Domain filtering enforced via RFC 5322 parser
- [ ] JWT validation via JWKS (not shared secret)
- [ ] Search query sanitization in audit events
- [ ] All tests pass

**Files**:
- `tests/architecture/test_email_proxy_security.py`

### Task 4.5: Write Security Red Team Tests
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.1

**Description**: Write red team tests for security vulnerabilities.

**Acceptance Criteria**:
- [ ] Send email containing known credential fingerprint, verify it doesn't appear in logs, audit events, or span attributes
- [ ] Attempt IMAP/SMTP injection via malformed search queries
- [ ] Attempt IMAP/SMTP injection via malformed email headers
- [ ] Attempt domain filtering bypass via malformed addresses
- [ ] Attempt rate limiting bypass by distributing requests across instances
- [ ] Concurrent OAuth2 token refresh (10 goroutines), verify singleflight prevents storms
- [ ] All tests pass

**Files**:
- `tests/security/test_email_proxy_redteam.py`

### Task 4.6: Write Performance Tests
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.1

**Description**: Write performance tests.

**Acceptance Criteria**:
- [ ] Load test with 100 concurrent operations
- [ ] Measure latency percentiles (p50, p95, p99)
- [ ] Verify connection pooling reduces overhead by 80%
- [ ] Verify rate limiting works under load
- [ ] Document performance characteristics

**Files**:
- `tests/performance/test_email_proxy_load.py`

## Milestone 5: Documentation & Deployment (Week 6)

### Task 5.1: Write User Documentation
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 4.3

**Description**: Write user-facing documentation.

**Acceptance Criteria**:
- [ ] How to configure email services
- [ ] How to use email MCP tools
- [ ] OAuth2 setup guide
- [ ] Troubleshooting guide
- [ ] Examples

**Files**:
- `docs/user-guide/email-proxy.md`

### Task 5.2: Write API Documentation
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 4.3

**Description**: Write API reference documentation.

**Acceptance Criteria**:
- [ ] REST API reference
- [ ] MCP tools reference
- [ ] Error codes reference
- [ ] Examples

**Files**:
- `docs/api-reference/email-proxy.md`

### Task 5.3: Create Grafana Dashboard
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 2.8

**Description**: Create Grafana dashboard for email proxy metrics.

**Acceptance Criteria**:
- [ ] Email operations per minute panel
- [ ] OAuth2 token refresh rate panel
- [ ] Error rates by provider panel
- [ ] Attachment upload/download rates panel
- [ ] Rate limit violations panel
- [ ] Domain blocks panel
- [ ] Dashboard imports without errors

**Files**:
- `grafana/dashboards/email-proxy.json`

### Task 5.4: Update Docker Compose
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 2.13

**Description**: Add email-proxy to docker-compose.yml.

**Acceptance Criteria**:
- [ ] email-proxy service defined
- [ ] Environment variables configured
- [ ] Health checks configured
- [ ] Port 993 exposed (IMAP)
- [ ] Port 587 exposed (SMTP)
- [ ] Port 8088 exposed (REST API + health/metrics)
- [ ] Depends on vault-adapter and admin-api
- [ ] docker-compose up starts email-proxy

**Files**:
- `docker-compose.yml`

### Task 5.5: Update CI/CD Pipeline
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 4.3

**Description**: Add email-proxy to CI/CD pipeline.

**Acceptance Criteria**:
- [ ] Build email-proxy in CI
- [ ] Run unit tests in CI
- [ ] Run integration tests in CI
- [ ] Run acceptance tests in nightly
- [ ] Deploy email-proxy on merge to main

**Files**:
- `.github/workflows/ci.yml`

## Milestone 6: Adversarial Review & Hardening (Week 7)

### Task 6.1: Conduct Adversarial Review
**Status**: ⏳ Pending  
**Effort**: 2 days  
**Dependencies**: Task 5.5

**Description**: Conduct adversarial review of email proxy implementation.

**Acceptance Criteria**:
- [ ] Security review completed
- [ ] Architecture review completed
- [ ] Performance review completed
- [ ] Findings documented
- [ ] Critical findings addressed

**Files**:
- `docs/architecture/contracts/_review-email-proxy.md`

### Task 6.2: Address Review Findings
**Status**: ⏳ Pending  
**Effort**: 3 days  
**Dependencies**: Task 6.1

**Description**: Address findings from adversarial review.

**Acceptance Criteria**:
- [ ] All critical findings fixed
- [ ] All high findings fixed or documented
- [ ] Tests updated
- [ ] Documentation updated

**Files**:
- Various based on findings

### Task 6.3: Performance Testing
**Status**: ⏳ Pending  
**Effort**: 1 day  
**Dependencies**: Task 6.2

**Description**: Conduct performance testing.

**Acceptance Criteria**:
- [ ] Load test with 100 concurrent operations
- [ ] Measure latency percentiles (p50, p95, p99)
- [ ] Identify bottlenecks
- [ ] Optimize critical paths
- [ ] Document performance characteristics

**Files**:
- `tests/performance/test_email_proxy_load.py`

## Milestone 7: Release (Week 8)

### Task 7.1: Create Release Notes
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 6.3

**Description**: Create release notes for email proxy feature.

**Acceptance Criteria**:
- [ ] Feature overview
- [ ] Breaking changes (if any)
- [ ] Migration guide (if needed)
- [ ] Known issues
- [ ] Changelog

**Files**:
- `RELEASE_NOTES.md`

### Task 7.2: Update Main Documentation
**Status**: ⏳ Pending  
**Effort**: 0.5 day  
**Dependencies**: Task 7.1

**Description**: Update main documentation to reference email proxy.

**Acceptance Criteria**:
- [ ] Update README.md
- [ ] Update architecture overview
- [ ] Update deployment guide
- [ ] Update user guide

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
- [ ] All tests pass
- [ ] All documentation updated
- [ ] Code review approved
- [ ] Merge to main
- [ ] Tag release

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
