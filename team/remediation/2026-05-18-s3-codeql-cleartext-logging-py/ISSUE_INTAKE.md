# Issue Intake — S3: CodeQL py/clear-text-logging-sensitive-data (Python)

## Problem statement

Eleven open CodeQL HIGH alerts (rule `py/clear-text-logging-sensitive-data`) report that raw
credential values — Authorization headers, API keys, and partial service keys — are written to
stdout/log sinks without redaction. This violates the Mintkey credential-in-logs policy and
creates a compliance risk if log aggregators ingest these streams.

## User-visible symptom

Running the mock-backend or the e2e smoke script produces log lines such as:

```
INFO mock_backend.rest.main: api-key-header: x_api_key=canary-demo-api-key
INFO mock_backend.rest.main: bearer: authorization=Bearer mk_svckey_ABCDE…
PASS Service API key issued for svc=abcd1234…: mk_svckey_ABCDE12345678901234…
```

Any log aggregator (Loki, CloudWatch, Datadog) receiving these lines stores the raw credential.

## Expected behavior

Log lines must contain only redacted representations of secrets:
- `authorization` header → `Bearer sk12…` (first 4 chars + `…`)  
- `x_api_key` / `api_key` → first 4 chars + `…`
- Issued service API keys in output → first 4 chars + `…`

## Evidence — confirmed alert sites (11)

### mock-backend/src/mock_backend/rest/main.py (6 sites)

| # | Line | Variable logged |
|---|------|----------------|
| 1 | 17   | `authorization` (Authorization header, health endpoint) |
| 2 | 25   | `x_api_key`    (X-Api-Key header) |
| 3 | 35   | `api_key`      (query-string API key) |
| 4 | 43   | `authorization` (Authorization header, bearer endpoint) |
| 5 | 52   | `authorization` (Authorization header, basic-auth endpoint) |
| 6 | 66   | `authorization` (Authorization header, oauth-protected endpoint) |

### scripts/e2e_smoke.py (5 sites)

| # | Line | Path |
|---|------|------|
| 7  | 100 | `print()` sink in `ok()` — receives `msg` that can carry secret values |
| 8  | 108 | `print()` sink in `bad()` — receives `msg` that can carry secret values |
| 9  | 303 | `ok(f"Service API key issued … {key[:20]}…")` — `key` from `resp.json().get("plaintext_key")` |
| 10 | 220 | `ok(f"CSRF token received")` — `csrf_token` flows through `ok()` sink |
| 11 | 305 | `bad(f"Service API key issue failed …", resp.text)` — `resp.text` may contain secret in error body |

## Scope

- `mock-backend/src/mock_backend/rest/main.py`
- `mock-backend/tests/test_mock.py`
- `scripts/e2e_smoke.py`
- `mintkey-models/mintkey_models/log_redact.py` (new helper)
- `mintkey-models/tests/test_log_redact.py` (new test)

## Out of scope

- `admin-api/`, `mcp-server/`, `services/`, `admin-ui/` — must not be touched.

## Risk level

`security / compliance`

## Verification target

```bash
cd /Users/alexandruiacobescu/gooseProjects/mintkey-s3-codeql-cleartext-logging-py
python -m pytest mock-backend/tests/ mintkey-models/tests/ -x -q \
  --ignore=mintkey-models/tests/test_models.py
git diff --stat origin/main..HEAD
```

All 11 log sites must pass only redacted values. New tests assert `caplog` / captured output
does NOT contain the raw secret string.

## Owner decisions needed

None — redaction policy (`val[:4]+"…"` for ids/keys; `"<redacted>"` for passwords/auth-headers)
is established by existing `mintkey-models/mintkey_models/otel_redaction.py`.
