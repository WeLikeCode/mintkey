# ADR-0021: SSH Proxy Support for Agent Remote Execution

## Status
Proposed — 2026-05-31

## Context
Agents need to execute commands on remote SSH servers without holding SSH credentials. 
The current egress proxy (ADR-0004) is HTTP-only and cannot proxy SSH traffic. SSH is 
a stateful, binary protocol requiring a different approach than HTTP reverse proxying.

Quality attributes affected:
- S-SEC-1: Agent never holds usable backend credential
- S-AUD-1: Every credential use is logged
- S-MOD-1: New auth scheme touches ≤3 files in proxy

## Decision

### D1: SSH Bastion Architecture
Deploy a **separate Go binary** (`apps/ssh-proxy/`) that implements an SSH bastion server:
- Listens on dedicated port (default 2222)
- Authenticates agents via Mintkey JWT (SSH password) or API-key-derived public key
- Fetches backend SSH private key from Vault Adapter per-session
- Establishes outbound SSH connection to backend
- Bridges bidirectional I/O between agent and backend channels
- Emits audit events for session lifecycle and commands

### D2: New Auth Schemes
Add two new auth schemes to support SSH:
- `AUTH_SCHEME_SSH_PRIVATE_KEY = 9` — Vault stores SSH private key (PEM/OpenSSH format)
- `AUTH_SCHEME_SSH_CA = 10` — Vault stores SSH CA signing key (for certificate mode, Phase 2)

### D3: Agent Authentication Methods
Support two authentication methods to the SSH bastion:
1. **JWT-as-password**: Agent presents Mintkey JWT as SSH password
2. **API-key-derived public key**: Derive SSH keypair from agent API key (Ed25519)

### D4: Session-Scoped Key Holding
SSH private keys are held in memory for the session duration (not per-request). This is 
an acceptable relaxation of ADR-0014.4's "no plaintext cache" rule — a session is not a 
cache. Keys are zeroed on session disconnect.

### D5: Full Feature Set (Phase 1)
- PTY support for interactive sessions
- SFTP subsystem support with protocol parsing
- Session recording (asciicast v2 format)
- Command filtering (allowlist/denylist per service)
- Session lifecycle audit (`ssh.session.started`, `ssh.session.ended`)
- Command-level audit (`ssh.session.exec`, `ssh.session.sftp`)
- Rate limiting (concurrent sessions per agent)
- Session timeout (bounded by JWT TTL)

### D6: Kong Bypass
Kong cannot proxy SSH. The SSH proxy listens on its own port and reads service 
configuration from Postgres via the Vault Adapter and admin API. Kong-syncer does not 
manage SSH routes.

## Consequences

### Positive
- Agents can execute remote commands without holding SSH credentials
- Full session audit trail (lifecycle + commands + I/O recording)
- Command-level access control (allowlist/denylist)
- Consistent with existing proxy architecture (JWT verify → Vault fetch → inject → audit)
- Supports any SSH backend the operator registers

### Costs
- ~2500 lines of new Go code
- New binary to deploy and operate
- Additional port to expose (2222)
- SFTP protocol parsing adds complexity

### Risks
- SSH session is long-lived; key held in memory longer than HTTP request
- SFTP parsing may miss edge cases (mitigate with thorough testing)
- Session recording storage growth (mitigate with retention policy)

## Trade-offs

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Memory dump exposes SSH key | Medium | Zero key on disconnect; same pattern as ADR-0014.4 |
| SFTP bypass of command filter | Low | Parse SFTP protocol; log all operations |
| Session recording storage | Low | Configurable retention; offload to object storage |
| Agent extracts key via SSH protocol | Low | Agent never sees outbound handshake; bastion bridges channels |

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| SSH port forwarding | Agent holds backend key (violates S-SEC-1) |
| SSH ProxyJump | Transparent tunnel; no credential injection |
| SSH certificates only | Agent briefly holds usable cert; no session audit |
| HashiCorp Boundary | Heavy dependency; replaces rather than extends Mintkey |
| Teleport | Very large; own identity model; not pluggable |
| Embed in proxy-plugin | SSH and HTTP have different lifecycles |

## Amends
- ADR-0004: SSH proxy is a sibling data-plane component, not an extension of Kong
- ADR-0014.4: Session-scoped key holding is acceptable (not a cache)

## Implications
- Update vault.proto with new auth schemes
- Update OpenAPI, MCP tools, audit/change event schemas
- New Kiro spec: `.kiro/specs/ssh-proxy/`
- New docker-compose service: `ssh-proxy`
- New Grafana dashboard: SSH session metrics

## Open Follow-ups
- SSH certificate mode (Phase 2) for operator-controlled backends
- Session recording retention policy
- SSH host key verification (TOFU vs. known_hosts)
- SSH agent forwarding support (if needed)

## Related
- ADR-0004: Egress proxy (Kong)
- ADR-0014.4: No plaintext credential cache
- ADR-0018: Classical API keys (similar auth pattern)
