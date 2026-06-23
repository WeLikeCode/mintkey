# Design — Vault Adapter backend: HashiCorp Vault (KV v2)

> Implementation design for the `hashicorp` Vault Adapter backend. Self-contained:
> every external constraint is quoted inline. Target ADR: **ADR-0025**.

---

## 1. Inline ADR stub (copy to `docs/architecture/01-architecture/adr/0025-vault-storage-backend-hashicorp.md`)

```markdown
# ADR-0025: Vault Adapter storage backend — HashiCorp Vault (KV v2), opt-in

## Status
Proposed — <DATE>. Implements the v2 backend deferred by ADR-0021 §Alternatives and
named as the lead candidate in open-question OQ-003.

Amends nothing. Adds a third value to the ADR-0021 backend selector
(`MINTKEY_VAULT_BACKEND=hashicorp`). Postgres remains the default; SQLite remains the
opt-in offline fallback. The KEK/DEK envelope scheme (ADR-0003 §Decision 2) is unchanged.

## Context
ADR-0021 chose Postgres as the default Vault Adapter store and recorded HashiCorp Vault as
"still planned as v2; deferred." OQ-003 (Vault Adapter horizontal scaling) lists
"bring HashiCorp Vault forward as v2" first. Operators who already run HashiCorp Vault want
the most sensitive Mintkey data to live in their existing secrets platform.

## Decision
Add a `*HashiCorpStore` implementing the existing `store.Backend` interface. HashiCorp Vault
KV v2 is used as an OPAQUE storage substrate for the already-encrypted envelope blobs
(`wrapped_dek`, `enc_payload`) plus metadata — exactly the role Postgres/SQLite play today.
Mintkey's KEK never leaves the adapter; HashiCorp's Transit engine is NOT used. Auth is via
AppRole with background token renewal. Tenant isolation is enforced application-side by the
KV path prefix (`<mount>/data/mintkey/<tenant_id>/<service_id>/<key_version>`); there is no
RLS equivalent, which is acceptable because the adapter is the sole writer and always scopes
reads by `(tenant_id, service_id)`.

## Consequences
- Positive: operators on HashiCorp Vault get a native store; the envelope scheme is reused
  verbatim, so a credential blob is byte-identical across Postgres and HashiCorp.
- Costs: a new compose service in dev/CI; an AppRole must be provisioned; HashiCorp Vault is
  now a runtime dependency when selected. SSH RPCs (`SSHVaultAdapter`) remain Postgres-only.
- Risks: KV v2 list semantics differ from SQL; we maintain a small per-(tenant,service)
  version index doc to avoid mount scans (see design §wire-level).

## Alternatives considered
- Transit engine (server-side encrypt): rejected — would duplicate / displace our KEK/DEK
  scheme and put trust in HashiCorp for confidentiality we already own.
- Per-tenant AppRole + per-tenant mount: rejected for v1 — one mount + path prefix is simpler
  and the adapter is the only writer.

## Related
- ADR-0003 (KEK/DEK envelope; pluggable backend), ADR-0011 (Go stack), ADR-0021 (backend
  selector; Postgres default), OQ-003.
```

---

## 2. Interface the new struct MUST implement (quoted exactly from `internal/store/store.go`)

```go
// Backend is the abstraction shared by the SQLite and Postgres credential
// stores. Both *Store (sqlite.go) and *PostgresStore (postgres.go) satisfy
// this interface without any modifications to those files.
type Backend interface {
	Put(ctx context.Context, rec CredentialRecord) (uint32, error)
	Get(ctx context.Context, tenantID, serviceID string, keyVersion uint32) (*CredentialRecord, error)
	Revoke(ctx context.Context, tenantID, serviceID string, keyVersion uint32) error
	ListVersions(ctx context.Context, tenantID, serviceID string, afterKeyVersion, limit uint32) ([]CredentialRecord, error)
	Close() error
}
```

`CredentialRecord` (quoted from `internal/store/sqlite.go`) is the record type; the HashiCorp
backend persists the same field set SQLite persists (the Postgres-JOIN-only fields
`ServiceBaseUrl`, `TlsInsecureSkipVerify`, `SMTPHost/Port`, `IMAPHost/Port` stay empty/zero):

```go
type CredentialRecord struct {
	CredentialID  string
	TenantID      string
	ServiceID     string
	KeyVersion    uint32
	AuthScheme    int32
	WrappedDEK    []byte
	EncPayload    []byte
	IsCurrent     bool
	IsRevoked     bool
	CreatedAt     int64 // Unix nanoseconds
	TargetURL     string
	HeaderName    string
	QueryParam    string
	TargetAddress string
	SSHUser       string
	// ServiceBaseUrl, TlsInsecureSkipVerify, SMTPHost, SMTPPort, IMAPHost, IMAPPort
	// are Postgres-JOIN-only — left zero by this backend (same as SQLite).
}
```

New file: `internal/store/hashicorp.go`. Compile-time conformance assertion (place at
package scope): `var _ Backend = (*HashiCorpStore)(nil)`.

---

## 3. Struct & constructor

```go
// internal/store/hashicorp.go
package store

type HashiCorpStore struct {
	client   *vaultapi.Client // github.com/hashicorp/vault/api
	mount    string           // KV v2 mount, e.g. "secret"
	prefix   string           // path prefix, e.g. "mintkey"
	auth     *appRoleAuth     // owns token renewal goroutine
	putMu    *keyedMutex      // per-(tenant,service) serialisation (FR-9)
	logger   *slog.Logger
}

func NewHashiCorp(ctx context.Context, cfg HashiCorpConfig) (*HashiCorpStore, error)
```

`HashiCorpConfig` is built from env in `NewFromEnv` (see §6). `appRoleAuth` performs the
AppRole login and starts the renewal goroutine; `HashiCorpStore.Close()` cancels it.

---

## 4. Wire-level details (HashiCorp KV v2 layout)

KV v2 stores secrets as JSON maps under `<mount>/data/<path>` and lists under
`<mount>/metadata/<path>`. Mintkey layout:

```
<mount>/data/<prefix>/<tenant_id>/<service_id>/v<key_version>   # one credential version
<mount>/data/<prefix>/<tenant_id>/<service_id>/_index           # version index doc
```

- **Version doc** (`.../v<N>`) JSON value map — all `[]byte` fields base64-std-encoded:
  ```json
  {
    "credential_id": "cred_01H...",
    "key_version": 3,
    "auth_scheme": 1,
    "wrapped_dek": "<base64>",
    "enc_payload": "<base64>",
    "is_current": true,
    "is_revoked": false,
    "created_at": 1716900000000000000,
    "target_url": "https://api.example.com",
    "header_name": "X-API-Key",
    "query_param": "",
    "target_address": "",
    "ssh_user": ""
  }
  ```
  (`tenant_id`/`service_id` are implied by the path; stored in the doc too for self-description.)

- **Index doc** (`.../_index`) JSON: `{"current": 3, "max": 3, "versions": [1,2,3]}`.
  - `Put` reads `_index`, computes `next = max+1`, writes `v<next>`, flips the old `current`
    version doc's `is_current=false`, then writes `_index` with CAS (`options.cas` = the
    index's KV-v2 metadata version) to detect concurrent writers. The in-process per-key
    mutex (FR-9) is the primary serialiser; CAS is the second-line defence (parity with the
    Postgres advisory-lock + UNIQUE-constraint pattern).
  - `Get(0)` reads `_index.current`, then reads `v<current>`.
  - `Get(N>0)` reads `v<N>` directly.
  - `ListVersions` reads `_index.versions`, filters `> afterKeyVersion`, clamps `limit`, reads
    each `v<N>` for metadata (or stores enough metadata in `_index` to avoid N reads — the
    simplest correct version reads each doc; optimisation is out of scope).
  - `Revoke(N)` reads `v<N>`; if `is_current` → `ErrRevokeCurrent`; else set `is_revoked=true`,
    write back. Missing `v<N>` → wrapped `sql.ErrNoRows`.

**Not-found mapping (FR-4/FR-5):** the HashiCorp API returns a nil `*Secret` (or nil `.Data`)
for a missing path. Translate that to `fmt.Errorf("vault hashicorp: Get: %w", sql.ErrNoRows)`
so `errors.Is(err, sql.ErrNoRows)` holds — parity with `postgres.go` line 234.

---

## 5. Auth method — AppRole + background renewal

Use `github.com/hashicorp/vault/api` and `.../api/auth/approle`.

```go
// internal/store/hashicorp_auth.go
import (
	vaultapi "github.com/hashicorp/vault/api"
	approle "github.com/hashicorp/vault/api/auth/approle"
)

func newAppRoleAuth(ctx context.Context, client *vaultapi.Client, roleID, secretID string, log *slog.Logger) (*appRoleAuth, error) {
	a := &appRoleAuth{client: client, log: log}
	if err := a.login(ctx, roleID, secretID); err != nil {  // sets client token, captures lease TTL
		return nil, err
	}
	a.startRenew(ctx)   // goroutine: vaultapi LifetimeWatcher on the auth secret
	return a, nil
}
```

- Login: `client.Auth().Login(ctx, approle.NewAppRoleAuth(roleID, &approle.SecretID{FromString: secretID}))`.
- Renewal: wrap the returned `*api.Secret` in `client.NewLifetimeWatcher(&api.LifetimeWatcherInput{Secret: authSecret})`,
  run `go watcher.Start()`, and consume `watcher.RenewCh()` / `watcher.DoneCh()`. On `DoneCh`
  (renewal failed / token expired): re-login with backoff (250 ms → 2 s, capped), log
  `"hashicorp token renewal restarted"` **without** the token. The goroutine exits when the
  store's `ctx` (passed to `NewHashiCorp`) is cancelled by `Close()`.
- **Security (NFR-1):** never log `roleID` value, `secretID`, or the client token. Log only
  fixed messages and the renewal TTL integer. Token lives only inside `*vaultapi.Client`.

---

## 6. Env vars (complete; all MUST be added to `.env.example`)

| Env var | Default | Validation | Purpose |
|---------|---------|-----------|---------|
| `MINTKEY_VAULT_BACKEND` | `postgres` | one of `postgres\|sqlite\|hashicorp` | backend selector (existing; new value). |
| `MINTKEY_VAULT_HASHICORP_ADDR` | _(none)_ | required when backend=hashicorp; must be a URL (`http(s)://host:port`) | HashiCorp Vault API address (dev: `http://hashicorp-vault:8201`). |
| `MINTKEY_VAULT_HASHICORP_MOUNT` | `secret` | non-empty | KV v2 mount path. |
| `MINTKEY_VAULT_HASHICORP_PREFIX` | `mintkey` | non-empty, no leading/trailing `/` | path prefix under the mount. |
| `MINTKEY_VAULT_HASHICORP_ROLE_ID` | _(none)_ | required when backend=hashicorp | AppRole role_id. |
| `MINTKEY_VAULT_HASHICORP_SECRET_ID` | _(none)_ | required when backend=hashicorp; SENSITIVE — never logged | AppRole secret_id. |
| `MINTKEY_VAULT_HASHICORP_NAMESPACE` | `` (empty) | optional | Vault Enterprise namespace (ignored by community). |
| `MINTKEY_VAULT_HASHICORP_CACERT` | `` (empty) | optional path | CA cert for TLS to Vault (prod). |

`NewFromEnv` adds:
```go
case "hashicorp":
	cfg, err := hashiCorpConfigFromEnv()   // reads the vars above; errors name the missing var
	if err != nil {
		return nil, err
	}
	return NewHashiCorp(ctx, cfg)
```
The missing-config error MUST name the specific env var (e.g.
`"MINTKEY_VAULT_BACKEND=hashicorp requires MINTKEY_VAULT_HASHICORP_ROLE_ID"`), matching the
style of the existing postgres/sqlite branches.

---

## 7. Compose service (dev/CI only)

Add to `infra/compose/docker-compose.yml`:

```yaml
  hashicorp-vault:
    image: hashicorp/vault:1.18      # community edition; pin the tag
    cap_add: [IPC_LOCK]
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: mk-dev-root            # DEV ONLY
      VAULT_DEV_LISTEN_ADDRESS: 0.0.0.0:8201
    ports:
      - "8201:8201"
    command: server -dev -dev-listen-address=0.0.0.0:8201
    profiles: ["hashicorp"]     # opt-in: only starts with `--profile hashicorp`
```

vault-adapter gains (only effective when `MINTKEY_VAULT_BACKEND=hashicorp`):
```yaml
      MINTKEY_VAULT_HASHICORP_ADDR: http://hashicorp-vault:8201
      MINTKEY_VAULT_HASHICORP_MOUNT: secret
      MINTKEY_VAULT_HASHICORP_PREFIX: mintkey
      MINTKEY_VAULT_HASHICORP_ROLE_ID: ${MINTKEY_VAULT_HASHICORP_ROLE_ID:-}
      MINTKEY_VAULT_HASHICORP_SECRET_ID: ${MINTKEY_VAULT_HASHICORP_SECRET_ID:-}
```
A dev bootstrap script enables the KV v2 mount + AppRole (`scripts/hashicorp-vault-dev-init.sh`):
`vault auth enable approle`, `vault secrets enable -version=2 -path=secret kv` (dev mode mounts
KV v2 at `secret/` already), `vault write auth/approle/role/mintkey token_ttl=20m token_max_ttl=1h
policies=mintkey`, then read `role-id` / `secret-id`. Integration tests do the same via the
container's exec, so the script is a convenience, not a test dependency.

---

## 8. Dev instance setup (isolated from the live `mintkey` stack)

The active Mintkey instance runs as compose project `mintkey` on standard ports. Run vault
testing on an **isolated** project `mintkey-dev` with ports offset **+100** so nothing collides.

```sh
# From repo root. -p sets the compose project name (isolated volumes + network).
# Override host port mappings via env so the +100 offset applies.

export COMPOSE_PROJECT_NAME=mintkey-dev

# HashiCorp Vault dev container on 8301 (8201 + 100):
docker compose -f infra/compose/docker-compose.yml --profile hashicorp \
  -p mintkey-dev up -d hashicorp-vault

# Initialise KV v2 + AppRole inside the dev container:
docker exec -e VAULT_ADDR=http://127.0.0.1:8201 -e VAULT_TOKEN=mk-dev-root \
  mintkey-dev-hashicorp-vault-1 sh -c '
    vault auth enable approle || true
    vault policy write mintkey - <<EOF
path "secret/data/mintkey/*"     { capabilities = ["create","read","update","delete","list"] }
path "secret/metadata/mintkey/*" { capabilities = ["read","list","delete"] }
EOF
    vault write auth/approle/role/mintkey token_ttl=20m token_max_ttl=1h policies=mintkey
    vault read  -field=role_id   auth/approle/role/mintkey/role-id
    vault write -f -field=secret_id auth/approle/role/mintkey/secret-id
  '

# Tear down the dev instance (does NOT touch the live `mintkey` project):
docker compose -f infra/compose/docker-compose.yml -p mintkey-dev down -v
```

> The integration tests use `testcontainers-go` and spin up their **own** ephemeral
> HashiCorp Vault container per test run, so they do not depend on `mintkey-dev` being up.
> The `mintkey-dev` instance is for manual end-to-end verification of the full adapter.

---

## 9. Migration path — `make migrate-vault-to-hashicorp`

New command `apps/vault-adapter/cmd/vault-migrate-pg-to-hashicorp/main.go`, modelled on the
existing `cmd/vault-migrate-sqlite-to-pg/main.go` (read it for the exact idempotency,
sample-verify, and DSN-redaction patterns — reuse them).

- **Source:** Postgres `vault.credentials` via `pgxpool` (reads `MINTKEY_VAULT_PG_DSN`), with
  the same per-row `set_config('app.current_tenant', $1, true)` RLS GUC discipline used in the
  existing migrator's `insertRow`.
- **Target:** HashiCorp Vault via the same `HashiCorpStore.Put`-equivalent write path (reuse
  the store package — call `NewHashiCorp` and write version + index docs; do NOT reimplement).
  Idempotency: skip when `v<key_version>` already exists for the `(tenant,service)` (read-before-write).
- **Verify:** 5-sample reservoir → read both sides → `bytes.Equal(wrapped_dek)` &&
  `bytes.Equal(enc_payload)` && `auth_scheme` equality. Print the same summary table format.
- **Makefile target** (append to `Makefile`, mirroring `migrate-vault-sqlite-to-pg`):

```make
## migrate-vault-to-hashicorp: Copy all vault credentials from Postgres to HashiCorp Vault (idempotent).
migrate-vault-to-hashicorp:
	docker run --rm --network=mintkey_mintkey \
		-v "$(REPO_ROOT)/apps/vault-adapter":/src -w /src \
		-e MINTKEY_VAULT_PG_DSN="postgres://mintkey_migrate:changeme@postgres:5432/mintkey?sslmode=disable" \
		-e MINTKEY_VAULT_HASHICORP_ADDR \
		-e MINTKEY_VAULT_HASHICORP_MOUNT=secret \
		-e MINTKEY_VAULT_HASHICORP_PREFIX=mintkey \
		-e MINTKEY_VAULT_HASHICORP_ROLE_ID \
		-e MINTKEY_VAULT_HASHICORP_SECRET_ID \
		golang:latest go run ./cmd/vault-migrate-pg-to-hashicorp/...
```

Cut over after success: set `MINTKEY_VAULT_BACKEND=hashicorp` and
`docker compose up -d --no-deps --force-recreate vault-adapter`. SQLite/Postgres data is left
in place (non-destructive rollback = flip the env back), matching ADR-0021's posture.

---

## 10. Security constraints (restated for the implementer)

- KEK never sent to HashiCorp. Only ciphertext blobs are written. (NFR-2)
- `secret_id` and client token: never logged, never in spans, never in error strings. (NFR-1)
- Token lives only in `*vaultapi.Client`; renewal goroutine logs fixed strings + TTL int only.
- No `init()` side effects; the renewal goroutine starts only from `NewHashiCorp`/`newAppRoleAuth`.
- `Close()` cancels the renewal goroutine (pass the store ctx down; `select` on `ctx.Done()`).

---

## 11. Test strategy

- **Unit (no container):**
  - `TestNewFromEnv_Hashicorp*` in `internal/store/store_test.go` — selector branch + missing-var
    error messages (uses `t.Setenv`; no network).
  - `internal/store/hashicorp_path_test.go` — pure functions: path construction, base64
    encode/decode of `wrapped_dek`/`enc_payload`, JSON marshal/unmarshal of the version + index
    docs, `limit` clamp, `afterKeyVersion` filter. No client needed.
- **Integration (`-tags=integration`, `testcontainers-go` HashiCorp Vault):**
  - `internal/store/hashicorp_integration_test.go` — full `Backend` conformance: Put→Get(0)→
    Get(N)→Revoke→ListVersions; monotonic versions; current flip; `ErrRevokeCurrent`; not-found
    → `errors.Is(sql.ErrNoRows)`; concurrent-Put no-dup (goroutine fan-out).
  - `hashicorp_noleak_test.go` — capture `slog` output to a buffer, run login + Get, assert the
    `secret_id` and token are absent.
  - `cmd/vault-migrate-pg-to-hashicorp/main_test.go` — Postgres (testcontainers) seeded →
    migrate → HashiCorp (testcontainers) → count + sample verify + idempotent second run.
- **Lint:** `go vet ./...`, `staticcheck ./...` (AC-7).

The container helper mirrors the project's existing `testcontainers-go` usage (ADR-0011 names
it as the testing standard). Reuse `testcontainers-go/modules/vault` if present, else a generic
container request running `hashicorp/vault:1.18` in `-dev` mode.

---

## 12. Files touched (surgical inventory)

| File | Change |
|------|--------|
| `internal/store/hashicorp.go` | NEW — `HashiCorpStore` + `Backend` methods + `var _ Backend = …`. |
| `internal/store/hashicorp_auth.go` | NEW — AppRole login + renewal goroutine. |
| `internal/store/hashicorp_doc.go` | NEW — version/index doc JSON marshal/unmarshal + path helpers (pure). |
| `internal/store/store.go` | EDIT — add `case "hashicorp":` to `NewFromEnv` (≈ 6 lines). |
| `internal/store/store_test.go` | EDIT — add `TestNewFromEnv_Hashicorp*`. |
| `internal/store/hashicorp_path_test.go` | NEW — pure-function unit tests. |
| `internal/store/hashicorp_integration_test.go` | NEW — testcontainers conformance. |
| `internal/store/hashicorp_noleak_test.go` | NEW — token-not-logged. |
| `cmd/vault-migrate-pg-to-hashicorp/main.go` + `_test.go` | NEW — migration tool + test. |
| `go.mod` / `go.sum` | EDIT — add `github.com/hashicorp/vault/api` (+ `/api/auth/approle`). |
| `.env.example` | EDIT — add the 7 new `MINTKEY_VAULT_HASHICORP_*` vars with comments. |
| `infra/compose/docker-compose.yml` | EDIT — add `hashicorp-vault` service (profile `hashicorp`) + adapter env. |
| `Makefile` | EDIT — add `migrate-vault-to-hashicorp` target. |
| `docs/architecture/01-architecture/adr/0025-vault-storage-backend-hashicorp.md` | NEW — from §1 stub. |

`main.go` (vault-adapter `cmd/`) is **not** edited: the `st.(*store.PostgresStore)` SSH-wiring
type assertion already degrades correctly for any non-Postgres backend (FR-11).
