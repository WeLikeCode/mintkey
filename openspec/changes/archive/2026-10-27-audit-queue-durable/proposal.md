# The audit queue keeps every event until the sink takes it

## Why

The broker, the proxy plugin, the email proxy and the SSH proxy record their audit events through
`packages/go/auditq`: `Enqueue` writes the event to a write-ahead log (WAL) and a background drainer posts it to the
audit sink (admin-api's `POST /v1/internal/audit/emit`). An audit trail of a credential broker must not depend on the
sink being up at the moment of the call. Today it does:

- The drainer tries an event five times, about 4 s in all, then moves it to `<wal>.dead` and drops it from the WAL.
  Nothing delivers it later: after a sink outage of a few seconds, the events of that window never reach the sink.
- Events drain one at a time, each through its five tries, so while the sink is down the queue moves at about 4 s
  per event, and one event the sink keeps failing holds up every event behind it.
- The drainer reads from an in-memory channel of 1,000. Events beyond that are only in the WAL and are read again
  only at the next start of the service.
- Each delivered event rewrites the whole WAL file, so draining a backlog costs time quadratic in its size.
- No metric shows how many events are waiting.

## What Changes

- The WAL is the queue: the drainer reads pending events from it, so every event is delivered while the service runs,
  however many arrived while the sink was down.
- An event is retried until the sink answers 2xx, with no attempt limit. After a round in which nothing was
  delivered, the drainer waits a delay that doubles from 250 ms up to 30 s; any progress resets it.
- Deliveries run in rounds of up to 4 requests at once, and a round that fails does not stop the pass: events behind
  an event that keeps failing are delivered.
- Only a final refusal by the sink (HTTP 400, 413, 422) moves an event to `<wal>.dead`, at its first answer. A down,
  slow or failing sink never does.
- A delivered line is overwritten in place with a tombstone the current code already reads; no file rewrite outside
  compaction. An unreadable line is dead-lettered instead of being skipped forever, and an append after a cut line
  starts on a new line.
- A new gauge, `auditq_backlog_events{service}`, gives the number of events waiting.
- Four optional environment variables, read by the package, tune the drainer: `MINTKEY_AUDIT_DRAIN_CONCURRENCY`
  (default 4), `MINTKEY_AUDIT_DRAIN_BATCH_SIZE` (1000), `MINTKEY_AUDIT_RETRY_INITIAL_MS` (250) and
  `MINTKEY_AUDIT_RETRY_MAX_MS` (30000). Each service logs the settings it runs with at start.

## Capabilities

### New Capabilities
- `audit-queue`: how the Go services' audit queue keeps, retries, delivers and reports its events.

## Impact

- Changed: `packages/go/auditq/queue.go`, `packages/go/auditq/metrics.go`. Unchanged: `compact.go`, every caller in
  `apps/` (no exported name is added or changed; the services get the defaults unless the variables are set).
- New tests: `packages/go/auditq/backlog_test.go`, `packages/go/auditq/settings_test.go`,
  `packages/go/auditq/durable_test.go`, `packages/go/auditq/walformat_test.go`. They use only the package's existing
  API, so they build against the code before the change. Changed test:
  `packages/go/auditq/compact_test.go::TestDeadLetterMetrics` (its sink refuses with 422 instead of failing with 500).
- WAL: no migration in either direction. Lines are written as before; a tombstone is `~` followed by spaces, which
  the current code reads as a tombstone, so a rollback reads the WAL too.
- `<wal>.dead`: it now receives only events the sink refused, and unreadable WAL lines. Files from before the upgrade
  are left as they are and are not read. To deliver events that were dead-lettered before the upgrade, an operator
  stops the service, appends each record's `event` to the WAL (for example `jq -c 'select(.event) | .event'
  <wal>.dead >> <wal>`), moves the `.dead` file aside and starts the service; the sink may receive an event it had
  stored before.
- Disk: while the sink is down the WAL grows by one line per event, as `<wal>.dead` grew before; compaction keeps
  only undelivered lines.
- Monitoring, outside this unit (`infra/observability/alert_rules.yml` is not edited by it): a person adds an alert on
  `auditq_backlog_events` with a threshold and a duration (one event the sink keeps answering with a retried status,
  such as admin-api's 403 for an actor outside the tenant, holds the backlog at 1), and rewords
  `AuditDeadLetterGrowing`: dead letters now mean events the sink refused, not an unreachable admin-api.
- Delivery stays at least once, and the order of the events within a round of concurrent deliveries is not fixed.
- Configuration: nothing to set. To change the drainer, set the variables above in a service's environment (compose
  or Helm values, outside this unit); an invalid value is logged and replaced by the default.
- Out of scope: a batch endpoint on the sink, idempotency keys.

## Issue Intake (remediation gate)

1. **Problem statement**: audit events are dropped from the WAL after five failed deliveries, events beyond the
   in-memory channel wait for a restart, and one failing event holds up the queue.
2. **User-visible symptom**: after an outage of the audit sink, the events of that window are missing from the
   audit trail (they sit in `<wal>.dead`); while it lasts, the queue drains at about one event per 4 s.
3. **Expected behavior**: with the sink down and then back, every event arrives, nothing is written to
   `<wal>.dead`, and the backlog is visible as a metric.
4. **Evidence**: `maxDeadLetterRetries = 5` and `emitWithRetry` (one event at a time, then `deadLetterWAL`),
   `channelCap = 1000` with the WAL-only fallback in `Enqueue`, and `tombstoneWAL`'s whole-file rewrite, in
   `packages/go/auditq/queue.go`.
5. **Scope**: the package and its tests, as above.
6. **Risk**: medium. The drain loop is rewritten; the WAL format, the request and the exported functions do not
   change, and the existing tests of the package keep passing (one changed as named).
