# Design — CI coverage for apps/ Go modules

## Ground truth (enumerated locally 2026-07-11, go 1.26.2, golangci-lint v1.64.8)

go.work modules: `.`, `apps/broker`, `apps/email-proxy`, `apps/kong-syncer`, `apps/proxy-plugin`, `apps/ssh-proxy`, `apps/vault-adapter`.

| Module | `go vet ./...` | golangci-lint | `go test -short` |
|---|---|---|---|
| . (packages/go) | pass | 0 | pass |
| broker | **FAIL** metrics.go:53 WriteTo | 0 | pass |
| email-proxy | pass | 0 | pass |
| kong-syncer | pass | 0 | pass |
| proxy-plugin | **FAIL** metrics.go:110 WriteTo | **4** | pass |
| ssh-proxy | pass | 0 | pass |
| vault-adapter | pass | 0 | pass |

proxy-plugin golangci (4): `emitter_test.go:171` errcheck (`tp.Shutdown`), `injector_test.go:151` errcheck (`credential.Inject`), `exchanger.go:528` unused `isNetworkError`, `exchanger.go:544` gosimple S1008 (inside `isNetworkError`).

## Fix design (minimal, no behavior change)

1. **`WriteTo` stdmethods (go vet)** — rename `func (m *Metrics) WriteTo(w io.Writer) error` → `WriteMetricsTo` in `apps/broker/internal/metrics/metrics.go` and `apps/proxy-plugin/internal/metrics/metrics.go`, and update every caller (`grep -rn '\.WriteTo(' apps/broker apps/proxy-plugin` — e.g. `cmd/proxy-plugin/main.go`). Chosen over changing the signature to `(int64, error)` because a rename is smaller, matches the existing `auditq.Queue.WriteMetricsTo` name, and needs no caller-side byte accounting. The `/metrics` output bytes are unchanged.
2. **unused `isNetworkError` + S1008** — delete the whole `isNetworkError` function (`exchanger.go` ~lines 527–548). It has no callers (`grep -rn isNetworkError` shows only the definition + its doc comment). Deleting it removes BOTH the `unused` and the S1008 findings (S1008 is inside it). Do not "fix" S1008 in place — the function is dead.
3. **errcheck (test files)** — `emitter_test.go:171` `defer tp.Shutdown(context.Background())` → `defer func() { _ = tp.Shutdown(context.Background()) }()`; `injector_test.go:151` `credential.Inject(req, cred)` → `_ = credential.Inject(req, cred)`. Test-only; matches the codebase's existing `_ =` discard idiom.

## CI extension design (`.github/workflows/ci.yml`)

The go jobs must iterate the go.work modules. Use a shell loop driven by `go work edit -json` so new modules are auto-covered (no hard-coded list to drift):

- **`lint-go` job**: after `setup-go`, replace `go vet ./...` with a loop:
  ```
  for d in $(go work edit -json | python3 -c "import sys,json;[print(u['DiskPath']) for u in json.load(sys.stdin)['Use']]"); do
    echo "::group::go vet $d"; (cd "$d" && go vet ./...) || exit 1; echo "::endgroup::"
  done
  ```
  Replace the single `golangci-lint-action` step with a **matrix** of that action over the module dirs (the action supports `working-directory`), OR install golangci-lint once and loop it per module. Prefer the matrix (parallel, first-class annotations); `version: v1.64.8` pinned (not `latest`, which drifts) with `args: --timeout=5m`. If a matrix is too invasive, a loop installing the pinned binary is acceptable — the implementer picks; either MUST fail the job on any module's findings.
- **`test-go-unit` job**: replace `go test ./... -v -short -timeout=120s` with the same go.work loop running `go test ./... -short -timeout=120s` per module (drop `-v` to keep logs readable, or keep it — implementer's call).

Keep `packages/go` covered (it already is, as `.`). Do NOT add `-race`/integration here (out of scope).

## Acceptance
- Every go.work module: `go vet ./...` exit 0.
- proxy-plugin: golangci-lint v1.64.8 exit 0 (0 findings); other modules stay 0.
- Every module: `go test ./... -short` exit 0.
- `ci.yml`'s new lint-go/test-go commands, run locally, exercise proxy-plugin/broker (grep the job for the loop; run the loop → passes).
- YAML valid (`python3 -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))"`).
- The 2 proxy fixes (form-encode Exchange, vault dial-timeout) remain intact; `Exchange`/`GetCredential` behavior unchanged.

## Risk / notes
- Rename touches a hot path (`/metrics`); a missed caller = build break — caught by `go build ./...` per module + the extended test-go job.
- The matrix/loop must `exit 1` on any module failure (a loop that swallows non-zero exit is the classic trap — verify the extended job actually fails when a module fails).
