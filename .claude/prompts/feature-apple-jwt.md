# Mintkey Feature Prompt: Native `apple_jwt` Auth Scheme (`.p8` + Auto-Rotating JWT)

> Pass this prompt verbatim to any Claude Code / agentic coding session opened at the root of the `WeLikeCode/mintkey` repository. The agent must read `CLAUDE.md` before doing anything else — this prompt is a supplement, not a replacement.

---

## 0. Pre-flight (mandatory before any code)

1. **Read `CLAUDE.md` in full.** It is authoritative and overrides everything below where there is a conflict.
2. **Read `docs/architecture/01-architecture/adr/` in full** — specifically ADRs 0003, 0004, 0005, 0006, 0008, 0009, 0011, 0012, 0014, 0017. Cite the relevant ones in your plan.
3. **Read `docs/architecture/contracts/rest/openapi.yaml`** — all `auth_scheme` enum values, the `credentials` POST body schema, and the `services` POST body schema. Your changes must extend these enums and schemas without breaking existing values.
4. **Read `docs/architecture/contracts/vault-adapter/vault.proto`** — the `CredentialType` enum and `RetrieveCredentialResponse` message. Your proto changes must add a new enum value; never reuse or renumber existing ones.
5. **Read `docs/architecture/contracts/mcp/tools.yaml`** — find the `auth_scheme` enum used in `list_services` and `describe_service` tool responses.
6. **Read `docs/architecture/contracts/events/audit-event.schema.json`** — your new credential type must appear nowhere in log or audit payloads as plaintext.
7. **Read `docs/architecture/01-architecture/03-quality-attributes.md`** — pay special attention to `S-SEC-1` (no plaintext credential leakage) and `S-MOD-1` (proxy plugin auth-scheme extension must touch ≤ 3 files).
8. **Read `apps/vault-adapter/` and `apps/proxy-plugin/`** source trees to understand the existing `bearer_token` injection path end-to-end before writing a single line.
9. **Run all verification commands** from `CLAUDE.md § Verification commands` against the current HEAD before making any changes. Capture exit codes. Do not start implementation until the baseline is green.

This is a **new feature**, so the correct routing per `CLAUDE.md § Routing` is the **Kiro spec-driven flow** (`.kiro/specs/`). Create a spec entry under `.kiro/specs/mintkey-mvp/` before writing any production code.

---

## 1. Problem statement

**Why this exists:** Apple's App Store Connect API authenticates with short-lived JWTs (max 20-minute TTL) signed with an EC private key stored in a `.p8` file. Mintkey currently only supports `bearer_token` as an auth scheme — a static value stored once and injected verbatim. This is unworkable for Apple APIs because the JWT expires every 20 minutes and must be regenerated from the `.p8` key material on each renewal cycle.

**What we want:** A new first-class `apple_jwt` auth scheme that:
- Accepts a `.p8` key file body (PEM, PKCS#8 EC private key), a Key ID (`kid`), and an Issuer ID (`iss`) as the stored credential material — **not** a pre-generated JWT.
- Generates a valid Apple-format JWT (ES256, `aud: "appstoreconnect-v1"`, 19-minute TTL with 1-minute clock skew buffer) on demand inside the Vault Adapter, never storing the generated JWT in the database or in logs.
- Rotates the JWT automatically so the Kong egress proxy always injects a fresh, valid token — without operator intervention and without ever exposing the `.p8` key material to the agent or to any log line.

---

## 2. Scope

**In scope:**
- New `apple_jwt` enum value propagated across all layers: OpenAPI spec, proto enum, MCP tools catalog, Python Pydantic models, Go Vault Adapter, Go proxy plugin injection logic, Admin UI form.
- Vault Adapter: storage of `{ p8_key_pem, key_id, issuer_id }` as the raw credential — encrypted at rest with the existing AES-256-GCM DEK/KEK scheme (ADR-0003). No new encryption mechanism.
- Vault Adapter: a `GenerateAppleJWT(ctx, tenantID, serviceID)` gRPC method (or extend `RetrieveCredential`) that generates the ES256 JWT on the fly and returns it as a short-lived bearer token string. The generated JWT must not be persisted anywhere.
- Kong proxy plugin: teach the `inject_credential` switch-case to handle `apple_jwt` by calling the Vault Adapter's generation method rather than fetching a static value, then injecting the result as `Authorization: Bearer <generated_jwt>`.
- Admin REST API: extend the `POST /v1/tenants/{tenant_id}/services/{service_id}/credentials` body to accept `auth_scheme: "apple_jwt"` alongside a `p8_key_pem`, `key_id`, and `issuer_id` field — all validated server-side before vault storage.
- `POST /v1/tenants/{tenant_id}/services/test-transient`: extend to support `apple_jwt` credential input (same three fields) so the operator can verify key material before committing.
- Service template: add an `appstoreconnect` entry to the bundled service templates (alongside the existing `github` template).
- New guide: `docs/guides/appstoreconnect-quickstart.md` following the same structure as `docs/guides/github-quickstart.md`.
- Audit events: credential creation/update/deletion for `apple_jwt` must emit audit events using the existing chokepoint. Audit payloads must contain only `{ key_id, issuer_id, fingerprint }` — never `p8_key_pem`, never the generated JWT.
- Tests: unit tests for JWT generation logic (clock skew, TTL, claim structure, ES256 algorithm); integration tests for the full proxy call path; red-team grep for any `.p8` key material in logs.

**Out of scope:**
- Support for any Apple API other than App Store Connect (e.g. Apple Music, Sign in with Apple, APNs). The `apple_jwt` scheme is scoped to `aud: "appstoreconnect-v1"`. If other audiences are needed later, a new ADR must be written.
- Key rotation UX (revoke + re-upload) beyond what the existing credential update endpoint already supports.
- Any change to the `bearer_token` scheme — surgical changes only.
- Frontend (AdminJS) beyond adding `apple_jwt` to the `auth_scheme` dropdown and revealing the three new fields (`p8_key_pem`, `key_id`, `issuer_id`) conditionally when that scheme is selected.

---

## 3. Architecture constraints (non-negotiable)

These come directly from accepted ADRs. Do not work around them — write an ADR if you believe one needs to change.

| Constraint | Source |
|---|---|
| Proto enum values are append-only; never renumber or remove | ADR-0011 + proto conventions |
| Every domain table change goes through a Liquibase changeset — no SQLAlchemy-first columns | ADR-0015 |
| Plaintext `.p8` key material must never appear in any log line, OTel span attribute, audit event payload, or HTTP response body visible to the agent | ADR-0014.4, S-SEC-1 |
| The generated JWT must not be cached beyond request scope in the proxy plugin | ADR-0014.4 |
| Proxy plugin auth-scheme extension must touch ≤ 3 files | S-MOD-1 |
| Every state-changing REST call emits an audit event through the FastAPI chokepoint | ADR-0001, ADR-0014.7 |
| `auth_scheme` OpenAPI enum is the single source of truth; FastAPI-emitted OpenAPI must match the checked-in YAML or CI fails | ADR-0017.1 |
| All wire IDs use ULID with stable prefix (e.g. `cred_…`); no raw UUIDs on the wire | ADR-0017.11 |
| Span attribute allowlist: anything matching `*_key*`, `*_pem*`, `*_token`, `*_secret`, `Authorization`, `Cookie` is forbidden | ADR-0017.6 |
| Multi-tenant: `tenant_id` on every DB row; RLS policy created in same Liquibase changeset as any new table/column | ADR-0008, ADR-0014.8 |

---

## 4. Technical design (implement this)

### 4.1 New credential storage schema

The Vault Adapter stores composite credential material. For `apple_jwt`, the stored secret blob (encrypted by the existing DEK/KEK) must contain a JSON envelope:

```json
{
  "scheme": "apple_jwt",
  "p8_key_pem": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
  "key_id": "TNRVKBLCWWTH",
  "issuer_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

No schema migration is needed if the `credentials` table already stores a generic `encrypted_value BYTEA` column. Verify this first with `\d credentials` on the running Postgres. If the column is typed to a specific scheme, a Liquibase changeset is required.

### 4.2 Admin API validation (Python / FastAPI)

In `apps/admin-api/`, extend the `CredentialCreate` Pydantic model:

```python
class AppleJWTFields(BaseModel):
    p8_key_pem: str      # must start with "-----BEGIN PRIVATE KEY-----"
    key_id: str          # 10-char alphanumeric
    issuer_id: str       # UUID format

class CredentialCreate(BaseModel):
    auth_scheme: AuthScheme   # extend enum: bearer_token | apple_jwt
    # bearer_token path:
    value: str | None = None
    # apple_jwt path:
    apple_jwt: AppleJWTFields | None = None

    @model_validator(mode="after")
    def check_scheme_fields(self) -> "CredentialCreate":
        if self.auth_scheme == AuthScheme.apple_jwt:
            if not self.apple_jwt:
                raise ValueError("apple_jwt fields required for apple_jwt scheme")
            if not self.apple_jwt.p8_key_pem.startswith("-----BEGIN PRIVATE KEY-----"):
                raise ValueError("p8_key_pem must be a PKCS#8 PEM private key")
        elif self.auth_scheme == AuthScheme.bearer_token:
            if not self.value:
                raise ValueError("value required for bearer_token scheme")
        return self
```

The admin API serializes the `AppleJWTFields` to JSON and passes the blob to the Vault Adapter's `StoreCredential` gRPC call. The `p8_key_pem` field must be scrubbed from all log calls using `structlog`'s `drop_missing` or a custom processor — verify with the red-team grep.

### 4.3 Proto extension (Vault Adapter)

In `docs/architecture/contracts/vault-adapter/vault.proto`, add:

```protobuf
enum CredentialType {
  CREDENTIAL_TYPE_UNSPECIFIED = 0;
  CREDENTIAL_TYPE_BEARER_TOKEN = 1;
  CREDENTIAL_TYPE_APPLE_JWT = 2;   // ADD THIS — append only, never renumber
}
```

Add a new RPC (or extend `RetrieveCredential`) to support on-demand JWT generation:

```protobuf
// RetrieveCredential already exists — extend its response:
message RetrieveCredentialResponse {
  string bearer_value = 1;   // existing field — populated for bearer_token, also for apple_jwt (contains freshly generated JWT)
  CredentialType type = 2;   // existing or new
  // No new field needed if the generated JWT is returned as bearer_value
}
```

The Vault Adapter's `RetrieveCredential` handler must switch on credential type: for `apple_jwt`, decrypt the stored blob, parse the JSON envelope, generate the JWT in-process (see §4.4), populate `bearer_value` with the generated JWT string, then immediately zeroize the `p8_key_pem` bytes from memory before returning.

### 4.4 JWT generation (Go, inside Vault Adapter)

Create `apps/vault-adapter/internal/applejwt/generate.go`:

```go
package applejwt

import (
    "crypto/ecdsa"
    "crypto/x509"
    "encoding/pem"
    "fmt"
    "time"

    "github.com/go-jose/go-jose/v4"
    "github.com/go-jose/go-jose/v4/jwt"
)

// Claims mirrors the App Store Connect JWT spec exactly.
type Claims struct {
    jwt.Claims
    // aud is set to "appstoreconnect-v1" via jwt.Claims.Audience
}

// Generate produces a signed ES256 JWT valid for ~19 minutes (1-minute clock skew buffer).
// p8KeyPEM must be a PKCS#8 PEM-encoded EC private key.
// keyID and issuerID are the Apple-provided identifiers.
// The returned string is the compact JWS serialization.
// Caller is responsible for zeroizing p8KeyPEM bytes after this call.
func Generate(p8KeyPEM []byte, keyID, issuerID string) (string, error) {
    block, _ := pem.Decode(p8KeyPEM)
    if block == nil {
        return "", fmt.Errorf("applejwt: failed to decode PEM block")
    }
    rawKey, err := x509.ParsePKCS8PrivateKey(block.Bytes)
    if err != nil {
        return "", fmt.Errorf("applejwt: parse PKCS8 private key: %w", err)
    }
    ecKey, ok := rawKey.(*ecdsa.PrivateKey)
    if !ok {
        return "", fmt.Errorf("applejwt: expected EC private key, got %T", rawKey)
    }

    sig, err := jose.NewSigner(
        jose.SigningKey{Algorithm: jose.ES256, Key: ecKey},
        (&jose.SignerOptions{}).WithType("JWT").WithHeader("kid", keyID),
    )
    if err != nil {
        return "", fmt.Errorf("applejwt: new signer: %w", err)
    }

    now := time.Now()
    claims := jwt.Claims{
        Issuer:   issuerID,
        IssuedAt: jwt.NewNumericDate(now),
        Expiry:   jwt.NewNumericDate(now.Add(19 * time.Minute)), // Apple max is 20m; 1m buffer
        Audience: jwt.Audience{"appstoreconnect-v1"},
    }

    return jwt.Signed(sig).Claims(claims).Serialize()
}
```

Unit tests in `apps/vault-adapter/internal/applejwt/generate_test.go` must cover:
- Happy path: parse → sign → decode claims → assert `iss`, `aud`, `exp - iat == 19m`, `kid` header, algorithm `ES256`.
- Error: malformed PEM returns error (no panic).
- Error: non-EC key (e.g. RSA) returns descriptive error.
- Clock skew: `exp` is strictly less than `iat + 20m`.

### 4.5 Proxy plugin (Go, Kong go-pdk)

In `apps/proxy-plugin/`, find the `inject_credential` function (or equivalent switch-case that currently handles `bearer_token`). Add a case for `apple_jwt`:

```go
case "apple_jwt":
    // The Vault Adapter already generated the JWT and returned it as bearer_value.
    // The proxy plugin treats it identically to bearer_token from this point.
    kong.Request.SetHeader("Authorization", "Bearer "+cred.BearerValue)
```

This must be ≤ 3 file changes total in `apps/proxy-plugin/` per S-MOD-1. Verify with `git diff --name-only` before declaring done.

The proxy plugin must NOT call the JWT generation logic itself. JWT generation lives exclusively in the Vault Adapter. The proxy plugin calls `RetrieveCredential` gRPC as it does today; the Vault Adapter's handler generates the JWT and returns it in `bearer_value`. This preserves the key material boundary.

### 4.6 OpenAPI contract update

In `docs/architecture/contracts/rest/openapi.yaml`, extend every `auth_scheme` enum:

```yaml
AuthScheme:
  type: string
  enum:
    - bearer_token
    - apple_jwt        # ADD
```

Add a new request body schema for apple_jwt credential creation. Use OAS 3.1 discriminator on `auth_scheme`. Validate with `openapi-spec-validator` and `@redocly/cli lint` before committing.

### 4.7 MCP tools catalog update

In `docs/architecture/contracts/mcp/tools.yaml`, extend the `auth_scheme` enum in `list_services` and `describe_service` tool response schemas to include `apple_jwt`.

### 4.8 Service template

Add to the bundled templates (wherever `github` template is defined — locate by `grep -r "github" apps/admin-api/`):

```python
{
    "slug": "appstoreconnect",
    "name": "App Store Connect",
    "display_name": "Apple App Store Connect API",
    "base_url": "https://api.appstoreconnect.apple.com",
    "auth_scheme": "apple_jwt",
    "description": "Apple App Store Connect API — customer reviews, app versions, lifecycle states, review responses, TestFlight, and in-app purchases.",
    "openapi_url": "https://developer.apple.com/sample-code/app-store-connect/app-store-connect-openapi-specification.zip",
}
```

### 4.9 Admin UI form

In `apps/admin-ui/`, find the `CredentialCreate` form. Extend the `auth_scheme` dropdown to include `apple_jwt`. Conditionally show three fields when `apple_jwt` is selected:
- `p8_key_pem` — textarea, placeholder: `-----BEGIN PRIVATE KEY-----`
- `key_id` — text input, placeholder: `TNRVKBLCWWTH`
- `issuer_id` — text input, placeholder: UUID

Hide the existing `value` field when `apple_jwt` is selected. The AdminJS UI must relay these fields to the Admin API BFF (per ADR-0019) — it must not attempt to validate or parse the key itself.

---

## 5. Verification targets (define-done)

The feature is complete when **all** of the following pass with tool-verified output (exit codes shown):

```
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

# 4. Go unit tests (vault-adapter package including applejwt package)
cd apps/vault-adapter && go test ./... -v -count=1
# → exit 0, all tests PASS, including applejwt/generate_test.go

# 5. Go build (all services — no regressions)
go build ./...    # from repo root with go.work in scope
# → exit 0

# 6. golangci-lint (proxy-plugin and vault-adapter only — surgical)
golangci-lint run ./apps/proxy-plugin/... ./apps/vault-adapter/...
# → exit 0, 0 issues

# 7. Python mypy (admin-api)
cd apps/admin-api && mypy --strict src/
# → exit 0

# 8. Python ruff (admin-api)
cd apps/admin-api && ruff check src/
# → exit 0

# 9. Proxy plugin file-count check (S-MOD-1)
git diff --name-only HEAD | grep apps/proxy-plugin | wc -l
# → prints ≤ 3

# 10. Red-team: no plaintext key material in logs
docker compose up -d
# register a service with apple_jwt, make one proxied call, then:
docker compose logs | grep -E "(BEGIN PRIVATE KEY|p8_key|p8Key|privateKey|private_key)"
# → output MUST be empty

# 11. Red-team: no apple_jwt credential value in audit events table
psql -c "SELECT payload FROM audit_events WHERE payload::text ILIKE '%BEGIN PRIVATE KEY%';"
# → 0 rows

# 12. End-to-end smoke (existing, must still pass)
make smoke
# → exit 0
```

---

## 6. Issue intake (fill before dispatching chunks)

Per `CLAUDE.md § Issue intake is mandatory`, confirm these 9 fields before any chunk dispatch:

1. **Problem:** Mintkey has no native `apple_jwt` auth scheme; operators must manually rotate short-lived Apple JWTs every 20 minutes, which is unworkable for agent-driven workflows.
2. **User-visible symptom:** Registering an App Store Connect service requires storing a pre-generated JWT; that JWT expires and all proxied calls return `401 Unauthorized` until manually refreshed.
3. **Expected behavior:** Operator uploads `.p8` + Key ID + Issuer ID once. Mintkey generates and injects a fresh ES256 JWT on every proxied request, with no operator intervention and no key material ever visible outside the vault.
4. **Evidence:** Apple documentation specifies a 20-minute maximum JWT TTL for App Store Connect API; there is no static token alternative.
5. **Scope:** New `apple_jwt` auth scheme across OpenAPI, proto, Vault Adapter, proxy plugin, Admin API, Admin UI, MCP tools catalog, service templates, and one new quickstart guide.
6. **Out of scope:** Other Apple JWT audiences (APNs, Sign in with Apple, Apple Music); key rotation UI; changes to `bearer_token` scheme.
7. **Risk level:** High — touches vault encryption/decryption path, proxy plugin injection, and OpenAPI contract. Independent REVIEWER subagent required per chunk.
8. **Verification target:** All 12 checks in §5 pass with tool-verified output and exit codes.
9. **Owner decisions needed:** (a) Confirm whether `RetrieveCredential` should be extended vs. a new `GenerateToken` RPC added — recommend extending to keep the proxy plugin call path unchanged. (b) Confirm whether the generated JWT should be cached in-process in the Vault Adapter for ≤ 15 minutes (performance) or regenerated on every call (simplicity, ADR-0014.4 compliance). Recommend regenerating on every call for Phase 1 — cache can be added under a new ADR if latency becomes a concern.

---

## 7. Work chunks (orchestrator pattern required)

Per `CLAUDE.md § Routing`, this is a multi-file change touching security and credential paths. Use the orchestrator pattern: ORCHESTRATOR owns state, IMPLEMENTER per chunk, independent REVIEWER per chunk.

Suggested chunk order (each must be independently green before the next starts):

| Chunk | Scope | Verify |
|---|---|---|
| C1 | Write Kiro spec entry under `.kiro/specs/mintkey-mvp/` | Spec file exists, reviewed |
| C2 | Write ADR-0021 for `apple_jwt` scheme (follow ADR-0001 convention; update `adrs/` symlink) | Accepted by owner |
| C3 | Proto enum + proto compilation | Verify check #3 |
| C4 | OpenAPI + MCP tools catalog extension | Verify checks #1, #2 |
| C5 | `applejwt` Go package + unit tests in Vault Adapter | Verify check #4 |
| C6 | Vault Adapter gRPC handler extension | Verify checks #4, #5, #6 |
| C7 | Admin API Pydantic model + endpoint + Liquibase (if needed) + audit emission | Verify checks #7, #8 |
| C8 | Proxy plugin switch-case extension | Verify checks #5, #6, #9 |
| C9 | Admin UI form changes | Manual UI smoke test |
| C10 | Service template + transient-test extension | API smoke test |
| C11 | Red-team + full e2e smoke | Verify checks #10, #11, #12 |
| C12 | `docs/guides/appstoreconnect-quickstart.md` | Doc review |

Do not combine C5 and C6 (vault logic + gRPC handler) into one chunk — the REVIEWER must see them separately because both touch the credential boundary.

---

## 8. Anti-patterns to watch for in this feature

These are in addition to the project-wide anti-patterns in `CLAUDE.md`:

- ❌ Storing the generated Apple JWT in the database or in a cache that persists beyond the gRPC call scope.
- ❌ Passing `p8_key_pem` as a gRPC field — the key material never leaves the Vault Adapter process.
- ❌ Logging any field from the `AppleJWTFields` struct (including `key_id` if it appears alongside key material in a log line). Log only `{ auth_scheme: "apple_jwt", key_id_fingerprint: sha256(key_id)[:8] }`.
- ❌ Adding a `p8_key_pem` field to the `RetrieveCredentialResponse` proto message — the proxy plugin must never see the raw key.
- ❌ Hardcoding `aud: "appstoreconnect-v1"` anywhere other than `apps/vault-adapter/internal/applejwt/generate.go` — it must be a named constant.
- ❌ Using a JWT TTL of exactly 20 minutes — Apple's documentation specifies 20 minutes as the maximum; always use 19 minutes to absorb clock skew.
- ❌ Handling the JWT generation in the proxy plugin — it lives exclusively in the Vault Adapter.
- ❌ Adding a column to the `credentials` table in SQLAlchemy — Liquibase only, if a column change is needed.
