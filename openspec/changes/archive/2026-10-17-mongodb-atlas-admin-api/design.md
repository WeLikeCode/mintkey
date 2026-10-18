# Design — MongoDB Atlas Administration API support

## Issue intake (CLAUDE.md routing gate)

1. **Problem statement** — Agents cannot perform MongoDB Atlas administrative operations through Mintkey because the Atlas Administration API authenticates only via OAuth2 client-credentials (Service Accounts) or HTTP Digest (Programmatic API Keys), neither of which Mintkey supports end-to-end.
2. **User-visible symptom** — There is no template or auth scheme that lets an operator register `cloud.mongodb.com/api/atlas/v2`; an agent cannot list/manage Atlas projects, clusters, or DB users via the proxy.
3. **Expected behavior** — An operator registers the Atlas Administration API from a template with either a Service Account or a Programmatic API Key, grants an agent `read:atlas` and/or `admin:atlas`, and the agent makes brokered calls; the proxy injects the credential (exchanged Bearer token for Service Accounts; Digest challenge-response for API Keys) and forwards the agent's dated `Accept` version header unchanged.
4. **Evidence** — Atlas auth docs (Digest + Service Accounts, 1-hour tokens, `api/oauth/token`); Atlas v2 requires `Accept: application/vnd.atlas.<date>+json` or returns 406; code review confirms `oauth2_client_credentials` (enum 5) has no exchanger/payload/validation and no `http_digest` scheme exists.
5. **Scope** — Two new auth schemes (oauth2_client_credentials live exchange; http_digest), a read-scoped proxy action, two service templates, contract/enum additions, validation, hints, docs, ADR, tests.
6. **Out of scope** — Reading collection documents / MongoDB wire protocol; injecting the version header automatically; a per-service default-headers/usage-notes column; mTLS; admin-ui changes beyond template instantiation.
7. **Risk level** — **High** (touches credentials, auth, and wire contracts). Orchestrator pattern + independent REVIEWER per chunk required.
8. **Verification target** — Go + admin-api unit suites green; enum-parity, bootstrap-parity, OpenAPI-snapshot, plaintext-in-logs gates green; live smoke against the real Atlas API for both credential types; read:atlas blocks a `DELETE`, admin:atlas allows it.
9. **Owner decisions** — Settled with the user: scope = Admin API only; auth = **both** Service Account + Programmatic API Key; version header = **agent sets it, explicitly told via template, never injected**; actions = `read:atlas` / `admin:atlas`; digest via vetted library; write an ADR.

## Architectural conformance

- Canonical brokered-call path is **Kong → Go proxy-plugin** (`apps/proxy-plugin/`); the Python `admin-api/api/proxy.py` is a BFF fallback and is **not** modified.
- New auth scheme follows the CLAUDE.md "add a new auth scheme on a backend" pattern: proto enum → OpenAPI enum → MCP tools enum → audit/change schemas → proxy injection logic. See the **S-MOD-1 note** below on file count.
- Plaintext credential never appears in any log, audit payload, span attribute, or agent-visible response ([S-SEC-1], ADR-0014.4). Token exchange reuses the SSRF-hardened client and host-only audit redaction already built for password-grant.
- IDs/time, RLS, audit chokepoint, Liquibase-only schema — unchanged; this change adds **no new tables or columns** (credentials ride the existing `vault.credentials` + `public.credentials` rows, keyed by the new `auth_scheme` value).

## Component 1 — OAuth2 client-credentials (Service Accounts)

**Reuse, do not modify, the password-grant engine.** `internal/credential/exchanger.go` already provides an SSRF-hardened `http.Client` (dial-time IP block + redirect guard), `extractJSONPath`, `extractExpiresIn`, and typed errors; `internal/egress/oauth2_handler.go` provides cache → singleflight → graceful-degradation orchestration; `internal/cache.TokenCache` + `DetermineExpiry` handle expiry. None of that changes.

**New credential payload** (`internal/credential/types.go`):
```go
type OAuth2ClientCredentialsCredential struct {
    TokenURL          string `json:"token_url"`            // HTTPS, e.g. https://cloud.mongodb.com/api/oauth/token
    ClientID          string `json:"client_id"`
    ClientSecret      string `json:"client_secret"`
    Scope             string `json:"scope,omitempty"`      // optional space-delimited scopes
    TokenResponsePath string `json:"token_response_path,omitempty"` // default "$.access_token"
    ExchangeTimeoutSeconds int `json:"exchange_timeout_seconds,omitempty"`
}
```

**New exchange method** (`internal/credential/exchanger.go`, sibling to `Exchange`): `ExchangeClientCredentials(ctx, req)` reuses `te.httpClient`, `validateTokenURL`, `extractJSONPath`, `extractExpiresIn` but builds the request differently from password-grant:
- `Content-Type: application/x-www-form-urlencoded`
- Body: `grant_type=client_credentials` (+ `scope=...` when set), form-encoded via `url.Values`.
- `Authorization: Basic base64(client_id:client_secret)` (MongoDB's documented method).
- Token via `token_response_path` (default `$.access_token`); `expires_in` honored for cache TTL.

Password-grant marshals a JSON body and applies caller-supplied `token_request_headers`; client-credentials is form + Basic, which is why this is a **sibling method, not a new param on `Exchange`** — keeping the working path untouched.

**New orchestration** (`internal/egress/`, e.g. `oauth2_client_credentials.go`): `HandleOAuth2ClientCredentials(ctx, deps, tenantID, serviceID, credPayload)` mirrors `HandleOAuth2PasswordGrant` exactly (same `OAuth2HandlerDeps`, same cache/SF keys, same `token.exchanged` audit shape) but parses `OAuth2ClientCredentialsCredential` and calls `ExchangeClientCredentials`.

**Dispatch** (`cmd/proxy-plugin/main.go`, right after the existing password-grant branch at ~line 354): when `AuthScheme == AuthSchemeOAuth2ClientCredentials` **and** the vault payload parses as JSON with a non-empty `token_url`, route to a `handleOAuth2ClientCredentials` method (a near-clone of `handleOAuth2PasswordGrant`, injecting the result as `Bearer`). If a scheme-5 payload is **not** exchange-shaped, fall through to the existing injector behavior (pre-fetched bearer) — preserving backward compatibility for any non-exchange use of OIDC/scheme-5. The injector's existing `case AuthSchemeOAuth2ClientCredentials … Bearer` is unchanged.

## Component 2 — HTTP Digest (Programmatic API Keys)

**New scheme** `AUTH_SCHEME_HTTP_DIGEST = 18` (proto; 17 is `reserved` for the pre-existing admin-api-only `email_oauth2_client` synthetic), `http_digest` (OpenAPI + MCP enums), `AuthSchemeHTTPDigest AuthScheme = 18` (Go const).

**New credential payload** (`internal/credential/types.go`):
```go
type HTTPDigestCredential struct {
    PublicKey  string `json:"public_key"`   // Atlas public key — RFC 2617 username
    PrivateKey string `json:"private_key"`  // Atlas private key — RFC 2617 password
}
```

**Transport, not header.** Digest is a 401→challenge→retry handshake, so a static header cannot express it. New `internal/credential/digest.go` builds a per-request `*digest.Transport` (from `github.com/icholy/digest`) wrapping a standard base transport: `&digest.Transport{Username: publicKey, Password: privateKey, Transport: base}`. In `main.go`, when `AuthScheme == AuthSchemeHTTPDigest`, set `proxy.Transport = digestTransport` on the `httputil.ReverseProxy` and, in the Director, strip the agent's `Authorization` (mirroring `credential.Inject`'s strip) **without** setting any auth header — the digest transport performs the handshake on dial. Everything else (path/host stripping, audit) matches the generic path.

**Library**: `github.com/icholy/digest` (MIT, widely used, correct nonce-count/cnonce/qop=auth handling). Added to `apps/proxy-plugin/go.mod`; `go mod tidy` + `go.work` sync; license noted in the dependency-bump intake stub.

## Component 3 — Read-scoped proxy actions (method gating)

Today the proxy does not inspect `r.Method` or the `scope` claim on the generic path. Add a minimal guard in `cmd/proxy-plugin/main.go`, after claims extraction (~line 290) and before the credential fetch:

```go
scope, _ := claims["scope"].(string)
if scope == "read:atlas" && r.Method != http.MethodGet &&
    r.Method != http.MethodHead && r.Method != http.MethodOptions {
    h.metrics.IncProxyDenied(serviceID, "permission_denied")
    http.Error(w, "forbidden: read:atlas grants read-only access", http.StatusForbidden)
    return
}
```

Only the literal scope `read:atlas` triggers the gate; `admin:atlas`, `call`, and email scopes are untouched (backward-compatible). Defense in depth: `request_token` already verifies a matching `permission_grants.action` row exists before the broker issues the scoped JWT, so an agent cannot obtain a `read:atlas` token without an operator grant. Operators grant the two actions through the existing permission-grant endpoint (the `action` column is freeform `VARCHAR(128)`; no allowlist change needed — to be confirmed during implementation).

## Component 4 — Service templates + version-header guidance

Two entries appended to `apps/admin-api/src/admin_api/templates/service_templates.yaml` (HTTP-service shape; flexible `credential_hint` like the apple_jwt / oauth2_password_grant templates):

- `mongodb-atlas-service-account` — `auth_type: oauth2_client_credentials`, `base_url: https://cloud.mongodb.com/api/atlas/v2`, `openapi_spec_url: https://mongodb.com/docs/atlas/reference/api-resources-spec/v2`, `test_path: /groups`, `credential_hint: {token_url: https://cloud.mongodb.com/api/oauth/token, client_id, client_secret, token_response_path: "$.access_token"}`.
- `mongodb-atlas-api-key` — `auth_type: http_digest`, same `base_url`/`openapi_spec_url`/`test_path`, `credential_hint: {public_key, private_key}`.

**Version header is explicit, never injected.** Both templates' `description` (stored on the service and surfaced to agents via `list_services`/`describe_service`) and `config_notes` (operator-facing) state, verbatim and prominently:

> REQUIRED: send `Accept: application/vnd.atlas.<yyyy-mm-dd>+json` (e.g. `2025-03-12`) on every request — the Atlas API returns **406** without it. Mintkey forwards your request headers to MongoDB unchanged; it does not add this header for you.

The proxy already forwards agent request headers upstream (only `Authorization` and `X-Mintkey-*` are stripped/replaced), so the agent-supplied `Accept` reaches MongoDB. No schema change.

## admin-api credential validation

New Pydantic payloads in `apps/admin-api/src/admin_api/services/credential_service.py`:
- `OAuth2ClientCredentialsPayload` — `token_url` must be HTTPS and pass the existing forbidden-destination (SSRF) check; `client_id`/`client_secret` non-empty; optional `scope`, `token_response_path`. `to_vault_envelope()` emits the canonical JSON the proxy parses.
- `HTTPDigestPayload` — `public_key`/`private_key` non-empty; `to_vault_envelope()` emits `{public_key, private_key}`.

Two validation blocks added to `create_credential` in `apps/admin-api/src/admin_api/api/credentials.py`, mirroring the `oauth2_password_grant` block (lines 187-229): parse `body.value`, validate, and on failure return 400/422 with structured field errors and **`include_input=False`** so no credential bytes are ever echoed ([S-SEC-1], ADR-0014.7). On success, the validated envelope is what reaches `vault.put_credential`.

## MCP discovery parity

`apps/mcp-server/src/mcp_server/auth_schemes.py` gains a real injection hint for `oauth2_client_credentials` ("proxy exchanges client_id/secret for a Bearer token and injects `Authorization: Bearer`; never send your own auth") and a new `http_digest` hint ("proxy performs HTTP Digest with the stored key pair; never send your own auth"). The enum-parity test (every `AuthScheme` value has an entry) and the bootstrap-parity test (every field the bootstrap promises exists) must stay green; the bootstrap cheat-sheet is regenerated from the table.

## S-MOD-1 note (proxy file count)

CLAUDE.md's "≤ 3 files in the proxy" guidance fits **injector-style** schemes (one `case` in `injector.go`). **Token-exchange** schemes inherently need {payload struct, exchange, orchestration, dispatch}; the existing `oauth2_password_grant` already spans `types.go` + `exchanger.go` + `oauth2_handler.go` + `main.go` (4 files). `oauth2_client_credentials` follows that established precedent; `http_digest` stays within an injector-style footprint (`digest.go` + scheme const + `main.go`). The ADR records this as a conscious, precedent-consistent choice, not new sprawl.

## Security considerations

- **Plaintext discipline**: client_secret / private_key live only in request-scoped buffers; exchanged tokens cache the same way password-grant tokens do (no plaintext beyond the encrypted DEK); audits carry host-only token URL + identifiers, never secrets.
- **SSRF**: token exchange reuses the hardened dial/redirect guard; `token_url` is HTTPS-validated at registration and dial time. The Digest upstream is the registered, SSRF-checked `base_url`.
- **Least privilege**: `read:atlas` enforces read-only at the proxy; full power is still bounded by the Service Account's / API Key's Atlas roles on MongoDB's side.
- **Logs/spans**: scheme additions inherit the existing redaction allowlist; red-team grep gate must stay clean.

## Verification plan

- **Go unit**: `ExchangeClientCredentials` (form body, Basic header, JSONPath, expires_in, error classes, SSRF block); the digest transport (challenge handled, Authorization stripped); the read:atlas gate (GET allowed, DELETE 403; admin:atlas/ call unaffected).
- **admin-api unit**: both payload validators accept valid input and reject malformed/non-HTTPS/empty input with **no plaintext in the response**.
- **Parity/CI gates**: vault.proto ↔ Go enum, enum-parity, bootstrap-parity, OpenAPI snapshot, plaintext-in-logs — all green.
- **Live smoke** (operator-supplied creds, isolated stack): register both templates; `read:atlas` agent does `GET /groups` (200) and is `403` on a `DELETE`; `admin:atlas` agent performs a create+delete; confirm `Accept` header reaches Atlas (404/version error without it, success with it); 0 plaintext in logs/audit.
