# Tasks — Contabo Service Template

## Task 1 — Extend exchanger for form-encoded token bodies

**File**: `apps/proxy-plugin/internal/credential/exchanger.go`

In `Exchange()`, detect `Content-Type: application/x-www-form-urlencoded` in
`req.TokenRequestHeaders` and encode the body as `url.Values` instead of JSON.
Existing JSON path unchanged.

Verify: `go build ./...` in the proxy-plugin workspace passes.

## Task 2 — Add exchanger tests for form encoding

**File**: `apps/proxy-plugin/internal/credential/exchanger_test.go`

Add:
- `TestExchange_FormEncoded_Success`: mock server asserts form-encoded body +
  correct Content-Type, returns `{"access_token":"tok","expires_in":3600}`.
- `TestExchange_JSON_BackwardCompat`: confirm existing JSON path unaffected when
  no `token_request_headers` is set.

Verify: `go test ./internal/credential/... -run TestExchange` passes.

## Task 3 — Add `token_request_headers` to `CredentialHint` model

**File**: `apps/admin-api/src/admin_api/templates/models.py`

Add `token_request_headers: dict[str, str] | None = None` to `CredentialHint`.
No migration needed — optional field, no DB involvement.

Verify: existing template YAML loads without error (run template registry import).

## Task 4 — Add Contabo template to service_templates.yaml

**File**: `apps/admin-api/src/admin_api/templates/service_templates.yaml`

Append the `contabo` entry (see design.md "Exact YAML entry") after the
`tailscale` template.

Verify: `python -c "from admin_api.templates.registry import TemplateRegistry; r = TemplateRegistry(); assert r.get('contabo') is not None"`.

## Task 5 — Add template registry test

**File**: `apps/admin-api/tests/unit/admin_api/test_email_service_templates.py`

Add `test_contabo_template_fields` in `TestEmailTemplateYamlLoading` and
extend `test_existing_http_templates_default_to_http_service_kind` to include
`"contabo"` in the `http_ids` assertion.

Verify: `cd apps/admin-api && uv run pytest tests/unit/admin_api/test_email_service_templates.py -v`.

## Task 6 — Go tests pass clean

Run `cd apps/proxy-plugin && go test ./...` and confirm exit 0.

## Task 7 — Python unit suite passes clean

Run `cd apps/admin-api && uv run pytest tests/unit/` and confirm exit 0.
