# Issue Intake — 2026-05-17-integration-tests-timeout

## Problem statement (required)

The CI `Integration Tests` job's "Start stack" step times out after 120 seconds on cold runners.
`docker compose up -d` triggers builds for 10 services (seed-job, vault-adapter, admin-api,
admin-ui, mcp-server, broker, kong-syncer, proxy-plugin, mock-backend, jaeger-auth) before any
container can start. On cold cache that build phase alone takes 3-10+ minutes, well beyond the
120 s wait-loop that checks for `running` state.

## User-visible symptom (required)

CI `Integration Tests` job exits with code 1 on the "Start stack" step — `timeout 120` expires
before `docker compose ps` shows all core services in `running` state. Integration and smoke
tests never run.

## Expected behavior (required)

All non-ephemeral services reach `running` state before the wait-loop times out; integration and
smoke tests execute and report real pass/fail results.

## Evidence (required)

- `docker-compose.yml`: 10 services have a `build:` directive (verified via `grep -c "build:"` =
  10) — seed-job, vault-adapter, admin-api, admin-ui, mcp-server, broker, kong-syncer,
  proxy-plugin, mock-backend, jaeger-auth.
- `.github/workflows/ci.yml:222-232`: single "Start stack" step runs `docker compose up -d`
  (triggers builds inline) followed immediately by `timeout 120` wait-loop. No pre-build step.
- Design analysis: build phase on cold CI cache far exceeds 120 s; the wait-loop cannot succeed
  because images are still being built when the timeout fires.

## Scope (required)

`.github/workflows/ci.yml` — `test-integration:` job only (lines 214-249).

## Out of scope (required)

- All other CI workflows.
- `docker-compose.yml` service definitions.
- Dockerfiles.
- Any application source code.

## Risk level (required)

CI — blocking integration tests from running; no production or data risk.

## Verification target (required)

```
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
```

Plus structural check: `test-integration` job must have a `Build stack images` step before
`Start stack`, and the wait-loop timeout must be >= 180 s.

## Owner decisions needed (if any)

None — the split-build approach (Option A) is unambiguous and within scope.

---

## Checklist (orchestrator may not start without all required fields)

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line or command)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (or "none")
