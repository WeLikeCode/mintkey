# SSH Proxy Requirements

## Architectural Prerequisites
- ADR-0021: SSH Proxy Support (Proposed)
- ADR-0004: Egress Proxy (Kong)
- ADR-0014.4: No plaintext credential cache
- ADR-0018: Classical API keys

## Glossary
- **SSH Bastion**: A proxy server that authenticates agents and bridges SSH connections to backend servers
- **Session-scoped key holding**: SSH private keys held in memory for the duration of a session (not cached across sessions)
- **Channel bridging**: Bidirectional I/O forwarding between agent and backend SSH channels
- **PTY**: Pseudo-terminal for interactive sessions
- **SFTP**: SSH File Transfer Protocol subsystem
- **asciicast v2**: Recording format for terminal sessions (used by asciinema)

## Requirements

### Req 1: SSH Bastion Server
**User Story**: As an operator, I want agents to execute commands on remote SSH servers without holding SSH credentials, so that credentials remain isolated in the Vault.

**Acceptance Criteria**:
1.1 SSH proxy listens on configurable port (default 2222)
1.2 Agent authenticates with JWT (SSH password) or API-key-derived public key
1.3 Proxy fetches SSH private key from Vault Adapter per-session
1.4 Proxy establishes outbound SSH connection to backend
1.5 Proxy bridges bidirectional I/O between agent and backend
1.6 SSH private key zeroed on session disconnect

**Error Codes**:
- `ssh.auth_failed`: Agent authentication failed (401)
- `ssh.vault_unavailable`: Vault Adapter unreachable (502)
- `ssh.backend_unreachable`: Backend SSH server unreachable (502)
- `ssh.credential_fetch_failed`: Failed to fetch SSH key from Vault (502)

### Req 2: Session Audit
**User Story**: As an operator, I want to audit all SSH sessions and commands, so that I have a complete trail of agent activity.

**Acceptance Criteria**:
2.1 Emit `ssh.session.started` on connection (agent_id, service_id, session_id, source_ip, auth_method)
2.2 Emit `ssh.session.exec` on command execution (session_id, command, exit_code)
2.3 Emit `ssh.session.sftp` on SFTP operations (session_id, operation, path)
2.4 Emit `ssh.session.ended` on disconnect (session_id, duration, bytes_sent, bytes_received)
2.5 All events flow through auditq.Queue
2.6 No plaintext credentials in audit payloads

**Error Codes**:
- `ssh.audit_emit_failed`: Failed to emit audit event (logged, non-fatal)

### Req 3: Session Recording
**User Story**: As an operator, I want to record SSH session I/O, so that I can replay sessions for debugging or compliance.

**Acceptance Criteria**:
3.1 Capture all terminal I/O in asciicast v2 format
3.2 Write recordings to configurable storage (local filesystem or object storage)
3.3 Implement retention policy (configurable days, default 30)
3.4 Recording captures I/O only, not authentication handshake
3.5 Recording file named: `{session_id}.cast`

**Error Codes**:
- `ssh.recording_write_failed`: Failed to write recording (logged, non-fatal)
- `ssh.recording_storage_full`: Storage quota exceeded (logged, session continues)

### Req 4: Command Filtering
**User Story**: As an operator, I want to restrict which commands agents can execute, so that I can enforce least-privilege access.

**Acceptance Criteria**:
4.1 Support allowlist mode (only listed commands allowed)
4.2 Support denylist mode (listed commands blocked)
4.3 Support regex patterns for command matching
4.4 Block disallowed commands and emit audit event
4.5 Per-service configuration via `command_filter` field
4.6 Default mode: denylist (empty = all commands allowed)

**Error Codes**:
- `ssh.command_blocked`: Command blocked by filter (403)

### Req 5: SFTP Support
**User Story**: As an operator, I want agents to transfer files via SFTP, so that they can read/write files on remote servers.

**Acceptance Criteria**:
5.1 Support SFTP subsystem requests
5.2 Parse SFTP protocol to extract operations (read, write, list, delete, mkdir, rmdir, rename)
5.3 Emit `ssh.session.sftp` audit events for all operations
5.4 Bridge SFTP I/O between agent and backend
5.5 Apply command filtering to SFTP operations (path-based)

**Error Codes**:
- `ssh.sftp_operation_blocked`: SFTP operation blocked by filter (403)

### Req 6: Rate Limiting
**User Story**: As an operator, I want to limit concurrent SSH sessions per agent, so that I can prevent resource exhaustion.

**Acceptance Criteria**:
6.1 Configurable max concurrent sessions per agent (default 5)
6.2 Reject new sessions when limit reached
6.3 Emit audit event on rejection
6.4 Clean up sessions on disconnect
6.5 Per-agent tracking (not per-tenant)

**Error Codes**:
- `ssh.session_limit_reached`: Max concurrent sessions reached (429)

### Req 7: Session Timeout
**User Story**: As an operator, I want SSH sessions to timeout, so that abandoned sessions don't consume resources.

**Acceptance Criteria**:
7.1 Session establishment bounded by JWT TTL (existing sessions not terminated on JWT expiry)
7.2 Configurable session timeout (default 3600 seconds)
7.3 Terminate session on timeout
7.4 Emit audit event on timeout
7.5 Graceful shutdown (send SIGHUP to backend)

**Error Codes**:
- `ssh.session_timeout`: Session exceeded timeout (408)

### Req 8: Agent Authentication
**User Story**: As an operator, I want flexible agent authentication methods, so that agents can connect using existing credentials.

**Acceptance Criteria**:
8.1 Support JWT-as-password: Agent presents Mintkey JWT as SSH password
8.2 Support API-key-derived public key: Derive Ed25519 keypair from agent API key
8.3 Validate JWT signature and claims (iss, aud, tnt, exp)
8.4 Validate API key via Vault Adapter
8.5 Reject invalid credentials with clear error message

**Error Codes**:
- `ssh.jwt_invalid`: JWT validation failed (401)
- `ssh.jwt_expired`: JWT expired (401)
- `ssh.api_key_invalid`: API key validation failed (401)

### Req 9: Host Key Verification
**User Story**: As an operator, I want to verify backend SSH server identity, so that I can prevent MITM attacks.

**Acceptance Criteria**:
9.1 Support Trust-on-First-Use (TOFU) mode (default)
9.2 Store host key fingerprints in database
9.3 Warn on host key change (configurable: fail or allow)
9.4 Support operator-provided known_hosts file (Phase 2)

**Error Codes**:
- `ssh.host_key_changed`: Backend host key changed (502, configurable)

### Req 10: Observability
**User Story**: As an operator, I want to monitor SSH proxy health and performance, so that I can detect issues early.

**Acceptance Criteria**:
10.1 Expose Prometheus metrics: active sessions, session duration, bytes transferred, auth failures
10.2 Expose `/metrics` endpoint
10.3 Emit OTel traces: authentication, Vault fetch, backend connection, session duration
10.4 Add span attributes per allowlist (no credentials)
10.5 Grafana dashboard with key metrics

**Error Codes**:
- N/A (observability failures are logged, non-fatal)

### Req 11: Revocation Integration
**User Story**: As an operator, I want SSH sessions to terminate when agents are revoked, so that I can enforce access control.

**Acceptance Criteria**:
11.1 Subscribe to `mintkey:agent` change channel
11.2 Terminate active sessions on agent revocation
11.3 Emit audit event on revocation-triggered termination
11.4 Graceful shutdown (send SIGHUP to backend)

**Error Codes**:
- `ssh.agent_revoked`: Agent revoked during session (401)

## Non-Functional Requirements

### Performance
- Session establishment latency: < 500ms (p95)
- I/O bridging overhead: < 5% (compared to direct SSH)
- Concurrent sessions: 1000+ per proxy instance

### Security
- No plaintext credentials in logs, spans, or audit payloads
- SSH private keys zeroed on disconnect
- Session recording captures I/O only, not authentication
- Command filtering enforced on all exec and SFTP operations

### Reliability
- Graceful degradation on Vault Adapter failure (reject new sessions, existing sessions continue)
- Automatic reconnection to change channel on disconnect
- Health check endpoint for load balancer integration

### Scalability
- Stateless design (no shared state between proxy instances)
- Horizontal scaling via load balancer
- Session affinity not required (each session self-contained)
