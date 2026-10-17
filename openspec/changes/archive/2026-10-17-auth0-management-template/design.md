# Design — Auth0 Management API service template

## Issue intake (CLAUDE.md routing gate)

1. **Problem statement** — Operators cannot register the Auth0 Management API through Mintkey: Auth0's client-credentials token request requires an `audience` form parameter that the `oauth2_client_credentials` scheme never sends, and no Auth0 template exists in the catalog.
2. **User-visible symptom** — Registering an Auth0 credential today silently drops a submitted `audience` (Pydantic `extra='ignore'` on `OAuth2ClientCredentialsPayload`), the proxy's token exchange then fails (Auth0 rejects an audience-less client-credentials request for the Management API), and every brokered call returns 502. `GET /v1/templates` has no `auth0-management` entry.
3. **Expected behavior** — An operator instantiates `auth0-management`, replaces the `YOUR_TENANT` placeholders with their tenant domain, pastes their M2M application's `client_id`/`client_secret` plus `audience`; the proxy exchanges them at `https://<tenant>/oauth/token` with `audience=https://<tenant>/api/v2/`, caches the 24-hour Bearer token, and injects it; an agent's `GET /clients` via the proxy succeeds.
4. **Evidence** — Auth0 production-token guide: `POST https://{yourDomain}/oauth/token`, `application/x-www-form-urlencoded`, body `grant_type=client_credentials&client_id&client_secret&audience=https://{yourDomain}/api/v2/` (trailing slash), response `{access_token, expires_in: 86400, scope, token_type: "Bearer"}`. Management API OAS (`https://auth0.com/docs/oas/management/v2/management-api-oas.json`, fetched 2026-07-11): `servers[0].url = https://{tenantDomain}/api/v2`, global security `bearerAuth` only, `oAuth2ClientCredentials` flow with `x-form-parameters: {audience: /api/v2/}`. Code: `ExchangeClientCredentials` sets only `grant_type` (+`scope`) in the form body (`exchanger.go:346-352`); `OAuth2ClientCredentialsPayload` has no `audience` field (`credential_service.py:583-665`); `grep -rn audience apps/proxy-plugin/internal/credential/*.go apps/admin-api/src/admin_api/services/credential_service.py` → 0 hits.
5. **Scope** — Optional `audience` across `types.go` / `exchanger.go` / `egress/oauth2_client_credentials.go` / `credential_service.py` (+ envelope); the `auth0-management` template + registry test; HOW-TO §14; a one-line D2 payload amendment to still-Proposed ADR-0029.
6. **Out of scope** — Read-scoped Auth0 actions (`read:auth0`-style method gating); a generic `extra_token_params` map; the Auth0 Authentication API as a service; a `client_auth_method` switch on the exchanger; automatic tenant-domain templating; admin-ui form work beyond template instantiation.
7. **Risk level** — **Medium-high** (touches a credential auth scheme; strictly additive-optional, no wire-contract change). Orchestrator pattern with an independent REVIEWER per chunk.
8. **Verification target** — Go + admin-api suites green including the new audience cases and a byte-level Atlas no-audience regression; enum-parity, bootstrap-parity, OpenAPI-snapshot (no diff), plaintext-in-logs gates green; live smoke: template → real Auth0 tenant → agent `GET /clients` 200 through the proxy with zero plaintext in logs/audit.
9. **Owner decisions needed** — None blocking. Two defaults taken, flag at review: `test_path: /clients` (requires `read:clients` on the M2M application — stated in `config_notes`); template `category: identity` (new freeform category string; `category` is an unconstrained `str` on `ServiceTemplate`).

## Verified Auth0 facts (all tool-checked 2026-07-11)

| Surface | Value | Evidence |
|---|---|---|
| Token endpoint | `POST https://{tenantDomain}/oauth/token` | Auth0 production-token guide; OAS `tokenUrl` |
| Content type | `application/x-www-form-urlencoded` | Auth0 guide (verbatim curl example) |
| Required params | `grant_type=client_credentials`, `client_id`, `client_secret`, `audience` | Auth0 guide; OAS `x-form-parameters` |
| Audience value | `https://{tenantDomain}/api/v2/` — **trailing slash is part of the identifier** | Auth0 guide; OAS `x-form-parameters: {audience: /api/v2/}` |
| Response | `{access_token, expires_in: 86400, scope, token_type: "Bearer"}` | Auth0 guide |
| Token TTL | 24 hours (86400 s) — `expires_in` honored by the existing cache | Auth0 guide |
| Management base URL | `https://{tenantDomain}/api/v2` (OAS server; default `{TENANT}.auth0.com`; regional and custom domains exist) | OAS `servers` |
| API auth | Plain `Authorization: Bearer <jwt>`; **no dated `Accept` version header** (contrast MongoDB Atlas) | OAS `securitySchemes` = `bearerAuth` only |
| Client auth at token endpoint | Per-application "Token Endpoint Authentication Method": Post (common default) or Basic; Auth0 supports `client_secret_basic` (Basic = concatenate `client_id:client_secret`, Base64, `Authorization: Basic`) | Auth0 Authentication API docs |

## The `audience` extension — minimal field vs general map

**Decision: the minimal optional `audience` field.** Considered against a general `extra_token_params map[string]string`:

1. **Known demand is exactly one parameter.** `audience` is a recognized cross-provider token-request parameter (Auth0 client-credentials; RFC 8693 token exchange uses the same name), not an Auth0-only quirk that hints at an open-ended family.
2. **The map is speculative generality** (Karpathy #2 / YAGNI) and **widens the security surface**: operator-controlled arbitrary form keys could override `grant_type`, `scope`, or smuggle `client_id`/`client_secret` duplicates, so it would demand a denylist, canonicalization rules, and their tests — more code to be less safe. With a typed field the exchanger keeps full control of every form key it emits.
3. **Reversible.** If a second provider ever needs a different parameter, a second typed field — or the map, with evidence — is a small follow-up. Nothing in this design forecloses it.

### Exact change surface (all additive)

**Go — `apps/proxy-plugin/internal/credential/types.go`** (on `OAuth2ClientCredentialsCredential`):

```go
// Audience is the optional OAuth2 token-request audience (e.g. the Auth0
// Management API identifier https://YOUR_TENANT.auth0.com/api/v2/).
// Omitted from the token-request form body when empty.
Audience string `json:"audience,omitempty"`
```

**Go — `apps/proxy-plugin/internal/credential/exchanger.go`**: `Audience string` added to `ClientCredentialsRequest`; in `ExchangeClientCredentials`, immediately after the existing `scope` branch (`exchanger.go:349-351`):

```go
if req.Audience != "" {
    vals.Set("audience", req.Audience)
}
```

**Go — `apps/proxy-plugin/internal/egress/oauth2_client_credentials.go`**: `Audience: cred.Audience,` added to the `exchangeReq` composite literal (Step 3, lines 81-88).

**NOT touched**: `cmd/proxy-plugin/main.go` (scheme-5 dispatch keys on a non-empty `token_url`, not on `audience`); the token cache (key stays `(tenant_id, service_id)` — `audience` is fixed per credential, so no cache-key dimension is added); the password-grant `Exchange`; the injector; singleflight/graceful-degradation orchestration.

**admin-api — `apps/admin-api/src/admin_api/services/credential_service.py`** (on `OAuth2ClientCredentialsPayload`):

- Field: `audience: str | None = None`.
- Validator: when present, must be a non-empty absolute URI (a scheme and no surrounding whitespace — `urlsplit(v).scheme` non-empty). **Deliberately NOT SSRF-checked and NOT restricted to HTTPS**: `audience` is an opaque identifier sent inside the form body; Mintkey never dereferences it as a network destination (Auth0's canonical value happens to be an HTTPS URL, but OAuth API identifiers may be e.g. `urn:` URIs). `token_url` keeps its existing HTTPS + SSRF validators unchanged.
- `to_vault_envelope()`: `if self.audience: envelope["audience"] = self.audience` — mirroring the existing `scope` emission and the Go `omitempty` parity.

**admin-api — `apps/admin-api/src/admin_api/api/credentials.py`: NO change.** The scheme-5 validation block constructs `OAuth2ClientCredentialsPayload(**raw_cc)` and serializes `to_vault_envelope()`, so the new field flows through validation and into the envelope automatically. (Today that same block silently *drops* a submitted `audience` via Pydantic's default `extra='ignore'` — the symptom in intake field 2; adding the field is the entire fix.)

### Backward compatibility (MongoDB Atlas)

With `audience` absent: `url.Values` renders exactly `grant_type=client_credentials` (+ `scope=...` when set) — **byte-identical** to today's request; `to_vault_envelope()` emits the identical envelope. This is pinned by a requirement + scenario in the spec and a byte-level form-body regression test in C1. All existing tests (`client_credentials_exchanger_test.go`, `egress/oauth2_client_credentials_test.go`, `oauth2_client_credentials_dispatch_test.go`, `test_atlas_credential_payloads.py`, `test_mongodb_atlas_templates.py`) must pass unmodified.

## Auth0 client authentication — HTTP Basic stays

`ExchangeClientCredentials` authenticates with HTTP Basic (`client_secret_basic`), unchanged. Auth0 supports Basic at `/oauth/token`; which method a given application *must* use is governed by its per-application "Token Endpoint Authentication Method" / "Authentication Methods" setting (Post is a common default for confidential apps). The template's `config_notes` therefore instruct: *if the token exchange fails with 401 `invalid_client`, set the M2M application's authentication method to **Client Secret (Basic)** in the Auth0 Dashboard (Applications → your app → Credentials).* The live smoke (C4) verifies the Basic path against a real tenant. Extending the exchanger with a `client_auth_method` switch (Basic vs form-body Post) is explicitly deferred until evidence shows Basic rejected in practice — same YAGNI reasoning as the map.

## The `auth0-management` template

Appended to `apps/admin-api/src/admin_api/templates/service_templates.yaml` (HTTP-service shape, matching `mongodb-atlas-service-account`):

```yaml
  - template_id: auth0-management
    name: auth0-management
    display_name: Auth0 Management API
    description: "Auth0 Management API (tenant administration — applications, users, connections, roles, actions, logs). Mintkey exchanges your M2M client_id/client_secret for a 24-hour Bearer access token at your tenant's /oauth/token endpoint (audience required) and injects it as Authorization: Bearer — never send your own auth. No versioned Accept header is required. Operations are bounded by the Management API scopes granted to the M2M application in Auth0."
    base_url: https://YOUR_TENANT.auth0.com/api/v2
    auth_type: oauth2_client_credentials
    openapi_spec_url: https://auth0.com/docs/oas/management/v2/management-api-oas.json
    category: identity
    version: "1.0.0"
    config_notes: "Replace YOUR_TENANT with your Auth0 tenant domain EVERYWHERE (base_url, token_url, audience), including any region suffix (e.g. my-tenant.us.auth0.com) or your custom domain. In Auth0: Applications → create or select a Machine-to-Machine application authorized for the Auth0 Management API, granting the scopes your agents need (the test_path /clients needs read:clients). Credential JSON: {token_url: https://YOUR_TENANT.auth0.com/oauth/token, client_id, client_secret, audience: https://YOUR_TENANT.auth0.com/api/v2/}. The audience MUST match your tenant's Management API identifier exactly, INCLUDING the trailing slash. Mintkey authenticates to the token endpoint with HTTP Basic (client_secret_basic); if the exchange fails with 401 invalid_client, set the application's Authentication Method to Client Secret (Basic) (Applications → your app → Credentials). Tokens last 24 hours (expires_in 86400) and are cached and auto-refreshed by the proxy. Grant agents the call action per service."
    credential_hint:
      token_url: https://YOUR_TENANT.auth0.com/oauth/token
      credential_fields:
        client_id: "(your M2M application Client ID)"
        client_secret: "(your M2M application Client Secret)"
        audience: "https://YOUR_TENANT.auth0.com/api/v2/"
      token_response_path: "$.access_token"
    test_path: /clients
```

### Credential-hint field survival (verified wrinkle)

`CredentialHint` (`templates/models.py:42-53`) is a Pydantic model with **typed fields only** (`field`, `help`, `format`, `token_url`, `credential_fields`, `token_response_path`) and default `extra='ignore'`. Verified by loading the registry: the Atlas template's *flat* `client_id:` / `client_secret:` hint keys are **silently dropped** — only `token_url` and `token_response_path` survive. The Auth0 template therefore carries its operator-facing placeholders in the typed `credential_fields: dict[str, str]` map, which survives loading and reaches the registry API; a registry test pins all three keys (`client_id`, `client_secret`, `audience`). The Atlas flat-key wrinkle itself is pre-existing and **not fixed here** (surgical changes — mention, don't touch); it is recorded as a follow-up observation in tasks C2.

### Per-tenant-domain placeholder handling (ssh CHANGE-ME pattern)

`base_url: https://YOUR_TENANT.auth0.com/api/v2` follows the `ssh://CHANGE-ME-HOST:22` convention: instantiate first, edit the service's `base_url` before use. Verified safe: the from-template SSRF gate (`_is_forbidden_destination` → `resolve_hostname_is_private`, `credential_service.py:75-78`) **fails open on DNS failure** (`socket.gaierror` → `False`), so the unresolvable placeholder does not block creation — connectivity simply fails until the operator replaces it, exactly like the ssh templates. The credential's `token_url` SSRF/HTTPS check runs at credential-creation time, by which point the operator has pasted their real tenant URL. `test_path: /clients` (`GET`, non-destructive, first path in the OAS) only works after placeholder replacement — `config_notes` say replace first.

## ADR decision — no new ADR

`audience` is an optional, additive token-request parameter **within** the client-credentials scheme ADR-0029 D2 already records: no new enum value, no new component, no new wire surface, no changed behavioral guarantee (S-SEC-1 discipline identical; the exchange transport, cache, singleflight, degradation, and audit shapes are all unchanged). A new ADR would document nothing architectural. Because ADR-0029 is still **Proposed** (Status: Proposed — 2026-06-28) and therefore not yet immutable, a one-line `"audience": "(optional)"` addition to its D2 payload example keeps the ADR in lock-step with the implementation — carried as doc task C3.2. Contingency: if ADR-0029 has been Accepted by the time C3 executes, do NOT edit it; record the extension as a note in this change's archive and stop (an amending ADR for one optional field would be ceremony, not architecture).

## Security notes

- **`client_secret` is a secret** — every existing discipline applies unchanged: request-scoped plaintext only, `include_input=False` on validation errors, host-only `token.exchanged` audit, no `*_secret` span attributes, red-team fingerprint grep must stay clean.
- **`audience` is NOT a secret** — it is the tenant's public API identifier. It still rides only inside the encrypted vault envelope and is not added to any log line, audit payload, or span attribute (the existing slog lines carry ids + `token_url_host` only; no change).
- **No SSRF surface added** — `audience` is never dereferenced; `token_url` keeps HTTPS + shared-resolver SSRF validation at registration, and the exchanger keeps its dial-time IP block and redirect guard.
- **Agent never sees the token** — 24-hour Auth0 tokens are cached per `(tenant_id, service_id)` exactly like 1-hour Atlas tokens and injected upstream only; graceful degradation semantics unchanged.

## Verification plan

- **Go unit** — form body contains `audience=<value>` when configured (asserted on the raw urlencoded body); form body contains **no** `audience` key when empty/absent (byte-level equality with the pre-change body); Basic header and JSONPath extraction unchanged; egress handler maps `cred.Audience` → `exchangeReq.Audience`; all pre-existing client-credentials, password-grant, digest, and dispatch tests pass unmodified. `go build ./... && go test ./... -short && go vet ./...` exit 0.
- **admin-api unit** — payload with `audience` accepted and envelope contains it; payload without `audience` yields an envelope with no `audience` key (today's bytes); whitespace-only / scheme-less `audience` rejected with a 4xx that echoes **zero** submitted values; template registry exposes `auth0-management` with the pinned fields and the three surviving `credential_fields` keys; from-template returns 201 with `auth_scheme: oauth2_client_credentials` and the placeholder base_url. `uv run pytest`, `uv run mypy --strict src/admin_api/`, `uv run ruff check src/` exit 0.
- **Gates** — enum-parity (`test_authscheme_parity.py`), bootstrap-parity, OpenAPI snapshot (expect **no diff**), plaintext-in-logs red-team grep — all green.
- **Live smoke** (operator-supplied Auth0 tenant + M2M app with `read:clients`, isolated stack, backup first per `docs/operations/backup-before-reset.md`) — instantiate the template; replace `YOUR_TENANT`; register the credential; grant `call`; agent `GET /clients` through the proxy → 200 with Auth0 data; second call within TTL performs no second exchange (cache hit); a deliberately slash-less `audience` reproduces Auth0's mismatch error (documenting the pitfall); Basic client auth verified (flip the app to Client Secret (Basic) if 401 `invalid_client`); 0 plaintext in logs/audit.
