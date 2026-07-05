# Contabo Service Template

## Why

Operators running cloud infrastructure on Contabo want AI agents to manage
their VPS/VDS fleet — list instances, start/stop/restart machines, manage
snapshots, inspect private networks, and handle DNS — without ever handing
the agent a long-lived Contabo API credential. Mintkey already brokers this
pattern for GitHub, Stripe, Cloudflare, and others via **service templates**
(`apps/admin-api/src/admin_api/templates/service_templates.yaml`).

There is no Contabo template today. An operator must hand-enter the base URL,
auth type, four credential fields, token endpoint URL, and the correct
`grant_type=password` form field from scratch — and get the Keycloak endpoint
and form encoding right by hand. A pre-configured template removes that
friction.

## Auth model

Contabo authenticates via **OAuth2 Resource Owner Password Credentials (ROPC)**
against a Keycloak instance:

```bash
POST https://auth.contabo.com/auth/realms/contabo/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

client_id=<clientId>&client_secret=<clientSecret>&username=<apiUser>&password=<apiPassword>&grant_type=password
```

The response contains `access_token` (JWT, typically 1 hour TTL). Every
upstream call uses `Authorization: Bearer <access_token>`.

This maps onto the existing `oauth2_password_grant` auth type — **but with one
gap**: the current `TokenExchanger.Exchange()` in
`apps/proxy-plugin/internal/credential/exchanger.go` always marshals
`credential_fields` as a JSON body (`Content-Type: application/json`). Keycloak
requires `application/x-www-form-urlencoded`. The exchanger must be extended to
support form encoding, controlled via `token_request_headers`.

## What Changes

### Code (two files)

1. **`apps/proxy-plugin/internal/credential/exchanger.go`** — extend `Exchange()`
   to use `url.Values` form encoding when
   `req.TokenRequestHeaders["Content-Type"] == "application/x-www-form-urlencoded"`.
   Backward-compatible: existing JSON-based templates are unaffected.

2. **`apps/admin-api/src/admin_api/templates/models.py`** — add
   `token_request_headers: dict[str, str] | None = None` to `CredentialHint`
   so the Admin UI can surface the required `Content-Type` header to operators.

### Data (one file)

3. **`apps/admin-api/src/admin_api/templates/service_templates.yaml`** — add the
   `contabo` HTTP service template entry with `auth_type: oauth2_password_grant`,
   the correct `token_url`, `credential_fields`, `token_request_headers`, and
   `test_path`.

### Tests (two files)

4. **`apps/proxy-plugin/internal/credential/exchanger_test.go`** — add tests for
   form-encoded body posting; verify existing JSON path is unaffected.

5. **`apps/admin-api/tests/unit/admin_api/test_email_service_templates.py`** —
   extend the template registry test with a `test_contabo_template_fields` method.

## Capabilities

### New Capabilities

- **Contabo service template**: operators register a Contabo service in one click
  via "Add from template"; the proxy handles the Keycloak token exchange
  transparently.
- **Form-encoded token exchange**: the `oauth2_password_grant` exchanger gains
  support for `application/x-www-form-urlencoded` token endpoints (broader than
  Contabo — any OIDC/Keycloak-backed service benefits).

### Modified Capabilities

- `oauth2_password_grant` exchanger: adds form-encoding path, backward-compatible.

## Impact

- **No wire-contract changes**: no `openapi.yaml` path additions, no MCP tool
  additions, no `vault.proto` enum change, no Liquibase changeset.
- **No ADR needed**: uses the already-Accepted `oauth2_password_grant` mechanism
  (ADR-0011 Go stack, ADR-0014 credential injector) with a backward-compatible
  encoding extension.
- **`x-request-id` header**: Contabo requires this UUID4 header on every API
  call. It is agent-supplied and proxy-forwarded. No proxy code change needed.
  Documented in `config_notes`.
