# Tasks — Vault Adapter backend: Azure Key Vault

> Atomic, one-at-a-time tasks for a Sonnet implementer. Each ≤ 200 lines of new code.
> All paths relative to `apps/vault-adapter/` unless absolute. Run `go`/`make` commands from
> `apps/vault-adapter/` (the module root) unless noted.
> Reference design: `.kiro/specs/vault-backend-azure-keyvault/design.md`.

---

### Task 1 — Write the failing test first (TDD): selector branch
**Depends on:** none.
**Files:** `internal/store/store_test.go` (EDIT — add tests only).
**Do:** Add `TestNewFromEnv_AzureMissingEndpoint` and `TestNewFromEnv_AzureSelectsBackend`.
The first sets `MINTKEY_VAULT_BACKEND=azure` with `MINTKEY_VAULT_AZURE_ENDPOINT` empty and
asserts the error mentions `MINTKEY_VAULT_AZURE_ENDPOINT`. The second sets a complete config and
asserts either an `*AzureKeyVaultStore` is returned OR a constructor error — but NOT the
`MINTKEY_VAULT_PG_DSN` error, proving the `azure` branch was taken.
**Verify:** `go test ./internal/store/ -run TestNewFromEnv_Azure` → **FAILS to compile** (no
`azure` case) or fails the assertion. Capture the red output.

---

### Task 2 — Add the Azure SDK dependencies
**Depends on:** Task 1.
**Files:** `go.mod`, `go.sum` (EDIT via go tooling).
**Do:** `go get github.com/Azure/azure-sdk-for-go/sdk/azidentity` and
`go get github.com/Azure/azure-sdk-for-go/sdk/security/keyvault/azsecrets`.
**Verify:** `go build ./...` succeeds; `grep keyvault/azsecrets go.mod` → exit 0.

---

### Task 3 — Pure name/doc helpers + their unit tests (TDD)
**Depends on:** Task 2.
**Files:** `internal/store/azure_name.go` (NEW), `internal/store/azure_name_test.go` (NEW).
**Do:** Write the test file FIRST. Implement pure functions (no client):
`secretName(prefix, tenantID, serviceID string, ver uint32) string` (SHA-256 hex, `mk-` prefix),
`indexSecretName(prefix, tenantID, serviceID string) string`,
`marshalVersionDoc(rec CredentialRecord) (string, error)` (JSON→base64-std; `[]byte` fields
base64),  `unmarshalVersionDoc(string) (CredentialRecord, error)`, `marshalIndex`/`unmarshalIndex`.
Tests assert: name charset `^[0-9a-zA-Z-]+$`, determinism (same inputs → same name; different
version → different name), full record round-trip with non-empty `wrapped_dek`/`enc_payload`,
`limit`-clamp and `afterKeyVersion`-filter helpers.
**Verify:** `go test ./internal/store/ -run TestAzureName` → exit 0. ≤ 200 lines.

---

### Task 4 — `AzureKeyVaultStore` + `Backend` methods + test seam
**Depends on:** Task 3.
**Files:** `internal/store/azure.go` (NEW).
**Do:** Implement `AzureKeyVaultStore`, `AzureConfig`, `NewAzureKeyVault(ctx, cfg)` (uses
`azidentity.NewDefaultAzureCredential` + `azsecrets.NewClient(cfg.Endpoint, cred, nil)`), and an
unexported `newAzureKeyVaultWithClient(client *azsecrets.Client, prefix string, log *slog.Logger)`
seam for tests. Implement `Put`, `Get`, `Revoke`, `ListVersions`, `Close` (no-op) per design §4
using the Task 3 helpers and the per-key `keyedMutex` (reuse the ADR-0025 `keyedMutex` if present,
else define it here once). Map `*azcore.ResponseError` 404 → wrapped `sql.ErrNoRows`;
current-version revoke → `store.ErrRevokeCurrent`. Add `var _ Backend = (*AzureKeyVaultStore)(nil)`.
**Verify:** `go build ./...` succeeds; `go vet ./internal/store/` exits 0. ≤ 200 lines.

---

### Task 5 — Wire the selector
**Depends on:** Task 4.
**Files:** `internal/store/store.go` (EDIT), `internal/store/azure.go` (add `azureConfigFromEnv()`).
**Do:** Add `case "azure":` to `NewFromEnv` calling `azureConfigFromEnv()` then
`NewAzureKeyVault`. The config reader MUST error naming `MINTKEY_VAULT_AZURE_ENDPOINT` when absent.
**Verify:** `go test ./internal/store/ -run TestNewFromEnv` → exit 0 (Task 1 tests GREEN + the 4
pre-existing selector tests still pass). Capture PASS output.

---

### Task 6 — In-repo mock Key Vault (shared by tests + compose)
**Depends on:** Task 2.
**Files:** `cmd/azure-keyvault-mock/main.go` (NEW), `cmd/azure-keyvault-mock/Dockerfile` (NEW),
and an exported test helper (e.g. `internal/store/azuremock/handler.go`) returning an
`http.Handler` implementing the azsecrets routes used by Task 4 (`PUT/GET /secrets/{name}`,
`GET /secrets/{name}/{version}`, conditional `If-Match`), backed by an in-memory map.
**Do:** Implement the minimal route set with ETag support for the index secret. The `cmd` binary
just serves the handler on `:8201`; the test helper is what `httptest.NewServer` wraps.
**Verify:** `go build ./cmd/azure-keyvault-mock/...` succeeds; `go vet ./...` exits 0. ≤ 200 lines.

---

### Task 7 — Integration conformance test (httptest mock)
**Depends on:** Task 5, Task 6.
**Files:** `internal/store/azure_integration_test.go` (NEW — no build tag; plain `go test`).
**Do:** Start `httptest.NewServer(azuremock.Handler())`, build an `AzureKeyVaultStore` via
`newAzureKeyVaultWithClient` pointing `azsecrets.NewClient` at the mock URL with a fake
`azcore.TokenCredential`. Assert the full `Backend` contract: Put→Get(0)→Get(N)→Revoke→
ListVersions; monotonic `key_version`; current-flip on second Put; `ErrRevokeCurrent` on current;
not-found → `errors.Is(err, sql.ErrNoRows)`; concurrent Put fan-out → distinct versions. Include
AC-4 round-trip via `crypto.Seal`.
**Verify:** `go test ./internal/store/ -run TestAzure` → exit 0.

---

### Task 8 — Secret-not-logged test
**Depends on:** Task 7.
**Files:** `internal/store/azure_noleak_test.go` (NEW).
**Do:** Inject a `slog.Logger` writing to a `bytes.Buffer`, run a `Get` (and any path that
touches the configured secret), assert the buffer does NOT contain a sentinel secret string.
**Verify:** `go test ./internal/store/ -run TestAzure_SecretNotLogged` → exit 0.

---

### Task 9 — `.env.example` entries
**Depends on:** Task 5.
**Files:** `/Users/alexandruiacobescu/gooseProjects/mintkey/.env.example` (EDIT).
**Do:** Add a commented block with `MINTKEY_VAULT_AZURE_ENDPOINT`, `MINTKEY_VAULT_AZURE_PREFIX`,
and the `AZURE_TENANT_ID`/`AZURE_CLIENT_ID`/`AZURE_CLIENT_SECRET` (mark `AZURE_CLIENT_SECRET`
SENSITIVE), each with a one-line purpose comment per design §6.
**Verify:** for each var name N in design §6: `grep -q N .env.example` → exit 0 (loop all).

---

### Task 10 — Migration command (TDD)
**Depends on:** Task 5, Task 6.
**Files:** `cmd/vault-migrate-pg-to-azure/main.go` (NEW), `cmd/vault-migrate-pg-to-azure/main_test.go` (NEW).
**Do:** Write the test first: seed Postgres `vault.credentials` (testcontainers Postgres +
Liquibase changelog `018`), run `run(ctx, dsn, azureCfg)` against an `httptest` mock Key Vault,
assert read==inserted, 5-sample byte-equal PASS, and a second run reports all skipped. Then
implement `run` reusing `cmd/vault-migrate-sqlite-to-pg/main.go` patterns (RLS GUC per row,
reservoir sample, DSN redaction) and the `store.NewAzureKeyVault`/`newAzureKeyVaultWithClient`
write path. ≤ 200 lines.
**Verify:** `go test ./cmd/vault-migrate-pg-to-azure/` → exit 0.

---

### Task 11 — Makefile target
**Depends on:** Task 10.
**Files:** `/Users/alexandruiacobescu/gooseProjects/mintkey/Makefile` (EDIT).
**Do:** Append the `migrate-vault-to-azure` target from design §9 and a help line next to
`migrate-vault-sqlite-to-pg`.
**Verify:** `make -n migrate-vault-to-azure` prints the docker run command (dry-run) → exit 0.

---

### Task 12 — Compose service
**Depends on:** Task 5, Task 6.
**Files:** `/Users/alexandruiacobescu/gooseProjects/mintkey/infra/compose/docker-compose.yml` (EDIT).
**Do:** Add the `azure-keyvault-mock` service (profile `azure`, built from the Task 6 Dockerfile)
and the two `MINTKEY_VAULT_AZURE_*` env entries on `vault-adapter` per design §7.
**Verify:** `docker compose -f infra/compose/docker-compose.yml --profile azure config` exits 0
and lists `azure-keyvault-mock`.

---

### Task 13 — ADR stub
**Depends on:** Task 5.
**Files:** `docs/architecture/01-architecture/adr/0026-vault-storage-backend-azure-keyvault.md`
(NEW), ADR `README.md` index + `adrs/` symlink per project convention.
**Do:** Copy the design §1 ADR stub verbatim, fill `<DATE>`. Add the symlink in `adrs/`.
**Verify:** `test -L docs/architecture/adrs/0026-vault-storage-backend-azure-keyvault.md` (or the
project's symlink convention) → exit 0; renders as markdown.

---

### Task 14 — Final gate: lint + full test + selector regression
**Depends on:** all prior.
**Files:** none (verification only).
**Do:** Run the full verification sweep.
**Verify (all must exit 0):**
- `go vet ./...`
- `staticcheck ./...`
- `go test ./internal/store/ -run TestNewFromEnv` (regression: existing + new)
- `go test ./internal/store/ -run TestAzure`
- `go test ./cmd/vault-migrate-pg-to-azure/`
- For each env var in design §6: `grep -q <VAR> /Users/.../.env.example`
Capture exit codes and salient output (Principle 1 — no "tests pass" without runner output).

---

## Dependency graph

```
1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 9
          6 ─►   └─► 7 ─► 8
                 └─► 10 ─► 11
          5,6 ─► 12
          5 ─► 13
all ─► 14
```

## Cross-spec note
If the HashiCorp spec (ADR-0025) lands first and introduces the `keyedMutex` type in
`internal/store/`, REUSE it — do not redefine. If this spec lands first, define `keyedMutex` here
and the HashiCorp spec reuses it. Exactly one definition in the package.
