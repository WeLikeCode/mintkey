# Tasks — Auth0 Management API service template

Executed orchestrator-style: one IMPLEMENTER per chunk (test-first, surgical), a fresh REVIEWER per chunk, 3-strike hard-stop. C1 lands first (C2's template is only useful once `audience` flows end-to-end); C3 can run in parallel with C2; C4 gates the whole change. Every chunk verifies from the repo root of this branch's worktree.

## C1 — Optional `audience` on the client-credentials scheme (Go + admin-api)

Files: `apps/proxy-plugin/internal/credential/types.go`, `apps/proxy-plugin/internal/credential/exchanger.go`, `apps/proxy-plugin/internal/egress/oauth2_client_credentials.go`, `apps/proxy-plugin/internal/credential/client_credentials_exchanger_test.go`, `apps/proxy-plugin/internal/egress/oauth2_client_credentials_test.go`, `apps/admin-api/src/admin_api/services/credential_service.py`, `apps/admin-api/tests/unit/admin_api/test_atlas_credential_payloads.py` (extend — or a sibling test module if the reviewer prefers separation).

- [ ] 1.1 `types.go`: add `Audience string \`json:"audience,omitempty"\`` to `OAuth2ClientCredentialsCredential` (doc comment per design)
- [ ] 1.2 `exchanger.go`: add `Audience string` to `ClientCredentialsRequest`; in `ExchangeClientCredentials`, after the `scope` branch, `if req.Audience != "" { vals.Set("audience", req.Audience) }` — password-grant `Exchange` untouched
- [ ] 1.3 `egress/oauth2_client_credentials.go`: add `Audience: cred.Audience,` to the `exchangeReq` literal — no other orchestration change; `cmd/proxy-plugin/main.go` untouched
- [ ] 1.4 Go tests (write first): (a) audience present → raw form body contains `audience=<urlencoded value>` alongside `grant_type=client_credentials`; (b) audience absent/empty → form body byte-identical to the pre-change body (no `audience` key); (c) egress handler maps `cred.Audience` into the exchange request; (d) all pre-existing client-credentials/password-grant/digest/dispatch tests pass **unmodified**
- [ ] 1.5 `credential_service.py`: add `audience: str | None = None` to `OAuth2ClientCredentialsPayload`; validator — when present, non-empty absolute URI (scheme required; NOT SSRF-checked, NOT HTTPS-restricted — never dereferenced); `to_vault_envelope()` emits `audience` only when set (Go `omitempty` parity); `api/credentials.py` needs NO edit (block validates via the payload model)
- [ ] 1.6 admin-api tests (write first): audience accepted → envelope contains it; absent → envelope omits the key (byte-parity with today); whitespace-only / scheme-less audience → `ValueError`/4xx with **zero submitted-secret bytes** echoed; existing Atlas payload tests pass unmodified
- [ ] 1.7 Verify:
  - `cd apps/proxy-plugin && go build ./... && go test ./... -short && go vet ./...` — exit 0
  - `cd apps/admin-api && uv run pytest tests/unit/admin_api/test_atlas_credential_payloads.py -q` — exit 0 (plus any new sibling module)
  - `cd apps/admin-api && uv run mypy --strict src/admin_api/ && uv run ruff check src/` — exit 0

## C2 — `auth0-management` service template + registry test

Files: `apps/admin-api/src/admin_api/templates/service_templates.yaml`, `apps/admin-api/tests/unit/admin_api/test_auth0_management_template.py` (new).

- [ ] 2.1 Append the `auth0-management` entry exactly as specified in design.md — `auth_type: oauth2_client_credentials`; `base_url: https://YOUR_TENANT.auth0.com/api/v2`; `openapi_spec_url: https://auth0.com/docs/oas/management/v2/management-api-oas.json`; `category: identity`; `test_path: /clients`; `credential_hint` using ONLY typed `CredentialHint` fields — `token_url: https://YOUR_TENANT.auth0.com/oauth/token`, `token_response_path: "$.access_token"`, and `credential_fields: {client_id, client_secret, audience: "https://YOUR_TENANT.auth0.com/api/v2/"}`; `config_notes` covering: replace `YOUR_TENANT` everywhere (regional/custom domains), M2M app authorized for the Management API (`/clients` needs `read:clients`), the trailing-slash audience requirement, the HTTP Basic / Client Secret (Basic) note, the 24-hour token TTL, and granting agents `call`
- [ ] 2.2 New `test_auth0_management_template.py` (write first), modeled on `test_mongodb_atlas_templates.py`: (a) YAML loads the template with the pinned auth_type/base_url/openapi_spec_url/test_path/category; (b) the credential hint **survives registry loading** with `token_url`, `token_response_path`, and all three `credential_fields` keys (guards the verified `CredentialHint` `extra='ignore'` drop wrinkle); (c) `config_notes` contains "YOUR_TENANT" and the trailing-slash audience instruction; (d) from-template returns 201 with `auth_scheme: oauth2_client_credentials` and the placeholder base_url (SSRF gate fails open on the unresolvable placeholder — patch is unnecessary but mirror the Atlas test's patching style)
- [ ] 2.3 Record (do NOT fix) the pre-existing wrinkle for the maintainers: the Atlas templates' flat `client_id:`/`client_secret:` hint keys are silently dropped by `CredentialHint` — follow-up candidate, out of scope here
- [ ] 2.4 Verify:
  - `cd apps/admin-api && uv run pytest tests/unit/admin_api/test_auth0_management_template.py tests/unit/admin_api/test_mongodb_atlas_templates.py -q` — exit 0
  - `cd apps/admin-api && uv run python -c "from admin_api.templates.registry import _load_templates; t={x.template_id:x for x in _load_templates()}['auth0-management']; assert t.credential_hint.credential_fields and set(t.credential_hint.credential_fields) == {'client_id','client_secret','audience'}"` — exit 0
  - `cd apps/admin-api && uv run ruff check src/ && uv run mypy --strict src/admin_api/` — exit 0

## C3 — Docs

Files: `docs/HOW-TO.md`, `docs/architecture/01-architecture/adr/0029-mongodb-atlas-admin-api-support.md` (conditional).

- [ ] 3.1 `docs/HOW-TO.md`: new `## 14. Auth0 Management API` section (after §13 MongoDB Atlas): create the M2M application in Auth0 and authorize it for the Management API with least-privilege scopes; instantiate `auth0-management`; replace `YOUR_TENANT` in base_url and in the credential's token_url/audience (regional + custom-domain note); the trailing-slash audience pitfall (Auth0 rejects a mismatched audience); the Client Secret (Basic) note; grant `call`; agent example `GET /clients`; note that no versioned Accept header is needed (contrast §13)
- [ ] 3.2 ADR-0029 D2 payload example: add `"audience": "(optional)"` — ONLY while ADR-0029's status is still Proposed. If it has been Accepted, do NOT edit it; note the extension in this change's archive notes instead (per design §ADR decision)
- [ ] 3.3 Verify:
  - `grep -n "^## 14. Auth0 Management API" docs/HOW-TO.md` — exactly one hit
  - `grep -c "YOUR_TENANT" docs/HOW-TO.md` — ≥ 1; section mentions "trailing slash" and "read:clients"
  - If 3.2 applied: `grep -n "audience" docs/architecture/01-architecture/adr/0029-mongodb-atlas-admin-api-support.md` — hit inside the D2 payload example; ADR status line still "Proposed"

## C4 — Integration & parity gates

- [ ] 4.1 Full suites: `go test ./... -short` (repo root, go.work) and `cd apps/admin-api && uv run pytest tests/ -q` — exit 0; report counts
- [ ] 4.2 Parity/snapshot gates: `uv run pytest tests/unit/admin_api/test_authscheme_parity.py -q` green; OpenAPI snapshot diff shows **no change** (no wire surface touched); mcp-server bootstrap-parity suite green
- [ ] 4.3 Plaintext red-team: `docker compose logs | grep -E "$(cat ./scripts/red-team-fingerprints.txt)"` — empty output after exercising the flow
- [ ] 4.4 Live smoke (operator-supplied Auth0 tenant + M2M app with `read:clients`; isolated stack; `bash scripts/dev-backup.sh` FIRST per `docs/operations/backup-before-reset.md`):
  - instantiate `auth0-management`; replace `YOUR_TENANT`; register credential `{token_url, client_id, client_secret, audience}`; grant `call`
  - agent `GET /clients` through the proxy → 200 with Auth0 data; `Via: kong` header present
  - second call within TTL → no second token exchange (cache hit; check `token.exchanged` audit count)
  - negative: audience without the trailing slash → exchange fails with Auth0's mismatch error (document verbatim in the smoke log)
  - client-auth check: if the exchange 401s with `invalid_client`, flip the app to Client Secret (Basic) and re-run → success (record which setting the tenant needed)
  - 0 plaintext (client_secret, access_token) in logs/audit/spans
