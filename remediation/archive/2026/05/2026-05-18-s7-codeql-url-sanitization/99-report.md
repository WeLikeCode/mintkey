# S7 CodeQL URL Sanitization — Closing Report

**Session:** `2026-05-18-s7-codeql-url-sanitization`
**Branch:** `fix/s7-codeql-url-sanitization-2026-05-18`
**Status:** **CLOSED**
**Closed:** 2026-05-18

## Outcome

3 high-severity `*/incomplete-url-substring-sanitization` CodeQL alerts are closed. Hostname-parsed comparison helpers were introduced using stdlib only — no new dependencies.

| Alert site | Fix |
|---|---|
| `admin-ui/e2e/tests/99-runbook-ui-verify.spec.ts:499` | `textContainsHost` helper — `new URL(text).hostname === host` |
| `admin-ui/e2e/verify-targeted.mjs:259` | `textContainsHost` helper — same |
| `mcp-server/tests/test_landing.py:172` | `_note_references_host` helper — `urlparse(text).hostname == host` |

## Commits

| SHA | Message |
|---|---|
| `ef71bf1` | fix(codeql): replace substring URL checks with hostname-parsed comparisons |
| `adc943a` | docs(remediation): add S7 session intake + closing report |

## What changed (and what didn't)

### Changed

- `admin-ui/e2e/tests/99-runbook-ui-verify.spec.ts` — replaced `.includes('api.github.com')` with `textContainsHost(url, 'api.github.com')` using `new URL(text).hostname` comparison.
- `admin-ui/e2e/verify-targeted.mjs` — same fix; shared `textContainsHost` helper.
- `mcp-server/tests/test_landing.py` — replaced `'api.github.com' in url` with `_note_references_host(note, 'api.github.com')` using `urllib.parse.urlparse`.
- Session folder (`team/remediation/2026-05-18-s7-codeql-url-sanitization/`).

### NOT changed

- Production code — all changes are confined to test files.
- Any other CodeQL rule / alert site — this session closed `incomplete-url-substring-sanitization` only.

## Verification status

- `pytest mcp-server/tests/test_landing.py` — **32 passed in 0.97s**.
- `tsc --noEmit` — clean for e2e files (pre-existing `tenants.ts` errors are unrelated to this change).

## Process notes

Single-implementer chunk; reviewer pending. The original implementer (commit `ef71bf1`) omitted the session documentation files. This is a docs-only follow-up commit that closes the scaffold gap; no code changes.

## Owner-locked decisions honored

| Decision | Honored |
|---|---|
| Fix in code — no suppressions | ✅ |
| Stdlib only (`new URL` / `urllib.parse`) | ✅ |
| Scope: test files only, no production code | ✅ |

## Residuals

None. All 3 alerts are addressed. No suppressions were introduced.
