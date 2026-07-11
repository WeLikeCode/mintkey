# CI: cover the apps/ Go modules (close the coverage gap) + land 2 proxy fixes

## Why

`ci.yml` runs `go vet ./...`, `go test ./... -short`, and golangci-lint at the **repo root**. Under the go.work workspace, root `./...` resolves to **only `packages/go`** — `go list ./...` returns **0** packages from the app modules. So the entire `apps/proxy-plugin`, `apps/broker`, `apps/email-proxy`, `apps/kong-syncer`, `apps/ssh-proxy`, `apps/vault-adapter` are **never vetted, linted, or unit-tested in CI**. CI is green because it never runs those checks — real issues hide there:

- `go vet` (stdmethods): `apps/broker/internal/metrics/metrics.go:53` and `apps/proxy-plugin/internal/metrics/metrics.go:110` — `WriteTo(io.Writer) error` collides with the `io.WriterTo` interface method name but has the wrong signature.
- golangci-lint (proxy-plugin, 4): `internal/audit/emitter_test.go:171` + `internal/credential/injector_test.go:151` (`errcheck`), `internal/credential/exchanger.go:528` (`unused` `isNetworkError`), `internal/credential/exchanger.go:544` (`gosimple` S1008 — inside `isNetworkError`).

All app-module `go test -short` runs pass; the other five modules are golangci-clean.

## What Changes

- **Extend `ci.yml`** so `lint-go` (`go vet` + golangci-lint) and `test-go-unit` (`go test -short`) run against **every go.work module**, not just the root.
- **Fix the issues that surface** so the now-covered checks pass: rename the metrics `WriteTo` method (→ `WriteMetricsTo`, matching the existing `auditq.Queue.WriteMetricsTo` convention) + update callers; delete the unused `isNetworkError` (removes both the `unused` and the S1008 finding inside it); explicitly discard the two unchecked test-helper error returns.
- **Land the 2 already-rebased proxy fixes** on this branch in the same PR: `67e21da` form-encode token-exchange body for `x-www-form-urlencoded` services (Contabo/Keycloak); `442de92` raise vault-adapter GetCredential dial timeout 5s→60s.

## Capabilities

### New Capabilities
- `ci-go-coverage`: CI vets, lints, and unit-tests all workspace Go modules.

## Impact

- **CI**: `.github/workflows/ci.yml` (`lint-go`, `test-go-unit` jobs) iterate go.work modules.
- **Go**: `apps/broker/internal/metrics/metrics.go`, `apps/proxy-plugin/internal/metrics/metrics.go` (+ their callers, e.g. `cmd/proxy-plugin/main.go`); `apps/proxy-plugin/internal/credential/exchanger.go` (remove dead fn); `apps/proxy-plugin/internal/audit/emitter_test.go`, `apps/proxy-plugin/internal/credential/injector_test.go`.
- **No behavior change**: metrics output is identical (method rename only); the WriteTo rename does not alter the `/metrics` payload. The 2 proxy fixes are already committed.
- **Out of scope**: golangci-lint config tuning / adding linters beyond current defaults (v1.64.8); the container-scan (Trivy base-image CVEs), Playwright, CodeQL, scorecard workflows; the stray `apps/admin-api/src/admin_api/api/_ssh_test.py` (Python, not in CI's `tests/unit/` collection path); mypy/ruff (already green).
