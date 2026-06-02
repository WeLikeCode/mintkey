# Email-proxy integration tests

## Build tag: `integration`

Integration tests live under `tests/integration/` and are **excluded from the
default `go test ./...` run** by the `//go:build integration` build tag at the
top of every file.

## Running locally

```sh
cd apps/email-proxy
go test -tags=integration ./tests/integration/... -v -count=1
```

Add `-timeout 120s` if your machine is slow:

```sh
go test -tags=integration ./tests/integration/... -v -count=1 -timeout 120s
```

## What is tested

| Test | Coverage |
|------|----------|
| `TestInteg_ListMailboxes_HappyPath` | Full list_mailboxes path: vault → IMAP connect → LIST → 200 + audit event |
| `TestInteg_ListMessages_HappyPath` | Pre-populated INBOX → list_messages returns correct subject |
| `TestInteg_SendMessage_HappyPath` | send_message reaches SMTP stub + emits email.message.sent audit |
| `TestInteg_SendMessage_AuditPayload_NoBodyLeak` | Body content never appears in emitted audit payload |
| `TestInteg_Metrics_AuditCounterIncremented` | Audit emitter count increases after each handler call |
| `TestInteg_OAuth2Revoked_Returns401` | 401 from admin-api mock propagates as 401 to caller |
| `TestInteg_ScrubBodyForLog_ShapeAndNoContent` | ScrubBodyForLog never leaks input content |
| `TestInteg_MultipleHandlers_AuditEventsEmitted` | Back-to-back handler calls emit distinct audit event types |

## Infrastructure

- **IMAP server**: `github.com/emersion/go-imap/v2/imapserver/imapmemserver` —
  in-process, no TLS, `InsecureAuth: true`.
- **OAuth2 admin-api**: `net/http/httptest` server returning mock `access_token`.
- **SMTP**: `integSMTPStub` captures send calls; no real server needed.
- **Vault**: `itVaultStub` returns password-scheme or OAuth2-scheme credentials
  pointing at the in-process IMAP server.

## Excluded from CI (default)

Integration tests are not required for PR merge gates (see memory/MEMORY.md
`project_mintkey_ci_merge_gates.md`). They are designed for pre-merge local
verification.
