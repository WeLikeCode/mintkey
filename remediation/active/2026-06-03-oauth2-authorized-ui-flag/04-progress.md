# Orchestration state — oauth2_authorized UI flag

## Definition of Done (from 00-issue-intake.md §8)
- [ ] `get_email_service` derives `oauth2_authorized` from `vault.get_credential` (auth_scheme=15 → true; otherwise false).
- [ ] Fail-closed on vault error (return false, do not 500).
- [ ] NFR-17 unaffected — no vault material leaks into response.
- [ ] 4 unit tests added and passing.
- [ ] Existing tests still pass.
- [ ] AST scanners still pass.
- [ ] Lint + mypy clean.
- [ ] Live UI test confirms green "authorized" status after refresh.

## Chunks
- **C-1**: Add vault.get_credential call to `get_email_service`; derive `oauth2_authorized`; add tests.

## Current round
- C-1 round 1 — PASS (implementer + fresh reviewer both green).

## Round history
### C-1 round 1 (2026-06-03)
- IMPLEMENTER (a0e800bd…): added `_AUTH_SCHEME_EMAIL_OAUTH2 = 15` module constant, `vault` Depends param, try/except vault call with fail-closed warning log, `oauth2_authorized` boolean in response. 4 new tests + 3 existing call-site updates. `+234/-0`.
- REVIEWER (a3cb06c2…, fresh): PASS on all 8 adversarial checks (NFR-17, fail-closed, auth_scheme=14 case, no new SQL, module constant, list_email_services untouched, WARNING log without plaintext, `await` present).
- All commands green: 65 unit tests, 26 AST-scanner tests, ruff clean, mypy clean.

## DoD status
- [x] `get_email_service` derives `oauth2_authorized` from `vault.get_credential` (auth_scheme=15 → true; otherwise false).
- [x] Fail-closed on vault error (returns false, does not 500).
- [x] NFR-17 unaffected — confirmed by reviewer grep + canary test.
- [x] 4 unit tests added and passing.
- [x] Existing tests still pass (61 → 65 in test_email_services.py).
- [x] AST scanners still pass.
- [x] Lint + mypy clean.
- [ ] Live UI test confirms green "authorized" status — REQUIRES admin-api rebuild + operator refresh.

## Open questions
*(none)*

## Notes
- Vault row already confirmed in DB; the operator does not need to re-authorize.
- The UI resource + widget already read `oauth2_authorized`; no UI changes required.

## Outcome — CLOSED 2026-06-03

C-1 merged in PR #193 (`ed511e36`). `get_email_service` now derives `oauth2_authorized` from vault (auth_scheme=15 → true, fail-closed on error). All 7/8 DoD boxes checked; live UI confirmation deferred to operator action after admin-api rebuild. admin-api image rebuilt during PR #193 session; container healthy with the flag live.
