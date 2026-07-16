# Orchestration state — email IMAP addr + email-permission-grants NOTIFY

## DoD (from 00-issue-intake.md §8)
### C-1 (Bug A — blocker)
- [ ] leaseIMAPClient uses cred.IMAPHost:cred.IMAPPort as primary, with payload + BaseUrl as ordered fallbacks.
- [ ] 5+ table-driven Go tests.
- [ ] go test ./... clean; go vet clean.
- [ ] Live: Gmail email_list_mailboxes returns 200 (or fails on cert/auth, not addr).
### C-2 (Bug B)
- [x] create_email_permission_grant emits pg_notify('mintkey:agent', payload).
- [x] delete_email_permission_grant does the same.
- [x] NFR-17 payload check; bound SQL.
- [x] Unit tests + AST scanners clean (11 + 115 + 26 PASS; ruff + mypy clean).
- [x] admin-api rebuilt + container healthy; 3 notify_change references in /app source.
- [ ] Live: grant invalidates cache immediately. Verifiable on next operator grant create/revoke + Hermes mintkey_discover within 5 min. Not blocking C-3.

## Chunks
- **C-1**: email-proxy IMAP addr fix (blocker) — DONE
- **C-2**: admin-api email_permission_grants pg_notify — DONE
- **C-3**: admin-api OAuth2 vault payload JSON envelope + Gmail userinfo fetch (Bug C, added mid-session) — DONE

## C-3 (Bug C) round 1 — PASS
- IMPLEMENTER: added `_GMAIL_USERINFO_URL`, rewrote `_exchange_oauth2_code_for_refresh_token` to fetch Gmail userinfo, store JSON envelope `{provider, refresh_token, email_address}`; added `_parse_oauth2_plaintext` helper + rewired `oauth2_refresh` for backwards-compat; extended `_ExchangeResult.email_address` + propagated to all 4 `email.oauth2.authorized` audit_emit callers.
- REVIEWER (fresh): PASS on all 16 adversarial checks.
- 7 new tests + 72 total in test_email_services.py + 28 AST scanners; ruff + mypy clean.
- admin-api rebuilt; container healthy; 31 references to {_parse_oauth2_plaintext, _GMAIL_USERINFO_URL, email_address} in /app source.

### C-3 DoD
- [x] Gmail userinfo fetch via `https://www.googleapis.com/gmail/v1/users/me/profile` (Bearer access_token).
- [x] Userinfo failure logs WARNING + proceeds with empty email_address (non-fatal).
- [x] Outlook explicitly skipped (scope limitation documented).
- [x] Vault payload stored as JSON envelope.
- [x] `oauth2_refresh` handles JSON envelope AND legacy raw string (backwards compat).
- [x] audit `email.oauth2.authorized` payload includes email_address.
- [x] NFR-17: no refresh_token / access_token / vault_plaintext / client_secret in logs. PII canary test covers all 4.
- [x] Scrub `del refresh_token / access_token / vault_plaintext` in `finally`.
- [ ] Live: re-authorize Gmail → vault row updated → `email_list_mailboxes` returns 200 with XOAUTH2 login succeeding.

## Current round
- C-1 round 1 — PASS (code green). Awaiting live verification.

## Round history
### C-1 round 1 (2026-06-03)
- IMPLEMENTER (ae55ec6c…): added `resolveIMAPAddr(cred, payloadIMAPHost) string` helper to `email.go`. All 3 email auth-scheme branches in `leaseIMAPClient` call it. OAuth2 passes `""` (no payload imap_host); password/app_password pass `parsePasswordPayload`'s result. Priority: IMAPHost+IMAPPort → payloadIMAPHost → BaseUrl → "". 8 table-driven helper tests + 1 end-to-end OAuth2 test. `+~50 / -~5` in email.go; `+111` new email_internal_test.go; `+~93` in handlers_email_test.go.
- REVIEWER (a717342c…, fresh): PASS on all 10 adversarial checks (priority order, edge cases IMAPPort=0 / IMAPHost="", password backwards compat, OAuth2 doesn't read payload, default unchanged, NFR-17, SMTP untouched, 503 guard intact, primary-overrides-fallbacks test would catch a regression).
- All commands clean: go test (full email-proxy regression), go vet, gofmt on touched files.
- email-proxy rebuilt + restarted via `docker compose up -d --build email-proxy`. Container healthy.

## DoD status after C-1 round 1
### C-1
- [x] resolveIMAPAddr helper with documented priority.
- [x] All 3 email auth-scheme branches use the helper.
- [x] 8 table-driven + 1 end-to-end tests passing.
- [x] go test ./..., go vet, gofmt clean (on touched files).
- [x] email-proxy image rebuilt + container restarted.
- [x] Live: Gmail `email_list_mailboxes` no longer fails with "no IMAP address found". 2026-06-03 20:54:03 — addr resolved to `imap.gmail.com:993`, advanced to dial. Failed with NEW error "credentials username is empty" (Bug C, separate task #363). C-1 DoD met: failure is now auth, not addr.

## Open questions
*(none)*

## Notes
- Vault-adapter side is already correct — no changes needed there.
- SMTP path (getSMTPCredential) already correct — no changes needed there.

## Outcome — CLOSED 2026-06-03

C-1 (IMAP addr resolver), C-2 (email_permission_grant pg_notify), and C-3 (Gmail userinfo + JSON envelope) all merged in PR #193 (`ed511e36`): chore(email-stack-fixes). Commits on main: `66be2fd` (email-proxy IMAP addr), `f309dd3` (admin-api pg_notify), `c716b41` (OAuth2 vault envelope with email_address + authz flag). All DoD checks met. Outlook parity tracked separately in 2026-06-07-outlook-userinfo.
