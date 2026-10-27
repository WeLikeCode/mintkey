# Audit event queue

## Purpose

How the Go services' audit queue (`packages/go/auditq`) keeps every event in its write-ahead log (WAL) until the sink
accepts or refuses it, retries without a limit with a capped delay, delivers several events at once so that failing
events do not hold up the others, keeps the WAL format the current code reads, and reports its backlog.

## ADDED Requirements

### Requirement: An undelivered event stays in the WAL until the sink accepts or refuses it
The queue SHALL deliver every event appended to its WAL until the sink answers it with a 2xx status or refuses it
(see "An event the sink refuses goes to the dead-letter file on its first answer"), with no limit on the number of
attempts, without a restart, and whatever the number of events waiting. A delivery that fails (a transport error, a
timeout, or a status that is neither 2xx nor a refusal) SHALL leave the event in the WAL for a later round and SHALL
NOT write to `<wal>.dead`. Events that cannot be written to the WAL SHALL be held in memory and delivered the same
way while the process runs. `Close` and `CloseWithContext` SHALL keep their deadline; what is not delivered by then
stays in the WAL. The exported API of the package SHALL stay as it is (no exported name added, removed or changed).

#### Scenario: the sink is down, then returns
- **WHEN** with `MINTKEY_AUDIT_RETRY_INITIAL_MS=5` and `MINTKEY_AUDIT_RETRY_MAX_MS=20`, a sink that answers 503 until
  the test switches it, and the queue started, all 1,500 events (payload `{"seq": i}`) are enqueued, the test waits
  (at most 3 s) until the sink has answered at least 10 requests with 503, and only then switches the sink to 200
- **THEN** at that point, before the switch, `DeadLetterTotal()` is 0, `<wal>.dead` does not exist and the queue's
  `auditq_backlog_events` is 1500 (no event can have been delivered: the sink has answered nothing but 503); within
  30 s after the switch every `seq` from 0 to 1499 has reached the sink, then the backlog becomes 0 and `<wal>.dead`
  still does not exist

#### Scenario: more failures than the old limit of five
- **WHEN** with `MINTKEY_AUDIT_RETRY_INITIAL_MS=1` and `MINTKEY_AUDIT_RETRY_MAX_MS=5`, the sink answers the first 8
  requests with 500 and later ones with 200, and one event is enqueued
- **THEN** within 3 s the event reaches the sink with a 200 answer, `DeadLetterTotal()` is 0 and `<wal>.dead` does
  not exist

#### Scenario: closing while the sink is down keeps the events
- **WHEN** with `MINTKEY_AUDIT_RETRY_INITIAL_MS=5` and `MINTKEY_AUDIT_RETRY_MAX_MS=20`, 3 events are enqueued while
  the sink answers 503, and `CloseWithContext` is called with a 2 s deadline after at least 2 failed requests
- **THEN** it returns within 3 s, the WAL holds the 3 events as live lines, `<wal>.dead` does not exist, and a new
  queue on the same WAL with a sink that answers 200 delivers all 3 after `Replay` and `Start`

#### Scenario: a WAL that cannot be written
- **WHEN** the WAL path is in a directory that does not exist and 2 events are enqueued to a started queue whose sink
  answers 200
- **THEN** both events reach the sink and the backlog becomes 0

### Requirement: Retries wait a capped delay that progress resets
The queue SHALL take its drain settings from the environment when `New` or `NewWithConfig` builds it:
`MINTKEY_AUDIT_DRAIN_CONCURRENCY` (requests in flight at once, default 4), `MINTKEY_AUDIT_DRAIN_BATCH_SIZE` (pending
events read per pass, default 1000), `MINTKEY_AUDIT_RETRY_INITIAL_MS` (default 250) and `MINTKEY_AUDIT_RETRY_MAX_MS`
(default 30000). An unset or empty variable SHALL take its default; a set value that is not an integer of at least 1 SHALL
take its default with one WARN record `auditq: ignoring invalid setting` whose `name` is the variable; a maximum
below the initial delay SHALL become the initial delay. `Start` SHALL log one INFO record `auditq: drain settings`
with the attributes `service`, `concurrency`, `batch_size`, `initial_retry_delay` and `max_retry_delay` (the two
delays as `time.Duration`), in that order. After a round in which no event was delivered or refused, the drainer SHALL
wait the current delay (returning early only when the queue closes) and then double it, capped at the maximum; a
round in which at least one event was delivered or refused SHALL reset the delay to the initial delay and go on
without waiting.

#### Scenario: the defaults
- **WHEN** none of the four variables is set and a queue with the label `test-svc` is started, with the default
  `slog` logger writing text to a buffer
- **THEN** the buffer holds `msg="auditq: drain settings" service=test-svc concurrency=4 batch_size=1000
  initial_retry_delay=250ms max_retry_delay=30s`

#### Scenario: set values, and a maximum below the initial delay
- **WHEN** the variables are `2`, `10`, `1000` and `1`
- **THEN** the record holds `concurrency=2 batch_size=10 initial_retry_delay=1s max_retry_delay=1s`

#### Scenario: invalid values
- **WHEN** the variables are `abc`, `-5`, `0` and `x`
- **THEN** the record holds `concurrency=4 batch_size=1000 initial_retry_delay=250ms max_retry_delay=30s`, and for each
  of the four variables a WARN record `auditq: ignoring invalid setting` holds `name=<the variable>`

#### Scenario: the delay doubles up to the cap
- **WHEN** with `MINTKEY_AUDIT_DRAIN_CONCURRENCY=1`, `MINTKEY_AUDIT_RETRY_INITIAL_MS=10` and
  `MINTKEY_AUDIT_RETRY_MAX_MS=40`, the sink answers every request with 503 and records when each arrives, and one
  event is enqueued
- **THEN** the sink receives 12 requests within 3 s; every gap between two of them is at least 10 ms and at most
  150 ms, and the third gap and every later one is at least 40 ms

### Requirement: Deliveries run concurrently up to a bound, and failing events do not hold up the others
Each pass of the drainer SHALL read up to the batch size of pending events from the WAL in file order (plus the events
held in memory) and deliver them in rounds of at most the concurrency setting, never holding the WAL lock during a
request. After a round without progress it SHALL wait (see "Retries wait a capped delay that progress resets") and go
on with the next round of the same pass, so that events behind events that keep failing are delivered in that pass;
the failed events are read again by the next pass.

#### Scenario: the number of requests in flight is bounded
- **WHEN** with `MINTKEY_AUDIT_DRAIN_CONCURRENCY=3`, the sink takes 20 ms per request and records the most requests it
  held at once, and 30 events are enqueued
- **THEN** all 30 reach the sink within 3 s and the most requests at once is 2 or 3

#### Scenario: events the sink keeps answering with 403
- **WHEN** with `MINTKEY_AUDIT_DRAIN_CONCURRENCY=4`, `MINTKEY_AUDIT_RETRY_INITIAL_MS=200` and
  `MINTKEY_AUDIT_RETRY_MAX_MS=5000`, 40 events are enqueued in the order one with payload `{"kind": "poison", "seq":
  i}` then three with `{"seq": i}`, ten times, and the sink answers 403 to the poison events until the test releases
  them and 200 to the others
- **THEN** within 3 s all 30 others reach the sink while the poison events are still answered 403 and the backlog is
  10; after the release all 10 reach the sink within 10 s, the backlog becomes 0, `DeadLetterTotal()` is 0 and
  `<wal>.dead` does not exist

### Requirement: An event the sink refuses goes to the dead-letter file on its first answer
A sink answer with status 400, 413 or 422 SHALL be a refusal: the sink read the request and will never accept it. On a
refusal the queue SHALL append `{"event": <the event>, "last_err": "rejected: HTTP <status>", "at": <RFC 3339 UTC>}`
and a newline to `<wal>.dead`, tombstone the event, add 1 to `auditq_dead_letter_events_total`, set
`auditq_dead_letter_file_size_bytes` to the file's size, and send no further request for it. A 2xx answer SHALL
deliver the event; every other status SHALL be retried.

#### Scenario: which statuses are a refusal
- **WHEN** with `MINTKEY_AUDIT_RETRY_INITIAL_MS=5` and `MINTKEY_AUDIT_RETRY_MAX_MS=5`, one event is enqueued on a new
  queue for each sink status in turn
- **THEN** for 400, 413 and 422 `DeadLetterTotal()` becomes 1 within 2 s and the sink has received exactly one request
  100 ms later; for 200 and 204 the WAL has no live line within 2 s and `<wal>.dead` does not exist; for 401, 403, 404,
  409, 429, 500, 502, 503 and 504 the sink receives at least 3 requests within 2 s, `DeadLetterTotal()` is 0 and
  `<wal>.dead` does not exist

#### Scenario: the record of a refused event
- **WHEN** the sink answers 422 to every request and one `token.issued` event is enqueued
- **THEN** within 2 s `<wal>.dead` holds one line whose `event.event_type` is `token.issued` and whose `last_err` is
  `rejected: HTTP 422`, the backlog is 0 and the WAL has no live line

#### Scenario: the dead-letter metrics follow refused events
- **WHEN** the sink answers 422 to every request and 3 events are enqueued
- **THEN** `DeadLetterTotal()` is 3, `DeadLetterFileSizeBytes()` equals the size of `<wal>.dead`, and each of its
  lines is JSON without the keys `credential`, `api_key`, `secret` and `token_value`

### Requirement: The WAL keeps the format the current code reads
Each event SHALL be one line, `json.Marshal(event)` and `\n`, as today, and the body of its delivery SHALL be that
line's bytes. A delivered or dead-lettered line SHALL be overwritten in place with `~` followed by spaces up to the
line's length, a line whose trimmed text starts with `~` as the current code's rule reads it; outside compaction the
queue SHALL NOT rewrite the file. Before a tombstone write the queue SHALL check that the bytes at the line's offset
are still that line, and otherwise tombstone the first live line with the same text. Before an append to a WAL that
does not end with `\n`, the queue SHALL write `\n`. A line that is neither blank nor a tombstone and does not decode
as an `Event` SHALL be appended to `<wal>.dead` as `{"line": <its text>, "last_err": "unreadable WAL line", "at":
<RFC 3339 UTC>}`, counted in `auditq_dead_letter_events_total`, and tombstoned. Compaction SHALL work as before.

#### Scenario: a WAL in today's format drains in place
- **WHEN** the WAL is written by hand as `json.Marshal` of event A (payload `{"marker": "alpha-payload"}`), `~`, an
  empty line and `json.Marshal` of event B, each followed by `\n`, and a queue is started on it
- **THEN** the sink receives two bodies byte-equal to the two event lines, and once the backlog is 0 the file has
  the same size as before, every non-blank line starts with `~`, and the file does not contain `alpha-payload`

#### Scenario: compaction between the read and the tombstone
- **WHEN** with `MINTKEY_AUDIT_DRAIN_CONCURRENCY=1` three events are enqueued, the sink answers the first two at once
  and holds the request of the third until released, and `TriggerCompact` runs while it is held
- **THEN** after the compaction the WAL holds that event as its only line; after the release the backlog becomes 0,
  the WAL has no live line, and 200 ms later the sink has received the third event exactly once

#### Scenario: an unreadable line
- **WHEN** the WAL holds the line `not json` and then the line of event B, and a queue is started on it
- **THEN** event B reaches the sink, `<wal>.dead` holds a record whose `line` is `not json` and whose `last_err` is
  `unreadable WAL line`, `DeadLetterTotal()` is 1 and the backlog becomes 0

#### Scenario: an append after a partial last line
- **WHEN** the WAL holds the line of event A and then `{"event_type":"tok` without a newline, and event B is
  enqueued on a queue that is not started
- **THEN** the file is the line of A, `\n`, `{"event_type":"tok`, `\n`, the line of B and `\n`; after `Replay` and
  `Start`, A and B reach the sink and `<wal>.dead` holds the fragment as an unreadable line

### Requirement: The backlog is a metric
`WriteMetricsTo` and `MetricsHandler` SHALL write the gauge `auditq_backlog_events{service="<label>"}` (HELP `Number of
audit events not yet delivered or dead-lettered.`, TYPE `gauge`) after the four existing families, which stay. Its
value SHALL be the events in the WAL that are neither delivered nor dead-lettered plus the events held in memory.
`Replay` SHALL set it from the WAL (blank lines, tombstones and lines that do not decode as an `Event` are not
counted) and deliver nothing itself (the drainer started by `Start` reads the WAL); each append SHALL add 1; each
tombstone, and each memory event delivered or refused, SHALL take 1 away; each pass SHALL set it from its read.

#### Scenario: the backlog in the exposition
- **WHEN** a queue with the label `test-svc` that is not started is replayed on an empty WAL and 3 events are
  enqueued
- **THEN** its metrics text contains `# TYPE auditq_backlog_events gauge` and
  `auditq_backlog_events{service="test-svc"} 3`

#### Scenario: Replay counts the pending events
- **WHEN** a WAL holds two event lines and a `~` line, and a new queue on it calls `Replay`
- **THEN** its backlog is 2
