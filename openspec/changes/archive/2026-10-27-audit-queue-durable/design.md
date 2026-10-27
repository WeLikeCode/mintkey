# Design: audit-queue-durable

## Context

`packages/go/auditq` is the audit queue of the broker, the proxy plugin, the email proxy and the SSH proxy. They build
it with `auditq.New` or `auditq.NewWithConfig`, call `Replay` and `Start`, `Enqueue` on the request path, expose
`WriteMetricsTo` (broker, proxy plugin) and `Close`/`CloseWithContext` at shutdown. Today (`queue.go`):

- `Enqueue` appends `json.Marshal(event)` and `\n` to the WAL under `walMu`, then sends the event to a channel of
  1,000 without blocking. When the channel is full the event is only in the WAL, and only `Replay` at the next start
  reads it again.
- One goroutine drains the channel. `emitWithRetry` tries an event up to five times (250 ms doubling), then appends it
  to `<wal>.dead` and tombstones it; the next event waits for all of that.
- A tombstone rewrites the whole file (`os.WriteFile`, the first line equal to the event's JSON replaced by `~`).
- `compact.go` drops blank lines and lines whose trimmed text starts with `~`, through a temporary file, fsync and
  rename, on a timer or a size threshold; `TriggerCompact` runs it at once.
- `metrics.go` writes four families: `auditq_dead_letter_events_total`, `auditq_dead_letter_file_size_bytes`,
  `auditq_wal_size_bytes`, `auditq_wal_pending_events`.

The sink is admin-api's `POST /v1/internal/audit/emit` (`admin_api.api.internal.audit_emit_endpoint`), or any URL an
operator points the queue at. It answers 401 for an unknown service token, 429 with `Retry-After` above its rate
limit, 422 for an event type not in its list or a tenant id that is not a UUID, 403 when the actor does not belong to
the tenant, and 5xx when its database fails.

## Decisions

**D1. The WAL is the queue.** The drainer reads pending lines from the WAL instead of a channel, so an event is
delivered while the process runs however many arrived while the sink was down. `Enqueue` keeps its signature: it
appends the line (adding a `\n` first when the file does not end with one, so a line cut by a crash cannot swallow the
next event), adds 1 to the backlog and wakes the drainer through a channel of capacity 1 (a send that would block is
dropped: a wake is already pending). When the append fails, the event goes to an in-memory channel of 1,000 (today's
fallback: the event is still delivered while the process runs) and adds 1 to the backlog; when that channel is full
too, the event is lost with an error log, as today. `Replay` keeps its name and call sites but now only sets the
backlog from the WAL and logs the count; it no longer pushes events anywhere.

**D2. A pass, rounds, and progress-based backoff.** One drainer goroutine:

```
delay = initial delay
loop:
  batch = readBatch()                 # under walMu: up to batch size pending lines in file order, with offsets;
                                      # unreadable lines dead-lettered and tombstoned; backlog = pending + memory;
                                      # then every event waiting in the memory channel
  if batch is empty: return if closing; wait for a wake or the close; continue
  for each round = the next min(concurrency, left) entries of batch:
      n = deliverRound(round)          # one goroutine per entry; each settles its entry as soon as it is answered
      if n > 0: delay = initial delay; continue
      if closing: return               # never wait while closing
      log one warning (round size, last error, next delay)
      wait delay or the close; delay = nextRetryDelay(delay, max delay)
  send the memory events of the batch that were neither delivered nor refused back to the memory channel
  if closing and no round of this pass made progress: return
```

Settling an entry: 2xx → tombstone (a memory event: backlog −1); `isRejected(status)` → dead-letter record, then
tombstone (memory: backlog −1); anything else → nothing (memory: kept for the send-back). `n` counts the delivered
and refused entries. Backoff applies only to a round in which nothing moved: a round in which one event keeps
failing (for example admin-api's 403 for an actor outside the tenant) but others are delivered does not slow the
queue. While the sink is down, each round costs one request per event of the round per delay, at most 4 per 30 s
by default. A
failed event is tried again by the next pass, after the rest of its batch.

**D3. Which answers are final.** Only 400, 413 and 422 are a refusal: the sink parsed the request and will never
accept that event. 401 (a token an operator fixes), 403 (many sinks answer 403 for a credential problem, which would
otherwise dead-letter every event), 404 (a wrong URL), 408, 429 and 5xx are retried, as are transport errors and the
10 s client timeout. `<wal>.dead` therefore means "refused by the sink" (or an unreadable WAL line), never "gave up";
the existing dead-letter metrics keep their names and now count exactly that.

**D4. In-place tombstones keep the format and drop the full rewrite.** A line is tombstoned by `WriteAt` of `~` and
spaces up to its length, under `walMu`, after reading back the bytes at its offset; offsets do not move on append
(`O_APPEND` only grows the file) and move only in compaction, so when the bytes differ the line is found again by
its text (the first live line with that text; equal lines are interchangeable). Today's code reads such a line as a
tombstone (`HasPrefix(TrimSpace(line), "~")` in compaction, `HasPrefix(line, "~")` in `Replay`), so a WAL written by
the new code is readable by the current one and the other way round: no migration. This replaces today's
`os.WriteFile` of the whole file per event, which is quadratic over a backlog and truncates the WAL before
rewriting it. A crash during a tombstone write leaves either a tombstone or a line that no longer decodes, which the
next pass dead-letters as unreadable; it never empties the file. Compaction is unchanged.

**D5. The delivery body is the WAL line.** The line is `json.Marshal(event)`, the body today's in-process delivery
sends; sending its bytes avoids a decode and re-encode of the payload (which would turn large integers into floats).
The line is decoded only to check it is an `Event`. A memory event is sent as `json.Marshal(event)`.

**D6. No change outside the package, and no new exported name.** `New`, `NewWithConfig`, `Replay`, `Start`,
`Enqueue`, `Close`, `CloseWithContext`, `TriggerCompact`, `DeadLetterTotal`, `DeadLetterFileSizeBytes`,
`MetricsHandler`, `WriteMetricsTo`, `CompactConfig`, `DefaultCompactConfig`, `Metrics` and `Event` keep their
signatures, and the services keep their calls. The drain settings are read by the package itself from four
environment variables when `New` or `NewWithConfig` builds a queue (`MINTKEY_AUDIT_DRAIN_CONCURRENCY`,
`MINTKEY_AUDIT_DRAIN_BATCH_SIZE`, `MINTKEY_AUDIT_RETRY_INITIAL_MS`, `MINTKEY_AUDIT_RETRY_MAX_MS`), next to the
services' existing `MINTKEY_AUDIT_WAL_*` names, so an operator can tune every service without a change in `apps/`
(which other changes of this round edit) and unset variables give the defaults. `Start` logs the effective settings
once (`auditq: drain settings`). The request (method, path, headers, 10 s timeout) does not change.

**D7. Unchanged behaviour, named.** Delivery is at least once: a crash after a 2xx and before the tombstone, or a
timeout after the sink stored the event, delivers it again, as today. Events of one round reach the sink in any
order; rounds follow the WAL order, and with a concurrency of 1 the order is the WAL order. The package already
does not order events across service instances, and admin-api sets `at` on arrival.

**D8. How the tests reach new code.** The L4 red step puts every non-Python production file back to the base, so the
new Go tests must compile against today's package: they use only `New`, `NewWithConfig`, `Replay`, `Start`,
`Enqueue`, `Close`, `CloseWithContext`, `TriggerCompact`, `DeadLetterTotal`, `DeadLetterFileSizeBytes`,
`WriteMetricsTo`, `MetricsHandler`, `Event`, `CompactConfig`, an `httptest` sink, `t.Setenv` for the settings, the
default `slog` logger for the settings record, and the metrics text for the backlog (a test helper reads the line
`auditq_backlog_events{service="<label>"} <n>` from `WriteMetricsTo` and fails the test with `t.Fatal` when it is
missing). Against the base they fail by `t.Fatal`/`t.Error` within their deadlines (the base ignores the variables,
dead-letters after five tries, writes no backlog line and no settings record); none waits longer than a few seconds
there, so the module stays well inside `-timeout=120s`. They are top-level test functions without `t.Run`, so each is
one case in the report. A test whose sink handler blocks closes its release channel in a `t.Cleanup` registered after
the server's `Close`, so that cleanup (last in, first out) unblocks the handler before the server waits for it.

## Interfaces

No exported name is added. Unexported, in `queue.go` (suggested names; only behaviour is tested):

```go
type drainSettings struct {
    concurrency  int           // MINTKEY_AUDIT_DRAIN_CONCURRENCY, default 4
    batchSize    int           // MINTKEY_AUDIT_DRAIN_BATCH_SIZE, default 1000
    initialDelay time.Duration // MINTKEY_AUDIT_RETRY_INITIAL_MS, default 250ms
    maxDelay     time.Duration // MINTKEY_AUDIT_RETRY_MAX_MS, default 30s; below initialDelay → initialDelay
}
func drainSettingsFromEnv() drainSettings          // one WARN "auditq: ignoring invalid setting" (name=<var>) per bad value
func nextRetryDelay(current, maxDelay time.Duration) time.Duration // maxDelay when current <= 0 or > maxDelay/2, else 2*current
func isRejected(status int) bool                   // 400, 413, 422
```

`NewWithConfig` stores `drainSettingsFromEnv()` in the queue; `New` calls `NewWithConfig` as today. `Start` logs
`slog.Info("auditq: drain settings", "service", label, "concurrency", c, "batch_size", b, "initial_retry_delay", d1,
"max_retry_delay", d2)` with `d1` and `d2` as `time.Duration` (the text handler writes `250ms`, `30s`). The constant
`maxDeadLetterRetries` and the function `emitWithRetry` go; `initialRetryDelay`, `maxRetryDelay` and `channelCap`
stay as the defaults and the memory channel's size. The backlog is an `atomic.Int64` in `Metrics`, changed under
`walMu` for WAL events so that a pass's `Store` and an append's `Add` do not race, and written by `writeMetrics` as
`# HELP auditq_backlog_events Number of audit events not yet delivered or dead-lettered.`, `# TYPE
auditq_backlog_events gauge` and `auditq_backlog_events{service="<label>"} <n>`.

## Failure cases

- The sink is down, slow or answers a retried status: events stay in the WAL; rounds wait up to the maximum delay;
  nothing is dead-lettered; the backlog grows.
- The sink refuses an event (400, 413, 422): one request, one dead-letter record, the backlog −1.
- The WAL cannot be written: memory delivery while the process runs (at most 1,000 waiting); the events are lost
  if the process stops first, as today.
- An unreadable line, or a fragment left by a crash: dead-lettered as unreadable once it ends with `\n`; a fragment
  at the end of the file is skipped until the next append terminates it.
- Compaction while a request is in flight: the tombstone finds the line by its text.
- `Close` while the sink is down: no wait inside the drainer; `CloseWithContext` returns by its deadline as today;
  the events stay in the WAL for the next start.
- No event pending: the drainer blocks on the wake channel; no request.

## Decisions taken without the owner

- The refusal set (400, 413, 422) and retrying 403 (D3); defaults 4 and 1,000; the settings as environment
  variables read by the package rather than by each service (D6). Each is reversible without a format change.

## Scaffold (a person commits these signature-only stubs on staging before the plan is activated)

None. Every new test compiles against the base package (D8): no exported name is added, the settings come from the
environment, and the backlog is read from the metrics text.

## Open questions

- The tests compress an outage of minutes into milliseconds (retry delays of 5 to 50 ms, 1,500 events); a run
  against a real admin-api that is stopped for ten minutes was not made here.
- Which statuses an audit sink other than admin-api (an embedding application) uses for a final refusal is not
  known; D3 assumes 400, 413 and 422 and retries the rest.
- `sh .l4/gates/lint-go.sh` (golangci-lint) was not run against the new code; the linter set may ask for small
  changes (for example a checked `Close` error).
