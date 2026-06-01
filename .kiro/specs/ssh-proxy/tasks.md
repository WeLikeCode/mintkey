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
- [ ] Go module initialized with dependencies (golang.org/x/crypto/ssh, google.golang.org/grpc, etc.)
- [ ] Dockerfile builds distroless image
- [ ] main.go loads configuration from environment variables
- [ ] config.go defines all configuration parameters with defaults
- [ ] Unit tests for configuration loading

**Dependencies**: None

### Task M1.2: SSH Server Implementation
**Description**: Implement the SSH server that listens for agent connections.
**Files**:
- `apps/ssh-proxy/internal/server/server.go`
- `apps/ssh-proxy/internal/server/server_test.go`

**Acceptance Criteria**:
- [ ] SSH server listens on configured port (default 2222)
- [ ] Host key loaded from file or generated
- [ ] Server configuration (ciphers, MACs, key exchanges) follows security best practices
- [ ] Graceful shutdown on SIGTERM
- [ ] Unit tests for server lifecycle

**Dependencies**: M1.1

### Task M1.3: JWT Authentication
**Description**: Implement JWT-as-password authentication method.
**Files**:
- `apps/ssh-proxy/internal/auth/jwt.go`
- `apps/ssh-proxy/internal/auth/jwt_test.go`

**Acceptance Criteria**:
- [ ] Parse JWT from SSH password field
- [ ] Validate JWT signature using JWKS from broker
- [ ] Extract agent_id, service_id, tenant_id from JWT claims
- [ ] Reject expired or invalid JWTs with clear error message
- [ ] Unit tests with valid/invalid/expired JWTs

**Dependencies**: M1.2

### Task M1.4: API Key Authentication
**Description**: Implement API-key-derived public key authentication method.
**Files**:
- `apps/ssh-proxy/internal/auth/apikey.go`
- `apps/ssh-proxy/internal/auth/apikey_test.go`

**Acceptance Criteria**:
- [ ] Derive Ed25519 public key from agent API key
- [ ] Validate API key via Vault Adapter
- [ ] Extract agent_id, service_id, tenant_id from API key metadata
- [ ] Reject invalid API keys with clear error message
- [ ] Unit tests with valid/invalid API keys

**Dependencies**: M1.2

### Task M1.5: Authentication Dispatcher
**Description**: Implement authentication dispatcher that routes to JWT or API key auth.
**Files**:
- `apps/ssh-proxy/internal/auth/auth.go`
- `apps/ssh-proxy/internal/auth/auth_test.go`

**Acceptance Criteria**:
- [ ] Detect authentication method (password = JWT, public key = API key)
- [ ] Route to appropriate authentication handler
- [ ] Return session context with agent_id, service_id, tenant_id
- [ ] Emit audit event on authentication failure
- [ ] Integration tests for both authentication methods

**Dependencies**: M1.3, M1.4

### Task M1.6: Health Check
**Description**: Implement health check endpoint for load balancer integration.
**Files**:
- `apps/ssh-proxy/internal/server/health.go`
- `apps/ssh-proxy/internal/server/health_test.go`

**Acceptance Criteria**:
- [ ] HTTP health check endpoint on separate port (default 8087)
- [ ] Return 200 OK when server is ready
- [ ] Return 503 Service Unavailable when server is shutting down
- [ ] Unit tests for health check responses

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
- [ ] Fetch SSH private key from Vault Adapter (gRPC)
- [ ] Parse SSH private key (PEM or OpenSSH format)
- [ ] Establish SSH connection to backend server
- [ ] Handle connection failures with clear error messages
- [ ] Zero private key material after use
- [ ] Unit tests with mock Vault Adapter and SSH server

**Dependencies**: M1.5

### Task M2.2: Host Key Verification
**Description**: Implement host key verification using Trust-on-First-Use (TOFU) mode.
**Files**:
- `apps/ssh-proxy/internal/backend/hostkey.go`
- `apps/ssh-proxy/internal/backend/hostkey_test.go`

**Acceptance Criteria**:
- [ ] Store host key fingerprints in database on first connection
- [ ] Verify host key on subsequent connections
- [ ] Configurable behavior on host key change (fail or warn)
- [ ] Emit audit event on host key change
- [ ] Unit tests for TOFU logic

**Dependencies**: M2.1

### Task M2.3: Channel Bridging
**Description**: Implement bidirectional I/O bridging between agent and backend channels.
**Files**:
- `apps/ssh-proxy/internal/bridge/bridge.go`
- `apps/ssh-proxy/internal/bridge/bridge_test.go`

**Acceptance Criteria**:
- [ ] Bridge stdin/stdout/stderr between agent and backend
- [ ] Handle channel close gracefully
- [ ] Track bytes sent/received for metrics
- [ ] Support multiple channels per session
- [ ] Unit tests for I/O bridging

**Dependencies**: M2.1

### Task M2.4: PTY Handling
**Description**: Implement pseudo-terminal (PTY) support for interactive sessions.
**Files**:
- `apps/ssh-proxy/internal/bridge/pty.go`
- `apps/ssh-proxy/internal/bridge/pty_test.go`

**Acceptance Criteria**:
- [ ] Handle PTY requests from agent
- [ ] Forward PTY requests to backend
- [ ] Handle window size changes
- [ ] Support terminal modes (echo, canonical, etc.)
- [ ] Unit tests for PTY handling

**Dependencies**: M2.3

### Task M2.5: Signal Forwarding
**Description**: Implement signal forwarding between agent and backend.
**Files**:
- `apps/ssh-proxy/internal/bridge/signal.go`
- `apps/ssh-proxy/internal/bridge/signal_test.go`

**Acceptance Criteria**:
- [ ] Forward signals from agent to backend (SIGINT, SIGTERM, etc.)
- [ ] Handle signal requests gracefully
- [ ] Unit tests for signal forwarding

**Dependencies**: M2.3

### Task M2.6: Session Management
**Description**: Implement session lifecycle management.
**Files**:
- `apps/ssh-proxy/internal/session/session.go`
- `apps/ssh-proxy/internal/session/session_test.go`

**Acceptance Criteria**:
- [ ] Create session context on authentication
- [ ] Track active sessions
- [ ] Clean up session resources on disconnect
- [ ] Handle concurrent sessions per agent
- [ ] Unit tests for session lifecycle

**Dependencies**: M1.5, M2.3

### Task M2.7: Rate Limiting
**Description**: Implement rate limiting for concurrent sessions per agent.
**Files**:
- `apps/ssh-proxy/internal/session/limiter.go`
- `apps/ssh-proxy/internal/session/limiter_test.go`

**Acceptance Criteria**:
- [ ] Track active sessions per agent
- [ ] Reject new sessions when limit reached (configurable, default 5)
- [ ] Emit audit event on session rejection
- [ ] Unit tests for rate limiting

**Dependencies**: M2.6

### Task M2.8: Session Timeout
**Description**: Implement session timeout to prevent resource exhaustion.
**Files**:
- `apps/ssh-proxy/internal/session/timeout.go`
- `apps/ssh-proxy/internal/session/timeout_test.go`

**Acceptance Criteria**:
- [ ] Terminate sessions after configurable timeout (default 3600s)
- [ ] Emit audit event on session timeout
- [ ] Graceful shutdown (send SIGHUP to backend)
- [ ] Unit tests for session timeout

**Dependencies**: M2.6

## Milestone M3: Audit & Recording
**Goal**: Implement comprehensive audit logging and session recording.

### Task M3.1: Audit Emission
**Description**: Implement audit event emission for SSH sessions.
**Files**:
- `apps/ssh-proxy/internal/audit/audit.go`
- `apps/ssh-proxy/internal/audit/audit_test.go`

**Acceptance Criteria**:
- [ ] Emit `ssh.session.started` on session start
- [ ] Emit `ssh.session.ended` on session end
- [ ] Emit `ssh.session.exec` on command execution
- [ ] Emit `ssh.session.sftp` on SFTP operations
- [ ] Include session_id, agent_id, service_id, tenant_id in all events
- [ ] No plaintext credentials in audit payloads
- [ ] Unit tests for audit emission

**Dependencies**: M2.6

### Task M3.2: Session Recording
**Description**: Implement session recording in asciicast v2 format.
**Files**:
- `apps/ssh-proxy/internal/recording/recording.go`
- `apps/ssh-proxy/internal/recording/recording_test.go`
- `apps/ssh-proxy/internal/recording/asciicast.go`
- `apps/ssh-proxy/internal/recording/asciicast_test.go`

**Acceptance Criteria**:
- [ ] Record session I/O in asciicast v2 format
- [ ] Write recording to configured storage path
- [ ] Include session metadata (agent_id, service_id, tenant_id)
- [ ] Handle recording write failures gracefully (log error, continue session)
- [ ] Unit tests for asciicast format

**Dependencies**: M2.3, M3.1

### Task M3.3: Recording Storage
**Description**: Implement recording storage with retention policy.
**Files**:
- `apps/ssh-proxy/internal/recording/storage.go`
- `apps/ssh-proxy/internal/recording/storage_test.go`

**Acceptance Criteria**:
- [ ] Store recordings in configured directory
- [ ] Implement retention policy (delete recordings older than N days, default 30)
- [ ] Periodic cleanup of old recordings (daily)
- [ ] Unit tests for storage and retention

**Dependencies**: M3.2

### Task M3.4: SFTP Support
**Description**: Implement SFTP subsystem support.
**Files**:
- `apps/ssh-proxy/internal/sftp/sftp.go`
- `apps/ssh-proxy/internal/sftp/sftp_test.go`
- `apps/ssh-proxy/internal/sftp/handler.go`
- `apps/ssh-proxy/internal/sftp/handler_test.go`

**Acceptance Criteria**:
- [ ] Handle SFTP subsystem requests from agent
- [ ] Forward SFTP requests to backend
- [ ] Parse SFTP operations (read, write, list, delete, mkdir, rmdir, rename)
- [ ] Emit audit events for SFTP operations
- [ ] Unit tests for SFTP handling

**Dependencies**: M2.3, M3.1

## Milestone M4: Command Filtering
**Goal**: Implement command filtering to enforce least-privilege access.

### Task M4.1: Command Filter
**Description**: Implement command filtering with allowlist/denylist modes.
**Files**:
- `apps/ssh-proxy/internal/filter/filter.go`
- `apps/ssh-proxy/internal/filter/filter_test.go`

**Acceptance Criteria**:
- [ ] Support allowlist mode (only listed commands allowed)
- [ ] Support denylist mode (listed commands blocked)
- [ ] Support regex patterns for command matching
- [ ] Default mode: denylist (empty = all commands allowed)
- [ ] Unit tests for filtering logic

**Dependencies**: None

### Task M4.2: Command Parser
**Description**: Implement command parser to extract command name and arguments.
**Files**:
- `apps/ssh-proxy/internal/filter/parser.go`
- `apps/ssh-proxy/internal/filter/parser_test.go`

**Acceptance Criteria**:
- [ ] Parse command string into command name and arguments
- [ ] Handle shell metacharacters (pipes, redirects, etc.)
- [ ] Handle quoted arguments
- [ ] Unit tests for command parsing

**Dependencies**: M4.1

### Task M4.3: Command Filter Integration
**Description**: Integrate command filtering into SSH session.
**Files**:
- `apps/ssh-proxy/internal/session/session.go` (update)
- `apps/ssh-proxy/internal/session/session_test.go` (update)

**Acceptance Criteria**:
- [ ] Load command filter configuration per service
- [ ] Check commands against filter before forwarding to backend
- [ ] Block filtered commands with clear error message
- [ ] Emit audit event on command block
- [ ] Integration tests for command filtering

**Dependencies**: M2.6, M4.1, M4.2

### Task M4.4: SFTP Path Filtering
**Description**: Implement path-based filtering for SFTP operations.
**Files**:
- `apps/ssh-proxy/internal/sftp/handler.go` (update)
- `apps/ssh-proxy/internal/sftp/handler_test.go` (update)

**Acceptance Criteria**:
- [ ] Apply command filter to SFTP paths
- [ ] Block filtered SFTP operations with clear error message
- [ ] Emit audit event on SFTP operation block
- [ ] Integration tests for SFTP path filtering

**Dependencies**: M3.4, M4.3

## Milestone M5: Integration & Observability
**Goal**: Integrate with existing Mintkey infrastructure and add observability.

### Task M5.1: Prometheus Metrics
**Description**: Implement Prometheus metrics for monitoring.
**Files**:
- `apps/ssh-proxy/internal/metrics/metrics.go`
- `apps/ssh-proxy/internal/metrics/metrics_test.go`

**Acceptance Criteria**:
- [ ] Expose metrics on HTTP endpoint (default 8087)
- [ ] Track active sessions, session duration, bytes transferred
- [ ] Track authentication failures, command blocks, session timeouts
- [ ] Unit tests for metrics collection

**Dependencies**: M2.6

### Task M5.2: OTel Tracing
**Description**: Implement OpenTelemetry tracing for distributed tracing.
**Files**:
- `apps/ssh-proxy/internal/trace/trace.go`
- `apps/ssh-proxy/internal/trace/trace_test.go`

**Acceptance Criteria**:
- [ ] Create spans for authentication, Vault fetch, backend connection, session duration
- [ ] Add attributes: session_id, agent_id, service_id, tenant_id, auth_method
- [ ] No credentials in span attributes (per allowlist)
- [ ] Export traces to OTel collector
- [ ] Unit tests for trace creation

**Dependencies**: M2.6

### Task M5.3: Grafana Dashboard
**Description**: Create Grafana dashboard for SSH proxy monitoring.
**Files**:
- `grafana/dashboards/ssh-proxy.json`

**Acceptance Criteria**:
- [ ] Dashboard shows active sessions over time
- [ ] Dashboard shows session duration distribution
- [ ] Dashboard shows authentication failure rate
- [ ] Dashboard shows command block rate
- [ ] Dashboard shows bytes transferred
- [ ] Dashboard shows error rate by type

**Dependencies**: M5.1

### Task M5.4: Revocation Integration
**Description**: Integrate with revocation system to terminate sessions on agent revocation.
**Files**:
- `apps/ssh-proxy/internal/revocation/revocation.go`
- `apps/ssh-proxy/internal/revocation/revocation_test.go`

**Acceptance Criteria**:
- [ ] Subscribe to `mintkey:agent` change channel
- [ ] Terminate active sessions on agent revocation
- [ ] Emit audit event on revocation-triggered termination
- [ ] Graceful shutdown (send SIGHUP to backend)
- [ ] Integration tests for revocation handling

**Dependencies**: M2.6

### Task M5.5: Docker Compose Integration
**Description**: Add ssh-proxy to docker-compose.yml.
**Files**:
- `docker-compose.yml` (update)

**Acceptance Criteria**:
- [ ] ssh-proxy service defined with correct dependencies
- [ ] Environment variables configured
- [ ] Ports exposed (2222 for SSH, 8087 for metrics/health)
- [ ] Health check configured
- [ ] Service starts after admin-api is healthy

**Dependencies**: M1.1, M1.6

### Task M5.6: Service Identity
**Description**: Create service identity for ssh-proxy.
**Files**:
- `seed-job/seed.py` (update)

**Acceptance Criteria**:
- [ ] Create service identity `svc_ssh_proxy` in seed job
- [ ] Generate service identity token
- [ ] Store token in Kubernetes secret (or environment variable)
- [ ] ssh-proxy uses token to authenticate to Vault Adapter

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
- [ ] Test end-to-end session flow (agent → bastion → backend)
- [ ] Test SFTP operations
- [ ] Test command filtering
- [ ] Test session recording
- [ ] Test authentication methods (JWT and API key)
- [ ] Test rate limiting and session timeout
- [ ] All tests pass

**Dependencies**: M2, M3, M4

### Task M6.2: Acceptance Tests
**Description**: Write acceptance tests with full docker-compose stack.
**Files**:
- `tests/acceptance/test_ssh_proxy.py`

**Acceptance Criteria**:
- [ ] Test golden path: agent → bastion → backend
- [ ] Test security: no credentials in logs/audit
- [ ] Test performance: latency < 500ms, overhead < 5%
- [ ] Test revocation: sessions terminated on agent revocation
- [ ] All tests pass

**Dependencies**: M5.5, M6.1

### Task M6.3: Architecture Tests
**Description**: Write architecture tests to enforce security invariants.
**Files**:
- `tests/architecture/test_ssh_proxy_security.py`

**Acceptance Criteria**:
- [ ] No plaintext credentials in code
- [ ] All sessions emit audit events
- [ ] Key material zeroed on disconnect
- [ ] Command filtering enforced
- [ ] All tests pass

**Dependencies**: M6.1

### Task M6.4: Update ADR Index
**Description**: Update ADR index with ADR-0021.
**Files**:
- `docs/architecture/01-architecture/adr/README.md` (update)

**Acceptance Criteria**:
- [ ] ADR-0021 listed in index
- [ ] Status: Proposed
- [ ] Summary: SSH proxy support for agent remote execution

**Dependencies**: ADR-0021 created

### Task M6.5: Update AGENTS.md
**Description**: Update AGENTS.md with SSH proxy information.
**Files**:
- `AGENTS.md` (update)

**Acceptance Criteria**:
- [ ] SSH proxy mentioned in architecture overview
- [ ] Link to ADR-0021
- [ ] Instructions for running SSH proxy tests

**Dependencies**: M6.4

### Task M6.6: Create PR
**Description**: Create pull request with all changes.
**Files**:
- Pull request description

**Acceptance Criteria**:
- [ ] All tasks completed
- [ ] All tests pass (unit, integration, acceptance, architecture)
- [ ] All contract validators pass
- [ ] Comprehensive PR description
- [ ] Review requested from maintainers

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
