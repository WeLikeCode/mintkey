# OpenAPI Parity Snapshot — Session Plan

**Session:** `2026-05-16-openapi-parity`
**Driver:** `remediation-orchestrator` (super-orchestrator)
**Status:** CLOSED

---

## Mission

Refresh `tests/acceptance/openapi_snapshot.json` to reflect the current router prefix set: two changes since the snapshot was created — `health` first inline path is `/metrics`, and `service_templates` router with prefix `/v1/service-templates` was added. A successful session leaves all 5 `test_openapi_parity.py` tests passing.

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

## Phase 1 — Single chunk: refresh snapshot

**Chunk C-1:** Update `tests/acceptance/openapi_snapshot.json`:
- Change `"health"` from `"/v1/health"` to `"/metrics"` (runtime truth)
- Add `"service_templates": "/v1/service-templates"` (new router added to main.py)

---

## Closing

Verified via `cd admin-api && uv run pytest ../tests/acceptance/test_openapi_parity.py -v` — all 5 tests pass.
