# Issue intake — Outlook userinfo fetch (C-3 parity gap)

## 1. Problem statement
The OAuth2 callback for Outlook does NOT fetch the user's email address. The Outlook branch of `_exchange_oauth2_code_for_refresh_token` was intentionally skipped during C-3 (PR #193) because the originally-requested Outlook scopes (`IMAP.AccessAsUser.All`, `SMTP.Send`, `offline_access`) don't grant Microsoft Graph access. Result: any Outlook email_service authorized through Mintkey has `email_address=""` in its vault envelope, and IMAP XOAUTH2 login fails with "credentials username is empty" — the same blocker we fixed for Gmail in C-3.

## 2. User-visible symptom
Operator authorizes a Microsoft 365 business mailbox via the admin UI → callback completes 200 OK → vault row written → agent tries `email_list_mailboxes` → email-proxy returns 503 with `pool.Get: pool: dial outlook.office365.com:993: imap: Dial: credentials username is empty`.

(Not observed live yet — operator hasn't authorized Outlook yet — but architecturally identical to the Gmail bug confirmed in session at 2026-06-03 20:54:03Z.)

## 3. Expected behavior
After the Microsoft token exchange returns success, Mintkey performs `GET https://graph.microsoft.com/v1.0/me` using the access_token, extracts the user's primary email (prefer `mail`, fall back to `userPrincipalName`), stores it in the vault JSON envelope alongside `refresh_token` and `provider`. The email-proxy XOAUTH2 path then reads `email_address` exactly like it does for Gmail.

## 4. Evidence
- `apps/admin-api/src/admin_api/api/email_services.py:994-1041` — current `_exchange_oauth2_code_for_refresh_token` body. The Outlook branch is explicitly gated:
  ```python
  if provider == "gmail":
      # ... gmail userinfo fetch ...
  # else: provider == "outlook" — see comment above; intentionally no extra
  # call. email_address remains "".
  ```
- C-3 implementer report (in `remediation/active/2026-06-03-email-imap-addr-and-grant-notify/04-progress.md`) flags this as a follow-up.
- Current `_OUTLOOK_SCOPES` at `email_services.py:78-82`:
  ```
  "https://outlook.office.com/IMAP.AccessAsUser.All "
  "https://outlook.office.com/SMTP.Send "
  "offline_access"
  ```
  Lacks `User.Read` (Microsoft Graph). Without it, Graph `/me` returns 401.

## 5. Scope
- `apps/admin-api/src/admin_api/api/email_services.py`:
  - Add `_OUTLOOK_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"` module-level constant near the existing `_GMAIL_USERINFO_URL`.
  - Add `User.Read` to `_OUTLOOK_SCOPES`.
  - In `_exchange_oauth2_code_for_refresh_token`, replace the "intentionally skipped" Outlook block with a Graph `/me` fetch parallel to Gmail's. Prefer `mail` over `userPrincipalName` when extracting the address. Same fail-closed-with-WARNING-log semantics as Gmail.
- `apps/admin-api/tests/unit/admin_api/test_email_services.py`:
  - Add tests parallel to the C-3 Gmail tests under a new `TestOutlookUserinfo` class:
    - `test_exchange_oauth2_code_outlook_stores_json_envelope_with_email_address` (happy path; mock Graph `/me` returning `{"mail": "user@biz.example", "userPrincipalName": "user@biz.example"}`)
    - `test_exchange_oauth2_code_outlook_falls_back_to_upn_when_mail_missing` (Graph returns `{"userPrincipalName": "user@biz.example"}` only — common for some account types)
    - `test_exchange_oauth2_code_outlook_userinfo_failure_still_stores_with_empty_email` (Graph 500 / httpx raise → email_address="" but vault put still happens)
    - `test_exchange_oauth2_code_outlook_payload_no_pii_leak_in_logs` (canary check: refresh_token / access_token / email / client_secret never appear in caplog)
- (Optional but desirable) The existing C-3 Gmail tests should still pass — verify no regressions in `TestOAuth2VaultEnvelopeC3`.

## 6. Out of scope
- Email-proxy changes (the parser `parseEmailAddressFromPayload` already reads `email_address` correctly — same JSON envelope shape works for Outlook).
- Token-exchange retries or backoff for Graph failures.
- Tenant-policy admin-consent edge cases (operator's Azure setup concern, not Mintkey code).
- Updating the AdminJS resource — no UI change needed.
- Migration / backfill of any existing Outlook vault rows (we have none today; first Outlook authorize will land via the fixed code).

## 7. Risk
LOW. Mirrors the C-3 Gmail change exactly; same test surface, same fail-closed semantics, same NFR-17 hygiene. The only new behavior is one extra outbound HTTP call to `graph.microsoft.com` after the token exchange — wrapped in try/except with WARNING-on-failure.

## 8. Verification target — DoD
- [ ] `_OUTLOOK_USERINFO_URL` module-level constant added; commented to reference Graph `/me`.
- [ ] `_OUTLOOK_SCOPES` now includes `User.Read` (or `https://graph.microsoft.com/User.Read` if Microsoft requires the full URL form — implementer chooses based on Graph docs; both work in 2026, but `User.Read` is canonical).
- [ ] In `_exchange_oauth2_code_for_refresh_token`, the Outlook branch fetches `/me`, extracts `mail` (then `userPrincipalName`), stores in vault envelope.
- [ ] On Graph failure (httpx error / non-200 / missing both `mail` and `userPrincipalName`): WARNING log + `email_address=""` + vault put still happens. Flow does NOT abort.
- [ ] NFR-17: refresh_token / access_token / vault_plaintext / client_secret / email_address never logged. PII canary test covers the Outlook fixtures.
- [ ] Scrub via `del` in `finally` block (same pattern as Gmail).
- [ ] 4 new tests added; all pass.
- [ ] Existing tests still pass: `pytest tests/unit/admin_api/test_email_services.py -x -q`.
- [ ] AST scanners pass (`test_audit_coverage.py`, `test_no_sql_injection.py`, `test_no_plaintext_in_audit.py`).
- [ ] `ruff check` + `mypy` clean on the modified source.
- [ ] PR opened against main, dep-review PASS, merged via merge-commit + `--admin`.
- [ ] (Operator) After merge + admin-api rebuild: any new Outlook authorize produces a vault envelope with non-empty `email_address`. (Not strictly part of DoD — operator will validate when they actually register an Outlook account.)

## 9. Owner decisions
- **Graph `/me` preference order**: `mail` → `userPrincipalName`. Reasoning: `mail` is the SMTP address (matches what Exchange Online IMAP expects as the SASL username); `userPrincipalName` is the canonical identity but for some account types is in `@<tenant>.onmicrosoft.com` form which IMAP wouldn't accept.
- **Scope addition**: add `User.Read` to `_OUTLOOK_SCOPES`. Adds NO meaningful operator burden (the operator's Azure app registration adds `User.Read` in the same click as the other delegated permissions). Existing Outlook authorizations (none today) would need re-auth to get the new scope.
- **Same-PR scope**: combine code + scope constant + tests into one PR. Mirrors the C-3 Gmail PR shape exactly.
- **No retry/backoff** on the Graph call: a single attempt with 15s timeout (same as Gmail). Fail-closed-with-empty-email is acceptable; operator can re-auth.
