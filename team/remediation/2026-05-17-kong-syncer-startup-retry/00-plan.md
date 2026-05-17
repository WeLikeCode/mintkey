# Kong-syncer Startup Retry — Session Plan

**Session:** `2026-05-17-kong-syncer-startup-retry`
**Branch:** `fix/kong-syncer-startup-retry-2026-05-17` (from main @ `fae984d`)
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Mission

Close the outage class where `kong-syncer` falls deaf after a startup race against Postgres. Three-layer fix:
1. **Code retry** on initial reconcile (exponential backoff, ~5 min cap)
2. **Compose `depends_on`** kong-syncer → postgres `service_healthy`
3. **Periodic safety-net reconcile** every N min (default 5 min, env-configurable)

## Hard rules

- No `Co-Authored-By` trailer.
- No `--no-verify`.
- No edits to accepted ADRs.
- No product behavior changes outside the kong-syncer scope (no admin-api changes; reconcile()/generateYAML()/pushToKong() unchanged).
- Atomic commits per chunk.
- Validate via tools: `go test`, `go vet`, `python3 -c "yaml.safe_load(...)"`.

## Chunks

| # | Wave | Chunk | Owner files |
|---|---|---|---|
| KS-1 | 1 | Code: retry helper + initial reconcile retry + periodic safety-net + config knobs + tests | `services/kong-syncer/internal/changes/subscriber.go`, `services/kong-syncer/internal/config/config.go`, `services/kong-syncer/cmd/kong-syncer/main.go`, `services/kong-syncer/internal/changes/subscriber_test.go` |
| KS-2 | 1 (parallel — disjoint file) | Compose: `depends_on` postgres `service_healthy` | `docker-compose.yml` |

Wave 2: 1 fresh REVIEWER (Opus) covers both chunks (small surface; single review pass).

## Closing acceptance criteria

- All Go unit tests pass: `go test ./services/kong-syncer/...`
- `go vet ./...` clean
- YAML parses cleanly
- Local live-test: stop postgres → restart kong-syncer → backoff logs visible → start postgres → reconcile succeeds → routes appear in Kong
- Periodic safety-net: set env `KONG_SYNCER_PERIODIC_INTERVAL=10s`; observe periodic logs; delete a Kong route manually; next tick restores it
- 99-report written
- PR opened
