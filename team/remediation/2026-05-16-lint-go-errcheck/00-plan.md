# Lint Go errcheck — Session Plan

**Session:** `2026-05-16-lint-go-errcheck`
**Driver:** `remediation-orchestrator` (super-orchestrator)
**Status:** CLOSED

---

## Mission

Fix three unchecked `f.Close()` calls in `internal/auditq/compact.go` so the errcheck linter passes. The temp file is a write file; all three calls must log or propagate the close error.

---

## Hard rules (every chunk inherits)

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No `docker compose down -v`
- No edits to accepted ADRs
- No product-code changes outside the scope defined in `ISSUE_INTAKE.md`
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit

---

## Phase 1 — Single chunk: fix compact.go

**Chunk C-1:** Edit `internal/auditq/compact.go` lines 160, 166, 171 to check the `f.Close()` return values.

- Lines 160, 166 (error-return paths): `if cerr := f.Close(); cerr != nil { slog.Warn(...) }`
- Line 171 (happy path before rename): `if err := f.Close(); err != nil { os.Remove(tmpPath); slog.Warn(...); return }`

---

## Closing

Verified via `go build ./...`, `go vet ./internal/auditq/...`, `go test ./internal/auditq/...` — all exit 0.
