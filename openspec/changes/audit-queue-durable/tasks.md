# Tasks: audit-queue-durable

Each task writes its tests first and sees them fail for the reason it names, then changes the code. All code is in
`packages/go/auditq` (the root Go module); run `go test ./packages/go/auditq/ -short -timeout=120s`, `go vet
./packages/go/auditq/` and `sh .l4/gates/lint-go.sh`.

Rules for every new test (design.md D8): it is a top-level test function in package `auditq_test`, without `t.Run`,
and uses only API that exists before the change: `auditq.New`, `auditq.NewWithConfig`, `auditq.CompactConfig`,
`auditq.Event` and the `Queue` methods `Replay`, `Start`, `Enqueue`, `Close`, `CloseWithContext`, `TriggerCompact`,
`DeadLetterTotal`, `DeadLetterFileSizeBytes`, `WriteMetricsTo` and `MetricsHandler`, plus the helpers `tmpWAL` and
`newEvent` of `packages/go/auditq/queue_test.go` and `walLineCount` of `packages/go/auditq/compact_test.go`. A queue is
built with `auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{IntervalSec: 0,
ThresholdBytes: 0})` unless the scenario says otherwise; settings are set with `t.Setenv` before it is built. The
backlog is read with the helper `backlogOf(t *testing.T, q *auditq.Queue) int64` (new, in
`packages/go/auditq/backlog_test.go`): it writes `q.WriteMetricsTo` into a buffer, finds the line that starts with
`auditq_backlog_events{service="test-svc"} ` and parses the number, and calls `t.Fatal` when the line is missing. Each
test registers `srv.Close` with `t.Cleanup` first, then a cleanup that calls `q.CloseWithContext` with a 1 s deadline,
then (when its handler blocks) a cleanup that closes the handler's release channel, so that the cleanups run in the
reverse order. A test waits for a condition by polling every 10 ms up to the deadline its scenario gives (3 s where
none is given) and then fails with `t.Fatalf`; it sleeps only where its scenario names a wait. Sink handlers read the
body, decode it as `auditq.Event` where they need the payload, and count with `sync/atomic` or a mutex.

## 1. The backlog metric

- [x] 1.1 Tests first, new file `packages/go/auditq/backlog_test.go` with the helper `backlogOf`:
  `TestBacklogInExposition` and `TestReplayCountsPendingEvents`, the two scenarios of the requirement "The backlog is a
  metric" (the first reads `q.MetricsHandler()` through an `httptest.NewRecorder`; the WAL of the second is written
  with `os.WriteFile`: two lines of `json.Marshal(newEvent(...))` and a `~` line). They fail before the change: the
  metrics text has no `auditq_backlog_events` line, so `backlogOf` and the `Contains` checks fail. Then add the
  backlog `atomic.Int64` to `Metrics` and its three lines to `writeMetrics` in `packages/go/auditq/metrics.go`, after
  the four existing families, as design.md's Interfaces give them; in `queue.go` set it in `Replay` (counting as the
  requirement says) and add 1 in `Enqueue` for each appended line. `TestMetricsExposition` in
  `packages/go/auditq/compact_test.go` passes unchanged.

## 2. The drain settings

- [x] 2.1 Tests first, new file `packages/go/auditq/settings_test.go`: `TestDrainSettingsDefaults`,
  `TestDrainSettingsFromEnvironment` and `TestDrainSettingsInvalidValues` (the first three scenarios of the requirement
  "Retries wait a capped delay that progress resets"). Each replaces the default logger with
  `slog.New(slog.NewTextHandler(w, nil))`, `w` a writer that appends to a `bytes.Buffer` under a mutex, restores the
  previous default with `t.Cleanup(func() { slog.SetDefault(prev) })`, sets the four variables with `t.Setenv` (to
  `""` for the defaults test), builds and starts a queue, and checks the buffer for the texts the scenario gives. They
  fail before the change: no `auditq: drain settings` record is written. Then in `packages/go/auditq/queue.go` add
  `drainSettings`, `drainSettingsFromEnv` and the settings record of design.md's Interfaces: `NewWithConfig` stores
  the settings, `Start` logs them before it starts the goroutines. An empty value counts as unset.

## 3. The WAL is the queue

- [ ] 3.1 Tests first, new file `packages/go/auditq/durable_test.go`, with a helper `seqEvent(i int) auditq.Event`
  (`newEvent("proxy.hit")` with payload `{"seq": i}`): `TestSinkDownThenBack`, `TestRetriesPastFiveFailures`,
  `TestCloseWhileSinkDownKeepsEvents`, `TestUnwritableWALDeliversFromMemory` (the four scenarios of the requirement "An
  undelivered event stays in the WAL until the sink accepts or refuses it"), `TestRetryDelayDoublesUpToCap` (the
  scenario "the delay doubles up to the cap"), `TestConcurrencyIsBounded` and `TestRefusedEventsDoNotHoldUpOthers` (the
  two scenarios of "Deliveries run concurrently up to a bound, and failing events do not hold up the others"),
  `TestRefusalStatuses` and `TestRefusedEventRecord` (the first two scenarios of "An event the sink refuses goes to the
  dead-letter file on its first answer"). `TestRefusalStatuses` loops over the statuses of its scenario with a new
  sink, WAL and queue for each, closing that queue (1 s deadline) and sink before the next, and stops at the first
  wrong status with `t.Fatalf` naming it (so that it fails within 2 s before the change). They fail before the change: the base ignores the variables, tries an event five times
  (250 ms doubling) and then dead-letters it, drains one event at a time and writes no backlog line. Change the existing
  `packages/go/auditq/compact_test.go::TestDeadLetterMetrics` so that its sink answers
  `http.StatusUnprocessableEntity` instead of `http.StatusInternalServerError` (and its comments say the sink refuses
  the events); the rest of the test stays. Then in `packages/go/auditq/queue.go` replace the channel drain and
  `emitWithRetry` by the drainer of design.md D1 and D2 (`readBatch`, rounds of up to the concurrency setting, one
  goroutine per entry settling it as soon as it is answered, the progress-based wait with `nextRetryDelay`,
  `isRejected`, the memory channel for events the WAL could not take, the wake channel, the closing rules), with
  `emit` returning the HTTP status as well as the error; remove `maxDeadLetterRetries`. The other tests of
  `packages/go/auditq/queue_test.go` and `packages/go/auditq/compact_test.go` pass unchanged.

- [ ] 3.2 Tests first, new file `packages/go/auditq/walformat_test.go`: `TestCurrentFormatWALDrainsInPlace`,
  `TestCompactionBetweenReadAndTombstone` (the held event has the type `hold.me`; the handler signals on a channel
  when it holds the request and waits on a release channel), `TestUnreadableLineDeadLettered` and
  `TestAppendAfterPartialLineStartsNewLine`, the four scenarios of the requirement "The WAL keeps the format the
  current code reads" (the WAL files are written with `os.WriteFile`; event lines are `json.Marshal` of
  `newEvent(...)` values). They fail before the change: today's tombstone shrinks the file, the base writes no backlog
  line, an unreadable line is skipped, and an append joins the fragment. Then in `packages/go/auditq/queue.go`: the
  tombstone of design.md D4 (`WriteAt` of `~` and spaces after reading back the bytes at the offset, else the first
  live line with the same text) replaces the whole-file rewrite; the delivery body is the line's bytes (D5);
  `readBatch` dead-letters an unreadable line as `{"line", "last_err": "unreadable WAL line", "at"}` and tombstones
  it; the append writes `\n` first when the file does not end with one. `packages/go/auditq/compact.go` is unchanged.
