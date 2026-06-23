# Tasks — Vault Adapter backend: HashiCorp Vault (KV v2)

> Atomic, one-at-a-time tasks for a Sonnet implementer. Each ≤ 200 lines of new code.
> All paths are relative to `apps/vault-adapter/` unless absolute. Run all `go`/`make`
> commands from `apps/vault-adapter/` (the module root) unless noted.
> Reference design: `.kiro/specs/vault-backend-hashicorp/design.md`.

---

### Task 1 — Write the failing test first (TDD): selector branch
**Depends on:** none.
**Files:** `internal/store/store_test.go` (EDIT — add tests only).
**Do:** Add `TestNewFromEnv_HashicorpMissingRoleID` and `TestNewFromEnv_HashicorpSelectsBackend`.
The first sets `MINTKEY_VAULT_BACKEND=hashicorp` with all `MINTKEY_VAULT_HASHICORP_*` empty and
asserts the error mentions `MINTKEY_VAULT_HASHICORP_ROLE_ID` (or `_ADDR`). The second sets a
fake but complete config and asserts either a `*HashiCorpStore` is returned OR a connection
error (since no live Vault) — use `errors.Is`/type-switch tolerant assertion that proves the
branch was taken (e.g. error does NOT mention `MINTKEY_VAULT_PG_DSN`).
**Verify:** `go test ./internal/store/ -run TestNewFromEnv_Hashicorp` → **FAILS to compile**
(no `hashicorp` case yet) or fails the assertion. Capture the failure output. This is the
expected red state.

---

### Task 2 — Add the HashiCorp dependency
**Depends on:** Task 1.
**Files:** `go.mod`, `go.sum` (EDIT via go tooling).
**Do:** `go get github.com/hashicorp/vault/api` and `go get github.com/hashicorp/vault/api/auth/approle`.
**Verify:** `go build ./...` succeeds; `grep hashicorp/vault/api go.mod` → exit 0.

---

### Task 3 — Pure doc/path helpers + their unit tests (TDD)
**Depends on:** Task 2.
**Files:** `internal/store/hashicorp_doc.go` (NEW), `internal/store/hashicorp_path_test.go` (NEW).
**Do:** Write the test file FIRST. Implement pure functions (no Vault client):
`dataPath(prefix, tenantID, serviceID string, ver uint32) string`,
`indexPath(prefix, tenantID, serviceID string) string`,
`marshalVersionDoc(rec CredentialRecord) (map[string]interface{}, error)` (base64-std the
`[]byte` fields), `unmarshalVersionDoc(map[string]interface{}) (CredentialRecord, error)`,
`marshalIndex(idx versionIndex) map[string]interface{}` / `unmarshalIndex`. Tests cover
round-trip of a record with non-empty `wrapped_dek`/`enc_payload`, path format
(`mintkey/<tenant>/<svc>/v3` and `.../_index`), and `limit`-clamp + `afterKeyVersion`-filter
helper for ListVersions.
**Verify:** `go test ./internal/store/ -run TestHashiCorpDoc` → exit 0. ≤ 200 lines.

---

### Task 4 — AppRole login + background renewal
**Depends on:** Task 2.
**Files:** `internal/store/hashicorp_auth.go` (NEW).
**Do:** Implement `appRoleAuth` with `newAppRoleAuth(ctx, client, roleID, secretID, logger)`:
AppRole login via `approle.NewAppRoleAuth`, capture the auth secret, start a
`client.NewLifetimeWatcher` goroutine, re-login with capped backoff on `DoneCh`, exit on
`ctx.Done()`. Add `func (a *appRoleAuth) stop()`. **Never** log `roleID`/`secretID`/token.
**Verify:** `go vet ./internal/store/` exits 0; `go build ./...` succeeds. (Behaviour is
covered by Task 8 integration + Task 9 no-leak tests.)

---

### Task 5 — `HashiCorpStore` + `Backend` methods
**Depends on:** Task 3, Task 4.
**Files:** `internal/store/hashicorp.go` (NEW).
**Do:** Implement `HashiCorpStore`, `HashiCorpConfig`, `NewHashiCorp(ctx, cfg)` (builds
`*vaultapi.Client`, sets addr/namespace/CA, calls `newAppRoleAuth`, inits the per-key
`keyedMutex`). Implement `Put`, `Get`, `Revoke`, `ListVersions`, `Close` per design §4 using
the Task 3 helpers and the KV v2 logical client (`client.KVv2(mount)`). Map nil-secret →
wrapped `sql.ErrNoRows`; current-version revoke → `store.ErrRevokeCurrent`. Add
`var _ Backend = (*HashiCorpStore)(nil)`. Implement a small `keyedMutex` type (or place it in
`hashicorp.go`).
**Verify:** `go build ./...` succeeds; `go vet ./internal/store/` exits 0. ≤ 200 lines.

---

### Task 6 — Wire the selector
**Depends on:** Task 5.
**Files:** `internal/store/store.go` (EDIT), `internal/store/hashicorp.go` (add
`hashiCorpConfigFromEnv()` if not already in Task 5).
**Do:** Add `case "hashicorp":` to `NewFromEnv` calling `hashiCorpConfigFromEnv()` then
`NewHashiCorp`. The config reader errors MUST name the specific missing env var.
**Verify:** `go test ./internal/store/ -run TestNewFromEnv` → exit 0 (Task 1 tests now GREEN,
plus the 4 pre-existing selector tests still pass). Capture output showing PASS for all.

---

### Task 7 — `.env.example` entries
**Depends on:** Task 6.
**Files:** `/Users/alexandruiacobescu/gooseProjects/mintkey/.env.example` (EDIT).
**Do:** Add a commented block with the 7 `MINTKEY_VAULT_HASHICORP_*` vars from design §6,
each with a one-line purpose comment; mark `MINTKEY_VAULT_HASHICORP_SECRET_ID` SENSITIVE.
**Verify:** for each var name N in design §6: `grep -q N .env.example` → exit 0 (loop all).

---

### Task 8 — Integration conformance test (testcontainers)
**Depends on:** Task 6.
**Files:** `internal/store/hashicorp_integration_test.go` (NEW, `//go:build integration`).
**Do:** Spin a `hashicorp/vault:1.18` `-dev` container, enable AppRole + policy + KV v2, obtain
role_id/secret_id, build a `HashiCorpStore`, and assert the full `Backend` contract: Put→Get(0)
→Get(N)→Revoke(non-current)→ListVersions; monotonic `key_version`; current-flip on second Put;
`ErrRevokeCurrent` revoking current; not-found → `errors.Is(err, sql.ErrNoRows)`; concurrent
Put fan-out yields distinct versions (no dup). Include an AC-4 round-trip via `crypto.Seal`.
**Verify:** `go test ./internal/store/ -tags=integration -run TestHashiCorp` → exit 0.

---

### Task 9 — Token-not-logged test
**Depends on:** Task 8.
**Files:** `internal/store/hashicorp_noleak_test.go` (NEW, `//go:build integration`).
**Do:** Inject a `slog.Logger` writing to a `bytes.Buffer`, run login + a `Get`, assert the
buffer does NOT contain the `secret_id` or the issued token substrings.
**Verify:** `go test ./internal/store/ -tags=integration -run TestHashiCorp_TokenNotLogged`
→ exit 0.

---

### Task 10 — Migration command (TDD)
**Depends on:** Task 6.
**Files:** `cmd/vault-migrate-pg-to-hashicorp/main.go` (NEW),
`cmd/vault-migrate-pg-to-hashicorp/main_test.go` (NEW, `//go:build integration`).
**Do:** Write the test first: seed Postgres `vault.credentials` (testcontainers Postgres +
Liquibase changelog `018`), run `run(ctx, dsn, hashiCorpCfg)`, assert read==inserted, 5-sample
byte-equal PASS, and a second run reports all skipped (idempotent). Then implement `run` reusing
the existing `cmd/vault-migrate-sqlite-to-pg/main.go` patterns (RLS GUC per row, reservoir
sample, DSN redaction) and the `store.NewHashiCorp` write path. ≤ 200 lines.
**Verify:** `go test ./cmd/vault-migrate-pg-to-hashicorp/ -tags=integration` → exit 0.

---

### Task 11 — Makefile target
**Depends on:** Task 10.
**Files:** `/Users/alexandruiacobescu/gooseProjects/mintkey/Makefile` (EDIT).
**Do:** Append the `migrate-vault-to-hashicorp` target from design §9 and add a help line next
to `migrate-vault-sqlite-to-pg`.
**Verify:** `make -n migrate-vault-to-hashicorp` prints the docker run command (dry-run) →
exit 0.

---

### Task 12 — Compose service
**Depends on:** Task 6.
**Files:** `/Users/alexandruiacobescu/gooseProjects/mintkey/infra/compose/docker-compose.yml` (EDIT).
**Do:** Add the `hashicorp-vault` service (profile `hashicorp`) and the five
`MINTKEY_VAULT_HASHICORP_*` env entries on `vault-adapter` per design §7.
**Verify:** `docker compose -f infra/compose/docker-compose.yml --profile hashicorp config`
exits 0 and lists `hashicorp-vault`.

---

### Task 13 — ADR stub
**Depends on:** Task 6.
**Files:** `docs/architecture/01-architecture/adr/0025-vault-storage-backend-hashicorp.md`
(NEW), `docs/architecture/01-architecture/adr/README.md` index + `adrs/` symlink per project
convention.
**Do:** Copy the design §1 ADR stub verbatim, fill `<DATE>`. Add the symlink in `adrs/`.
**Verify:** `test -L docs/architecture/adrs/0025-vault-storage-backend-hashicorp.md` (or the
project's symlink convention) → exit 0; file renders as markdown.

---

### Task 14 — Final gate: lint + full test + selector regression
**Depends on:** all prior.
**Files:** none (verification only).
**Do:** Run the full verification sweep.
**Verify (all must exit 0):**
- `go vet ./...`
- `staticcheck ./...`
- `go test ./internal/store/ -run TestNewFromEnv` (regression: 4 existing + 2 new)
- `go test ./internal/store/ -tags=integration -run TestHashiCorp`
- `go test ./cmd/vault-migrate-pg-to-hashicorp/ -tags=integration`
- For each env var in design §6: `grep -q <VAR> /Users/.../.env.example`
Capture exit codes and salient output (Principle 1 — no "tests pass" without runner output).

---

## Dependency graph

```
1 ─► 2 ─► 3 ─► 5 ─► 6 ─► 7
          4 ─►        ├─► 8 ─► 9
                      ├─► 10 ─► 11
                      ├─► 12
                      └─► 13
all ─► 14
```
