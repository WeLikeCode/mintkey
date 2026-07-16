# Issue intake — oauth2_authorized UI flag missing from API response

## 1. Problem statement
After a successful Gmail OAuth2 authorization (Google → callback → refresh_token stored in `vault.credentials`), the admin UI continues to show the email_service as "Not yet authorized". The data is correct in the backend; the GET endpoints simply don't surface a flag the UI is already declaring.

## 2. User-visible symptom
On `/admin/resources/email_services/records/{id}/show`, the OAuth2 setup widget (`EmailServiceOAuth2Setup.tsx`) displays "Not yet authorized" + Authorize button, even after the operator has completed the Google consent screen and the backend has stored the refresh_token.

## 3. Expected behavior
After `vault.credentials` contains a current, non-revoked row with `auth_scheme=15 (EMAIL_OAUTH2)` for `(tenant_id, service_id)`, the API response from `GET /v1/tenants/{tid}/email-services/{sid}` should include `"oauth2_authorized": true`. The widget reads `record.params.oauth2_authorized` (line 82 of EmailServiceOAuth2Setup.tsx) and renders the green "authorized" status (line 208) when true.

## 4. Evidence (verified 2026-06-03)
- `vault.credentials` row exists:
  - `tenant_id=ce79c39d-33de-4689-b827-2e926cb5f2c7`
  - `service_id=4d696d5d-78ab-44be-a7af-c19b2fd99653`
  - `auth_scheme=15`
  - `is_current=true`
  - `is_revoked=false`
  - `created_at=1780507278134427966` (ns epoch → 2026-06-03 17:21:18 UTC)
- audit event `email.oauth2.authorized` emitted same timestamp
- `httpx HTTP Request: POST https://oauth2.googleapis.com/token "HTTP/1.1 200 OK"` confirms Google exchange succeeded
- `GET /v1/tenants/.../email-services/4d696d5d...` returns 200 but JSON body lacks `oauth2_authorized` (see `apps/admin-api/src/admin_api/api/email_services.py:1894-1911`)
- AdminJS resource declares `{ path: "oauth2_authorized", type: "boolean" }` (line 57 of `apps/admin-ui/src/resources/email-services.ts`) and lists it in `showProperties` (line 110)
- The widget reads `params["oauth2_authorized"] as boolean | undefined` (line 82 of `EmailServiceOAuth2Setup.tsx`)

## 5. Scope
- `apps/admin-api/src/admin_api/api/email_services.py` — `get_email_service` handler (line 1856–1911)
- `apps/admin-api/tests/unit/admin_api/test_email_services.py` (or equivalent) — add unit tests
- OpenAPI / contracts if the response schema is locked elsewhere

## 6. Out of scope
- The OAuth2 callback flow itself (works, verified end-to-end)
- vault put_credential behavior
- The popup postMessage flow (separate concern)
- `list_email_services` (UI does NOT show oauth2_authorized on the list page; add only if cheap and no N+1)
- Any UI changes (the resource already declares the field correctly)

## 7. Risk level
LOW. Read-only API enrichment on an existing endpoint. No schema changes. No security surface (the boolean does not expose credential material — NFR-17 unaffected).

## 8. Verification target — Definition of Done
- [ ] `get_email_service` calls `vault.get_credential(tenant_id, service_id)`; on a non-None result whose `auth_scheme == 15` (AUTH_SCHEME_EMAIL_OAUTH2), the JSON response includes `"oauth2_authorized": true`.
- [ ] When `vault.get_credential` returns None OR auth_scheme != 15, response includes `"oauth2_authorized": false`.
- [ ] If `vault.get_credential` raises an unexpected exception, the endpoint MUST NOT 500 — log the error and return `"oauth2_authorized": false` (fail-closed on display, never fail-open).
- [ ] No NFR-17 violation: never expose `plaintext`, `header_name`, `query_param`, or any other vault metadata in the response.
- [ ] Unit tests added:
  - `test_get_email_service_returns_oauth2_authorized_true_when_vault_has_email_oauth2_cred`
  - `test_get_email_service_returns_oauth2_authorized_false_when_vault_returns_none`
  - `test_get_email_service_returns_oauth2_authorized_false_when_vault_returns_non_oauth2_scheme` (defense in depth — e.g. cred exists but auth_scheme=14 EMAIL_PASSWORD)
  - `test_get_email_service_returns_oauth2_authorized_false_and_logs_when_vault_raises`
- [ ] All existing tests still pass: `cd apps/admin-api && uv run pytest tests/unit/admin_api/test_email_services.py -x`
- [ ] AST scanners still pass: `uv run pytest tests/unit/admin_api/test_audit_coverage.py tests/unit/admin_api/test_no_sql_injection.py -x` (no new audit handlers; no new SQL — but verify)
- [ ] Lint clean: `uv run ruff check` and `uv run mypy src/admin_api/api/email_services.py`
- [ ] Live test (operator-driven): refresh the user's email_service show page → widget shows "Authorized" / green status box.

## 9. Owner decisions made
- Source of truth = `vault.credentials` presence + `auth_scheme=15` (consistent with how other auth schemes treat vault as source of truth).
- Use the existing `VaultAdapterClient.get_credential` gRPC call (no new direct DB join into vault schema; keep abstraction).
- Return only the boolean `oauth2_authorized` — no `oauth2_authorized_at` (UI doesn't need it; would require additional `list_versions` call for created_at).
- Skip list endpoint enrichment (N+1 vault calls per page; UI doesn't show the field on list view).
- Fail-closed: on vault error, return `false` (never block the page load).
