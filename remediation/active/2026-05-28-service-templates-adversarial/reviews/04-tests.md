# 04 — Test-Quality & Coverage Adversarial Review

**Branch:** `feature/service-templates` @ `828bd7c`
**Scope:** Service-template catalog + APIs (Python/FastAPI) and OAuth2 Password Grant auth scheme (Go proxy-plugin + vault-adapter).
**Mode:** Read-only. No code modified.
**Spec:** `.kiro/specs/service-templates/{requirements,design,tasks}.md`. Properties 1–12 defined in `design.md` §Correctness Properties.

---

## 1. BASELINE — actual suite runs

### 1.1 Go — proxy-plugin (`apps/proxy-plugin`)

`go test ./...` → **all packages PASS**. Re-run with `-race -count=1` on the four feature packages (no cache):

```
ok  github.com/mintkey/mintkey/services/proxy-plugin/internal/cache       1.330s
ok  github.com/mintkey/mintkey/services/proxy-plugin/internal/audit       1.203s
ok  github.com/mintkey/mintkey/services/proxy-plugin/internal/credential  1.540s
ok  github.com/mintkey/mintkey/services/proxy-plugin/internal/egress      1.407s
```

Per-package `--- PASS` counts (verbose, `-count=1`):

| Package | PASS | FAIL |
|---|---|---|
| internal/cache | 20 | 0 |
| internal/audit | 9 | 0 |
| internal/credential | 7 | 0 |
| internal/egress | 10 | 0 |

**proxy-plugin feature total: 46 PASS / 0 FAIL.** Full `go test ./...` (13 packages) green.

### 1.2 Go — vault-adapter (`apps/vault-adapter`)

`go test -count=1 ./...` → **all packages PASS**:

```
ok  .../internal/cache    0.192s
ok  .../internal/changes  0.302s
ok  .../internal/crypto   0.466s
ok  .../internal/kek      0.632s
ok  .../internal/server   0.851s
ok  .../internal/store    0.569s
?   .../cmd/vault-adapter   [no test files]
?   .../internal/config     [no test files]
```

`internal/server`: **33 PASS / 0 FAIL.** The OAuth2/scope tests added by this feature all pass:

```
--- PASS: TestGRPCOAuth2PasswordGrant_RoundTrip (0.00s)
--- PASS: TestGRPCOAuth2PasswordGrant_MinimalPayload (0.00s)
--- PASS: TestGRPCScopeEnforcement_GetCredential_RequiresVaultRead (0.03s)
--- PASS: TestGRPCScopeEnforcement_GetCredential_AllowedWithVaultRead (0.03s)
--- PASS: TestGRPCScopeEnforcement_MissingToken (0.00s)
```

### 1.3 Python — admin-api service-templates (`tests/integration/admin_api/test_service_templates.py`)

**TRUE BASELINE (correct interpreter): 61 passed, 0 failed.**

```
$ apps/admin-api/.venv/bin/python -m pytest tests/integration/admin_api/test_service_templates.py -q
.............................................................            [100%]
61 passed, 2 warnings in 3.14s
```

This boots a real Postgres 16 testcontainer + runs Liquibase changelogs (`conftest.py`), so it is a DB-backed integration run, not a stub. Docker was running on this machine; the container came up and migrations applied cleanly.

> **DoD WARNING — interpreter trap (not a product defect, but it will bite the remediation).**
> The documented command `make test-unit` / `cd apps/admin-api && uv run pytest ...` does NOT reliably select the project interpreter in this shell. `uv run pytest` ran under **anaconda Python 3.9.7** (`/Applications/anaconda3`), where `admin_api/templates/models.py`'s PEP 604 `str | None` annotations fail pydantic forward-ref evaluation at import:
> ```
> TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
> ... 2 warnings, 61 errors in 7.43s   (exit code 0 — misleading!)
> ```
> All 61 tests then ERROR at fixture setup. `pyproject.toml` declares `requires-python = ">=3.12"`; the project `.venv` is 3.12.12 and is green. **The remediation must run via `.venv/bin/python -m pytest` (or fix the `uv`/PATH so the anaconda shim doesn't shadow it). Do NOT trust `uv run pytest` exit code 0 here — it reported exit 0 with 61 errors.**

### 1.4 Could-not-run / infra notes

- Python integration test **was** runnable (Docker up, Postgres+Liquibase testcontainers OK).
- **Go testcontainers integration (task 9.7)** — N/A: no such test exists in the diff (see matrix). Nothing to run.
- Admin-UI vitest (task 12.2) — not run; the only template-related vitest files are pre-existing source-grep tests (see §2.5), not part of this diff.

---

## 2. Anti-pattern audit of EXISTING tests

### 2.1 PBT libraries are entirely absent (the single biggest finding)

The spec mandates **12 property-based tests** (Properties 1–12), Go via `pgregory.net/rapid`, Python via `hypothesis`.

- **`pgregory.net/rapid` is in NEITHER `go.mod`** (proxy-plugin or vault-adapter). `grep -rl 'pgregory.net/rapid' apps/proxy-plugin apps/vault-adapter` → no matches. **Zero** of the 11 Go property tests (`TestCredentialStorageRoundTrip`, `TestExchangeRequestConstruction`, `TestJSONPathExtraction`, `TestNon2xxErrorMapping`, `TestCacheKeyedRetrieval`, `TestExpiryDetectionPriority`, `TestCacheThreshold`, `TestGracefulDegradation`, `TestAuditEventCompleteness`, `TestSensitiveDataExclusion`, `TestTokenURLValidation`) exist.
- **No `hypothesis` test file in the diff.** `hypothesis-6.141.1` is installed in the venv but is NOT a declared dep in `apps/admin-api/pyproject.toml`, and no Python PBT (Property 1 / Property 3) file exists.

Every property test in the design's table (`design.md` §Testing Strategy 19–23) is unwritten. The existing example-based tests are *consistent with* some properties but do not *verify* them across an input space.

### 2.2 Admin-UI tests are source-string-grep tests, not behavior tests (SEVERE)

`apps/admin-ui/tests/test_service_template_prefill.test.ts` and `test_template_prefill_ee_fix.test.ts` (both **pre-existing**, not in this feature diff) assert against the component **source code as a string**, never rendering anything:

```ts
// test_service_template_prefill.test.ts
it("imports useSearchParams from react-router-dom", () => {
  expect(formSrc).toContain("useSearchParams");
  expect(formSrc).toContain("react-router-dom");
});
it("sets name from template (pre-fill)", () => {
  expect(formSrc).toContain("setName(tName)");
});
```
```ts
// test_template_prefill_ee_fix.test.ts
expect(servicesSrc).toContain('"template-detail"');
expect(servicesSrc).toContain("auth_scheme: raw.auth_scheme");
```

These are tautological with respect to behavior: they pass iff a literal substring is present in the source, so any refactor that preserves behavior but renames a setter breaks them, and any behavior regression that keeps the substring passes them. They do **not** render `ServiceTemplatePicker`, do **not** exercise category grouping, search filtering, or the from-template submit. They cannot satisfy task 12.2.

### 2.3 `GetForDegradation` (graceful-degradation cache path) has no direct unit test

`apps/proxy-plugin/internal/cache/token_cache.go:85` defines `GetForDegradation` (returns a token even inside the 30s buffer, but not if fully expired — the core of Property 10). It is **never referenced in `token_cache_test.go`**; it is only indirectly exercised by two example cases in `egress/oauth2_handler_test.go` (`..._GracefulDegradation`, `..._CacheFullyExpired_Returns502`). The boundary that matters for Property 10 (refresh-failed + expiry exactly at/after the absolute deadline) is not swept. Happy-path-ish: one "not expired" case, one "fully expired" case, no boundary.

### 2.4 Audit/redaction tests are structural reflection, not data-flow

`audit/emitter_test.go::TestEmitTokenExchangedSendsCorrectPayload` and `TestTokenExchangedEventNoCredentialFields` are good as far as they go, but Property 11/12 require sweeping **arbitrary** token_urls and credential/token values and asserting they never appear in audit events, log fields, OTel span attrs, or response headers/bodies. The current test:
- `TestTokenExchangedEventNoCredentialFields` only inspects the **struct's JSON tags** via reflection for a fixed forbidden-name set — it never feeds a real secret through and greps the emitted bytes. A field named innocuously (e.g. `detail`) that happened to carry a secret value would pass.
- Note a latent typo in the forbidden map literal (gofmt-misaligned `"credential_fields": true,`) — harmless, but the map is name-based only.
- There is **no** test asserting the OTel span / `slog` fields / response body exclude the token or credential values (Property 12's "all observable outputs"). The egress handler does log `token_url_host` and `error_type` only (good), but nothing tests that the token never lands in a span attribute or response.

### 2.5 Happy-path skew / weaker-than-spec assertions

- `egress/oauth2_handler_test.go::TestHandleOAuth2PasswordGrant_CacheMiss_ExchangeSuccess` asserts `result.ExchangeLatencyMS > -1` (`assert.Greater(t, result.ExchangeLatencyMS, int64(-1))`). That is satisfied by `0`; it is a near-tautology that doesn't verify latency is actually measured.
- `token_cache_test.go` `DetermineExpiry*` cases are solid for examples but Property 8's full priority chain (valid-JWT-exp **beats** expires_in **beats** default) is only spot-checked; no generated JWTs with random exp vs random expires_in.
- The Python `test_service_templates.py` covers **list/detail only** (GET endpoints). It does NOT touch `POST /v1/tenants/{tid}/services/from-template` at all — no create, no overrides, no audit-event assertion, no 409 duplicate, no 404 unknown-template, no change-channel. Task 5.4 explicitly enumerates all of those.
- `vault-adapter/internal/server/grpc_test.go` round-trip tests assert **byte-for-byte** equality of the stored JSON (good, strictly correct for Property 2's *example*), but it is two hand-written payloads, not arbitrary generated `OAuth2PasswordGrantCredential` structs.

### 2.6 No `t.Skip` / `pytest.skip` / `xfail` masking found

Clean on this axis — no skips or xfails hiding gaps in the feature test files. The masking here is by **omission** (whole tasks unwritten), not by skip directives.

### 2.7 Tests do call real production code (good)

The Go example tests exercise real prod paths: `egress` tests drive the real `HandleOAuth2PasswordGrant` against an `httptest.NewTLSServer` + real `TokenExchanger`/`TokenCache`; `injector_test.go::TestInject_OAuth2PasswordGrant` calls real `credential.Inject`; vault round-trip uses real `grpcVaultServer` over bufconn + real in-memory store. The prod wiring exists and is reachable: `HandleOAuth2PasswordGrant` is called from `cmd/proxy-plugin/main.go:452`, and `EmitTokenExchanged` is emitted there (`main.go` ~460). The gap is **coverage breadth (PBT + integration + from-template + UI behavior)**, not fake stubs of the SUT.

---

## 3. OPTIONAL-TASK COVERAGE MATRIX

Legend: **ABSENT** = no test exists for it; **PARTIAL** = some example/structural coverage but missing the spec'd method (PBT / enumerated cases / behavior); **COVERED** = meets the task's stated checklist.

| Task | What it requires | File that would/does hold it | Status | What is missing |
|---|---|---|---|---|
| **2.4** | Unit tests for `TemplateRegistry` + `ServiceTemplate` model: valid YAML → 13 templates, skip-malformed-with-warning, category filter, case-insensitive search, required-field validation | `tests/unit/admin_api/test_template_registry.py` (does not exist) | **ABSENT** | No registry-level unit test exists. The integration test exercises the registry *through HTTP* but never tests malformed-entry skipping/warning logs, nor `ServiceTemplate` model validation directly. No unit file. |
| **3.2** | PBT Property 1: arbitrary payloads accepted iff `token_url` HTTPS **and** `credential_fields` non-empty (any field names). `hypothesis`. | `tests/unit/admin_api/test_oauth2_payload_pbt.py` (does not exist) | **ABSENT** | `OAuth2PasswordGrantPayload` exists in prod (`credential_service.py:103`) but has zero tests. No `hypothesis` import anywhere. |
| **3.3** | PBT Property 3: arbitrary URL strings accepted iff HTTPS **and** passes SSRF allowlist. `hypothesis`. | same as above / `test_oauth2_payload_pbt.py` | **ABSENT** | No PBT; SSRF-allowlist interaction with `token_url` untested at any level. |
| **3.4** | Unit tests for `OAuth2PasswordGrantPayload`: reject non-HTTPS, reject empty `credential_fields`, default `token_response_path=$.access_token`, accept arbitrary field names, SSRF rejects private/loopback | `tests/unit/admin_api/test_oauth2_payload.py` (does not exist) | **ABSENT** | None of the five enumerated cases tested. Prod code present but unexercised. |
| **5.4** | Integration tests for template API: list-13, category filter, search (CI), detail, 404, **POST from-template create**, **overrides**, **audit `service.registered` w/ template_id**, **change-channel notify**, **409 dup**, **404 unknown** | `tests/integration/admin_api/test_service_templates.py` (exists) | **PARTIAL** | Covered: list-13, category filter, search CI, detail, 404 GET. **Missing: every POST `/from-template` case** — create, overrides, audit-event-with-template_id, change-channel, 409 duplicate, 404 unknown-template. The endpoint (`services.py:464`) is wholly untested. |
| **6.2** | PBT Property 4: arbitrary `credential_fields`+headers → POST body == JSON(credential_fields) and all headers present. `rapid`. | `apps/proxy-plugin/internal/credential/exchanger_test.go` (does not exist) | **ABSENT** | No `exchanger_test.go`; no `rapid`. Request-construction never asserted (body shape, header propagation). |
| **6.3** | PBT Property 5: arbitrary JSON body + valid JSONPath to a string → extraction returns exactly that string. `rapid`. | `exchanger_test.go` (does not exist) | **ABSENT** | `extractJSONPath` (exchanger.go:155) only ever exercised via the egress happy-path with `$.token`; no PBT over nested paths / arbitrary bodies. |
| **6.4** | PBT Property 6: any non-2xx status → `ErrTokenExchangeFailed`. `rapid`. | `exchanger_test.go` (does not exist) | **ABSENT** | Only one example (`500`) via egress test. No sweep of 1xx/3xx/4xx/5xx; mapping not asserted at the exchanger level. |
| **6.5** | Unit tests for `TokenExchanger`: `ErrTokenEndpointUnreachable` on conn timeout, on DNS failure; 10s client timeout configured | `exchanger_test.go` (does not exist) | **ABSENT** | No timeout/DNS-failure test; no assertion that `httpClient.Timeout == 10s` (the value lives at exchanger.go:69 but is untested). |
| **7.2** | PBT Property 7: arbitrary `(tenant,service)` pairs → Get returns only that key's token. `rapid`. | `apps/proxy-plugin/internal/cache/token_cache_test.go` (exists) | **PARTIAL** | Two example-based cases (`TestTokenCache_Get_MissForDifferentKey`) + a 100-goroutine thread-safety loop, but **no `rapid` PBT** over arbitrary key sets proving keyed isolation. No `rapid` import. |
| **7.3** | PBT Property 8: generated JWT/non-JWT + bodies with/without `expires_in` → priority JWT-exp → expires_in → 300s. `rapid`. | `token_cache_test.go` (exists) | **PARTIAL** | ~9 hand-written `DetermineExpiry_*` examples cover each branch once, but no generated inputs; priority *ordering* (JWT-exp beating a present expires_in) is checked in exactly one fixed case. No `rapid`. |
| **7.4** | PBT Property 9: cached tokens at various expiries → Get hits iff expiry > 30s, else miss. `rapid`. | `token_cache_test.go` (exists) | **PARTIAL** | Example boundary cases at 20s/31s/expired present, but no `rapid` sweep across the threshold. No `rapid`. |
| **7.5** | Unit tests for `TokenCache`: empty on construction; memory-only / no persistence | `token_cache_test.go` (exists) | **PARTIAL** | `TestTokenCache_EmptyOnConstruction` covers empty-on-construction. **No-persistence (memory-only, empty-on-restart) is NOT tested** — there's no test simulating a new instance / restart to assert nothing survives. |
| **9.4** | PBT Property 10: refresh-failed + cached token at various expiry states → use cache if not expired, 502 only after full expiry. `rapid`. | `apps/proxy-plugin/internal/egress/oauth2_handler_test.go` (exists) | **PARTIAL** | Two examples (`_GracefulDegradation` at 15s, `_CacheFullyExpired_Returns502`). No `rapid` sweep; `GetForDegradation` boundary (exact absolute-expiry instant) untested. No `rapid`. |
| **9.5** | PBT Property 11: arbitrary token_urls → event has tenant/service/agent/success/latency and `token_url_host` is host-only (no path/query). `rapid`. | `apps/proxy-plugin/internal/audit/emitter_test.go` (exists) | **PARTIAL** | `TestExtractHost` table (7 cases) + one fixed `TokenExchangedEvent` payload assert required fields. No `rapid` over arbitrary URLs proving host-only redaction universally; field-presence asserted for one example only. No `rapid`. |
| **9.6** | PBT Property 12: arbitrary credential_fields + tokens never appear in audit events, log fields, OTel span attrs, response headers/bodies. `rapid`. | `audit/emitter_test.go` / `egress/oauth2_handler_test.go` | **PARTIAL** | Only a **reflection-based JSON-tag name check** (`TestTokenExchangedEventNoCredentialFields`) — name-based, not value-flow. No test feeds a real secret and asserts absence across spans/logs/response. No `rapid`. |
| **9.7** | Integration test: full vault→proxy→exchange→inject Bearer; cache prevents redundant exchange; refresh near-expiry; audit emitted. `testcontainers-go`. | `apps/proxy-plugin/internal/egress/*_integration_test.go` (does not exist) | **ABSENT** | No `testcontainers-go` flow test. The egress handler tests stub the token endpoint with `httptest` and never touch the real vault path or end-to-end injection/audit emission wiring (which lives in `main.go:452`). |
| **10.2** | PBT Property 2: arbitrary valid `OAuth2PasswordGrantCredential` → Put then Get → JSON-decoded structure identical. `rapid`. | `apps/vault-adapter/internal/server/grpc_test.go` (exists) | **PARTIAL** | Two hand-written round-trips (`_RoundTrip`, `_MinimalPayload`) assert byte-for-byte equality — good examples, but not `rapid`-generated arbitrary payloads (varying field names, header maps, unicode, ordering). No `rapid`. |
| **12.2** | vitest: template browser renders category groups; search filters; selection pre-fills form; submit calls from-template | `apps/admin-ui/tests/*.test.ts` (prefill tests exist, pre-existing) | **ABSENT** | The two existing prefill tests are **source-string-grep** (`expect(formSrc).toContain(...)`), don't render, and cover none of the four 12.2 criteria. No test for category grouping, search filtering, or that submit calls `/from-template`. Counted ABSENT for 12.2's stated checklist. |

### 3.1 Tally

- **ABSENT (8):** 2.4, 3.2, 3.3, 3.4, 6.2, 6.3, 6.4, 6.5, 9.7, 12.2 → **wait, recount below.**

Authoritative count:

| Status | Count | Tasks |
|---|---|---|
| **ABSENT** | **10** | 2.4, 3.2, 3.3, 3.4, 6.2, 6.3, 6.4, 6.5, 9.7, 12.2 |
| **PARTIAL** | **8** | 5.4, 7.2, 7.3, 7.4, 7.5, 9.4, 9.5, 9.6, 10.2 → **9** |
| **COVERED** | **0** | — |

Recheck totals against the 19 enumerated optional tasks (2.4, 3.2, 3.3, 3.4, 5.4, 6.2, 6.3, 6.4, 6.5, 7.2, 7.3, 7.4, 7.5, 9.4, 9.5, 9.6, 9.7, 10.2, 12.2):

- **ABSENT (10):** 2.4, 3.2, 3.3, 3.4, 6.2, 6.3, 6.4, 6.5, 9.7, 12.2
- **PARTIAL (9):** 5.4, 7.2, 7.3, 7.4, 7.5, 9.4, 9.5, 9.6, 10.2
- **COVERED (0):** none
- Total = 19. ✓

### 3.2 Cross-cutting blocker for the remediation

**Every PBT task (3.2, 3.3, 6.2, 6.3, 6.4, 7.2, 7.3, 7.4, 9.4, 9.5, 9.6, 10.2) is blocked on a dependency that isn't installed:**
- Go: add `pgregory.net/rapid` to `apps/proxy-plugin/go.mod` and `apps/vault-adapter/go.mod` (`go get pgregory.net/rapid`).
- Python: add `hypothesis` to `apps/admin-api/pyproject.toml` dev deps (it's transitively present in the venv but undeclared — do not rely on that).

The 11 "PARTIAL" PBT tasks already have example-based scaffolding in the right files; the remediation should *add* `rapid`/`hypothesis` cases alongside, not replace.

---

## 4. Summary of worst anti-patterns (priority order)

1. **All 12 property-based tests unwritten; `rapid` not in either go.mod, `hypothesis` undeclared.** The headline feature of the spec's testing strategy is entirely absent.
2. **Admin-UI "tests" assert on source text (`toContain`), never render.** Cannot validate the enhanced picker's category grouping, search, or from-template submit (12.2 effectively absent).
3. **`POST /from-template` (5.3) has zero tests** despite being live prod code; 5.4 covers only the GET endpoints.
4. **Property 12 (sensitive-data exclusion) reduced to a JSON-tag name check** — name-based reflection, no real secret pushed through logs/spans/response.
5. **Misleading green:** `uv run pytest` exits 0 while reporting 61 errors under the wrong (anaconda 3.9) interpreter. The remediation DoD must pin `.venv/bin/python -m pytest`.
6. **No-persistence (7.5) and `GetForDegradation` boundary (9.4) untested**; one near-tautological latency assertion (`> -1`).
