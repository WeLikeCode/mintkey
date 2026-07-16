# Remediation: Outlook userinfo fetch (C-3 parity gap)

**Session:** 2026-06-07-outlook-userinfo
**Branch:** feat/outlook-userinfo
**Pattern:** direct (single chunk, fresh reviewer)

## Summary

See `00-issue-intake.md` for full intake. Bug: Outlook branch of `_exchange_oauth2_code_for_refresh_token` did not fetch Graph `/me`, leaving `email_address=""` in vault envelope. IMAP XOAUTH2 login then failed with "credentials username is empty".

## Chunks

- **C-1** — Add `_OUTLOOK_USERINFO_URL`, add `User.Read` to `_OUTLOOK_SCOPES`, implement Graph `/me` fetch with `mail`→`userPrincipalName` fallback, 4 new unit tests.

## Round history

- **R1**: C-1 implemented and reviewed. All DoD checks satisfied.

## Outcome — CLOSED 2026-06-07

Merged as PR #197 (`68f2d84`). Commit `a1352ca`: feat(admin-api): fetch Outlook user email via Graph /me (C-3 parity). `_OUTLOOK_SCOPES` now includes `User.Read`. Graph `/me` fetch fail-closed with WARNING. All 4 new tests + existing suite pass. NFR-17 canary clean. Existing Outlook vault rows (none at merge time) will get `email_address` populated on next re-auth.
