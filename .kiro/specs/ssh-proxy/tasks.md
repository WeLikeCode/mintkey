# SSH Proxy Implementation Tasks

## Milestone M1: Foundation
**Goal**: Establish the basic SSH proxy infrastructure and authentication mechanisms.

### Task M1.1: Project Setup
**Description**: Create the ssh-proxy binary structure and build configuration.
**Files**:
- `apps/ssh-proxy/go.mod`
- `apps/ssh-proxy/Dockerfile`
- `apps/ssh-proxy/cmd/ssh-proxy/main.go`
- `apps/ssh-proxy/internal/config/config.go`
- `apps/ssh-proxy/internal/config/config_test.go`

**Acceptance Criteria**:
- [x] Go module initialized with dependencies (golang.org/x/crypto/ssh, google.golang.org/grpc, etc.)
- [x] Dockerfile builds distroless image
- [x] main.go loads configuration from environment variables
- [x] config.go defines all configuration parameters with defaults
- [x] Unit tests for configuration loading

**Dependencies**: None

### Task M1.2: SSH Server Implementation
**Description**: Implement the SSH server that listens for agent connections.
**Files**:
- `apps/ssh-proxy/internal/server/server.go`
- `apps/ssh-proxy/internal/server/server_test.go`

**Acceptance Criteria**:
- [x] SSH server listens on configured port (default 2222)
- [x] Host key loaded from file or generated
- [x] Server configuration (ciphers, MACs, key exchanges) follows security best practices
- [x] Graceful shutdown on SIGTERM
- [x] Unit tests for server lifecycle

**Dependencies**: M1.1

### Task M1.3: JWT Authentication
**Description**: Implement JWT-as-password authentication method.
**Files**:
- `apps/ssh-proxy/internal/auth/jwt.go`
- `apps/ssh-proxy/internal/auth/jwt_test.go`

**Acceptance Criteria**:
- [x] Parse JWT from SSH password field
- [x] Validate JWT signature using JWKS from broker
- [x] Extract agent_id, service_id, tenant_id from JWT claims
- [x] Reject expired or invalid JWTs with clear error message
- [x] Unit tests with valid/invalid/expired JWTs

**Dependencies**: M1.2

### Task M1.4: API Key Authentication
**Description**: Implement API-key-derived public key authentication method.
**Files**:
- `apps/ssh-proxy/internal/auth/apikey.go`
- `apps/ssh-proxy/internal/auth/apikey_test.go`

**Acceptance Criteria**:
- [x] Derive Ed25519 public key from agent API key
- [x] Validate API key via Vault Adapter
- [x] Extract agent_id, service_id, tenant_id from API key metadata
- [x] Reject invalid API keys with clear error message
- [x] Unit tests with valid/invalid API keys

**Dependencies**: M1.2

### Task M1.5: Authentication Dispatcher
**Description**: Implement authentication dispatcher that routes to JWT or API key auth.
**Files**:
- `apps/ssh-proxy/internal/auth/auth.go`
- `apps/ssh-proxy/internal/auth/auth_test.go`

**Acceptance Criteria**:
- [x] Detect authentication method (password = JWT, public key = API key)
- [x] Route to appropriate authentication handler
- [x] Return session context with agent_id, service_id, tenant_id
- [x] Emit audit event on authentication failure
- [x] Integration tests for both authentication methods

**Dependencies**: M1.3, M1.4

### Task M1.6: Health Check
**Description**: Implement health check endpoint for load balancer integration.
**Files**:
- `apps/ssh-proxy/internal/server/health.go`
- `apps/ssh-proxy/internal/server/health_test.go`

**Acceptance Criteria**:
- [x] HTTP health check endpoint on separate port (default 8087)
- [x] Return 200 OK when server is ready
- [x] Return 503 Service Unavailable when server is shutting down
- [x] Unit tests for health check responses

**Dependencies**: M1.2

## Milestone M2: Core Proxy
**Goal**: Implement the core SSH proxy functionality (backend connection, channel bridging, session management).

### Task M2.1: Backend SSH Connection
**Description**: Implement backend SSH connection using credentials from Vault Adapter.
**Files**:
- `apps/ssh-proxy/internal/backend/backend.go`
- `apps/ssh-proxy/internal/backend/backend_test.go`
- `apps/ssh-proxy/internal/vault/client.go`
- `apps/ssh-proxy/internal/vault/client_test.go`

**Acceptance Criteria**:
- [x] Fetch SSH private key from Vault Adapter (gRPC)
- [x] Parse SSH private key (PEM or OpenSSH format)
- [x] Establish SSH connection to backend server
- [x] Handle connection failures with clear error messages
- [x] Zero private key material after use
- [x] Unit tests with mock Vault Adapter and SSH server

**Dependencies**: M1.5

### Task M2.2: Host Key Verification
**Description**: Implement host key verification using Trust-on-First-Use (TOFU) mode.
**Files**:
- `apps/ssh-proxy/internal/backend/hostkey.go`
- `apps/ssh-proxy/internal/backend/hostkey_test.go`

**Acceptance Criteria**:
- [x] Store host key fingerprints in database on first connection
- [x] Verify host key on subsequent connections
- [x] Configurable behavior on host key change (fail or warn)
- [x] Emit audit event on host key change
- [x] Unit tests for TOFU logic

**Dependencies**: M2.1

### Task M2.3: Channel Bridging
**Description**: Implement bidirectional I/O bridging between agent and backend channels.
**Files**:
- `apps/ssh-proxy/internal/bridge/bridge.go`
- `apps/ssh-proxy/internal/bridge/bridge_test.go`

**Acceptance Criteria**:
- [x] Bridge stdin/stdout/stderr between agent and backend
- [x] Handle channel close gracefully
- [x] Track bytes sent/received for metrics
- [x] Support multiple channels per session
- [x] Unit tests for I/O bridging

**Dependencies**: M2.1

### Task M2.4: PTY Handling
**Description**: Implement pseudo-terminal (PTY) support for interactive sessions.
**Files**:
- `apps/ssh-proxy/internal/bridge/pty.go`
- `apps/ssh-proxy/internal/bridge/pty_test.go`

**Acceptance Criteria**:
- [x] Handle PTY requests from agent
- [x] Forward PTY requests to backend
- [x] Handle window size changes
- [x] Support terminal modes (echo, canonical, etc.)
- [x] Unit tests for PTY handling

**Dependencies**: M2.3

### Task M2.5: Signal Forwarding
**Description**: Implement signal forwarding between agent and backend.
**Files**:
- `apps/ssh-proxy/internal/bridge/signal.go`
- `apps/ssh-proxy/internal/bridge/signal_test.go`

**Acceptance Criteria**:
- [x] Forward signals from agent to backend (SIGINT, SIGTERM, etc.)
- [x] Handle signal requests gracefully
- [x] Unit tests for signal forwarding

**Dependencies**: M2.3

### Task M2.6: Session Management
**Description**: Implement session lifecycle management.
**Files**:
- `apps/ssh-proxy/internal/session/session.go`
- `apps/ssh-proxy/internal/session/session_test.go`

**Acceptance Criteria**:
- [x] Create session context on authentication
- [x] Track active sessions
- [x] Clean up session resources on disconnect
- [x] Handle concurrent sessions per agent
- [x] Unit tests for session lifecycle

**Dependencies**: M1.5, M2.3

### Task M2.7: Rate Limiting
**Description**: Implement rate limiting for concurrent sessions per agent.
**Files**:
- `apps/ssh-proxy/internal/session/limiter.go`
- `apps/ssh-proxy/internal/session/limiter_test.go`

**Acceptance Criteria**:
- [x] Track active sessions per agent
- [x] Reject new sessions when limit reached (configurable, default 5)
- [x] Emit audit event on session rejection
- [x] Unit tests for rate limiting

**Dependencies**: M2.6

### Task M2.8: Session Timeout
**Description**: Implement session timeout to prevent resource exhaustion.
**Files**:
- `apps/ssh-proxy/internal/session/timeout.go`
- `apps/ssh-proxy/internal/session/timeout_test.go`

**Acceptance Criteria**:
- [x] Terminate sessions after configurable timeout (default 3600s)
- [x] Emit audit event on session timeout
- [x] Graceful shutdown (send SIGHUP to backend)
- [x] Unit tests for session timeout

**Dependencies**: M2.6

## Milestone M3: Audit & Recording
**Goal**: Implement comprehensive audit logging and session recording.

### Task M3.1: Audit Emission
**Description**: Implement audit event emission for SSH sessions.
**Files**:
- `apps/ssh-proxy/internal/audit/audit.go`
- `apps/ssh-proxy/internal/audit/audit_test.go`

**Acceptance Criteria**:
- [x] Emit `ssh.session.started` on session start
- [x] Emit `ssh.session.ended` on session end
- [x] Emit `ssh.session.exec` on command execution
- [x] Emit `ssh.session.sftp` on SFTP operations
- [x] Include session_id, agent_id, service_id, tenant_id in all events
- [x] No plaintext credentials in audit payloads
- [x] Unit tests for audit emission

**Dependencies**: M2.6

### Task M3.2: Session Recording
**Description**: Implement session recording in asciicast v2 format.
**Files**:
- `apps/ssh-proxy/internal/recording/recording.go`
- `apps/ssh-proxy/internal/recording/recording_test.go`
- `apps/ssh-proxy/internal/recording/asciicast.go`
- `apps/ssh-proxy/internal/recording/asciicast_test.go`

**Acceptance Criteria**:
- [x] Record session I/O in asciicast v2 format
- [x] Write recording to configured storage path
- [x] Include session metadata (agent_id, service_id, tenant_id)
- [x] Handle recording write failures gracefully (log error, continue session)
- [x] Unit tests for asciicast format

**Dependencies**: M2.3, M3.1

### Task M3.3: Recording Storage
**Description**: Implement recording storage with retention policy.
**Files**:
- `apps/ssh-proxy/internal/recording/storage.go`
- `apps/ssh-proxy/internal/recording/storage_test.go`

**Acceptance Criteria**:
- [x] Store recordings in configured directory
- [x] Implement retention policy (delete recordings older than N days, default 30)
- [x] Periodic cleanup of old recordings (daily)
- [x] Unit tests for storage and retention

**Dependencies**: M3.2

### Task M3.4: SFTP Support
**Description**: Implement SFTP subsystem support.
**Files**:
- `apps/ssh-proxy/internal/sftp/sftp.go`
- `apps/ssh-proxy/internal/sftp/sftp_test.go`
- `apps/ssh-proxy/internal/sftp/handler.go`
- `apps/ssh-proxy/internal/sftp/handler_test.go`

**Acceptance Criteria**:
- [x] Handle SFTP subsystem requests from agent
- [x] Forward SFTP requests to backend
- [x] Parse SFTP operations (read, write, list, delete, mkdir, rmdir, rename)
- [x] Emit audit events for SFTP operations
- [x] Unit tests for SFTP handling

**Dependencies**: M2.3, M3.1

## Milestone M4: Command Filtering
**Goal**: Implement command filtering to enforce least-privilege access.

### Task M4.1: Command Filter
**Description**: Implement command filtering with allowlist/denylist modes.
**Files**:
- `apps/ssh-proxy/internal/filter/filter.go`
- `apps/ssh-proxy/internal/filter/filter_test.go`

**Acceptance Criteria**:
- [x] Support allowlist mode (only listed commands allowed)
- [x] Support denylist mode (listed commands blocked)
- [x] Support regex patterns for command matching
- [x] Default mode: denylist (empty = all commands allowed)
- [x] Unit tests for filtering logic

**Dependencies**: None

### Task M4.2: Command Parser
**Description**: Implement command parser to extract command name and arguments.
**Files**:
- `apps/ssh-proxy/internal/filter/parser.go`
- `apps/ssh-proxy/internal/filter/parser_test.go`

**Acceptance Criteria**:
- [x] Parse command string into command name and arguments
- [x] Handle shell metacharacters (pipes, redirects, etc.)
- [x] Handle quoted arguments
- [x] Unit tests for command parsing

**Dependencies**: M4.1

### Task M4.3: Command Filter Integration
**Description**: Integrate command filtering into SSH session.
**Files**:
- `apps/ssh-proxy/internal/session/session.go` (update)
- `apps/ssh-proxy/internal/session/session_test.go` (update)

**Acceptance Criteria**:
- [x] Load command filter configuration per service
- [x] Check commands against filter before forwarding to backend
- [x] Block filtered commands with clear error message
- [x] Emit audit event on command block
- [x] Integration tests for command filtering

**Dependencies**: M2.6, M4.1, M4.2

### Task M4.4: SFTP Path Filtering
**Description**: Implement path-based filtering for SFTP operations.
**Files**:
- `apps/ssh-proxy/internal/sftp/handler.go` (update)
- `apps/ssh-proxy/internal/sftp/handler_test.go` (update)

**Acceptance Criteria**:
- [x] Apply command filter to SFTP paths
- [x] Block filtered SFTP operations with clear error message
- [x] Emit audit event on SFTP operation block
- [x] Integration tests for SFTP path filtering

**Dependencies**: M3.4, M4.3

## Milestone M5: Integration & Observability
**Goal**: Integrate with existing Mintkey infrastructure and add observability.

### Task M5.1: Prometheus Metrics
**Description**: Implement Prometheus metrics for monitoring.
**Files**:
- `apps/ssh-proxy/internal/metrics/metrics.go`
- `apps/ssh-proxy/internal/metrics/metrics_test.go`

**Acceptance Criteria**:
- [x] Expose metrics on HTTP endpoint (default 8087)
- [x] Track active sessions, session duration, bytes transferred
- [x] Track authentication failures, command blocks, session timeouts
- [x] Unit tests for metrics collection

**Dependencies**: M2.6

### Task M5.2: OTel Tracing
**Description**: Implement OpenTelemetry tracing for distributed tracing.
**Files**:
- `apps/ssh-proxy/internal/trace/trace.go`
- `apps/ssh-proxy/internal/trace/trace_test.go`

**Acceptance Criteria**:
- [x] Create spans for authentication, Vault fetch, backend connection, session duration
- [x] Add attributes: session_id, agent_id, service_id, tenant_id, auth_method
- [x] No credentials in span attributes (per allowlist)
- [x] Export traces to OTel collector
- [x] Unit tests for trace creation

**Dependencies**: M2.6

### Task M5.3: Grafana Dashboard
**Description**: Create Grafana dashboard for SSH proxy monitoring.
**Files**:
- `grafana/dashboards/ssh-proxy.json`

**Acceptance Criteria**:
- [x] Dashboard shows active sessions over time
- [x] Dashboard shows session duration distribution
- [x] Dashboard shows authentication failure rate
- [x] Dashboard shows command block rate
- [x] Dashboard shows bytes transferred
- [x] Dashboard shows error rate by type

**Dependencies**: M5.1

### Task M5.4: Revocation Integration
**Description**: Integrate with revocation system to terminate sessions on agent revocation.
**Files**:
- `apps/ssh-proxy/internal/revocation/revocation.go`
- `apps/ssh-proxy/internal/revocation/revocation_test.go`

**Acceptance Criteria**:
- [x] Subscribe to `mintkey:agent` change channel
- [x] Terminate active sessions on agent revocation
- [x] Emit audit event on revocation-triggered termination
- [x] Graceful shutdown (send SIGHUP to backend)
- [x] Integration tests for revocation handling

**Dependencies**: M2.6

### Task M5.5: Docker Compose Integration
**Description**: Add ssh-proxy to docker-compose.yml.
**Files**:
- `docker-compose.yml` (update)

**Acceptance Criteria**:
- [x] ssh-proxy service defined with correct dependencies
- [x] Environment variables configured
- [x] Ports exposed (2222 for SSH, 8087 for metrics/health)
- [x] Health check configured
- [x] Service starts after admin-api is healthy

**Dependencies**: M1.1, M1.6

### Task M5.6: Service Identity
**Description**: Create service identity for ssh-proxy.
**Files**:
- `seed-job/seed.py` (update)

**Acceptance Criteria**:
- [x] Create service identity `svc_ssh_proxy` in seed job
- [x] Generate service identity token
- [x] Store token in Kubernetes secret (or environment variable)
- [x] ssh-proxy uses token to authenticate to Vault Adapter

**Dependencies**: M2.1

## Milestone M6: Testing & Documentation
**Goal**: Comprehensive testing and documentation.

### Task M6.1: Integration Tests
**Description**: Write integration tests with real Postgres, Vault Adapter, and mock SSH server.
**Files**:
- `tests/integration/ssh_proxy/test_session_flow.py`
- `tests/integration/ssh_proxy/test_sftp.py`
- `tests/integration/ssh_proxy/test_command_filter.py`
- `tests/integration/ssh_proxy/test_recording.py`

**Acceptance Criteria**:
- [x] Test end-to-end session flow (agent → bastion → backend)
- [x] Test SFTP operations
- [x] Test command filtering
- [x] Test session recording
- [x] Test authentication methods (JWT and API key)
- [x] Test rate limiting and session timeout
- [x] All tests pass

**Dependencies**: M2, M3, M4

### Task M6.2: Acceptance Tests
**Description**: Write acceptance tests with full docker-compose stack.
**Files**:
- `tests/acceptance/test_ssh_proxy.py`

**Acceptance Criteria**:
- [x] Test golden path: agent → bastion → backend
- [x] Test security: no credentials in logs/audit
- [x] Test performance: latency < 500ms, overhead < 5%
- [x] Test revocation: sessions terminated on agent revocation
- [x] All tests pass

**Dependencies**: M5.5, M6.1

### Task M6.3: Architecture Tests
**Description**: Write architecture tests to enforce security invariants.
**Files**:
- `tests/architecture/test_ssh_proxy_security.py`

**Acceptance Criteria**:
- [x] No plaintext credentials in code
- [x] All sessions emit audit events
- [x] Key material zeroed on disconnect
- [x] Command filtering enforced
- [x] All tests pass

**Dependencies**: M6.1

### Task M6.4: Update ADR Index
**Description**: Update ADR index with ADR-0021.
**Files**:
- `docs/architecture/01-architecture/adr/README.md` (update)

**Acceptance Criteria**:
- [x] ADR-0021 listed in index
- [x] Status: Proposed
- [x] Summary: SSH proxy support for agent remote execution

**Dependencies**: ADR-0021 created

### Task M6.5: Update AGENTS.md
**Description**: Update AGENTS.md with SSH proxy information.
**Files**:
- `AGENTS.md` (update)

**Acceptance Criteria**:
- [x] SSH proxy mentioned in architecture overview
- [x] Link to ADR-0021
- [x] Instructions for running SSH proxy tests

**Dependencies**: M6.4

### Task M6.6: Create PR
**Description**: Create pull request with all changes.
**Files**:
- Pull request description

**Acceptance Criteria**:
- [x] All tasks completed
- [x] All tests pass (unit, integration, acceptance, architecture)
- [x] All contract validators pass
- [x] Comprehensive PR description
- [x] Review requested from maintainers

**Dependencies**: All previous tasks

## Summary

**Total Tasks**: 33
**Estimated Effort**: ~2500 lines of Go code, ~500 lines of Python tests
**Timeline**: 4-6 weeks (assuming 1 developer)

**Milestone Breakdown**:
- M1 (Foundation): 6 tasks, ~1 week
- M2 (Core Proxy): 8 tasks, ~1.5 weeks
- M3 (Audit & Recording): 4 tasks, ~1 week
- M4 (Command Filtering): 4 tasks, ~0.5 week
- M5 (Integration): 6 tasks, ~1 week
- M6 (Testing & Documentation): 6 tasks, ~1 week

**Critical Path**: M1 → M2 → M3 → M4 → M5 → M6

**Risk Mitigation**:
- Start with MVP (M1-M2) to validate core functionality
- Add audit and recording (M3) early for security compliance
- Defer advanced features (SFTP, command filtering) to later milestones
- Comprehensive testing (M6) before production deployment
