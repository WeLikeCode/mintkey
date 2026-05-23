# Kong-syncer Startup Retry — Chunk Catalog

**Session:** `2026-05-17-kong-syncer-startup-retry`
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)
**Phase 0:** ✅ baseline + intake built by ORCHESTRATOR (see `ISSUE_INTAKE.md`)

---

## Locked decisions (from owner intake)

| Decision | Value |
|---|---|
| Scope | Code retry + compose `depends_on` + periodic safety-net (all three) |
| Retry backoff | Exponential — implementer picks schedule; ~5 min total cap |
| Initial retry exhaustion | Log + proceed to LISTEN (do NOT crash) |
| Periodic interval default | 5 min; env-overridable via `KONG_SYNCER_PERIODIC_INTERVAL` |
| Initial retry env knob | `KONG_SYNCER_INITIAL_RETRY_MAX_DURATION` (default 5m) |
| Log level for periodic ticks | INFO |
| Reconcile() / generateYAML / pushToKong | Out of scope — DO NOT TOUCH |
| ADR-0010 | LISTEN/NOTIFY transport stays — only add safety-net on top |
| Co-Authored-By | NONE on any commit |

---

## Universal hard rules

- No `Co-Authored-By` trailer
- No `--no-verify`
- No edits to accepted ADRs
- No edits outside the in-scope file set
- Atomic commits per chunk
- Validate via tools:
  - `go test ./internal/changes/... ./internal/config/...` (inside `services/kong-syncer/`)
  - `go vet ./...`
  - `gofmt -l .` ⇒ no output
  - `python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"`
- Update `02-matrix.md` row(s) before commit
- Implementer DoD: green test run pasted as evidence inside the chunk message (per `feedback_validate_via_tools`)

---

## Wave 0 — Orchestrator scaffold

C-1: **Session scaffold + intake + plan**

- Owner: ORCHESTRATOR
- Status: ✅ done
- Output: `ISSUE_INTAKE.md`, `00-plan.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `03-escalations.md`, `04-progress.md`

---

## Wave 1 — parallel implementer chunks (disjoint files)

### KS-1: Go retry + periodic safety-net + config knobs + unit tests

| Field | Value |
|---|---|
| Owner files (only) | `services/kong-syncer/internal/changes/subscriber.go`<br>`services/kong-syncer/internal/config/config.go`<br>`services/kong-syncer/cmd/kong-syncer/main.go`<br>`services/kong-syncer/internal/changes/subscriber_test.go` |
| Forbidden | reconcile(), generateYAML(), pushToKong() bodies; admin-api; broker; other services |
| Test invariant | All existing tests still pass; new tests target the retry helper + periodic ticker in isolation |

**Required outcomes:**

1. **Config knobs** in `config.go`:
   - `KONG_SYNCER_INITIAL_RETRY_MAX_DURATION` (default `5m`, parseable as `time.Duration`).
   - `KONG_SYNCER_PERIODIC_INTERVAL` (default `5m`, parseable as `time.Duration`). Value `0` or `"off"` disables periodic safety-net.
   - Both threaded through the existing config struct used by `main.go` / subscriber `Client`.

2. **Initial reconcile retry** in `subscriber.go` (replace lines 166-168 era code):
   - Exponential backoff: start at 1s, double each attempt (1, 2, 4, 8, 16, 32, 64, 128, 256s) capped by `InitialRetryMaxDuration`. Implementer may add ±25% jitter.
   - Each attempt logs structured: `level=info event=kong_sync.initial_retry attempt=N elapsed_ms=X next_backoff_ms=Y err="..."` (or equivalent — keep consistent with existing log format if structured logging is in place).
   - On final-attempt-still-failing: log `level=warn event=kong_sync.initial_retry_exhausted total_elapsed_ms=X attempts=N` and **proceed to LISTEN mode without crashing**. Periodic safety-net or a future NOTIFY will catch the recovery.
   - On success: log `level=info event=kong_sync.initial_reconcile_ok attempt=N elapsed_ms=X`.

3. **Periodic safety-net** in the LISTEN loop in `subscriber.go`:
   - Add a `time.Ticker` (or equivalent) at `cfg.PeriodicInterval`. If interval is `0`, skip ticker entirely.
   - On each tick: invoke `reconcile()` and log `level=info event=kong_sync.periodic_reconcile elapsed_ms=X` on success or `level=error event=kong_sync.periodic_reconcile_err err=...` on failure (no crash).
   - The select must still cleanly handle: NOTIFY event, periodic tick, ctx.Done(). Order them so a NOTIFY-driven reconcile that races with a tick doesn't double-reconcile; a coalescing latch on `reconcileRequested` is acceptable but not required.

4. **main.go wiring**:
   - Read the two new config values; pass them through to subscriber Client constructor or its options.

5. **Unit tests** in `subscriber_test.go`:
   - `TestInitialReconcileSucceedsFirstTry` — reconcile fn returns nil → 0 retries, LISTEN setup proceeds.
   - `TestInitialReconcileRetriesThenSucceeds` — fn returns error N times then nil → N retries logged, LISTEN proceeds.
   - `TestInitialReconcileExhaustsRetries` — fn always errors → after the configured duration, exhaustion logged, LISTEN proceeds (no panic).
   - `TestPeriodicReconcileFires` — with a tiny interval and a fake clock or fake ticker channel, advance time and assert reconcile fn is invoked.
   - `TestPeriodicDisabledWhenZero` — interval `0` → no ticker fires; reconcile fn only invoked by NOTIFY/initial.
   - Tests MUST be hermetic — no live Postgres, no live Kong. Inject a fake reconcile function and a fake clock if `time.Now/Ticker` is in play. If existing code talks directly to `time.NewTicker`, refactor minimally to inject; do not invent a new clock abstraction project-wide.

6. **Logging hygiene**:
   - Keep log lines on a single line each (no embedded newlines).
   - Do not log full Kong YAML bodies, secrets, or DB DSNs.

7. **Behavior unchanged**:
   - `reconcile()` itself, the YAML emitter, and `pushToKong()` are untouched.
   - LISTEN payload semantics unchanged.
   - Existing public/exported API of `changes.Client` is preserved (no breaking renames).

**Verification commands the implementer MUST run and paste in chunk message:**

```bash
cd services/kong-syncer
go vet ./...
gofmt -l .
go test ./internal/changes/... ./internal/config/...
```

All three must be green and the output must be quoted in the chunk completion message.

### KS-2: docker-compose `depends_on` for postgres

| Field | Value |
|---|---|
| Owner files (only) | `docker-compose.yml` |
| Forbidden | any other service block; any other file |

**Required outcome:**

Under `services.kong-syncer.depends_on`, add `postgres: condition: service_healthy`. Preserve existing entries (`kong` and `admin-api`).

Existing block (for reference; do not paraphrase):
```yaml
  kong-syncer:
    ...
    depends_on:
      kong:
        condition: service_healthy
      admin-api:
        condition: service_healthy
```

Target:
```yaml
  kong-syncer:
    ...
    depends_on:
      postgres:
        condition: service_healthy
      kong:
        condition: service_healthy
      admin-api:
        condition: service_healthy
```

(Alphabetical or original ordering both acceptable. Postgres healthcheck already exists — verify with a quick read but do not edit it.)

**Verification commands the implementer MUST run:**

```bash
python3 -c "import yaml; d=yaml.safe_load(open('docker-compose.yml')); print(d['services']['kong-syncer']['depends_on'])"
docker compose config --quiet
```

Output must show `postgres: {'condition': 'service_healthy'}` (and the original two) and `docker compose config` must exit 0. Paste both in chunk message.

---

## Wave 2 — REVIEWER (Opus, fresh)

| # | Chunk | Reviewer task |
|---|---|---|
| REV-KS-1 | KS-1 | Re-read final `subscriber.go`, `config.go`, `main.go`, `subscriber_test.go` end-to-end. Verify: (a) retry helper present with exponential backoff capped at cfg duration; (b) initial-retry-exhausted does NOT crash, falls through to LISTEN; (c) periodic ticker present and disabled when interval is `0`; (d) reconcile()/generateYAML/pushToKong bodies unchanged; (e) tests are hermetic (no real Postgres / Kong); (f) `go vet`, `gofmt -l`, `go test ./...` green; (g) no Co-Authored-By trailer staged. |
| REV-KS-2 | KS-2 | Re-read `docker-compose.yml` diff. Verify: (a) only `kong-syncer.depends_on` changed; (b) `postgres: condition: service_healthy` added; (c) original 2 entries preserved; (d) `docker compose config --quiet` exits 0; (e) no whitespace damage elsewhere. |

PASS_ALL gate: both must pass before ORCHESTRATOR pushes branch and opens PR.

3-strike hard-stop per chunk. On 3rd implementer FAIL, ORCHESTRATOR STOPS and escalates to owner via `03-escalations.md`.

---

## Wave 3 — Push + PR + Admin-merge

- Commit each chunk atomically (KS-1 then KS-2 — or vice-versa).
- Push `fix/kong-syncer-startup-retry-2026-05-17` to origin.
- Open PR via `gh pr create`; reference this session folder.
- Mintkey proxy admin-merge after CI green.

---

## Status legend (`02-matrix.md`)

| Symbol | Meaning |
|---|---|
| ⬜ | Pending |
| 🔵 | Dispatched (in-flight) |
| ✅ | Reviewer PASS |
| ❌ | Reviewer FAIL — new implementer dispatched |
| 🛑 | Hard-stop — 3 failures; awaiting user |
| ⚠️ | Escalated — awaiting owner decision |
