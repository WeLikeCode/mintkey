# Issue Intake — lint-go-errcheck-round2

**Session:** `2026-05-17-lint-go-errcheck-round2`
**Date:** 2026-05-17

---

## Problem statement (required)

7 unchecked error returns remain in `internal/auditq` after PR #37 fixed `compact.go`.
`golangci-lint` (errcheck) flags 3 `fmt.Fprintf` calls in `metrics.go` and 4 `Close`/`resp.Body.Close` calls in `queue.go`.

## User-visible symptom (required)

CI errcheck gate fails on the `internal/auditq` package:

```
internal/auditq/metrics.go:61:13: Error return value of `fmt.Fprintf` is not checked
internal/auditq/metrics.go:69:13: Error return value of `fmt.Fprintf` is not checked
internal/auditq/metrics.go:77:13: Error return value of `fmt.Fprintf` is not checked
internal/auditq/queue.go:163:15: Error return value of `f.Close` is not checked
internal/auditq/queue.go:257:15: Error return value of `f.Close` is not checked
internal/auditq/queue.go:316:15: Error return value of `f.Close` is not checked
internal/auditq/queue.go:442:18: Error return value of `resp.Body.Close` is not checked
```

## Expected behavior (required)

All 7 findings resolved with zero-behavior-change idioms; lint gate passes; build/vet/test remain green.

## Evidence (required)

- `internal/auditq/metrics.go:61,69,77` — `fmt.Fprintf` to `io.Writer` (HTTP ResponseWriter or caller-supplied writer): benign disconnect, use `_, _ = fmt.Fprintf(...)`.
- `internal/auditq/queue.go:163` — `defer f.Close()` on a read-only WAL file opened with `os.Open`; use `defer func() { _ = f.Close() }()`.
- `internal/auditq/queue.go:257` — `defer f.Close()` in `appendWAL`; write file; close error benign after successful write, use `defer func() { _ = f.Close() }()`.
- `internal/auditq/queue.go:316` — `defer f.Close()` in `deadLetterWAL`; write file; close error benign (data already flushed), use `defer func() { _ = f.Close() }()`.
- `internal/auditq/queue.go:442` — `resp.Body.Close()` inside a defer func that already drains the body; use `_ = resp.Body.Close()`.

## Scope (required)

`internal/auditq/metrics.go` and `internal/auditq/queue.go` only.

## Out of scope (required)

All other files. No behavior changes.

## Risk level (required)

CI (lint gate).

## Verification target (required)

```
go build ./...
go vet ./internal/auditq/...
go test -count=1 ./internal/auditq/...
golangci-lint run ./internal/auditq/...   # if available
```
All must exit 0.

## Owner decisions needed (if any)

None. All fixes are mechanical, zero-behavior-change idioms.

---

## Checklist (orchestrator may not start without all required fields)

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (none)
