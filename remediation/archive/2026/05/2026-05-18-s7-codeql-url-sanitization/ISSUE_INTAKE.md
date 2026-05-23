# Issue Intake — 2026-05-18-s7-codeql-url-sanitization

**Session:** `team/remediation/2026-05-18-s7-codeql-url-sanitization/`
**Branch:** `fix/s7-codeql-url-sanitization-2026-05-18`
**Reported:** 2026-05-18
**Reporter:** Owner — CodeQL dashboard sweep; S7 chunk of ongoing security remediation campaign.
**Triggered by:** CodeQL reported 3 high-severity `incomplete-url-substring-sanitization` alerts across two test files.

## Problem statement (required)

3 high-severity CodeQL alerts (`*/incomplete-url-substring-sanitization`) are open at:

1. `admin-ui/e2e/tests/99-runbook-ui-verify.spec.ts:499` — `js/incomplete-url-substring-sanitization`
2. `admin-ui/e2e/verify-targeted.mjs:259` — `js/incomplete-url-substring-sanitization`
3. `mcp-server/tests/test_landing.py:172` — `py/incomplete-url-substring-sanitization`

Each site performs an `.includes()` (JS/TS) or `in` (Python) substring match to check whether a URL belongs to an expected host. This pattern is bypassable: a crafted URL such as `https://attacker.evil.com/api.github.com` passes the substring check even though the hostname is entirely attacker-controlled.

## User-visible symptom (required)

Tests can pass on adversarial inputs that embed the expected hostname as a path component rather than as the actual hostname. While these are test files rather than production gate code, tests that accept bad URL inputs without flagging them are themselves a correctness defect — poor URL validation in tests silently erodes confidence in what the test is actually asserting.

## Expected behavior (required)

URL membership checks must parse the URL and compare `.hostname` exactly. A URL like `https://attacker.evil.com/api.github.com` must NOT match a check intended to accept only `api.github.com` traffic.

Per owner-locked decision: fix in code. No `// lgtm` suppressions, no CodeQL config exclusions.

## Evidence (required)

Vulnerable substring-check pattern (before fix):

**JS/TS** (`admin-ui/e2e/tests/99-runbook-ui-verify.spec.ts:499`, `admin-ui/e2e/verify-targeted.mjs:259`):
```ts
// bypassable — hostname appears anywhere in the URL string
if (url.includes('api.github.com')) { ... }
```

**Python** (`mcp-server/tests/test_landing.py:172`):
```python
# bypassable — hostname appears anywhere in the URL string
if 'api.github.com' in url: ...
```

Both patterns fail CodeQL rule `*/incomplete-url-substring-sanitization` (high severity): an attacker-controlled URL such as `https://evil.com/api.github.com` satisfies the check.

## Scope (required)

May be changed:
- `admin-ui/e2e/tests/99-runbook-ui-verify.spec.ts` — replace substring check with hostname-parsed comparison; extract `textContainsHost` helper.
- `admin-ui/e2e/verify-targeted.mjs` — same fix; reuse `textContainsHost` helper.
- `mcp-server/tests/test_landing.py` — replace `in` substring check with `urllib.parse`-based hostname comparison; extract `_note_references_host` helper.
- Session folder (`team/remediation/2026-05-18-s7-codeql-url-sanitization/`).

## Out of scope (required)

- Production code — all three alert sites are test files; no production paths are affected by this change.
- Any other CodeQL rule — this session targets `incomplete-url-substring-sanitization` only.
- Adding new test coverage for the helpers beyond what the existing test suites already exercise.

## Risk level (required)

- **Regression risk**: Low — changes are confined to test files; no production behavior is altered.
- **Signal impact**: High — these are dashboard-visible high-severity alerts; closing them cleans the CodeQL triage queue and removes a recurring distraction.

## Verification target (required)

- `pytest mcp-server/tests/test_landing.py` passes (all tests green).
- `tsc --noEmit` is clean for the e2e files (pre-existing `tenants.ts` type errors are unrelated and do not count against this change).

## Owner decisions (required)

- ✅ Fix in code — no suppressions, no CodeQL config exclusions. Locked per master remediation plan.
- ✅ Stdlib only — `new URL(...)` in JS/TS; `urllib.parse.urlparse` in Python. No new dependencies.
- ✅ Scope: test files only. No production code changed in this session.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with file:line + vulnerable pattern)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted
