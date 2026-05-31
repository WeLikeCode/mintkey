# Mintkey Feature Prompt: Native `google_service_account` Auth Scheme (JSON Key File + Auto-Rotating OAuth2 Token)

> Pass this prompt verbatim to any Claude Code / agentic coding session opened at the root of the `WeLikeCode/mintkey` repository. The agent **must** read `CLAUDE.md` before doing anything else — this prompt is a supplement, not a replacement.

---

## 0. Pre-flight (mandatory before any code)

1. **Read `CLAUDE.md` in full.** It is authoritative and overrides everything below where there is a conflict.
2. **Read `docs/architecture/01-architecture/adr/` in full** — specifically ADRs 0001, 0003, 0004, 0005, 0008, 0009, 0011, 0012, 0014, 0015, 0017, 0019, 0020. Cite them by number in your plan.
3. **Read `docs/architecture/contracts/rest/openapi.yaml` in full.** Pay particular attention to:
   - The `AuthScheme` enum (current values: `bearer_token`, `api_key_header`, `basic_auth`, `oauth2_client_credentials`).
   - The `RegisterCredentialRequest` discriminator block — your new scheme must follow the same `oneOf` + `discriminator: propertyName: auth_scheme` pattern.
   - The `GET /v1/service-templates` and `GET /v1/service-templates/{slug}` operations — locate them and understand their response shape. If they do not yet exist in the YAML, locate the template implementation in `apps/admin-api/` by grepping for `"github"` template data, and add the missing OpenAPI operation as part of this feature.
   - The `POST /v1/tenants/{tenant_id}/services/test-transient` operation — your new scheme must be accepted by its request body discriminator.
4. **Read `docs/architecture/contracts/mcp/tools.yaml`** — find every `auth_scheme` enum or oneOf that must be extended.
5. **Read `docs/architecture/contracts/vault-adapter/vault.proto`** — `CredentialType` enum and `RetrieveCredentialResponse`. Your extension is append-only.
6. **Read `docs/architecture/contracts/events/audit-event.schema.json`** and `span-attributes.md` — confirm zero plaintext credential fields leak into audit or OTel.
7. **Read `docs/architecture/01-architecture/03-quality-attributes.md`** — focus on `S-SEC-1` (no plaintext leakage), `S-MOD-1` (proxy plugin ≤ 3 file changes per new auth scheme), and `S-PERF-1` (token cache must not exceed vault TTL).
8. **Read `apps/vault-adapter/` source tree end-to-end** — understand how `bearer_token` and `oauth2_client_credentials` credentials are stored, retrieved, and returned as `bearer_value` in the gRPC response. The `google_service_account` scheme follows the same retrieval interface but generates its token internally.
9. **Read `apps/proxy-plugin/` source tree** — find the `inject_credential` switch-case. Understand exactly what a new case requires.
10. **Read `apps/admin-api/` source tree** — find: (a) `RegisterCredentialRequest` Pydantic discriminated union, (b) the service-template registry (`grep -r '"github"' apps/admin-api/`), (c) the `test-transient` endpoint handler, (d) the `structlog` configuration to confirm which fields are scrubbed.
11. **Read `apps/admin-ui/` source tree** — find: (a) the `CredentialCreate` AdminJS form component or resource, (b) the `ServiceCreate` form and the Templates picker page/action at `/admin/resources/services/actions/templates`, (c) how conditional field rendering is currently implemented (look at how `bearer_token` vs `api_key_header` toggle different input fields).
12. **Run all verification commands** from `CLAUDE.md § Verification commands` against the current HEAD before making any changes. Capture exit codes. Do not start implementation until the baseline is completely green.

This is a **new feature**, so the correct routing per `CLAUDE.md § Routing` is the **Kiro spec-driven flow** (`.kiro/specs/`). Create a spec entry under `.kiro/specs/mintkey-mvp/` before writing any production code.

---

## 1. Problem statement

**Why this exists:** The Google Play Developer API authenticates via OAuth 2.0 service-account flow. The operator downloads a JSON key file from Google Cloud Console containing a `client_email`, `private_key`, `private_key_id`, `token_uri`, and `project_id`. At runtime, the server generates a signed JWT from this key file and exchanges it with Google's token endpoint (`https://oauth2.googleapis.com/token`) for a short-lived OAuth2 access token (valid for 3,600 seconds). This access token is then injected as `Authorization: Bearer <token>` on every proxied call.

Mintkey's existing `bearer_token` scheme stores a static value that the operator must manually refresh. The existing `oauth2_client_credentials` scheme covers the `client_id + client_secret → token` flow but does not cover the service-account JWT assertion flow that Google requires. Neither scheme can accept a JSON key file, sign a JWT assertion internally, or refresh the Google access token automatically.

**What we want:** A new first-class `google_service_account` auth scheme that:
- Accepts the full Google service account JSON key file body as the stored credential material — not a pre-generated token.
- Validates the JSON key file structure server-side before persisting it (required fields, correct `"type": "service_account"` value, non-empty `private_key`).
- Generates a signed JWT assertion using the service account's private key and exchanges it with Google's token endpoint for an access token — entirely inside the Vault Adapter, on demand.
- Caches the resulting access token in-process within the Vault Adapter for up to 55 minutes (token TTL is 3,600s; 5-minute renewal buffer), so repeated proxy calls within the same window do not hit Google's token endpoint on every request.
- Returns the cached or freshly generated access token as `bearer_value` in the `RetrieveCredentialResponse` gRPC message, so the proxy plugin treats it identically to a `bearer_token` — injecting `Authorization: Bearer <access_token>` with no proxy-side changes beyond a new case in the scheme switch.
- Surfaces in the Admin UI Templates picker as a `googleplay` template card, pre-filling all service fields and prompting the operator to paste their JSON key file into a dedicated textarea.
- Propagates the `google_service_account` enum value across every layer: OpenAPI spec, proto, MCP tools catalog, Pydantic models, Vault Adapter, proxy plugin, Admin UI forms, and service templates.
- Emits correct audit events on credential creation, rotation, and deletion — containing only `{ client_email, private_key_id, project_id }` as identifiers — never the private key, never the access token.

---

## 2. Scope

### In scope

- New `google_service_account` enum value added to `AuthScheme` everywhere it appears (OpenAPI, proto, MCP tools, Python `AuthScheme` enum, Go constants).
- **Vault Adapter (Go):** storage of the full JSON key file body (encrypted at rest using the existing AES-256-GCM DEK/KEK from ADR-0003). A new `googleserviceaccount` package (`apps/vault-adapter/internal/googleserviceaccount/`) containing:
  - `ParseKeyFile([]byte) (*ServiceAccountKey, error)` — validates and parses the JSON key file.
  - `GenerateAccessToken(ctx, key *ServiceAccountKey, scope string) (token string, expiresAt time.Time, error)` — generates the JWT assertion and calls `https://oauth2.googleapis.com/token`.
  - An in-process token cache (`sync.Map` or a simple struct with `sync.RWMutex`) keyed by `(tenant_id, service_id, private_key_id)`, with entries expiring 5 minutes before the Google token's `expires_in`.
- **Vault Adapter gRPC handler:** extend `RetrieveCredential` to detect `CREDENTIAL_TYPE_GOOGLE_SERVICE_ACCOUNT`, decrypt the stored JSON key, call the cache-then-generate path, and return the access token as `bearer_value`. Zeroize the private key bytes after use.
- **Proto:** add `CREDENTIAL_TYPE_GOOGLE_SERVICE_ACCOUNT = 3` to the `CredentialType` enum (append-only).
- **Admin REST API (Python/FastAPI):** new `GoogleServiceAccountCredentialFields` Pydantic model and discriminated-union branch in `RegisterCredentialRequest`; server-side validation of the JSON key file structure; scrubbing of `private_key` from all log calls via the existing `structlog` processor; extend `test-transient` to accept and exercise `google_service_account` credential input.
- **OpenAPI contract:** add `google_service_account` to the `AuthScheme` enum; add a `GoogleServiceAccountCredentialCreate` schema component to the `RegisterCredentialRequest` `oneOf` discriminator; add an example to the `registerCredential` operation.
- **MCP tools catalog:** extend every `auth_scheme` enum in `docs/architecture/contracts/mcp/tools.yaml`.
- **Service template:** add a `googleplay` entry to the bundled service template registry in `apps/admin-api/`. The template must pre-fill: `slug: "googleplay"`, `name: "Google Play"`, `display_name: "Google Play Developer API"`, `base_url: "https://androidpublisher.googleapis.com"`, `auth_scheme: "google_service_account"`, `description` (see §4.8), `openapi_url: "https://androidpublisher.googleapis.com/$discovery/rest?version=v3"`.
- **Admin UI (AdminJS / TypeScript):**
  - Extend the `auth_scheme` dropdown in the `CredentialCreate` resource form to include `google_service_account`.
  - When `google_service_account` is selected, hide the `value` field and show three fields: `service_account_json` (textarea, large, monospace font, placeholder: `Paste the contents of your Google service account JSON key file here`), a read-only helper label listing the required JSON fields (`type`, `project_id`, `private_key_id`, `private_key`, `client_email`, `token_uri`), and a `scope` text input pre-filled with `https://www.googleapis.com/auth/androidpublisher`.
  - Add a `googleplay` card to the Templates picker page (`/admin/resources/services/actions/templates`). The card must display: title "Google Play Developer API", subtitle "Android app reviews, subscriptions, purchases, tracks", the Google Play logo colour (`#01875F`), and a "Use this template" button. Clicking it must navigate to the ServiceCreate form with all template fields pre-filled, including `auth_scheme: "google_service_account"`, and must reveal the `google_service_account` credential fields immediately.
  - The `test-transient` button in the ServiceCreate form must work for `google_service_account` — the form must serialize `service_account_json` and `scope` as the credential fields, not `value`.
- **Proxy plugin (Go):** add a `case "google_service_account":` branch to the `inject_credential` switch that injects `bearer_value` as `Authorization: Bearer <token>` — identical to `bearer_token`. Total file changes in `apps/proxy-plugin/` must remain ≤ 3 (S-MOD-1).
- **Docs:** new `docs/guides/googleplay-quickstart.md` following the same structure as `docs/guides/github-quickstart.md`.

### Out of scope

- Support for Google APIs other than the Android Publisher API (`androidpublisher` scope). Other scopes (Gmail, Drive, etc.) are a follow-on feature requiring a new ADR.
- Workload Identity Federation or Application Default Credentials (ADC) — service account JSON key only.
- Key rotation UI beyond what the existing `POST .../credentials/rotate` endpoint provides.
- Frontend validation of the JSON key file structure — validation lives server-side only.
- Any changes to `bearer_token`, `api_key_header`, `basic_auth`, or `oauth2_client_credentials` — surgical changes only.

---

## 3. Architecture constraints (non-negotiable)

| Constraint | Source |
|---|---|
| Proto enum values are append-only; never renumber or remove existing values | ADR-0011 proto conventions |
| Schema changes through Liquibase only — never in SQLAlchemy | ADR-0015 |
| Plaintext JSON key file (especially `private_key`) must never appear in any log, OTel span, audit event payload, or HTTP response other than the single immediate creation response | ADR-0014.4, S-SEC-1 |
| The generated access token must not be cached beyond 55 minutes; cache is in-process in Vault Adapter only, never persisted to disk or DB | ADR-0014.4 |
| The private key must be zeroized from memory after the JWT assertion signing step | ADR-0014.4 |
| Proxy plugin extension ≤ 3 file changes total | S-MOD-1 |
| Every state-changing REST call emits an audit event through the FastAPI chokepoint | ADR-0001, ADR-0014.7 |
| `AuthScheme` OpenAPI enum is canonical; FastAPI-emitted OpenAPI must match checked-in YAML or CI fails | ADR-0017.1 |
| All wire IDs use ULID with stable prefix; no raw UUIDs on the wire | ADR-0017.11 |
| Span attribute allowlist: `*_key*`, `*_pem*`, `*_json*`, `*_token`, `*_secret`, `Authorization`, `Cookie` are all forbidden | ADR-0017.6 |
| Multi-tenant: `tenant_id` on every DB row; RLS policy in same Liquibase changeset as any new table/column | ADR-0008, ADR-0014.8 |
| AdminJS must relay all writes through the Admin REST API BFF — it must never hold a DB connection or call Google directly | ADR-0019 |
| `RegisterCredentialRequest` must use OAS 3.1 `oneOf` + `discriminator` — not `anyOf` or nullable fields | ADR-0017 (OAS 3.1 conventions) |

---

## 4. Technical design (implement this exactly)

### 4.1 JSON key file storage

The Vault Adapter stores the entire Google service account JSON key file body, verbatim, as the encrypted secret blob. No pre-processing — the operator pastes the raw JSON string.

The stored ciphertext decrypts to the Google-standard JSON shape:
```json
{
  "type": "service_account",
  "project_id": "my-project-123",
  "private_key_id": "abc123def456",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "mintkey-agent@my-project-123.iam.gserviceaccount.com",
  "client_id": "123456789",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "..."
}
```

Server-side validation (Admin API, before vault storage):
- `type` must equal `"service_account"` exactly.
- `private_key`, `client_email`, `private_key_id`, `project_id`, `token_uri` must all be non-empty strings.
- `private_key` must contain `"BEGIN"` and `"KEY"` (PEM guard check — do not attempt to parse the key at this layer).
- JSON must be syntactically valid (standard `json.loads`).

If validation fails, return HTTP 400 with a descriptive `problem+json` body. Do not pass the key material to the vault.

Check whether the `credentials` table's `encrypted_value` column is typed generically (BYTEA) or scheme-specific. If generic, no Liquibase migration is needed. If scheme-specific, add a Liquibase changeset. Confirm by running `\d credentials` against the running Postgres before writing migration code.

### 4.2 Admin API Pydantic model

In `apps/admin-api/`, extend the discriminated union:

```python
class GoogleServiceAccountFields(BaseModel):
    service_account_json: str   # raw JSON string, validated server-side
    scope: str = "https://www.googleapis.com/auth/androidpublisher"

    @field_validator("service_account_json")
    @classmethod
    def validate_json_key(cls, v: str) -> str:
        try:
            data = json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError("service_account_json must be valid JSON") from exc
        required = {"type", "private_key", "client_email", "private_key_id", "project_id", "token_uri"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"service_account_json missing required fields: {sorted(missing)}")
        if data.get("type") != "service_account":
            raise ValueError('service_account_json "type" must be "service_account"')
        if "BEGIN" not in data.get("private_key", "") or "KEY" not in data.get("private_key", ""):
            raise ValueError("service_account_json private_key does not look like a PEM key")
        return v
```

The `RegisterCredentialRequest` discriminated union branch for `google_service_account`:
```python
class GoogleServiceAccountCredentialCreate(BaseModel):
    auth_scheme: Literal["google_service_account"]
    google_service_account: GoogleServiceAccountFields
```

The value stored in the vault is `GoogleServiceAccountFields.service_account_json` (the raw JSON string). The `scope` is stored alongside it as metadata — include it in the encrypted blob as `{ "json_key": <raw_json>, "scope": <scope> }`.

Audit event on creation: emit `{ auth_scheme: "google_service_account", client_email: <parsed>, private_key_id: <parsed>, project_id: <parsed> }`. Never include `private_key` or `service_account_json`.

Log scrubbing: ensure `service_account_json`, `private_key`, and `google_service_account` are in the `structlog` drop/redact processor's field list before any log call that touches the credential request body. Verify with a unit test that logs a `RegisterCredentialRequest` with `google_service_account` scheme and asserts the output contains neither `private_key` nor the key body.

### 4.3 Proto extension

In `docs/architecture/contracts/vault-adapter/vault.proto`, append:

```protobuf
enum CredentialType {
  CREDENTIAL_TYPE_UNSPECIFIED        = 0;
  CREDENTIAL_TYPE_BEARER_TOKEN       = 1;
  CREDENTIAL_TYPE_APPLE_JWT          = 2;   // if already added by a prior feature
  CREDENTIAL_TYPE_GOOGLE_SERVICE_ACCOUNT = 3;   // ADD — append-only
}
```

If `CREDENTIAL_TYPE_APPLE_JWT = 2` does not yet exist (the `apple_jwt` feature was not yet implemented), use `= 2` for `CREDENTIAL_TYPE_GOOGLE_SERVICE_ACCOUNT`. Never reorder or renumber.

No new RPC needed. The existing `RetrieveCredential` RPC is sufficient — see §4.4.

### 4.4 Vault Adapter: `googleserviceaccount` package

Create `apps/vault-adapter/internal/googleserviceaccount/` with the following files:

**`key.go`** — key file model and parser:
```go
package googleserviceaccount

import (
    "encoding/json"
    "fmt"
)

// KeyFile mirrors the fields Mintkey needs from a Google service account JSON key file.
// The full JSON is stored encrypted; this struct is populated by parsing the decrypted blob.
type KeyFile struct {
    Type            string `json:"type"`
    ProjectID       string `json:"project_id"`
    PrivateKeyID    string `json:"private_key_id"`
    PrivateKey      string `json:"private_key"`      // PEM RSA or EC private key
    ClientEmail     string `json:"client_email"`
    TokenURI        string `json:"token_uri"`
}

// StoredBlob is the shape persisted (then encrypted) in the vault.
type StoredBlob struct {
    JSONKey string `json:"json_key"`  // raw service account JSON string
    Scope   string `json:"scope"`
}

// ParseStoredBlob deserializes the vault blob and returns a parsed KeyFile and scope.
func ParseStoredBlob(raw []byte) (*KeyFile, string, error) {
    var blob StoredBlob
    if err := json.Unmarshal(raw, &blob); err != nil {
        return nil, "", fmt.Errorf("googleserviceaccount: parse stored blob: %w", err)
    }
    var key KeyFile
    if err := json.Unmarshal([]byte(blob.JSONKey), &key); err != nil {
        return nil, "", fmt.Errorf("googleserviceaccount: parse key file: %w", err)
    }
    return &key, blob.Scope, nil
}
```

**`token.go`** — JWT assertion + token exchange:
```go
package googleserviceaccount

import (
    "context"
    "crypto/rsa"
    "crypto/x509"
    "encoding/json"
    "encoding/pem"
    "fmt"
    "net/http"
    "net/url"
    "strings"
    "time"

    "github.com/go-jose/go-jose/v4"
    josejwt "github.com/go-jose/go-jose/v4/jwt"
)

// TokenResponse is the subset of Google's token endpoint JSON response Mintkey needs.
type TokenResponse struct {
    AccessToken string `json:"access_token"`
    ExpiresIn   int    `json:"expires_in"`    // seconds
    TokenType   string `json:"token_type"`
}

// FetchAccessToken signs a JWT assertion with keyFile.PrivateKey and exchanges it
// at keyFile.TokenURI for a Google OAuth2 access token.
// The private key bytes are zeroized by the caller after this function returns.
func FetchAccessToken(ctx context.Context, key *KeyFile, scope string) (*TokenResponse, error) {
    block, _ := pem.Decode([]byte(key.PrivateKey))
    if block == nil {
        return nil, fmt.Errorf("googleserviceaccount: failed to decode PEM block from private_key")
    }
    rawKey, err := x509.ParsePKCS8PrivateKey(block.Bytes)
    if err != nil {
        // Fallback: try PKCS1 (older Google keys)
        rawKey, err = x509.ParsePKCS1PrivateKey(block.Bytes)
        if err != nil {
            return nil, fmt.Errorf("googleserviceaccount: parse private key: %w", err)
        }
    }
    rsaKey, ok := rawKey.(*rsa.PrivateKey)
    if !ok {
        return nil, fmt.Errorf("googleserviceaccount: expected RSA private key, got %T", rawKey)
    }

    sig, err := jose.NewSigner(
        jose.SigningKey{Algorithm: jose.RS256, Key: rsaKey},
        (&jose.SignerOptions{}).
            WithType("JWT").
            WithHeader("kid", key.PrivateKeyID),
    )
    if err != nil {
        return nil, fmt.Errorf("googleserviceaccount: new signer: %w", err)
    }

    now := time.Now()
    claims := josejwt.Claims{
        Issuer:   key.ClientEmail,
        Subject:  key.ClientEmail,
        Audience: josejwt.Audience{key.TokenURI},
        IssuedAt: josejwt.NewNumericDate(now),
        Expiry:   josejwt.NewNumericDate(now.Add(60 * time.Second)), // assertion TTL; not the access token TTL
    }
    // Google requires a "scope" claim in the assertion — non-standard but documented.
    extra := map[string]string{"scope": scope}
    assertion, err := josejwt.Signed(sig).Claims(claims).Claims(extra).Serialize()
    if err != nil {
        return nil, fmt.Errorf("googleserviceaccount: serialize assertion: %w", err)
    }

    // Exchange assertion for access token
    form := url.Values{
        "grant_type": {"urn:ietf:params:oauth2:grant-type:jwt-bearer"},
        "assertion":  {assertion},
    }
    req, err := http.NewRequestWithContext(ctx, http.MethodPost, key.TokenURI,
        strings.NewReader(form.Encode()))
    if err != nil {
        return nil, fmt.Errorf("googleserviceaccount: build token request: %w", err)
    }
    req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("googleserviceaccount: token exchange: %w", err)
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("googleserviceaccount: token endpoint returned %d", resp.StatusCode)
    }

    var tok TokenResponse
    if err := json.NewDecoder(resp.Body).Decode(&tok); err != nil {
        return nil, fmt.Errorf("googleserviceaccount: decode token response: %w", err)
    }
    return &tok, nil
}
```

**`cache.go`** — in-process token cache:
```go
package googleserviceaccount

import (
    "sync"
    "time"
)

type cachedToken struct {
    token     string
    expiresAt time.Time
}

// Cache is a thread-safe in-process token cache keyed by (tenantID, serviceID, privateKeyID).
type Cache struct {
    mu    sync.RWMutex
    items map[string]cachedToken
}

var GlobalCache = &Cache{items: make(map[string]cachedToken)}

const renewalBuffer = 5 * time.Minute

func cacheKey(tenantID, serviceID, privateKeyID string) string {
    return tenantID + ":" + serviceID + ":" + privateKeyID
}

// Get returns a cached token if valid (not yet within the renewal buffer window).
func (c *Cache) Get(tenantID, serviceID, privateKeyID string) (string, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()
    entry, ok := c.items[cacheKey(tenantID, serviceID, privateKeyID)]
    if !ok || time.Now().Add(renewalBuffer).After(entry.expiresAt) {
        return "", false
    }
    return entry.token, true
}

// Set stores a token with an absolute expiry time.
func (c *Cache) Set(tenantID, serviceID, privateKeyID, token string, expiresIn int) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.items[cacheKey(tenantID, serviceID, privateKeyID)] = cachedToken{
        token:     token,
        expiresAt: time.Now().Add(time.Duration(expiresIn) * time.Second),
    }
}

// Invalidate removes a cache entry — called when a credential is rotated or deleted.
func (c *Cache) Invalidate(tenantID, serviceID, privateKeyID string) {
    c.mu.Lock()
    defer c.mu.Unlock()
    delete(c.items, cacheKey(tenantID, serviceID, privateKeyID))
}
```

**`token_test.go`** — unit tests (minimum coverage):
- Happy path: `FetchAccessToken` with a test RSA key and a local HTTP mock of `token_uri` that asserts correct `grant_type`, decodes the JWT assertion, verifies `iss` == `client_email`, `scope` == expected, returns `{"access_token":"test-token","expires_in":3600,"token_type":"Bearer"}`.
- Error: invalid PEM returns error.
- Error: non-RSA key returns descriptive error.
- Error: token endpoint returns 401 — error propagated.
- Cache: after `Set`, `Get` returns the token; after renewal buffer advance (`time.Now()` mock), `Get` returns miss.
- Cache: `Invalidate` removes entry.

### 4.5 Vault Adapter gRPC handler

In the existing `RetrieveCredential` handler, add a case for `CREDENTIAL_TYPE_GOOGLE_SERVICE_ACCOUNT`:

```go
case pb.CredentialType_CREDENTIAL_TYPE_GOOGLE_SERVICE_ACCOUNT:
    key, scope, err := googleserviceaccount.ParseStoredBlob(plaintextBytes)
    if err != nil {
        return nil, status.Errorf(codes.Internal, "parse google service account blob: %v", err)
    }

    // Check cache first
    if cached, ok := googleserviceaccount.GlobalCache.Get(req.TenantId, req.ServiceId, key.PrivateKeyID); ok {
        return &pb.RetrieveCredentialResponse{BearerValue: cached, Type: cred.Type}, nil
    }

    // Generate fresh token
    tok, err := googleserviceaccount.FetchAccessToken(ctx, key, scope)
    if err != nil {
        return nil, status.Errorf(codes.Internal, "fetch google access token: %v", err)
    }

    // Cache and zeroize
    googleserviceaccount.GlobalCache.Set(req.TenantId, req.ServiceId, key.PrivateKeyID, tok.AccessToken, tok.ExpiresIn)
    zeroizeString(&key.PrivateKey) // helper that overwrites the string's backing bytes with zeros

    return &pb.RetrieveCredentialResponse{BearerValue: tok.AccessToken, Type: cred.Type}, nil
```

The `zeroizeString` helper must use `unsafe` package to overwrite string memory:
```go
func zeroizeString(s *string) {
    b := []byte(*s)
    for i := range b { b[i] = 0 }
    *s = string(b)
}
```

When a `credential.rotated` or `credential.deleted` change event arrives on the change channel (existing subscription in the vault adapter), call `googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)`. The `privateKeyID` must be stored in the change event payload — verify this is already the case by reading the change event schema. If not, add `private_key_id` as an optional field to the `credential` change event schema (JSON schema + audit emission call site).

### 4.6 Proxy plugin

In `apps/proxy-plugin/`, in the `inject_credential` function:

```go
case "google_service_account":
    // Vault Adapter already exchanged the service account key for a bearer token.
    // Treat identically to bearer_token from the proxy's perspective.
    kong.Request.SetHeader("Authorization", "Bearer "+cred.BearerValue)
```

This must touch ≤ 3 files total. Confirm with `git diff --name-only` before declaring done.

### 4.7 OpenAPI contract

In `docs/architecture/contracts/rest/openapi.yaml`:

**1. Extend `AuthScheme` enum:**
```yaml
AuthScheme:
  type: string
  enum:
    - bearer_token
    - api_key_header
    - basic_auth
    - oauth2_client_credentials
    - google_service_account    # ADD
```

**2. Add `GoogleServiceAccountCredentialCreate` to the `RegisterCredentialRequest` `oneOf`:**
```yaml
GoogleServiceAccountCredentialCreate:
  type: object
  required: [auth_scheme, google_service_account]
  properties:
    auth_scheme:
      type: string
      enum: [google_service_account]
    google_service_account:
      type: object
      required: [service_account_json]
      properties:
        service_account_json:
          type: string
          description: >
            Full contents of the Google service account JSON key file
            (downloaded from Google Cloud Console → IAM → Service Accounts → Keys).
            Must contain: type, project_id, private_key_id, private_key, client_email, token_uri.
          x-mintkey-sensitive: true
        scope:
          type: string
          default: "https://www.googleapis.com/auth/androidpublisher"
          description: >
            OAuth2 scope to request. Defaults to the Android Publisher scope.
```

**3. Add example to `registerCredential` operation:**
```yaml
google-service-account:
  value:
    auth_scheme: "google_service_account"
    google_service_account:
      service_account_json: '{"type":"service_account","project_id":"my-project",...}'
      scope: "https://www.googleapis.com/auth/androidpublisher"
```

**4. If `GET /v1/service-templates` and `GET /v1/service-templates/{slug}` operations do not already exist in the YAML**, add them following the existing operation pattern. The response schema for a template must include: `slug`, `name`, `display_name`, `description`, `base_url`, `auth_scheme`, `openapi_url`. Use OAS 3.1 conventions.

Validate the entire file with `openapi-spec-validator` and `@redocly/cli lint` after every change. Zero errors required.

### 4.8 Service template

Locate the template registry in `apps/admin-api/` (likely a Python dict or list seeded at startup). Add:

```python
{
    "slug":         "googleplay",
    "name":         "Google Play",
    "display_name": "Google Play Developer API",
    "description":  (
        "Google Play Developer API v3 — read and reply to user reviews, "
        "validate in-app purchases and subscriptions, manage app tracks and releases. "
        "Requires a Google Cloud service account with the Android Publisher scope."
    ),
    "base_url":     "https://androidpublisher.googleapis.com",
    "auth_scheme":  "google_service_account",
    "openapi_url":  "https://androidpublisher.googleapis.com/$discovery/rest?version=v3",
}
```

This template must appear in the response of `GET /v1/service-templates` alongside the existing `github` entry. Verify by hitting the endpoint with `curl` after restart and confirming `googleplay` appears in the list.

### 4.9 Admin UI — credential form

In `apps/admin-ui/`, locate the `CredentialCreate` AdminJS resource definition (likely in a `resources/` or `components/` directory).

**Extend the `auth_scheme` dropdown** to include `google_service_account` as a selectable option.

**Conditional field rendering** — when `auth_scheme === "google_service_account"`:
- Hide the `value` field entirely.
- Show `google_service_account.service_account_json`: a `<textarea>` with `rows={12}`, monospace font, placeholder text: `Paste the full contents of your Google Cloud service account JSON key file here (the .json file downloaded from IAM → Service Accounts → Keys)`.
- Show `google_service_account.scope`: a text input, default value `"https://www.googleapis.com/auth/androidpublisher"`, with a helper label: `"OAuth2 scope — do not change unless you need a different Google API"`.
- Show a static helper note (not an input field): `"The private key is stored encrypted. It will not be displayed after saving."`.

The form must serialize the credential as:
```json
{
  "auth_scheme": "google_service_account",
  "google_service_account": {
    "service_account_json": "<textarea value>",
    "scope": "<scope input value>"
  }
}
```

This serialization must be relayed to the Admin API BFF endpoint (per ADR-0019); the AdminJS UI must not attempt to parse or validate the JSON key file — that is the API's responsibility.

### 4.10 Admin UI — Templates picker

In `apps/admin-ui/`, locate the Templates picker page or action (path: `/admin/resources/services/actions/templates`, introduced in a prior feature per the quickstart guide). Find the component that renders the existing `github` card.

Add a `googleplay` card with:
- **Title:** "Google Play Developer API"
- **Subtitle:** "Reviews, subscriptions, purchases, tracks"
- **Accent color:** `#01875F` (Google Play brand green — apply as a left border or card header background)
- **Icon/logo:** A simple `G ▶` text badge styled in the accent colour is sufficient if no SVG icon is available; do not import an external icon library that isn't already a dependency.
- **"Use this template" button:** on click, call the Admin API `GET /v1/service-templates/googleplay` endpoint (BFF relay), populate the ServiceCreate form fields with the template data, set `auth_scheme` to `google_service_account`, and scroll/navigate to the credential section of the form to reveal the `google_service_account` fields.

### 4.11 Admin UI — test-transient integration

In the ServiceCreate form, the "Test connection" button serializes the current form state and sends it to `POST /v1/tenants/{tenant_id}/services/test-transient`. Ensure that when `auth_scheme === "google_service_account"`, the button:
- Is enabled only when `service_account_json` is non-empty, `base_url` is non-empty, and `name` is non-empty.
- Sends the credential as `{ "auth_scheme": "google_service_account", "google_service_account": { "service_account_json": ..., "scope": ... } }` in the `credential` field of the transient test request body.
- Displays the result panel showing `status_code`, `latency_ms`, and truncated response body — identical to the `bearer_token` case.

---

## 5. Verification targets (define-done)

All of the following must pass with tool-verified output and exit codes before declaring the feature complete:

```bash
# 1. OpenAPI structural validity
python3 -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')))"
# → exit 0

# 2. OpenAPI lint
npx --yes @redocly/cli@latest lint docs/architecture/contracts/rest/openapi.yaml
# → exit 0, 0 errors

# 3. Proto compiles
protoc --proto_path=docs/architecture/contracts/vault-adapter \
       --descriptor_set_out=/dev/null \
       docs/architecture/contracts/vault-adapter/vault.proto
# → exit 0

# 4. Go unit tests — googleserviceaccount package
cd apps/vault-adapter && go test ./internal/googleserviceaccount/... -v -count=1
# → exit 0, all tests PASS

# 5. Go unit tests — vault-adapter full
cd apps/vault-adapter && go test ./... -v -count=1
# → exit 0

# 6. Go build — all services, no regressions
go build ./...
# → exit 0

# 7. golangci-lint — proxy-plugin and vault-adapter
golangci-lint run ./apps/proxy-plugin/... ./apps/vault-adapter/...
# → exit 0, 0 issues

# 8. Proxy plugin file count (S-MOD-1)
git diff --name-only HEAD | grep apps/proxy-plugin | wc -l
# → prints ≤ 3

# 9. Python mypy
cd apps/admin-api && mypy --strict src/
# → exit 0

# 10. Python ruff
cd apps/admin-api && ruff check src/
# → exit 0

# 11. Python unit test — credential validation
cd apps/admin-api && python -m pytest tests/unit/test_google_service_account_credential.py -v
# → exit 0; must cover: valid JSON accepted, invalid type rejected, missing fields rejected,
#   private_key not in log output

# 12. Admin UI TypeScript compile
cd apps/admin-ui && pnpm tsc --noEmit
# → exit 0

# 13. Service template endpoint smoke
docker compose up -d
curl -s http://localhost:8080/v1/service-templates | jq '.[] | .slug' | grep googleplay
# → prints "googleplay"

# 14. Red-team: no private_key in logs
docker compose up -d
# Register a google_service_account credential with a test key file, make one proxied call, then:
docker compose logs | grep -E "(BEGIN RSA PRIVATE KEY|BEGIN PRIVATE KEY|private_key|service_account_json)"
# → output MUST be empty

# 15. Red-team: no private_key in audit events
psql -c "SELECT payload FROM audit_events WHERE payload::text ILIKE '%BEGIN%KEY%';"
# → 0 rows

# 16. End-to-end smoke (existing, must still pass)
make smoke
# → exit 0
```

---

## 6. Issue intake

Per `CLAUDE.md § Issue intake is mandatory`:

1. **Problem:** No native Google service account auth scheme. Operators must manually exchange a service account JSON key for a short-lived OAuth2 access token and push it to Mintkey every hour, which is operationally untenable for agent-driven workflows.
2. **User-visible symptom:** Registering Google Play requires `auth_scheme: bearer_token` with a token that expires after 3,600 seconds. All proxied calls return `401 Unauthorized` after expiry until the operator runs a manual refresh script.
3. **Expected behavior:** Operator pastes the service account JSON key file once — via the Admin UI Templates picker or credential form. Mintkey exchanges it for access tokens automatically, caches them for up to 55 minutes, and refreshes transparently. Agents always get a valid proxied call through without operator intervention.
4. **Evidence:** Google OAuth2 service-account access tokens have `expires_in: 3600` by definition. There is no static-token alternative for server-to-server Google API access.
5. **Scope:** New `google_service_account` auth scheme across OpenAPI, proto, Vault Adapter, proxy plugin, Admin REST API, Admin UI credential form, Admin UI Templates picker card, service template registry, MCP tools catalog, and one new quickstart guide.
6. **Out of scope:** Other Google API scopes, Workload Identity Federation, Application Default Credentials, frontend JSON validation, changes to existing auth schemes.
7. **Risk level:** High — touches vault encryption path, gRPC handler, proxy plugin injection, OpenAPI discriminator, Admin UI BFF relay. Independent REVIEWER subagent required per chunk.
8. **Verification target:** All 16 checks in §5 pass with tool-verified output and exit codes.
9. **Owner decisions needed:** (a) In-process cache in Vault Adapter vs. a Redis-backed shared cache — recommend in-process for Phase 1 (simpler, no new infra dependency, acceptable given single Vault Adapter instance). (b) Whether to add `private_key_id` to the change event schema for cache invalidation on rotation — recommend yes, as a non-breaking addition. (c) Whether the `scope` field should be editable after credential creation — recommend no: make it immutable, require credential rotation to change scope (consistent with `auth_scheme` immutability on services).

---

## 7. Work chunks (orchestrator pattern required)

Per `CLAUDE.md § Routing`, this is a multi-file change touching the credential boundary. Use the orchestrator pattern.

| Chunk | Scope | Key verify check |
|---|---|---|
| C1 | Kiro spec entry under `.kiro/specs/mintkey-mvp/` | Spec file exists, reviewed |
| C2 | ADR-0021 (or next available number) for `google_service_account` scheme | ADR accepted by owner |
| C3 | Proto enum extension + compilation | Check #3 |
| C4 | OpenAPI + MCP tools catalog + service-templates OpenAPI operations | Checks #1, #2 |
| C5 | `googleserviceaccount` Go package: `key.go`, `token.go`, `cache.go` | Check #4 |
| C6 | Unit tests for `googleserviceaccount` package | Check #4 fully green |
| C7 | Vault Adapter gRPC handler extension + change-event cache invalidation | Checks #5, #6 |
| C8 | Admin API Pydantic model + validation + log scrubbing + test-transient extension | Checks #9, #10, #11 |
| C9 | Liquibase migration (if required by §4.1 column-type check) | Migration applies cleanly |
| C10 | Proxy plugin switch-case extension | Checks #6, #7, #8 |
| C11 | Service template registry entry | Check #13 |
| C12 | Admin UI credential form — conditional fields for `google_service_account` | Check #12 |
| C13 | Admin UI Templates picker — `googleplay` card + form pre-fill + test-transient wiring | Check #12 + manual UI smoke |
| C14 | Red-team + full e2e smoke | Checks #14, #15, #16 |
| C15 | `docs/guides/googleplay-quickstart.md` | Doc review |

Do not merge C7 and C8 — the gRPC handler (credential boundary) and the Admin API (input validation) must be reviewed independently.

---

## 8. Anti-patterns specific to this feature

These supplement the project-wide anti-patterns in `CLAUDE.md § Anti-patterns`:

- ❌ Calling `FetchAccessToken` from the proxy plugin — all token generation and caching lives exclusively in the Vault Adapter.
- ❌ Storing `service_account_json`, `private_key`, or the generated access token in any Postgres column — the vault blob is encrypted BYTEA only.
- ❌ Logging any field from `GoogleServiceAccountFields` — not even `client_email` at DEBUG level without explicit scrub confirmation.
- ❌ Using `http.DefaultClient` without a timeout in `FetchAccessToken` — set `Timeout: 10 * time.Second` via a package-level `var httpClient = &http.Client{Timeout: 10 * time.Second}`.
- ❌ Adding `scope` as a column on the `credentials` table — store it inside the encrypted blob alongside `json_key`.
- ❌ Making the `GlobalCache` a package-level `var` that is reset on process restart without documentation — document the restart behavior explicitly in a comment: `// GlobalCache is in-process only. On Vault Adapter restart, all entries are evicted and tokens are re-fetched on the next RetrieveCredential call.`
- ❌ Making the Admin UI validate the JSON key file structure client-side — validation is server-side only, per the AdminJS BFF posture (ADR-0019).
- ❌ Importing a new npm package into `apps/admin-ui/` for the Google Play logo — use a styled text badge if no suitable icon already exists in the project's icon set.
- ❌ Returning the `service_account_json` field in any `GET` response — `value` and `service_account_json` are both `null` on all reads after creation, consistent with other credential types.
