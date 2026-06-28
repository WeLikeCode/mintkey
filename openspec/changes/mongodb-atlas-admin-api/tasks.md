# Tasks — MongoDB Atlas Administration API support

Executed orchestrator-style: one IMPLEMENTER per chunk (test-first, surgical), a fresh REVIEWER per chunk, 3-strike hard-stop. Chunks C2–C4 (Go proxy) and C5–C6 (admin-api) are independent and can run in parallel worktrees; C1 (contracts/enums) lands first because C2–C8 reference the new enum.

## C1 — Contracts & enums (http_digest = 17)

- [ ] 1.1 `docs/architecture/contracts/vault-adapter/vault.proto`: add `AUTH_SCHEME_HTTP_DIGEST = 17`; `protoc --descriptor_set_out=/dev/null` passes
- [ ] 1.2 `docs/architecture/contracts/rest/openapi.yaml`: add `http_digest` to the `AuthScheme` enum (confirm `oauth2_client_credentials` already present); `openapi-spec-validator` + Redocly lint pass
- [ ] 1.3 `docs/architecture/contracts/mcp/tools.yaml`: add `http_digest`; `yaml.safe_load` passes
- [ ] 1.4 Regenerate `openapi_snapshot.json` (admin-api emits OpenAPI; CI diff green); update audit/change event schemas only if they enumerate auth schemes
- [ ] 1.5 Verify: vault.proto ↔ Go enum parity test still references a single source; no closed-enum drift

## C2 — Go proxy: OAuth2 client-credentials exchange

- [ ] 2.1 `apps/proxy-plugin/internal/credential/types.go`: add `OAuth2ClientCredentialsCredential` struct
- [ ] 2.2 `apps/proxy-plugin/internal/credential/exchanger.go`: add `ExchangeClientCredentials(ctx, req)` — form-encoded `grant_type=client_credentials` (+ optional `scope`), `Authorization: Basic base64(client_id:client_secret)`, reuse hardened client + `extractJSONPath` (default `$.access_token`) + `extractExpiresIn`; typed errors; **password-grant `Exchange` untouched**
- [ ] 2.3 `apps/proxy-plugin/internal/egress/oauth2_client_credentials.go`: add `HandleOAuth2ClientCredentials` mirroring `HandleOAuth2PasswordGrant` (cache → singleflight → graceful degradation → `token.exchanged` audit)
- [ ] 2.4 `apps/proxy-plugin/cmd/proxy-plugin/main.go`: dispatch scheme-5 exchange-shaped payloads to a `handleOAuth2ClientCredentials` method (clone of `handleOAuth2PasswordGrant`); non-exchange scheme-5 falls through to existing injector
- [ ] 2.5 Tests: form body + Basic header + JSONPath + expires_in + error classes + SSRF block; cache reuse + singleflight; `go test ./...` green; `golangci-lint` clean

## C3 — Go proxy: HTTP Digest

- [ ] 3.1 `apps/proxy-plugin/go.mod` + `go.work`: add `github.com/icholy/digest`; `go mod tidy`; record license in the dependency-bump stub
- [ ] 3.2 `apps/proxy-plugin/internal/credential/types.go` (+ const in the credential pkg): `HTTPDigestCredential` struct; `AuthSchemeHTTPDigest AuthScheme = 17`
- [ ] 3.3 `apps/proxy-plugin/internal/credential/digest.go`: build a per-request `*digest.Transport{Username, Password, Transport: base}`
- [ ] 3.4 `apps/proxy-plugin/cmd/proxy-plugin/main.go`: dispatch `http_digest` — set `proxy.Transport` to the digest transport, strip agent `Authorization` in the Director, inject no auth header
- [ ] 3.5 Tests: 401-challenge handled against an httptest digest server; agent `Authorization` stripped; `go test ./...` green

## C4 — Go proxy: read:atlas method gate

- [ ] 4.1 `apps/proxy-plugin/cmd/proxy-plugin/main.go`: after claims extraction, deny `scope == "read:atlas"` with a non-safe method (`403`); `admin:atlas`/`call`/email unaffected
- [ ] 4.2 Tests: GET allowed, DELETE 403 under `read:atlas`; admin:atlas POST/DELETE allowed; existing `call` path regression-free

## C5 — admin-api: credential validation

- [ ] 5.1 `apps/admin-api/src/admin_api/services/credential_service.py`: `OAuth2ClientCredentialsPayload` (HTTPS + forbidden-destination `token_url`, non-empty `client_id`/`client_secret`, optional `scope`/`token_response_path`, `to_vault_envelope()`); `HTTPDigestPayload` (non-empty `public_key`/`private_key`, `to_vault_envelope()`)
- [ ] 5.2 `apps/admin-api/src/admin_api/api/credentials.py`: two validation blocks mirroring `oauth2_password_grant` (lines 187-229) — `include_input=False`, static titles, no plaintext echoed; serialise canonical envelope to vault
- [ ] 5.3 Map `http_digest` in the admin-api auth_scheme string→int conversion used by the Vault client
- [ ] 5.4 Tests: valid accepted (metadata-only response); malformed/non-HTTPS/empty rejected with **zero submitted-secret bytes** in the response body

## C6 — admin-api: service templates

- [ ] 6.1 `apps/admin-api/src/admin_api/templates/service_templates.yaml`: add `mongodb-atlas-service-account` (oauth2_client_credentials) and `mongodb-atlas-api-key` (http_digest) with base_url, Atlas v2 OpenAPI URL, `test_path: /groups`, credential hints, and the explicit `Accept`-version-header instruction in `description` + `config_notes`
- [ ] 6.2 Confirm `ServiceTemplate` model (`admin_api/templates/models.py`) accepts both entries (flexible `credential_hint`); registry loads them
- [ ] 6.3 Tests: registry exposes both templates; `from-template` creates services with the right `auth_scheme` and base_url

## C7 — MCP discovery parity

- [ ] 7.1 `apps/mcp-server/src/mcp_server/auth_schemes.py`: real `oauth2_client_credentials` hint + new `http_digest` hint
- [ ] 7.2 Regenerate the bootstrap cheat-sheet; enum-parity and bootstrap-parity tests green

## C8 — Permission-grant actions (verify, minimal)

- [ ] 8.1 Confirm the permission-grant create endpoint accepts freeform `read:atlas`/`admin:atlas` actions (no allowlist change expected); `request_token` already maps a generic action → `scope`
- [ ] 8.2 Test: grant both actions; `request_token` issues correct `scope`; un-granted action → 403

## C9 — Docs & ADR

- [ ] 9.1 `docs/HOW-TO.md`: new "MongoDB Atlas Administration API" section (register via either template, grant read:atlas/admin:atlas, the mandatory `Accept` version header, what's out of scope re: document reads)
- [ ] 9.2 `docs/architecture/01-architecture/adr/0029-mongodb-atlas-admin-api-support.md` + `docs/architecture/adrs/0029-...` symlink + README index row
- [ ] 9.3 Update the CLAUDE.md "How to add an X" table with a MongoDB Atlas row (optional, if the maintainers want it discoverable)

## C10 — Integration & live verification

- [ ] 10.1 Full Go + admin-api + mcp-server suites green; all parity/snapshot/plaintext gates green
- [ ] 10.2 Live smoke on an isolated stack with operator-supplied creds: both templates registered; `read:atlas` GET `/groups` 200 + DELETE 403; `admin:atlas` create+delete; `Accept` header reaches Atlas (406 without it, success with it); 0 plaintext in logs/audit; backup taken first per `docs/operations/backup-before-reset.md`
