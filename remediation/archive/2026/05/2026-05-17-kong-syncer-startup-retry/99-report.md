# Kong-syncer Startup Retry — Closing Report

**Session:** `2026-05-17-kong-syncer-startup-retry`
**Branch:** `fix/kong-syncer-startup-retry-2026-05-17` (from `main @ fae984d`)
**Status:** **CLOSED**
**Closed:** 2026-05-17

## Outcome

The bug class where `kong-syncer` loses to a startup race against Postgres and falls deaf is closed. Three layers landed atomically on the branch:

| Layer | Commit | Change |
|---|---|---|
| Session scaffold | `e294d4b` | ISSUE_INTAKE + plan + chunks + matrix + escalations + progress |
| Layer 2 — compose | `45ade23` | `services.kong-syncer.depends_on` gained `postgres: condition: service_healthy` |
| Layers 1 + 3 — Go | `40a997a` | initial-reconcile exponential-backoff retry (~5 min budget) + periodic safety-net ticker (5 min default, env-overridable, 0 disables) + 5 hermetic unit tests + 2 new env knobs |

## What changed (and what didn't)

### Changed

- `services/kong-syncer/internal/changes/subscriber.go` — replaced the no-retry initial `reconcile()` call with `initialReconcileWithRetry(ctx)`; added periodic ticker case in `listenLoop`; added `dispatchPeriodicReconcile()`. Backoff base 1s, doubling, capped 256s per attempt, ±25% jitter, total bounded by `InitialRetryMaxDuration`. On exhaustion: warn-log + fall-through to LISTEN (no panic, no `os.Exit`).
- `services/kong-syncer/internal/config/config.go` — added `InitialRetryMaxDuration` (env `KONG_SYNCER_INITIAL_RETRY_MAX_DURATION`, default `5m`) and `PeriodicInterval` (env `KONG_SYNCER_PERIODIC_INTERVAL`, default `5m`; `0` / `"off"` disables periodic).
- `services/kong-syncer/cmd/kong-syncer/main.go` — wired both new knobs into `changes.NewClient` via `WithInitialRetryMaxDuration` + `WithPeriodicInterval`.
- `services/kong-syncer/internal/changes/subscriber_test.go` — 5 new hermetic tests:
  - `TestInitialReconcileSucceedsFirstTry`
  - `TestInitialReconcileRetriesThenSucceeds`
  - `TestInitialReconcileExhaustsRetries`
  - `TestPeriodicReconcileFires`
  - `TestPeriodicDisabledWhenZero`
- `docker-compose.yml` — `services.kong-syncer.depends_on` extended by `postgres: condition: service_healthy` (kong + admin-api entries preserved).
- Session folder (`team/remediation/2026-05-17-kong-syncer-startup-retry/`).

### NOT changed

- `reconcile()`, `generateYAML()`, `pushToKong()` bodies — byte-identical to `main @ fae984d`.
- ADRs (all 20 immutable per ADR-0001). ADR-0010 (Postgres LISTEN/NOTIFY transport) stands as-is — the safety-net is additive over it.
- Other services' `depends_on` (broker, admin-api, mcp-server, etc.). If any of those have analogous gaps, separate sessions.
- admin-api force-reconcile endpoint — out of scope.
- Public API of `changes.Client` — only unexported helpers (`initialReconcileWithRetry`, `dispatchPeriodicReconcile`) were added; no renames or removals.

## Evidence

### Implementer KS-1 verification (executed in implementer subagent)

```
$ cd services/kong-syncer
$ go vet ./...
(no output — clean, exit 0)
$ gofmt -l .
internal/kong/yaml.go            <-- pre-existing, non-owner
internal/wireids/encode_test.go  <-- pre-existing, non-owner
$ go test -race ./internal/changes/... ./internal/config/... -timeout 60s
ok    github.com/mintkey/mintkey/services/kong-syncer/internal/changes  1.823s
?     github.com/mintkey/mintkey/services/kong-syncer/internal/config   [no test files]
```

### Reviewer (Opus, fresh) verification

```
go vet ./...                                              exit 0
go test -race -v ./internal/changes/... -timeout 60s     10/10 PASS, 1.897s total
docker compose config --quiet                             exit 0
python3 ...['services']['kong-syncer']['depends_on']      {postgres, kong, admin-api: service_healthy}
git diff fae984d -- ...subscriber.go | grep public-API   +2 new unexported funcs only; zero removals
rg -n "panic|os\.Exit|log\.Fatal" retry-helper           zero hits inside helper
rg -n "pq\.Listener|sql\.Open|http\.Client" tests        zero hits — tests are hermetic
```

15/15 reviewer checklist items PASS. PASS_ALL gate cleared on first reviewer pass.

### Live behavioral evidence pre-fix (anchored to this conversation, 2026-05-17)

- Pre-manual-NOTIFY: `curl http://localhost:8001/routes` showed 1 Kong route (`/proxy/`) despite 5 active services in admin-api DB.
- `kong-syncer` logs from the 10:38:42 startup attempt:
  ```
  2026/05/17 10:38:42 changes: initial reconcile error:
    fetchActiveServices: db.Conn: dial tcp 192.168.144.5:5432: connect: connection refused
  ```
  ...followed by LISTEN wiring. No retry. No periodic reconcile. State stayed broken until a manual `NOTIFY "mintkey:service" '{"event":"reconcile_request"}'` at 15:39:53 immediately published all 5 services + 10 routes in 20ms.

After this PR lands, both axes are closed: (a) compose orders kong-syncer behind postgres health, and (b) even if a transient blip slips past, the in-process retry + 5 min safety-net heal automatically.

## Owner-locked decisions honored

| Decision | Honored |
|---|---|
| Code retry + compose `depends_on` + periodic safety-net (all three) | ✅ |
| Exponential backoff, ~5 min cap | ✅ (1s base, doubling to 256s, ±25% jitter, budget-capped) |
| Default periodic interval 5 min, env-overridable | ✅ |
| Initial-retry exhaustion: log + fall through to LISTEN, no crash | ✅ |
| Periodic log level INFO | ✅ |
| `reconcile()` / `generateYAML` / `pushToKong` unchanged | ✅ (byte-identical) |

## Verification status

- **In this session, freshly run**: `go vet ./...`, `go test -race ./internal/changes/... ./internal/config/...`, `python3 yaml.safe_load`, `docker compose config --quiet`.
- **NOT re-run in this session** (relying on CI on PR + on local production behavior): full repo `go test ./...`, full docker compose live integration. No claim of "all tests pass" beyond the kong-syncer module.
- **NOT manually staged** (operational sanity-check, recommended for the operator post-merge):
  1. `docker compose down kong-syncer postgres && docker compose up -d kong-syncer postgres` and watch kong-syncer logs for `kong_sync.initial_reconcile_ok` or `kong_sync.initial_retry attempt=N` followed by ok.
  2. Set `KONG_SYNCER_PERIODIC_INTERVAL=10s` locally; observe `kong_sync.periodic_reconcile` every 10s; manually `DELETE` a Kong route and watch it reappear on the next tick.

## Residuals (intentionally not addressed)

- **`dispatchPeriodicReconcile` does not clear `LastErr` on success** — matches the existing NOTIFY-driven reconcile path. If `/health` ergonomics ever feel stale, separate one-line change.
- **Sibling-service `depends_on` audit** — not in scope. Other services may benefit from analogous fixes.
- **No admin-api force-reconcile endpoint** — periodic ticker already eliminates the only failure mode that motivated such an endpoint.

## Links

- Commits: `e294d4b` (scaffold) · `45ade23` (compose) · `40a997a` (Go)
- PR: _populated after `gh pr create`_
- Branch base: `main @ fae984d` (PR #54 merge of doc-state-sync; v0.1.0-prealpha tag day)
- Triggered by: investigation of Hermes/Ares agent's "Kong routes missing" report earlier in this 2026-05-17 working session
