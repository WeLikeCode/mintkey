# SSH Proxy Design

## Component Diagram

```mermaid
graph TB
    Agent[Agent] -->|SSH + JWT/API Key| Bastion[SSH Bastion<br/>apps/ssh-proxy]
    Bastion -->|gRPC| Vault[Vault Adapter]
    Bastion -->|SSH + Private Key| Backend[Backend SSH Server]
    Bastion -->|Audit Events| AuditQ[auditq.Queue]
    Bastion -->|Metrics| Prometheus
    Bastion -->|Traces| OTel[OTel Collector]
    Bastion -->|Change Channel| Postgres[(Postgres)]
    
    Vault -->|SSH Private Key| Bastion
    AuditQ --> Postgres
```

## Sequence Diagram: SSH Session Flow

```mermaid
sequenceDiagram
    participant A as Agent
    participant B as SSH Bastion
    participant V as Vault Adapter
    participant S as Backend SSH
    
    A->>B: SSH connect (JWT as password)
    B->>B: Validate JWT
    B->>V: GetCredential(service_id, agent_id)
    V-->>B: SSH private key (plaintext)
    B->>S: SSH connect (private key)
    S-->>B: SSH session established
    B->>B: Emit ssh.session.started
    B->>B: Bridge channels (A ↔ S)
    
    loop Session I/O
        A->>B: Command/input
        B->>B: Check command filter
        B->>S: Forward
        S-->>B: Output
        B-->>A: Forward
        B->>B: Emit ssh.session.exec (if exec request)
    end
    
    A->>B: Disconnect
    B->>S: Close connection
    B->>B: Zero SSH private key
    B->>B: Emit ssh.session.ended
```

## Sequence Diagram: SFTP Session Flow

```mermaid
sequenceDiagram
    participant A as Agent
    participant B as SSH Bastion
    participant S as Backend SSH
    
    A->>B: SSH connect + SFTP subsystem request
    B->>B: Validate agent
    B->>B: Fetch SSH key from Vault
    B->>S: SSH connect + SFTP subsystem
    S-->>B: SFTP session established
    B-->>A: SFTP session established
    B->>B: Emit ssh.session.started
    
    loop SFTP Operations
        A->>B: SFTP request (read/write/list)
        B->>B: Parse SFTP operation
        B->>B: Check path filter
        B->>S: Forward SFTP request
        S-->>B: SFTP response
        B-->>A: Forward SFTP response
        B->>B: Emit ssh.session.sftp
    end
    
    A->>B: SFTP close
    B->>S: Close SFTP session
    B->>B: Emit ssh.session.ended
```

## Data Structures

### Session Context
```go
type SessionContext struct {
    SessionID    string
    TenantID     string
    AgentID      string
    ServiceID    string
    SourceIP     string
    AuthMethod   string  // "jwt" or "api_key"
    StartedAt    time.Time
    BackendConn  *ssh.Client
    BackendKey   []byte  // SSH private key (zeroed on disconnect)
    Recording    *RecordingWriter
    Filter       *CommandFilter
    Metrics      *SessionMetrics
}
```

### SSH Credential (from Vault Adapter)
```go
type SSHCredential struct {
    PrivateKey   []byte  // PEM or OpenSSH format
    User         string  // SSH username
    Port         int     // SSH port (default 22)
    Host         string  // Backend host
}
```

### Command Filter
```go
type CommandFilter struct {
    Mode      string   // "allowlist" or "denylist"
    Patterns  []string // Regex patterns
}

func (f *CommandFilter) IsAllowed(command string) bool {
    // Match command against patterns
    // Return true if allowed, false if blocked
}
```

### Recording Writer
```go
type RecordingWriter struct {
    File       *os.File
    SessionID  string
    StartedAt  time.Time
    Width      int
    Height     int
}

func (w *RecordingWriter) WriteOutput(data []byte) error {
    // Write asciicast v2 format
}

func (w *RecordingWriter) Close() error {
    // Finalize recording file
}
```

## Module Structure

```
apps/ssh-proxy/
├── cmd/
│   └── ssh-proxy/
│       └── main.go              # Entry point
├── internal/
│   ├── auth/
│   │   ├── auth.go              # Authentication dispatcher
│   │   ├── jwt.go               # JWT-as-password auth
│   │   └── apikey.go            # API-key-derived public key auth
│   ├── backend/
│   │   ├── backend.go           # Backend SSH connection
│   │   └── hostkey.go           # Host key verification (TOFU)
│   ├── bridge/
│   │   ├── bridge.go            # Channel bridging
│   │   ├── pty.go               # PTY handling
│   │   └── signal.go            # Signal forwarding
│   ├── session/
│   │   ├── session.go           # Session management
│   │   └── limiter.go           # Rate limiting
│   ├── audit/
│   │   └── audit.go             # Audit emission
│   ├── recording/
│   │   ├── recording.go         # Recording manager
│   │   ├── asciicast.go         # asciicast v2 format
│   │   └── storage.go           # Storage backend
│   ├── sftp/
│   │   ├── sftp.go              # SFTP subsystem handler
│   │   └── handler.go           # SFTP operation parser
│   ├── filter/
│   │   ├── filter.go            # Command filter
│   │   └── parser.go            # Command parser
│   ├── metrics/
│   │   └── metrics.go           # Prometheus metrics
│   ├── trace/
│   │   └── trace.go             # OTel tracing
│   ├── revocation/
│   │   └── revocation.go        # Revocation handler
│   ├── config/
│   │   └── config.go            # Configuration
│   └── server/
│       └── server.go            # SSH server
├── Dockerfile
└── go.mod
```

## Error Handling

| Error | Code | Action |
|-------|------|--------|
| JWT validation failed | 401 | Reject connection, emit audit |
| API key validation failed | 401 | Reject connection, emit audit |
| Vault fetch failed | 502 | Reject connection, emit audit |
| Backend connection failed | 502 | Reject connection, emit audit |
| Command filtered | 403 | Block command, emit audit, continue session |
| SFTP operation filtered | 403 | Block operation, emit audit, continue session |
| Session limit reached | 429 | Reject connection, emit audit |
| Session timeout | 408 | Terminate session, emit audit |
| Agent revoked | 401 | Terminate session, emit audit |
| Host key changed | 502 | Reject connection (configurable), emit audit |
| Recording write failed | N/A | Log error, continue session (non-fatal) |
| Audit emit failed | N/A | Log error, continue session (non-fatal) |

## Security Considerations

### Credential Isolation
- SSH private key held in session scope only (not cached)
- Key zeroed on session disconnect (`defer clear(key)`)
- Agent never sees outbound SSH handshake
- Session recording captures I/O only, not authentication

### Session Isolation
- Each session gets its own goroutine, Vault fetch, and backend connection
- No shared state between sessions
- Per-session context with `tenant_id`, `agent_id`, `service_id`

### Audit Trail
- Session lifecycle: `ssh.session.started`, `ssh.session.ended`
- Command-level: `ssh.session.exec`, `ssh.session.sftp`
- All events flow through `auditq.Queue` for consistency
- Session recording stored separately (configurable retention)

### Access Control
- JWT TTL bounds session establishment window (existing sessions not terminated)
- Rate limiting: concurrent sessions per agent (configurable)
- Command filtering: allowlist/denylist per service
- IP-based restrictions: SSRF guard blocks private ranges

### Host Key Verification
- Phase 1: Trust-on-First-Use (TOFU) mode
- Store host key fingerprints in database
- Warn on host key change (configurable: fail or allow)
- Phase 2: Operator-provided known_hosts file

## Performance Considerations

### Session Establishment
- JWT validation: < 10ms
- Vault fetch: < 100ms (gRPC)
- Backend SSH connect: < 300ms (network-dependent)
- Total: < 500ms (p95)

### I/O Bridging
- Direct channel bridging (no buffering)
- Recording writes async (non-blocking)
- Overhead: < 5% (compared to direct SSH)

### Concurrency
- Stateless design (no shared state)
- Horizontal scaling via load balancer
- Target: 1000+ concurrent sessions per instance

## Deployment

### Docker Compose
```yaml
ssh-proxy:
  build:
    context: .
    dockerfile: apps/ssh-proxy/Dockerfile
  environment:
    MINTKEY_ENV: dev
    SSH_PROXY_PORT: "2222"
    VAULT_GRPC_ADDR: vault-adapter:8084
    BROKER_ADDR: broker:8083
    DATABASE_URL: postgres://mintkey_app:mintkey_app_password@postgres:5432/mintkey
  ports:
    - "2222:2222"
  networks:
    - mintkey
  depends_on:
    admin-api:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "/ssh-proxy", "-health"]
    interval: 10s
    timeout: 5s
    retries: 10
    start_period: 15s
```

### Environment Variables
```bash
SSH_PROXY_PORT=2222
SSH_PROXY_HOST_KEY_PATH=/run/secrets/ssh_host_key
VAULT_GRPC_ADDR=vault-adapter:8084
BROKER_ADDR=broker:8083
DATABASE_URL=postgres://mintkey_app:...@postgres:5432/mintkey
SESSION_TIMEOUT=3600  # seconds
MAX_CONCURRENT_SESSIONS_PER_AGENT=5
RECORDING_STORAGE_PATH=/var/lib/mintkey/ssh-recordings
RECORDING_RETENTION_DAYS=30
COMMAND_FILTER_MODE=denylist  # or allowlist
HOST_KEY_VERIFY_MODE=tofu  # or known_hosts (Phase 2)
```

### Secrets
- SSH host key: generated on first run, stored in `ssh_host_key` secret
- Service identity token: `svc_ssh_proxy` (same pattern as other services)

## Monitoring

### Prometheus Metrics
- `ssh_proxy_active_sessions`: Gauge of active sessions
- `ssh_proxy_session_duration_seconds`: Histogram of session durations
- `ssh_proxy_bytes_sent_total`: Counter of bytes sent to agents
- `ssh_proxy_bytes_received_total`: Counter of bytes received from agents
- `ssh_proxy_auth_failures_total`: Counter of authentication failures
- `ssh_proxy_command_blocks_total`: Counter of blocked commands
- `ssh_proxy_session_timeouts_total`: Counter of session timeouts

### Grafana Dashboard
- Active sessions over time
- Session duration distribution
- Authentication failure rate
- Command block rate
- Bytes transferred
- Error rate by type

### OTel Tracing
- Spans: authentication, Vault fetch, backend connection, session duration
- Attributes: session_id, agent_id, service_id, tenant_id, auth_method
- No credentials in span attributes (per allowlist)

## Testing Strategy

### Unit Tests
- All internal packages
- Mock Vault Adapter, backend SSH, audit queue
- Coverage target: > 80%

### Integration Tests
- Real Postgres, Vault Adapter, mock SSH server
- End-to-end session flow
- SFTP operations
- Command filtering
- Session recording

### Acceptance Tests
- Full docker-compose stack
- Real SSH server (OpenSSH in container)
- Golden path: agent → bastion → backend
- Security: no credentials in logs/audit
- Performance: latency, throughput

### Architecture Tests
- No plaintext credentials in code
- All sessions emit audit events
- Key material zeroed on disconnect
- Command filtering enforced

## Future Enhancements (Phase 2)

### SSH Certificate Mode
- `AUTH_SCHEME_SSH_CA = 10`
- Mintkey CA signs short-lived SSH certificates
- Agent connects directly to backend (no bastion in data path)
- Use case: operator-controlled backends

### Session Recording Enhancements
- Object storage backend (S3, GCS)
- Session replay UI
- Search and filtering

### Advanced Command Filtering
- Command argument parsing
- Context-aware filtering (time of day, source IP)
- Machine learning-based anomaly detection

### SSH Agent Forwarding
- Forward SSH agent socket to backend
- Use case: backend needs to authenticate to other SSH servers

### Known Hosts File
- Operator-provided known_hosts file
- Strict host key verification
- Use case: high-security environments
