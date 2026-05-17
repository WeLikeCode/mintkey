# Issue Intake — 2026-05-17-kong-syncer-startup-retry

**Session:** `team/remediation/2026-05-17-kong-syncer-startup-retry/`
**Branch:** `fix/kong-syncer-startup-retry-2026-05-17` (from main @ `fae984d`)
**Reported:** 2026-05-17
**Reporter:** Owner — "open a session for the kong-syncer startup retry bug"
**Triggered by:** Investigation of Hermes/Ares agent report ("Kong's DB only has /proxy/ routes registered"). Ares misattributed the responsibility to proxy-plugin; the actual responsible component is kong-syncer.

## Problem statement (required)

`kong-syncer` performs exactly ONE initial reconcile at startup and does not retry on failure. If Postgres is unreachable at startup (e.g., docker compose ordering issue, momentary blip during stack restart), the initial reconcile fails with `connection refused`, kong-syncer logs the error, then proceeds straight to `LISTEN mintkey:service` and waits forever for a NOTIFY that may never come for already-present services. Result: Kong's declarative config remains whatever it was last (often empty / mock-backend-only), even though `services WHERE status='active'` in Postgres has rows.

Compounding factor: `docker-compose.yml` `kong-syncer.depends_on` only lists `kong` and `admin-api` (both `service_healthy`), NOT `postgres`. So the startup race against Postgres isn't constrained by the compose dependency graph either.

## User-visible symptom (required)

- `curl http://10.243.1.200:8000/v1/call/<svc_id>/<path>` returns `no Route matched` from Kong even though the service exists in admin-api's DB with `status='active'`.
- Hermes/Ares (agent) sees the same — cannot reach GitHub via the brokered proxy.
- Operator-side, `curl http://localhost:8001/routes` shows zero `/v1/call/...` routes despite 5 active services in DB.
- Forensic anchor (this conversation 2026-05-17): kong-syncer logs at `15:39:53` after manual `NOTIFY "mintkey:service" '{"event":"reconcile_request"}'` showed:
  ```
  received NOTIFY on "mintkey:service" (payload="{\"event\":\"reconcile_request\"}") — triggering reconcile
  level=info event=kong_sync routes_published=5 elapsed_ms=20
  ```
  Confirming 5 services were sitting in DB the entire time, unreflected in Kong.

## Expected behavior (required)

1. **Code retry**: kong-syncer's initial reconcile retries with exponential backoff for up to ~5 minutes (configurable). On every retry attempt, logs a structured message with attempt number and elapsed time. If retries exhaust without success, kong-syncer keeps running (does not crash) and proceeds to LISTEN mode — so a later NOTIFY can still trigger reconcile.

2. **Compose dependency**: `kong-syncer.depends_on` includes `postgres: condition: service_healthy`. (Postgres healthcheck already declared via `pg_isready`.)

3. **Periodic safety-net reconcile**: kong-syncer also performs a periodic reconcile at a fixed interval (default 5 min, env-configurable) regardless of LISTEN traffic. Logs each tick. Catches:
   - Missed NOTIFY (channel hiccup, kong-syncer connection dropped briefly during a NOTIFY)
   - Manual DB edits that don't fire the trigger
   - Mismatched declarative-vs-actual Kong config (Kong returns 304 if already current — harmless)

## Evidence (required)

Confirmed empirically 2026-05-17:

- `services/kong-syncer/internal/changes/subscriber.go:166-168` (initial reconcile, no retry):
  ```
  if err := c.reconcile(); err != nil {
      log.Printf("changes: initial reconcile error: %v", err)
  }
  ```
  Followed directly by `pq.Listener` wiring — NO retry, NO crash.

- `services/kong-syncer/internal/changes/subscriber.go:210-263` (LISTEN loop): reacts to NOTIFY events and ctx cancellation only. No periodic timer.

- `docker-compose.yml` kong-syncer.depends_on parsed: `{kong: service_healthy, admin-api: service_healthy}`. Postgres NOT included.

- `docker-compose.yml` postgres.healthcheck: `pg_isready -U mintkey_migrate -d mintkey` — already defined and working.

- Live kong-syncer logs over 2 recent startups:
  ```
  2026/05/17 06:10:57 changes: initial reconcile error: pushToKong: kong /config returned 304
  2026/05/17 10:38:42 changes: initial reconcile error: fetchActiveServices: db.Conn: dial tcp 192.168.144.5:5432: connect: connection refused
  ```
  Second one was a real Postgres race; no retry happened; LISTEN wired up afterward; 5+ hours later, Kong still had zero per-service routes until manual NOTIFY.

## Scope (required)

May be changed:
- `services/kong-syncer/internal/changes/subscriber.go` — add retry helper around initial reconcile; add periodic-reconcile ticker in the LISTEN loop.
- `services/kong-syncer/internal/config/config.go` — add env-configurable knobs (`KONG_SYNCER_INITIAL_RETRY_MAX_DURATION`, `KONG_SYNCER_PERIODIC_INTERVAL`).
- `services/kong-syncer/cmd/kong-syncer/main.go` — read new config knobs, pass into subscriber Client.
- `services/kong-syncer/internal/changes/subscriber_test.go` — add unit tests for retry (fakeable clock + fakeable reconcile fn) and periodic ticker.
- `docker-compose.yml` — extend `kong-syncer.depends_on` with `postgres: condition: service_healthy`.
- Session folder.

## Out of scope (required)

- Other services' depends_on hygiene. (broker, admin-api, mcp-server etc. may have similar gaps; separate session if/when they surface.)
- Refactoring the LISTEN/NOTIFY transport itself. ADR-0010 (Postgres LISTEN/NOTIFY as change channel) stays.
- Rewriting reconcile() / generate-YAML / pushToKong() — those work fine.
- Adding admin-api endpoint to force-reconcile from outside (separate concern).
- The mock-backend route already in Kong — unaffected.

## Risk level (required)

- **Operator availability**: high positive — closes a real outage class (kong-syncer goes deaf after Postgres race + stays deaf for hours).
- **Behavior regression**: low — retry + periodic are additive over existing reconcile logic; reconcile() itself is unchanged.
- **Performance**: negligible — periodic safety-net runs once per 5 min; Kong responds with 304 when nothing changed (harmless).
- **Log noise**: small — one INFO line per 5 min on each kong-syncer instance. Acceptable; can be DEBUG if it's too chatty.

## Verification target (required)

### Code retry (subscriber.go)
- Run `go test ./internal/changes/...` — new unit tests cover:
  - Initial reconcile succeeds first try → no retries logged, LISTEN proceeds.
  - Initial reconcile fails 2 times then succeeds → 2 retry logs, LISTEN proceeds.
  - Initial reconcile fails the entire backoff window → final error logged, LISTEN still proceeds (no crash).
- Live test: stop postgres → restart kong-syncer → logs show "retry attempt 1, retry attempt 2…" → start postgres → next attempt succeeds → routes appear in Kong.

### Compose dependency
- `python3 -c "import yaml; d=yaml.safe_load(open('docker-compose.yml')); print(d['services']['kong-syncer']['depends_on'])"` includes `postgres: {condition: service_healthy}`.
- `docker compose up -d --force-recreate kong-syncer` waits for postgres to be healthy before starting.

### Periodic safety-net
- Set `KONG_SYNCER_PERIODIC_INTERVAL=10s` locally for fast verification.
- Start kong-syncer; observe ~one reconcile log every 10s.
- DELETE the route in Kong manually (`curl -X DELETE ...`); next periodic reconcile re-adds it.

### Final integration
- Default config: `docker compose up -d --force-recreate kong-syncer`; observe one initial reconcile (with retry on failure) + periodic reconciles at the default interval.
- Existing CI Go-unit tests + Integration Tests on PR still green.

## Owner decisions

- ✅ **Scope**: full 3-layer fix — code retry + compose `depends_on` + periodic safety-net.
- ✅ **Retry backoff**: exponential (e.g., 1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s; jitter optional), capped at ~5 min total. Implementer picks exact schedule per Go idioms.
- ✅ **Periodic interval default**: 5 min. Env-overridable for testing.
- ✅ **Failure behavior after exhausting initial retries**: log + proceed to LISTEN mode (do NOT crash). The periodic safety-net catches recovery.
- ✅ **Log level for periodic ticks**: INFO. Can be revisited if too noisy.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with file:line + log snippets)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted
