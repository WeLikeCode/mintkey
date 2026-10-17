# Tasks — CI coverage for apps/ Go modules

## C1 — Fix the surfaced Go issues (make all app modules vet+lint clean)

- [x] 1.1 `apps/broker/internal/metrics/metrics.go` + `apps/proxy-plugin/internal/metrics/metrics.go`: rename `WriteTo(w io.Writer) error` → `WriteMetricsTo`; `grep -rn '\.WriteTo(' apps/broker apps/proxy-plugin` and update every caller (e.g. `cmd/proxy-plugin/main.go`). Build both modules.
- [x] 1.2 `apps/proxy-plugin/internal/credential/exchanger.go`: delete the unused `isNetworkError` function (verify zero callers first). Removes the `unused` + S1008 findings.
- [x] 1.3 `apps/proxy-plugin/internal/audit/emitter_test.go:171` + `internal/credential/injector_test.go:151`: explicitly discard the unchecked error returns (`_ =` / deferred `_ =`).
- [x] 1.4 Verify: for EACH go.work module `go vet ./...` exit 0; `cd apps/proxy-plugin && go run github.com/golangci/golangci-lint/cmd/golangci-lint@v1.64.8 run --timeout=5m ./...` exit 0; `go test ./... -short` exit 0 in every module. Report exit codes.

## C2 — Extend ci.yml to cover all go.work modules

- [x] 2.1 `.github/workflows/ci.yml` `lint-go`: iterate go.work modules for `go vet` (loop) and golangci-lint (matrix over module dirs, or looped pinned binary) — pin `v1.64.8`, `--timeout=5m`; the job MUST fail if ANY module has findings.
- [x] 2.2 `.github/workflows/ci.yml` `test-go-unit`: iterate go.work modules for `go test ./... -short -timeout=120s`; MUST fail if ANY module fails.
- [x] 2.3 Verify: YAML parses; run the exact new loop/commands locally → proxy-plugin + broker are exercised and pass; deliberately (temporarily) re-break one module and confirm the loop returns non-zero (no swallowed exit), then restore.

## C3 — Integration & land (orchestrator)

- [x] 3.1 Full local sweep: all go.work modules vet+golangci+test green; `packages/go` unaffected; YAML valid.
- [x] 3.2 Independent review of the whole diff (fixes + CI change + the 2 proxy fixes).
- [x] 3.3 Commit; merge branch → main; push. (CI on the resulting PR/main must be green with the new coverage.)
