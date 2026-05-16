# Issue Intake — 2026-05-16-lint-go-errcheck

## Problem statement

Three unchecked `f.Close()` calls in `internal/auditq/compact.go` cause `golangci-lint errcheck` to fail. The calls are on a writable temp file in both error-return paths and the happy path before atomic rename; ignoring the Close error on a write file can silently mask flush failures or OS-level write-back errors.

## User-visible symptom

CI `golangci-lint` job exits non-zero:
```
internal/auditq/compact.go:160:10: Error return value of `f.Close` is not checked (errcheck)
internal/auditq/compact.go:166:10: Error return value of `f.Close` is not checked (errcheck)
internal/auditq/compact.go:171:9: Error return value of `f.Close` is not checked (errcheck)
```

## Expected behavior

All three `f.Close()` calls have their return value checked; `golangci-lint` exits 0.

## Evidence

- `internal/auditq/compact.go` lines 160, 166, 171 — bare `f.Close()` calls on a writable temp file (`tmpPath`).
- golangci-lint errcheck linter flags all three.

## Scope

`internal/auditq/compact.go` only.

## Out of scope

All other files; accepted ADRs; WAL logic beyond these three lines; metrics; audit event schema.

## Risk level

CI (lint gate failure); low production risk since the temp file is used atomically and write errors are already logged.

## Verification target

```
go build ./...                   # exit 0
go vet ./internal/auditq/...    # exit 0
go test ./internal/auditq/...   # exit 0, ok
```

## Owner decisions needed

None — treating all three as write-file Close calls; error paths log the close error; happy path returns early on close failure before rename.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line or command)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (or "none")
