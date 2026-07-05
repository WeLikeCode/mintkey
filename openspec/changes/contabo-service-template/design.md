# Design — Contabo Service Template

## Context

Contabo's REST API (`https://api.contabo.com`, all paths under `/v1/`) uses
OAuth2 ROPC for every call. The operator provides four credentials from the
Contabo Customer Control Panel (`https://my.contabo.com/api/details`):

| Field | Description |
|---|---|
| `client_id` | OAuth2 client ID for API access |
| `client_secret` | OAuth2 client secret |
| `username` | API User (operator's email address) |
| `password` | API Password (separate from the web-console login password) |
| `grant_type` | Always `"password"` (ROPC grant; fixed value) |

Token exchange:
```
POST https://auth.contabo.com/auth/realms/contabo/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

client_id=...&client_secret=...&username=...&password=...&grant_type=password
```

Response: standard OAuth2 `{"access_token": "...", "expires_in": 3600, ...}`.

## Decisions

**D1 — `auth_type: oauth2_password_grant` (existing scheme, not a new one)**

The ROPC flow is structurally identical to what the `oauth2_password_grant`
auth type does: store N credential fields, exchange them at a token URL, inject
the resulting bearer token. The only gap is body encoding. Introducing a new
auth scheme (`oauth2_ropc_form`, etc.) would duplicate the entire flow; the
minimal, backward-compatible approach is to extend the exchanger to detect
`Content-Type: application/x-www-form-urlencoded` and use `url.Values` encoding.

**D2 — Form-encoding controlled by `token_request_headers["Content-Type"]`**

The credential payload already has a `token_request_headers` map. Setting
`{"Content-Type": "application/x-www-form-urlencoded"}` is the natural signal.
The exchanger checks this header:
- `application/x-www-form-urlencoded` → encode body as `url.Values`
- anything else (or absent) → encode as JSON (existing behaviour)

No new JSON field, no flag, no auth-scheme enum change. The check is a single
`strings.EqualFold` comparison before the body serialisation.

**D3 — `grant_type=password` stored as a credential field (not hardcoded)**

The exchanger encodes whatever is in `credential_fields` — it does not know or
care about OAuth2 semantics. `grant_type: password` is just another field. This
approach works without any new exchanger knowledge of OAuth2 grant types.
Operators set it once during credential creation. The template credential_hint
documents this.

**D4 — `test_path: /v1/users/client`**

`GET /v1/users/client` (`retrieveUserClient` operationId) returns 200 with any
valid access token and requires:
- `Authorization: Bearer <token>` (injected by proxy)
- `x-request-id: <uuid4>` (the Mintkey test harness or operator must supply
  this; the proxy forwards it)
- No path parameters, no query parameters

Runner-up: `GET /v1/tags` — also zero path params, minimal permissions.

**D5 — `x-request-id` is agent responsibility; no proxy change needed**

The Contabo API mandates `x-request-id: <uuid4>` on every request. The proxy
(Go `httputil.ReverseProxy`) forwards all request headers from the agent to the
upstream. Agents must include this header in every call. This is documented in
`config_notes`. A future proposal could add "auto-inject UUID header" capability
to the proxy (tracked as OQ-CTB-1).

**D6 — `category: cloud`**

Contabo is a cloud VPS/VDS infrastructure provider. `cloud` is a new category
value (category is a free-string field on `ServiceTemplate`) that accurately
describes it and will be reusable for future AWS, GCP, Hetzner, etc. templates.

**D7 — `openapi_spec_url` points to the Contabo API docs page**

The Contabo OAS file is served as a browser blob download, not at a stable
HTTP URL. The docs page at `https://api.contabo.com/` is the canonical
public reference. This is consistent with the pattern used by `heroku`,
`datadog`, and `azure-devops` templates.

## Exact YAML entry

```yaml
  - template_id: contabo
    name: contabo
    display_name: Contabo Cloud API
    description: "Contabo cloud control API — manage VPS/VDS instances (create, start, stop, restart, snapshot), object storage, private networks, DNS zones, firewalls, and floating IPs. Uses OAuth2 ROPC (Keycloak) to exchange four operator credentials for a short-lived bearer token; the proxy handles token exchange and caching automatically."
    base_url: https://api.contabo.com
    auth_type: oauth2_password_grant
    openapi_spec_url: https://api.contabo.com/
    category: cloud
    version: "1.0.0"
    config_notes: "Credentials come from the Contabo Customer Control Panel → API section (https://my.contabo.com/api/details). Fill in client_id, client_secret, username (your email), password (API password — not your web login), and leave grant_type as 'password'. IMPORTANT: Every Contabo API call requires an 'x-request-id' header with a unique UUID4 value. Your agent must generate and include this header on each request; the proxy forwards it to Contabo. Example: x-request-id: 04e0f898-37b4-48bc-a794-1a57abe6aa31"
    credential_hint:
      token_url: https://auth.contabo.com/auth/realms/contabo/protocol/openid-connect/token
      credential_fields:
        client_id: "(clientId from my.contabo.com/api/details)"
        client_secret: "(clientSecret from my.contabo.com/api/details)"
        username: "(your Contabo account email)"
        password: "(API Password from my.contabo.com/api/details)"
        grant_type: password
      token_response_path: "$.access_token"
      token_request_headers:
        Content-Type: "application/x-www-form-urlencoded"
    test_path: /v1/users/client
```

## Code change: exchanger form encoding

**File**: `apps/proxy-plugin/internal/credential/exchanger.go`

In `Exchange()`, immediately before the body serialization and HTTP request
construction, add:

```go
const formMIME = "application/x-www-form-urlencoded"

// Determine encoding from Content-Type in token_request_headers.
useForm := strings.EqualFold(req.TokenRequestHeaders[http.CanonicalHeaderKey("Content-Type")], formMIME) ||
    strings.EqualFold(req.TokenRequestHeaders["Content-Type"], formMIME)

var body []byte
var defaultContentType string
if useForm {
    vals := url.Values{}
    for k, v := range req.CredentialFields {
        vals.Set(k, v)
    }
    body = []byte(vals.Encode())
    defaultContentType = formMIME
} else {
    body, err = json.Marshal(req.CredentialFields)
    if err != nil {
        return nil, fmt.Errorf("%w: marshal credential fields: %v", ErrTokenParseFailed, err)
    }
    defaultContentType = "application/json"
}
```

Then use `defaultContentType` when setting the `Content-Type` header (before
`token_request_headers` override).

**Required import additions**: `"net/url"`, `"strings"` (check if already imported).
`"net/http"` is already imported.

## Code change: CredentialHint model

**File**: `apps/admin-api/src/admin_api/templates/models.py`

Add to `CredentialHint`:
```python
token_request_headers: dict[str, str] | None = None
```

This field is optional; existing templates without it continue to load without
modification. The Admin UI will surface it so operators can see the required
`Content-Type` header for Contabo credential creation.

## Test plan

### exchanger_test.go additions

1. `TestExchange_FormEncoded_Success` — mock HTTP server that asserts:
   - `Content-Type: application/x-www-form-urlencoded`
   - Body is form-encoded (parse with `url.ParseQuery`)
   - `grant_type=password` present
   - Returns `{"access_token": "tok", "expires_in": 3600}`
   - Token extraction via `$.access_token`

2. `TestExchange_FormEncoded_DoesNotMutateJSONPath` — when `token_request_headers`
   is absent or `application/json`, body is still JSON. Verifies backward compat.

### Template registry test

In `apps/admin-api/tests/unit/admin_api/test_email_service_templates.py`,
add `test_contabo_template_fields`:
- `registry.get("contabo")` is not None
- `auth_type == "oauth2_password_grant"`
- `base_url == "https://api.contabo.com"`
- `test_path == "/v1/users/client"`
- `category == "cloud"`
- `credential_hint.token_url` contains `auth.contabo.com`

## Open Questions

- **OQ-CTB-1**: Should the proxy auto-inject a UUID4 `x-request-id` header when
  absent (to simplify agent code)? Would require a new per-service
  "auto-inject-headers" config and a small proxy change. Track operator demand first.
- **OQ-CTB-2**: Contabo access tokens expire in ~1 hour. The proxy's `TokenCache`
  reads `expires_in` from the token exchange response — verify the Contabo
  Keycloak response includes `expires_in` and that `cache.DetermineExpiry`
  handles it correctly (it should; this is standard OAuth2).

## Scope / Non-Goals

- No new auth scheme, no `vault.proto` enum change.
- No Liquibase migration.
- No MCP tool additions.
- No OpenAPI YAML contract changes.
- OAuth2 client-credentials flow (not ROPC) is out of scope — Contabo offers
  this but Mintkey does not yet auto-refresh client-credentials tokens (OQ-CTB-3).
