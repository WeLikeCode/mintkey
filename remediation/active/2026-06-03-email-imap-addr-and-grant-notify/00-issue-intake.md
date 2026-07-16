# Issue intake — email IMAP addr resolution + email-permission-grants cache invalidation

## 1. Problem statement
Two related bugs blocking end-to-end email functionality for newly-credentialed email_services:

- **Bug A (blocker):** `leaseIMAPClient` in email-proxy resolves the IMAP dial `addr` from `cred.BaseUrl` (OAuth2 branch) or `parsePasswordPayload(...)` with fallback to `cred.BaseUrl` (email_password / email_app_password branches). For email_services rows, `cred.BaseUrl` is empty because the vault-adapter's JOIN sources it from `public.services` (which doesn't contain email_services rows). Result: addr=`""`, handler returns `"no IMAP address found for service %s"`, HTTP 503. The vault-adapter already returns `cred.IMAPHost` / `cred.IMAPPort` from a JOIN with `public.email_services` (postgres.go:194 → grpc.go:361), but the handler never reads them.

- **Bug B (mitigated by TTL):** `create_email_permission_grant` and `delete_email_permission_grant` (admin-api) emit audit events but do NOT emit `pg_notify('mintkey:agent', ...)`. The mcp-server discovery cache (TTL 300s, keyed per `(tenant_id, agent_id)`) is invalidated only on receiving that NOTIFY (subscriber.py:122). Result: after an operator creates an email-permission grant, the agent's discovery cache shows stale data for up to 5 minutes. Regular `permission_grants` (HTTP/SSH services) do emit this NOTIFY at permissions.py:633.

## 2. User-visible symptom
- **Bug A:** Hermes_agent1 calls `email_list_mailboxes` for Gmail service `4d696d5d-78ab-44be-a7af-c19b2fd99653` → `503 Service Unavailable`. email-proxy logs: `"list_mailboxes: failed to lease IMAP client", "error":"no IMAP address found for service 4d696d5d-78ab-44be-a7af-c19b2fd99653"`. Affects ALL IMAP tools (`email_list_mailboxes`, `email_list_emails`, `email_search_messages`, `email_fetch_message`, `email_mark_email`, `email_move_email`, `email_delete_email`, `email_download_attachment`) for any email_service whose vault credential was set via the current `set_email_service_credential` endpoint (cb2ae0b 2026-06-02 20:20) OR the OAuth2 callback flow. Pre-cb2ae0b credentials (e.g. `cici-softuraj` d28eec49-…) still work because their vault payload was bootstrapped with an `imap_host` field that `parsePasswordPayload` picks up.
- **Bug B:** Operator creates a permission grant; agent calling `mintkey_discover` within 5 minutes does not see the new service. Forces operator/agent to wait or manually restart the mcp-server.

## 3. Expected behavior
- **Bug A:** `leaseIMAPClient` should source the IMAP dial address from `cred.IMAPHost`+`cred.IMAPPort` for ALL email auth schemes (the JOIN already populates them). The old JSON-payload `imap_host` field and `cred.BaseUrl` fallback can remain as backwards-compat for pre-existing rows but should NOT be the primary source going forward. After fix, `GET /v1/email-proxy/mailboxes` for service `4d696d5d-…` returns 200 with the Gmail mailbox list. SMTP path (`getSMTPCredential`, line 1248) already does this correctly via `cred.SMTPHost`/`cred.SMTPPort` — mirror that pattern.
- **Bug B:** After creating or deleting an `email_permission_grant`, mcp-server's discovery cache for affected `(tenant, agent)` is invalidated immediately, so the very next `mintkey_discover` call returns fresh data. Mirror the pattern in `permissions.py:633` for HTTP/SSH grants.

## 4. Evidence (verified 2026-06-03)

### Bug A
- email-proxy log at 20:09:18: `{"level":"WARN","msg":"list_mailboxes: failed to lease IMAP client","error":"no IMAP address found for service 4d696d5d-78ab-44be-a7af-c19b2fd99653"}`
- HTTP response: `GET /v1/email-proxy/mailboxes  → 503  (6017ms)`
- admin-api log just before: `POST /v1/internal/oauth2/gmail/refresh?service_id=4d696d5d-...  → 200 OK` (OAuth2 access_token fetch succeeded, so the failure is strictly the IMAP addr resolution).
- Source: `apps/email-proxy/internal/server/handlers/email.go:1165-1216`. OAuth2 branch line 1190 (`addr = cred.BaseUrl`), password branches lines 1192-1203 (`addr = imapHost; if addr == "" { addr = cred.BaseUrl }`).
- `cred.BaseUrl` comes from vault.proto `BaseUrl` field, populated at `apps/vault-adapter/internal/server/grpc.go:357` from `result.BaseUrl`, which is `rec.ServiceBaseUrl` (vault.go:348), which is `COALESCE(s.base_url, '')` from JOIN with `public.services` (postgres.go:190). `email_services` rows have no corresponding `public.services` row, so this returns `''`.
- `cred.IMAPHost`+`cred.IMAPPort` are populated at vault-adapter/internal/server/grpc.go:361-362 from JOIN with `public.email_services` (postgres.go:194-195). Email-proxy reads them into the Credential struct at `apps/email-proxy/internal/vault/client.go:223-224`. They are NEVER read by `leaseIMAPClient`.

### Bug B
- `apps/admin-api/src/admin_api/api/email_permission_grants.py:72-230` (create handler) — emits audit at line 169 but no `pg_notify`.
- `apps/admin-api/src/admin_api/api/email_permission_grants.py:275-322` (delete handler) — emits audit at line 315 but no `pg_notify`.
- Compare `apps/admin-api/src/admin_api/api/permissions.py:633` which DOES emit `pg_notify('mintkey:agent', {tenant_id, agent_id, ...})`.
- `apps/mcp-server/src/mcp_server/changes/subscriber.py:122` invalidates discovery cache on `_on_agent_change` (mintkey:agent channel).
- Discovery cache TTL = 300s (`cache/discovery.py:23`).

## 5. Scope

### Chunk C-1 (Bug A — blocker, dispatch first)
- `apps/email-proxy/internal/server/handlers/email.go` — `leaseIMAPClient` (lines 1165-1232): change all email auth-scheme branches to use `cred.IMAPHost:cred.IMAPPort` as primary, with existing `imap_host`-in-payload + `cred.BaseUrl` only as fallbacks.
- `apps/email-proxy/internal/server/handlers/email_test.go` (or wherever `leaseIMAPClient` is tested) — add table-driven tests covering: OAuth2 with IMAPHost set; email_password with IMAPHost set; email_app_password with IMAPHost set; legacy fallback case where IMAPHost empty but payload has `imap_host`; legacy fallback to BaseUrl; failure case where ALL three are empty.

### Chunk C-2 (Bug B — sequenced after C-1)
- `apps/admin-api/src/admin_api/api/email_permission_grants.py` — add `pg_notify('mintkey:agent', json_payload)` to both `create_email_permission_grant` (after audit emit) and `delete_email_permission_grant` (after audit emit).
- `apps/admin-api/tests/unit/admin_api/test_email_permission_grants.py` — add tests that the NOTIFY is emitted with expected payload shape (mock-based, no real DB listen).
- Optional but desirable: an integration test that creates a grant and verifies the mcp-server discovery cache is invalidated end-to-end (deferred to a separate task if it requires complex test infra).

## 6. Out of scope
- The `email_fetch_message → 401 Unauthorized` observed in logs (Hermes' brokered JWT scope / expiry issue — separate concern).
- Backfilling `imap_host` into pre-existing vault JSON payloads (the fallback chain handles them).
- Refactoring `parsePasswordPayload` to remove the now-redundant `imap_host` parse (keep for backwards compat).
- Changing vault-adapter response shape (it's already correct).
- mcp-server discovery cache TTL changes.
- Any UI / AdminJS resource changes.

## 7. Risk level
- **C-1: MEDIUM.** Touches the production IMAP code path. Multiple branches (OAuth2 + password + app_password). However, the fix is small, well-localized, and adding a primary source while keeping fallbacks is strictly additive for existing rows.
- **C-2: LOW.** Pure additive — emit a notification after an already-committed transaction. Mirrors existing pattern.

## 8. Verification target — Definition of Done

### C-1 (Bug A)
- [ ] `leaseIMAPClient` constructs `addr` as `cred.IMAPHost:cred.IMAPPort` when `cred.IMAPHost != ""` and `cred.IMAPPort != 0`, for all 3 email auth schemes (OAuth2 + password + app_password).
- [ ] Falls back to existing JSON-payload `imap_host` or `cred.BaseUrl` only when `cred.IMAPHost` is empty (backwards compat).
- [ ] No NFR-17 violation: no plaintext / credential material echoed into logs.
- [ ] At least 5 new table-driven tests covering primary path + 2 fallback paths + failure path + at least one for each of the 3 auth schemes.
- [ ] Existing email-proxy tests still pass: `cd apps/email-proxy && go test ./internal/server/handlers/... -count=1`.
- [ ] Wider regression: `cd apps/email-proxy && go test ./... -count=1`.
- [ ] No new `go vet ./...` warnings.
- [ ] Live verification: after rebuild of `mintkey-email-proxy` image, `email_list_mailboxes` for Gmail service `4d696d5d-…` returns 200 (or fails on cert/auth not addr).

### C-2 (Bug B)
- [ ] `create_email_permission_grant` emits `pg_notify('mintkey:agent', payload)` where `payload` is a JSON dict including `tenant_id`, `agent_id`, `email_service_id`, and a `change_type` discriminator (e.g. `"email_permission_grant.created"`). Payload MUST NOT contain credential material.
- [ ] `delete_email_permission_grant` does the same with `change_type: "email_permission_grant.revoked"`.
- [ ] Bound SQL parameters only (no f-strings into `text()`).
- [ ] Both handlers emit NOTIFY AFTER the audit event is emitted, mirroring `permissions.py`.
- [ ] Unit tests assert the NOTIFY call is made with expected payload shape.
- [ ] Existing tests still pass: `cd apps/admin-api && uv run python -m pytest tests/unit/admin_api/test_email_permission_grants.py -x`.
- [ ] Lint + mypy clean: `uv run ruff check src/admin_api/api/email_permission_grants.py` and `uv run python -m mypy src/admin_api/api/email_permission_grants.py`.
- [ ] AST scanners pass: `uv run python -m pytest tests/acceptance/test_audit_coverage.py tests/acceptance/test_no_sql_injection.py -x` (no new SQL string interpolation; audit already present).
- [ ] Live verification: after admin-api rebuild, creating a grant immediately invalidates the agent's discovery cache (next `mintkey_discover` call hits DB, not cache).

## 9. Owner decisions
- **Primary IMAP addr source = `cred.IMAPHost`+`cred.IMAPPort`** (the JOIN-populated fields). Keep payload-`imap_host` and `cred.BaseUrl` as ordered fallbacks for backwards compat.
- **NOTIFY channel = `mintkey:agent`** (same channel as regular `permission_grants`). Already invalidates the full tenant cache, so no need for a new channel.
- **No backfill** of pre-existing vault rows with `imap_host`. Fallback handles them.
- **NFR-17:** NOTIFY payload includes `tenant_id`, `agent_id`, `email_service_id`, `change_type` — NO email_address, NO usernames, NO tokens.
