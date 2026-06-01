# ADR-0022: SSH Bastion for Agent Remote Execution

**Supersedes:** the content previously filed as `0021-ssh-proxy-support.md` (which was mis-numbered; `0021` is taken by the Vault Adapter Postgres backend decision).

## Status

Accepted — 2026-06-01

---

## Context

Agents need to execute commands on remote SSH servers without holding SSH credentials. The current egress proxy (ADR-0004) is HTTP-only (Kong + go-pdk plugin) and cannot proxy the SSH wire protocol — SSH is a stateful, binary, long-lived TCP protocol that Kong does not speak.

Two design goals conflict:

1. **S-SEC-1** — the agent must never hold a usable backend credential.
2. **S-AUD-1** — every credential use must be logged with full session context.

An agent that SSHs directly to a backend (even via ProxyJump or a credential fetched from MCP) violates S-SEC-1. A solution that does not proxy the full session cannot satisfy S-AUD-1 for interactive or long-running exec workloads.

Quality attributes affected:

- **S-SEC-1** — Agent never holds usable backend credential
- **S-AUD-1** — Every credential use is logged
- **S-MOD-1** — New auth scheme touches ≤ 3 files in proxy

---

## Decision

### D1: Standalone SSH bastion binary (`apps/ssh-proxy/`)

Deploy a separate Go binary that implements a full `crypto/ssh` server:

- Listens on `:2222` (one port, all services — see D3).
- Authenticates agents via Mintkey JWT presented as the SSH password (primary path).
- Optionally authenticates via API-key-derived Ed25519 public key (secondary path; vault wiring deferred to C7).
- Fetches the backend SSH private key or password from vault-adapter per session (gRPC `GetCredential`).
- Establishes a second, independent SSH connection to the upstream.
- Bridges bidirectional I/O between the agent's channel and the upstream session.
- Records every session as asciicast v2 (SHA-256 integrity in audit event).
- Emits structured audit events for the full session lifecycle.

**Architecture reference:** [docs/architecture/01-architecture/ssh-bastion.md](../ssh-bastion.md)

### D2: New vault auth schemes

Two new auth schemes added to `vault.proto` and `vault.credentials.auth_scheme`:

- `AUTH_SCHEME_SSH_PRIVATE_KEY = 9` — vault stores PEM/OpenSSH private key.
- `AUTH_SCHEME_SSH_CA = 10` — vault stores SSH CA signing key (Phase 2 only; not implemented in Phase 1).

The credential row also carries `target_address` (host:port) and `ssh_user` — the bastion dials these directly without any additional lookup.

### D3: Single-port multiplexing via JWT `service_id` claim

The bastion binds exactly one TCP listener (`:2222`). Every incoming connection is authenticated with its own JWT. The JWT's `service_id` claim is the routing key: the bastion calls `GetCredential(tenant_id, service_id)` to find the upstream address and credential for that specific session.

This means N services share one port. The alternative — binding a dedicated port per registered SSH service — does not scale (requires N firewall rules, N DNS entries, N persistent sockets; see [ssh-bastion.md § 3](../ssh-bastion.md#3-single-port-multiplexing--explained)).

### D4: Session-scoped credential holding

SSH private keys are held in process memory for the session duration. This is an explicit relaxation of ADR-0014.4's "no plaintext cache" rule: a session is not a cache. The key is zeroed (`range slice; slice[i] = 0`) on session disconnect via `backend.Close`.

### D5: Phase 1 feature set (shipped as of 2026-06-01)

- PTY support for interactive sessions (`pty-req`, `window-change`).
- `exec` request support with optional command filter (allowlist/denylist per service).
- `shell` request support (spawns a shell on the upstream).
- SFTP subsystem support (protocol-parsed; operations audited as `ssh.session.sftp`).
- Session recording (asciicast v2) with SHA-256 integrity.
- Session lifecycle audit (`ssh.session.started`, `ssh.session.ended`).
- Command-level audit (`ssh.session.exec`, `ssh.session.sftp`).
- Rate limiting at the Accept loop: token-bucket 10/s burst 20; concurrent-handshake semaphore 200.
- Session timeouts: max-duration and idle (context cancellation).
- Live revocation: `LISTEN mintkey:agent` on Postgres; `agent.revoked` events terminate in-flight sessions immediately.
- Upstream host-key TOFU pinning per `(tenant_id, service_id)` in `vault.ssh_host_keys`.

### D6: Kong bypass

Kong cannot proxy SSH. The bastion is a sibling data-plane component that reads service configuration via the vault-adapter. Kong-syncer does not manage SSH routes. Amends ADR-0004.

---

## Consequences

### Positive

- Agents can execute remote commands without ever holding the SSH credential.
- Full session audit trail: lifecycle + per-command + I/O recording.
- Command-level access control (allowlist/denylist).
- No custom client required — vanilla `ssh` + JWT-as-password works.
- Consistent with the existing credential-indirection invariant (`agent → JWT → bastion → vault → upstream`).
- Any SSH backend the operator registers is supported; no per-service deployment change.

### Costs

- ~2500 lines of new Go code; new binary to deploy and operate.
- Additional exposed port (`:2222`); must be firewalled appropriately in production.
- SFTP protocol parsing adds implementation complexity.
- A downed bastion takes out every SSH-type service — it is a single point of failure for the SSH data plane path.

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Memory dump exposes SSH key during session | Medium | Key zeroed on disconnect; same pattern as ADR-0014.4 |
| JWT lifetime limits long sessions | Medium | Re-authenticate before expiry; `request_token` is cheap |
| SFTP bypass of command filter | Low | SFTP protocol parsed; all operations logged |
| Session recording storage growth | Low | Configurable retention policy; offload to object storage |
| Agent observes upstream host from bastion IP | Low | By design; agents are not meant to know the upstream topology |

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Agent-side credential delivery (SSH keys from MCP) | Agent holds the secret — violates S-SEC-1. |
| SSH ProxyJump | Transparent tunnel; no credential injection; agent sees backend. |
| HTTP-tunneled SSH via Kong | Kong does not speak SSH; the protocol is incompatible. |
| SSH certificate mode (agent holds cert) | Agent briefly holds a usable certificate; no full session audit. |
| HashiCorp Boundary | Heavy dependency; replaces rather than extends Mintkey; own identity model. |
| Teleport | Very large (~80 MB binary); own identity model; not pluggable into Mintkey. |
| One port per upstream service | Does not scale (N firewall rules, N DNS, N sockets); breaks MCP service-discovery model. |
| Embed in proxy-plugin (Kong go-pdk) | SSH and HTTP have fundamentally different session lifecycles; Kong's plugin API is per-request HTTP. |

---

## Amends

- **ADR-0004**: SSH proxy is a sibling data-plane component, not an extension of Kong. Kong-syncer does not manage SSH routes.
- **ADR-0014.4**: Session-scoped key holding is an accepted exception to the no-plaintext-cache rule.

---

## Related

- [ADR-0021](0021-vault-storage-backend-postgres.md) — Vault Adapter Postgres backend (the `vault.credentials` table the bastion reads from).
- [ADR-0004](0004-egress-proxy-kong.md) — HTTP egress proxy (sibling to the bastion).
- [ADR-0006](0006-token-format-and-binding.md) — JWS Ed25519 JWT format used by the bastion for agent authentication.
- [ADR-0008](0008-multi-tenancy-row-level-with-db-tier.md) — tenant context (`app.current_tenant` GUC) used by vault-adapter for RLS.
- [ADR-0018](0018-classical-service-api-keys.md) — classical API keys (similar auth indirection pattern).
- [docs/architecture/01-architecture/ssh-bastion.md](../ssh-bastion.md) — full architecture narrative and data-flow diagram.
- [docs/HOW-TO.md § 5](../../../HOW-TO.md#5-ssh-bastion-onboarding) — operator runbook.

---

## Corrigendum — superseded in part by ADR-0023

**Date:** 2026-06-01. **Authority:** [ADR-0023](0023-ssh-upstream-base-url-canonical.md).

§D2 states: "The credential row also carries `target_address` (host:port) and `ssh_user` — the
bastion dials these directly without any additional lookup."

This is **no longer accurate** for `target_address`. As of ADR-0023:

- `services.base_url` is the canonical upstream address for SSH routing. vault-adapter LEFT JOINs
  `public.services` in `GetCredential` and returns `base_url`; ssh-proxy reads `base_url` for all
  SSH auth schemes (`ssh_password`, `ssh_private_key`, `ssh_ca`).
- `vault.credentials.target_address` is **deprecated**. It is retained as a transition safety net
  (ssh-proxy falls back to it when `base_url` is absent), but operators should not set it
  explicitly — it is inherited from `services.base_url` via the C-6 cascade.
- `ssh_user` remains per-credential (auth material, not routing) — §D2 is correct for that field.

See [ADR-0023](0023-ssh-upstream-base-url-canonical.md) for the full decision, consequences, and
follow-up items (including planned removal of `target_address`).
