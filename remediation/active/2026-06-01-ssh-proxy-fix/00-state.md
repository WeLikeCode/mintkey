# Remediation: SSH proxy feature — fix the merged-but-broken implementation

**Session:** 2026-06-01-ssh-proxy-fix
**Branch:** `fix/ssh-proxy-integration` (off main)
**Pattern:** orchestrator (Sonnet implementer + fresh Opus reviewer per chunk, 3-strike hard-stop, flip-tests)
**Triggered by:** merge of `feature/ssh-proxy-support` at `ee4f7aa` / `e9f4d1a` by another agent.

## Issue intake

1. **Problem.** A new SSH bastion service was merged at `apps/ssh-proxy/`. Adversarial review surfaced (a) won't compile (`internal/vault` paths hallucinated; module not in `go.work`), (b) 7 session-channel handlers are `// TODO` stubs (PTY/shell/exec/subsystem/env/window-change/signal — `session.go:222-280`), (c) MITM-wide-open (`backend.go:97` host-key callback always returns nil), (d) API-key→SSH-private-key derivation backdoor (`auth.go:166` `ed25519.NewKeyFromSeed(sha256(api_key)[:32])`), (e) zero integration with admin-UI / admin-API / compose / vault-adapter identity.
2. **Symptom.** Cannot create an SSH credential through any path (UI lacks dropdown; admin-API silently downgrades `auth_scheme=ssh_private_key` → `UNSPECIFIED` because `_AUTH_SCHEME_MAP` is missing 11/12). Cannot run the service (not in compose, doesn't build). Even if forced to run, would MITM every session and a leaked agent token would auto-grant shell access platform-wide.
3. **Expected.** End-to-end workflow: operator stores SSH private key via admin UI → ssh-proxy serves bastion on port 2222 → client `ssh <agent>@bastion` authenticates with a Mintkey JWT → bastion fetches creds from vault → connects to upstream → records session → audits commands. Same isolation guarantees as the HTTP credential broker.
4. **Evidence.** Full adversarial review captured (20 sec findings + 11 integration gaps + 5 NEW finds): `remediation/active/2026-06-01-ssh-proxy-fix/01-adversarial-review.md` (to be saved).
5. **Scope (in).** All 15 MUST-FIX items from the adversarial review (compile, wire handlers, host-key TOFU, remove API-key→SSH derivation, channel-type denylists, admin-API + admin-UI + vault-adapter integration, compose stanza, recording integrity, session timeouts, rate limiting). Then a full end-to-end test against a local `linuxserver/openssh-server` container.
6. **Out of scope.** Recording viewer UI (just metadata + retrieval API). S3 storage backend. Filter improvements beyond regex-token (current implementation is best-effort by design). mTLS to vault (use existing service-identity-token model). Production deployment.
7. **Risk.** **CRITICAL** — every chunk touches security-sensitive code (private keys, MITM, key derivation, multi-tenant isolation). Every chunk requires a fresh Opus reviewer with flip-tests. Three-strike hard stop per chunk.
8. **Verification target.** End-to-end smoke: spin up `linuxserver/openssh-server` as the target, store an SSH private key via the admin UI dropdown, SSH through the bastion with a fresh Mintkey JWT, verify the upstream `whoami` output flows back AND a recording is written AND audit events are emitted AND the upstream key is never logged. Adversarial flips: revoke mid-session (kills active connection), wrong-tenant JWT (denied), agent-forwarding `ssh -A` (rejected), tamper recording (verification fails), upstream host-key change (denied on TOFU).
9. **Owner decisions needed** (carry over from intake; defaults locked unless re-asked):
   - SSH credentials stored as: raw PEM in `vault.credentials.enc_payload` + `target_address`/`ssh_user` as TOP-LEVEL columns on `vault.credentials` (NOT in envelope). Need a schema migration. **DEFAULT: yes, top-level cols (consistent with other auth-schemes' approach).**
   - API-key-to-SSH-pubkey: remove derivation; require agents to register an SSH public key explicitly. **DEFAULT: yes.**
   - Session ID: ULID per-session, NOT agent_id. **DEFAULT: yes.**
   - Recording integrity: SHA-256 over the .cast file, stored in `ssh.session.ended` audit event. **DEFAULT: yes.**

## Chunk plan

Sequential where files overlap; parallel where disjoint. Fresh Opus reviewer per chunk.

- **C1 — Compile fix (FOUNDATION).** Fix `apps/ssh-proxy/go.mod` replaces (`internal/X` → `packages/go/X`). Add `./apps/ssh-proxy` to root `go.work`. Bump `go` directive to 1.26.0 to match workspace. Create `apps/ssh-proxy/internal/vault/client.go` — borrow from `apps/proxy-plugin/internal/vault/client.go` shape, expose `Client`, `Client.GetCredential(ctx, tenant, service) (*Credential, error)`, constants `AuthSchemeSSHPrivateKey=11`, `AuthSchemeSSHCA=12`, struct fields `TargetAddress`, `SSHUser`. Stub `GetAgentByFingerprint`, `GetHostKeyFingerprint`, `StoreHostKeyFingerprint` (return `ErrNotImplemented` for now; C7 wires them). Goal: `cd apps/ssh-proxy && go build ./...` exits 0.

- **C2 — Wire session handlers (SHELL/EXEC/PTY).** Replace TODO stubs in `session.go:222-280`. Each handler must invoke `backend.Connect` → `bridge.NewBridge` → `recorder.Start` → optional `filter.Check` (exec only). Add audit emit on session start/end. Fix `ParseSessionContext` (`strings.SplitN(s, "|", 4)` not `Sscanf`). Use `ulid.New()` for session_id, not agent_id. Tests: table-driven `session_test.go` for parser; integration test for one PTY round-trip using `ssh.NewServerConn` + in-memory client.

- **C3 — Vault-adapter integration (admin-api, vault-adapter, schema).** Parallelizable with C5. Add `svcid_ssh_proxy` identity in `apps/vault-adapter/cmd/vault-adapter/main.go` with `vault.read` scope. Add Liquibase changeset `020-vault-ssh-cols.yaml` adding `target_address TEXT NOT NULL DEFAULT ''` and `ssh_user TEXT NOT NULL DEFAULT ''` to `vault.credentials`. Add `Set/Get` for those fields in `apps/vault-adapter/internal/store/postgres.go`. Extend proto `GetCredentialResponse` with `target_address`, `ssh_user`. Add admin-API Pydantic `SSHPrivateKeyPayload` (validators: PEM header check, target_address `host:port`, ssh_user non-empty). Add `_AUTH_SCHEME_MAP` entries 11/12. Endpoint dispatch in `apps/admin-api/src/admin_api/api/credentials.py`.

- **C4 — Admin-UI dropdown + form (UX).** Parallel with C5. Add `ssh_private_key` (and `ssh_ca` for Phase 2) entries to `apps/admin-ui/src/lib/auth-scheme.ts` `AUTH_SCHEMES`. SCHEME_FIELDS: `private_key_pem` (textarea, secret:true, required, validate PEM header), `target_address` (text, placeholder `host:port`, required), `ssh_user` (text, required). buildCredentialPayload branch: JSON-stringify `{scheme, private_key_pem, target_address, ssh_user}` into `value`. Add vitest for the 3 cases.

- **C5 — Compose stanza + secrets + persistent volumes.** Parallel with C3+C4. Add `ssh-proxy:` service in `infra/compose/docker-compose.yml`. Ports 2222 + 8087. Env (`VAULT_ADAPTER_ADDR`, `BROKER_ADDR`, `MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID`, `MINTKEY_VAULT_SSH_PROXY_TOKEN`, `SSH_PROXY_HOST_KEY_PATH`). Volumes: persistent `ssh_proxy_hostkey` (host key) + `ssh_proxy_recordings`. depends_on vault-adapter+broker+postgres. Token via bootstrap-secrets pattern. Wire the new env vars in `.env.example`.

- **C6 — Security hardening (host-key TOFU + channel denylist + remove key derivation + integrity).** Wire `TOFUCallback(strict=true)` into `backend.Connect` (replace nil callback). Disable agent forwarding, X11, TCP `direct-tcpip`/`forwarded-tcpip`, `direct-streamlocal` — reject explicitly + audit `ssh.channel.denied`. Remove `DerivePublicKeyFromAPIKey` + change `AuthenticatePublicKey` to look up explicit `agents.ssh_pubkey` column. Migration adds the column. Persistent proxy host key (load from path, generate-if-missing toggle defaults `false`). Recording SHA-256 on close + audit emit. SessionTimeout + SessionIdleTimeout enforced via manager timers. Rate-limit on Accept + `MaxAuthTries=2`. Add `BannerCallback` + `ServerVersion`.

- **C7 — Vault host-key store + agent SSH-pubkey field.** Liquibase changeset `021-ssh-hostkeys.yaml`: `vault.ssh_host_keys (tenant_id UUID, service_id UUID, fingerprint TEXT, first_seen TIMESTAMPTZ, last_seen TIMESTAMPTZ, PRIMARY KEY(tenant_id, service_id, fingerprint))` with tenant-isolation RLS. Add `agents.ssh_pubkey TEXT` column. Wire `vault.Client.{Get,Store}HostKeyFingerprint` (gRPC calls on vault-adapter) + `vault.Client.GetAgentByFingerprint` lookups `agents.ssh_pubkey`. Admin-UI agent-detail page: add field for SSH public key (read-only display + rotate action).

- **C8 — End-to-end test.** Bring up `linuxserver/openssh-server` test target in the `mintkey_mintkey` network. Store SSH private key via admin UI (using C4 form). Issue Mintkey JWT (broker request_token). `ssh -p 2222 <agent_id>@localhost 'whoami; uname -a'` with JWT in password slot. Verify: connection succeeds, output flows, recording is in `vault.ssh_recordings/<session_id>.cast`, audit events `ssh.session.{started,exec,ended}` present, NO PEM material in any log. Adversarial flips: revoke (kill mid-session), wrong tenant (deny), `ssh -A` (reject), SFTP `get /etc/shadow` (filter denies), tamper recording (verify fails), upstream host-key change (deny on TOFU mismatch), DoS (rate-limit holds healthz green).

- **C9 — Final adversarial review + docs + ADR.** Fresh Opus full-DoD reviewer goes through the 20-item original review and confirms each is closed (or accepted-with-reason). ADR-0022 documents the design + threat model + recording retention policy. `docs/HOW-TO.md` section for SSH bastion onboarding.

## Dependency graph

```
C1 (compile) ──► C2 (handlers) ──► C6 (security hardening) ──┐
                                                              │
C3 (admin-api+vault) ──► C7 (hostkey+pubkey storage) ────────┤
                                                              ├─► C8 (e2e test) ──► C9 (final review + docs)
C4 (admin-ui) ────────────────────────────────────────────────┤
                                                              │
C5 (compose) ─────────────────────────────────────────────────┘
```

Parallel waves:
- **R1**: C1 alone (foundation, blocks all).
- **R2**: C2 + C3 + C4 + C5 in parallel (all disjoint after C1 ships).
- **R3**: C6 + C7 in parallel (C6 needs C2; C7 needs C3).
- **R4**: C8 (needs R1+R2+R3).
- **R5**: C9.

## Hard rules (carried into every implementer brief)

- **No `Co-Authored-By: Claude`** trailer (CLAUDE.md).
- **Read-only on `apps/ssh-proxy/cmd/ssh-proxy/main.go` unless explicitly in scope** — preserve the existing entry-point contract.
- **No mocks of the vault client in unit tests** — use real vault-adapter via testcontainers OR live local stack.
- **Every chunk must end with `go build ./...` + `go vet ./...` + `go test ./... -race -short -count=1` exit 0**.
- **No `InsecureIgnoreHostKey()` anywhere except in clearly-labeled test code**.
- **Private key bytes**: pass as `[]byte`, not `string`, where possible; zero on session close. Acknowledge that Go GC can't guarantee full erasure of `ssh.Signer` internals — document that limit.
- **Use the existing service-identity-token pattern**: ssh-proxy → vault-adapter via gRPC with `x-mintkey-service-identity` + `x-mintkey-service-token` metadata.

## Round history

- **R0 (2026-06-01 ~00:30)**: adversarial review by fresh Opus reviewer; 4 most damning claims trust-but-verified by direct file inspection (compile fail, TODO stubs, key derivation, host-key MITM). State file written.
- **R1 (in progress)**: dispatching C1 (compile fix).
- **R2–R5**: all 9 chunks (C1–C9) completed across subsequent sessions.

## Open questions

(none — owner directive locked: "I'll fix it now via the orchestrator pattern")

## Outcome — CLOSED 2026-06-01

All 9 chunks completed. Key commits on main: C1 build fix (`41a243e`), C2 handlers, C3 admin-api+vault, C4 admin-ui (`8b9a113`), C5 compose (`d00d8d2`), C6 security hardening — TOFU, channel denylist, session timeouts, rate limiting (`7637564`), C7 hostkey+pubkey storage, C8 e2e test (`d9b0746`), C9 final review + ADR-0022 + HOW-TO SSH bastion section (`f209810`). CI wiring: host key auto-generation (`4fb9224`). SSH proxy feature is fully functional on main.
