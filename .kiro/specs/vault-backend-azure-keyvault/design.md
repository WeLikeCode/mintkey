# Design — Vault Adapter backend: Azure Key Vault

> Implementation design for the `azure` Vault Adapter backend. Self-contained:
> external constraints quoted inline. Target ADR: **ADR-0026**.

---

## 1. Inline ADR stub (copy to `docs/architecture/01-architecture/adr/0026-vault-storage-backend-azure-keyvault.md`)

```markdown
# ADR-0026: Vault Adapter storage backend — Azure Key Vault, opt-in

## Status
Proposed — <DATE>. Adds a fourth value to the ADR-0021 backend selector
(`MINTKEY_VAULT_BACKEND=azure`). Postgres remains the default; SQLite and HashiCorp remain
opt-in alternatives. The KEK/DEK envelope scheme (ADR-0003 §Decision 2) is unchanged.

## Context
Operators running Mintkey on Azure want the most sensitive Mintkey data stored in their managed
Azure Key Vault rather than in Postgres. ADR-0021 demoted SQLite to a fallback and made Postgres
the default while leaving the backend pluggable per ADR-0003. This ADR realises an Azure-native
store.

## Decision
Add an `*AzureKeyVaultStore` implementing the existing `store.Backend` interface. Azure Key
Vault is used as an OPAQUE secret store for the already-encrypted envelope blobs (`wrapped_dek`,
`enc_payload`) plus metadata, base64+JSON-packed into a single Key Vault **secret value** per
credential version. Mintkey's KEK never leaves the adapter; Azure Key Vault Keys / Managed HSM
crypto operations are NOT used. Auth is via `DefaultAzureCredential` (azidentity), so the same
binary uses a service principal in CI, a managed identity in production, and `az login` locally.
Tenant isolation is application-side via the secret-name prefix; there is no RLS equivalent,
acceptable because the adapter is the sole writer and always scopes reads by
`(tenant_id, service_id)`.

## Consequences
- Positive: Azure operators get a native managed store; the envelope blob is byte-identical
  across all backends; no static secret in the production binary (managed identity).
- Costs: a new dev/CI mock service; Azure Key Vault is a runtime dependency when selected;
  Key Vault soft-delete/purge semantics require per-version-distinct secret names. SSH RPCs
  (`SSHVaultAdapter`) remain Postgres-only.
- Risks: Key Vault throttling (429) on bursty writes — mitigated by the adapter's low write rate
  (credential rotation is infrequent — ADR-0021 §Constraints).

## Alternatives considered
- Key Vault Keys (RSA-wrap our DEK): rejected — duplicates the KEK role we already own with our
  own AES-256-GCM scheme; adds an Azure crypto round-trip per read.
- One secret per credential holding a Key Vault secret-version history: rejected — Key Vault
  secret versions are immutable and auto-versioned, which does not map to our mutable
  is_current/is_revoked flags; we use distinct named secrets per logical version instead.

## Related
- ADR-0003 (KEK/DEK envelope; pluggable backend), ADR-0011 (Go stack), ADR-0021 (selector;
  Postgres default), ADR-0025 (HashiCorp backend — sibling pattern).
```

---

## 2. Interface the new struct MUST implement (quoted exactly from `internal/store/store.go`)

```go
type Backend interface {
	Put(ctx context.Context, rec CredentialRecord) (uint32, error)
	Get(ctx context.Context, tenantID, serviceID string, keyVersion uint32) (*CredentialRecord, error)
	Revoke(ctx context.Context, tenantID, serviceID string, keyVersion uint32) error
	ListVersions(ctx context.Context, tenantID, serviceID string, afterKeyVersion, limit uint32) ([]CredentialRecord, error)
	Close() error
}
```

`CredentialRecord` (quoted from `internal/store/sqlite.go`) — persist the SQLite field set; the
Postgres-JOIN-only fields (`ServiceBaseUrl`, `TlsInsecureSkipVerify`, `SMTPHost/Port`,
`IMAPHost/Port`) stay empty/zero:

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
}
```

New file: `internal/store/azure.go`. Compile-time conformance: `var _ Backend = (*AzureKeyVaultStore)(nil)`.

---

## 3. Struct & constructor

```go
// internal/store/azure.go
package store

import (
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/security/keyvault/azsecrets"
)

type AzureKeyVaultStore struct {
	client *azsecrets.Client // Key Vault Secrets data-plane client
	prefix string            // secret-name prefix, e.g. "mintkey"
	putMu  *keyedMutex       // per-(tenant,service) serialisation (FR-9)
	logger *slog.Logger
}

func NewAzureKeyVault(ctx context.Context, cfg AzureConfig) (*AzureKeyVaultStore, error) {
	cred, err := azidentity.NewDefaultAzureCredential(nil)  // FR-8
	if err != nil { return nil, fmt.Errorf("vault azure: default credential: %w", err) }
	client, err := azsecrets.NewClient(cfg.Endpoint, cred, nil) // cfg.Endpoint overridable (FR-13)
	if err != nil { return nil, fmt.Errorf("vault azure: new client: %w", err) }
	return &AzureKeyVaultStore{client: client, prefix: cfg.Prefix, putMu: newKeyedMutex(), logger: cfg.Logger}, nil
}
```

If the `keyedMutex` type was added by the HashiCorp spec (ADR-0025), reuse it; otherwise add it
here (one place only).

---

## 4. Wire-level details (Azure Key Vault secret naming + value layout)

Key Vault secret **names** must match `^[0-9a-zA-Z-]+$` (no `/`, `_`, `:`). Mintkey IDs are
ULID-prefixed with `_` (e.g. `tenant_01H...`, `svc_01H...`), which contain `_` — therefore the
name MUST be a deterministic, collision-free **encoding** of `(prefix, tenant_id, service_id,
key_version)`. Use: lowercased hex of SHA-256 over the canonical
`"<prefix>|<tenant_id>|<svc_id>|v<key_version>"` string, prefixed with `mk-`:

```
secret name (version doc):  mk-<hex32 sha256 of "<prefix>|<tenant>|<svc>|v<N>">
secret name (index doc):    mk-<hex32 sha256 of "<prefix>|<tenant>|<svc>|_index">
```

(32 bytes → 64 hex chars; Key Vault allows up to 127-char names. The mapping is one-way but
deterministic, so reads recompute the name from `(tenant,service,version)`. ListVersions reads
the index, not a name enumeration, so the one-way hash is fine.)

- **Secret value** = base64-std of the JSON version doc (same JSON shape as the HashiCorp design
  §4 version doc: `credential_id`, `key_version`, `auth_scheme`, `wrapped_dek` (base64),
  `enc_payload` (base64), `is_current`, `is_revoked`, `created_at`, `target_url`, `header_name`,
  `query_param`, `target_address`, `ssh_user`, plus `tenant_id`/`service_id` for self-description).
- **Index secret value** = base64-std JSON `{"current":N,"max":N,"versions":[...]}`.
- **Put:** under the per-key mutex — read index secret (capture its ETag), `next=max+1`, set
  the previous `current` version doc's `is_current=false` (read-modify-write that secret), write
  the new `v<next>` secret, write the index secret with `If-Match: <etag>` (azsecrets
  `SetSecretParameters` + conditional via the client's options) so a concurrent writer is
  detected; on ETag conflict, retry the whole sequence (bounded).
- **Get(0):** read index → `current` → read `v<current>` secret → unmarshal.
- **Get(N>0):** compute name for `v<N>`, read directly.
- **Revoke(N):** read `v<N>`; `is_current` → `ErrRevokeCurrent`; else set `is_revoked=true`,
  re-set the secret; missing → wrapped `sql.ErrNoRows`.
- **ListVersions:** read index `versions`, filter `> afterKeyVersion`, clamp `limit`, read each
  `v<N>` for metadata.

**Not-found mapping (FR-4/FR-5):** azsecrets returns an `*azcore.ResponseError` with
`StatusCode == http.StatusNotFound` for a missing secret. Translate to
`fmt.Errorf("vault azure: Get: %w", sql.ErrNoRows)` so `errors.Is(err, sql.ErrNoRows)` holds —
parity with `postgres.go` line 234.

**Soft-delete note (NFR-4):** we never reuse a secret name across logical versions (each
`v<N>` is distinct and monotonic), so Key Vault soft-delete of an old name never collides with a
new write. Operators with purge-protection get the same guarantee. Document in the HOW-TO runbook.

---

## 5. Auth method — `DefaultAzureCredential`

`azidentity.NewDefaultAzureCredential(nil)` resolves, in order: environment variables
(`AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` — CI service principal) →
workload identity → managed identity (production) → Azure CLI (`az login`, local dev). No custom
token-renewal goroutine: the SDK's credential caches and refreshes the AAD token internally
(contrast HashiCorp AppRole). For the **mock** dev/CI path (FR-13), the endpoint is overridden to
the mock server; the credential still constructs but its token is never validated by the mock
(the mock ignores `Authorization`). Tests that need a real-credential code path inject a fake
`azcore.TokenCredential` via an unexported constructor seam (`newAzureKeyVaultWithClient`).

**Security (NFR-1):** never log `AZURE_CLIENT_SECRET` or any token. Log only fixed strings and
the (non-secret) endpoint host. The secret lives only inside the azidentity credential.

---

## 6. Env vars (complete; all MUST be added to `.env.example`)

| Env var | Default | Validation | Purpose |
|---------|---------|-----------|---------|
| `MINTKEY_VAULT_BACKEND` | `postgres` | one of `postgres\|sqlite\|hashicorp\|azure` | backend selector (existing; new value). |
| `MINTKEY_VAULT_AZURE_ENDPOINT` | _(none)_ | required when backend=azure; URL | Key Vault data-plane URL (prod: `https://<name>.vault.azure.net`; dev: mock `http://azure-keyvault-mock:8201`). |
| `MINTKEY_VAULT_AZURE_PREFIX` | `mintkey` | non-empty | secret-name prefix component (hashed into the name). |
| `AZURE_TENANT_ID` | `` | optional (env-credential path) | AAD tenant for service-principal auth in CI. |
| `AZURE_CLIENT_ID` | `` | optional | service-principal / managed-identity client id. |
| `AZURE_CLIENT_SECRET` | `` | optional; SENSITIVE — never logged | service-principal secret (CI only; prod uses managed identity → leave empty). |

> `AZURE_*` are the standard names `azidentity` already reads; we list them for `.env.example`
> completeness, not because we read them ourselves. Only `MINTKEY_VAULT_AZURE_ENDPOINT` and
> `MINTKEY_VAULT_AZURE_PREFIX` are read by our code.

`NewFromEnv` adds:
```go
case "azure":
	cfg, err := azureConfigFromEnv()   // requires MINTKEY_VAULT_AZURE_ENDPOINT
	if err != nil {
		return nil, err
	}
	return NewAzureKeyVault(ctx, cfg)
```
Missing-config error MUST name `MINTKEY_VAULT_AZURE_ENDPOINT`, matching the existing
postgres/sqlite branch style.

---

## 7. Compose service (dev/CI only — Azure has no community container)

Azure Key Vault is a cloud service with no official local container. For hermetic dev/CI we run a
**mock** Key Vault HTTP server. Two options; pick the simpler that passes the conformance tests:

- **Option A (preferred):** an in-repo tiny mock in Go (`cmd/azure-keyvault-mock/main.go`) that
  implements the handful of azsecrets REST routes we use (`PUT/GET /secrets/{name}`,
  `GET /secrets/{name}/{version}`), storing values in memory. Started as a compose service.
- **Option B:** a community Key Vault emulator image if one is vetted and pinned.

```yaml
  azure-keyvault-mock:
    build:
      context: ../..
      dockerfile: apps/vault-adapter/cmd/azure-keyvault-mock/Dockerfile   # Option A
    ports:
      - "8201:8201"     # internal mock port; host map only in dev
    profiles: ["azure"]   # opt-in: only with `--profile azure`
```

vault-adapter gains (effective only when `MINTKEY_VAULT_BACKEND=azure`):
```yaml
      MINTKEY_VAULT_AZURE_ENDPOINT: http://azure-keyvault-mock:8201
      MINTKEY_VAULT_AZURE_PREFIX: mintkey
```

> Integration tests do NOT need the compose service: they spin the mock via `httptest.Server`
> in-process. The compose mock is for manual end-to-end verification of the full adapter.

---

## 8. Dev instance setup (isolated from the live `mintkey` stack)

The active Mintkey instance runs as compose project `mintkey` on standard ports. Run Azure
testing on an isolated project `mintkey-dev` with ports offset **+100**.

```sh
export COMPOSE_PROJECT_NAME=mintkey-dev

# Start the mock Key Vault on 8301 (8201 + 100) in the isolated project:
docker compose -f infra/compose/docker-compose.yml --profile azure \
  -p mintkey-dev up -d azure-keyvault-mock

# Point a dev vault-adapter at it (azure backend):
docker compose -f infra/compose/docker-compose.yml --profile azure \
  -p mintkey-dev up -d \
  -e MINTKEY_VAULT_BACKEND=azure \
  -e MINTKEY_VAULT_AZURE_ENDPOINT=http://azure-keyvault-mock:8201 \
  vault-adapter

# Tear down the dev instance (does NOT touch the live `mintkey` project):
docker compose -f infra/compose/docker-compose.yml -p mintkey-dev down -v
```

> For verification against a **real** Azure Key Vault, set `MINTKEY_VAULT_AZURE_ENDPOINT` to your
> `https://<name>.vault.azure.net` and `az login` (or provide `AZURE_*` env). Never commit a
> real client secret; use `az login` locally or a managed identity on an Azure VM.

---

## 9. Migration path — `make migrate-vault-to-azure`

New command `apps/vault-adapter/cmd/vault-migrate-pg-to-azure/main.go`, modelled on the existing
`cmd/vault-migrate-sqlite-to-pg/main.go` (reuse its idempotency, sample-verify, DSN-redaction).

- **Source:** Postgres `vault.credentials` via `pgxpool` (`MINTKEY_VAULT_PG_DSN`), per-row RLS
  GUC `set_config('app.current_tenant', $1, true)` as in the existing migrator's `insertRow`.
- **Target:** Azure Key Vault via the store package (`store.NewAzureKeyVault` + the `Put` write
  path; do NOT reimplement). Idempotency: skip when the `v<key_version>` secret already exists.
- **Verify:** 5-sample reservoir → read both sides → `bytes.Equal(wrapped_dek)` &&
  `bytes.Equal(enc_payload)` && `auth_scheme` equality → same summary table format.
- **Makefile target** (append, mirroring `migrate-vault-sqlite-to-pg`):

```make
## migrate-vault-to-azure: Copy all vault credentials from Postgres to Azure Key Vault (idempotent).
migrate-vault-to-azure:
	docker run --rm --network=mintkey_mintkey \
		-v "$(REPO_ROOT)/apps/vault-adapter":/src -w /src \
		-e MINTKEY_VAULT_PG_DSN="postgres://mintkey_migrate:changeme@postgres:5432/mintkey?sslmode=disable" \
		-e MINTKEY_VAULT_AZURE_ENDPOINT \
		-e MINTKEY_VAULT_AZURE_PREFIX=mintkey \
		-e AZURE_TENANT_ID -e AZURE_CLIENT_ID -e AZURE_CLIENT_SECRET \
		golang:latest go run ./cmd/vault-migrate-pg-to-azure/...
```

Cut over after success: set `MINTKEY_VAULT_BACKEND=azure` and
`docker compose up -d --no-deps --force-recreate vault-adapter`. Source data is left in place
(non-destructive rollback = flip the env back), matching ADR-0021.

---

## 10. Security constraints (restated for the implementer)

- KEK never sent to Azure. Only ciphertext blobs are written. (NFR-2)
- `AZURE_CLIENT_SECRET` and any AAD token: never logged, never in spans, never in error strings. (NFR-1)
- Production uses managed identity (no static secret in the binary); CI may use a service principal.
- No `init()` side effects; no background goroutine (SDK handles token refresh).
- `Close()` is a no-op for connection state but MUST be implemented to satisfy `Backend`.

---

## 11. Test strategy

- **Unit (no network):**
  - `TestNewFromEnv_Azure*` in `internal/store/store_test.go` — selector branch + missing-endpoint
    error message (`t.Setenv`).
  - `internal/store/azure_name_test.go` — pure functions: secret-name hashing determinism +
    charset compliance (`^[0-9a-zA-Z-]+$`), version/index doc JSON round-trip incl. base64 of
    `wrapped_dek`/`enc_payload`, `limit` clamp, `afterKeyVersion` filter.
- **Integration (`httptest` mock Key Vault — runs in default `go test`, no build tag, no Azure):**
  - `internal/store/azure_integration_test.go` — start an in-process mock implementing the
    azsecrets routes; build an `AzureKeyVaultStore` via the `newAzureKeyVaultWithClient` seam
    pointing at the mock; assert full `Backend` conformance (Put→Get(0)→Get(N)→Revoke→
    ListVersions; monotonic versions; current flip; `ErrRevokeCurrent`; not-found →
    `errors.Is(sql.ErrNoRows)`; concurrent-Put no-dup); AC-4 round-trip via `crypto.Seal`.
  - `azure_noleak_test.go` — capture `slog` output, run Get with a configured secret, assert the
    secret substring is absent.
  - `cmd/vault-migrate-pg-to-azure/main_test.go` — Postgres (testcontainers) seeded → migrate →
    mock Key Vault (`httptest`) → count + sample verify + idempotent second run.
- **Lint:** `go vet ./...`, `staticcheck ./...` (AC-7).

The `httptest` mock approach (vs testcontainers) is chosen because Azure Key Vault has no local
container; an in-process mock keeps tests fast and hermetic and runs in plain `go test` without a
build tag.

---

## 12. Files touched (surgical inventory)

| File | Change |
|------|--------|
| `internal/store/azure.go` | NEW — `AzureKeyVaultStore` + `Backend` methods + `var _ Backend = …` + `newAzureKeyVaultWithClient` test seam. |
| `internal/store/azure_name.go` | NEW — secret-name hashing + version/index doc marshal (pure). |
| `internal/store/store.go` | EDIT — add `case "azure":` to `NewFromEnv` (≈ 6 lines). |
| `internal/store/store_test.go` | EDIT — add `TestNewFromEnv_Azure*`. |
| `internal/store/azure_name_test.go` | NEW — pure-function unit tests. |
| `internal/store/azure_integration_test.go` | NEW — httptest-mock conformance. |
| `internal/store/azure_noleak_test.go` | NEW — secret-not-logged. |
| `cmd/azure-keyvault-mock/main.go` (+ Dockerfile) | NEW — Option A in-repo mock (also reused by integration tests' route logic if shared). |
| `cmd/vault-migrate-pg-to-azure/main.go` + `_test.go` | NEW — migration tool + test. |
| `go.mod` / `go.sum` | EDIT — add `github.com/Azure/azure-sdk-for-go/sdk/azidentity` + `.../sdk/security/keyvault/azsecrets`. |
| `.env.example` | EDIT — add `MINTKEY_VAULT_AZURE_*` + `AZURE_*` vars with comments. |
| `infra/compose/docker-compose.yml` | EDIT — add `azure-keyvault-mock` service (profile `azure`) + adapter env. |
| `Makefile` | EDIT — add `migrate-vault-to-azure` target. |
| `docs/architecture/01-architecture/adr/0026-vault-storage-backend-azure-keyvault.md` | NEW — from §1 stub. |

`main.go` (vault-adapter `cmd/`) is NOT edited: the `st.(*store.PostgresStore)` SSH-wiring type
assertion already degrades correctly for any non-Postgres backend (FR-12). If `keyedMutex` was
introduced by ADR-0025, reuse it; do not define it twice.
