# MongoDB Atlas Administration API support

## Why

Agents have no first-class way to perform MongoDB Atlas administrative operations (create/scale clusters, manage projects, database users, network access, backups, alerts) through Mintkey. The Atlas Administration API (`https://cloud.mongodb.com/api/atlas/v2`) authenticates **only** via two schemes Mintkey does not support end-to-end today:

- **Service Accounts** — OAuth 2.0 **client-credentials** (`client_id`/`client_secret` → 1-hour Bearer access token from `https://cloud.mongodb.com/api/oauth/token`). The `oauth2_client_credentials` enum value (5) is declared across the contracts but has **no token-exchange implementation, no credential payload schema, and no admin-api validation** — the proxy injector treats it as a pre-fetched bearer that nothing ever produces.
- **Programmatic API Keys** — HTTP **Digest** (RFC 2617) challenge-response with a public key (username) + private key (password). Mintkey has **no Digest support** at all.

Two further Atlas-specific facts shape the design:

1. The Administration API is **control-plane only** — it cannot read documents from collections. The former Atlas Data API (HTTP document access) has been **retired** by MongoDB; reading collection data requires the MongoDB wire protocol, which Mintkey's HTTP proxy does not speak. **Reading collection data is explicitly out of scope.**
2. Atlas v2 **requires** a dated `Accept: application/vnd.atlas.<yyyy-mm-dd>+json` version header (e.g. `2025-03-12`) on every request; omitting it returns **406 Not Acceptable**.

Operators also need to bound what an agent can do: Atlas operations range from harmless (`GET /groups`) to destructive (`DELETE` a cluster). A read-only grant should exist alongside a full-admin grant.

## What Changes

- **OAuth2 client-credentials becomes a real, live-exchange auth scheme** (reuses, does not modify, the existing `oauth2_password_grant` token-exchange engine): a new credential payload `{token_url, client_id, client_secret, scope?, token_response_path?}`, a sibling exchange that POSTs form-encoded `grant_type=client_credentials` with HTTP Basic `client_id:client_secret`, and a proxy orchestration that mirrors the password-grant cache → singleflight → graceful-degradation → inject-`Bearer` flow. Scheme stays enum **5** (already in proto/OpenAPI/MCP).
- **A new `http_digest` auth scheme** (enum **18**; integer **17 is reserved** for the pre-existing admin-api-only `email_oauth2_client` synthetic): credential payload `{public_key, private_key}`; the proxy attaches a per-request RFC 2617 Digest `RoundTransport` (vetted `github.com/icholy/digest`) to the reverse proxy instead of injecting a static header.
- **Read-only vs full proxy actions**: the proxy plugin gains a minimal, backward-compatible method gate — when the JWT `scope` is `read:atlas`, only `GET`/`HEAD`/`OPTIONS` are allowed (else `403`); `admin:atlas` and every existing action (`call`, email scopes, …) are unaffected. Operators grant `read:atlas` and/or `admin:atlas` per agent.
- **Two service templates** — `mongodb-atlas-service-account` (oauth2_client_credentials) and `mongodb-atlas-api-key` (http_digest) — with `base_url: https://cloud.mongodb.com/api/atlas/v2`, the Atlas v2 OpenAPI URL, `test_path: /groups`, credential hints, and a **`description`/`config_notes` that explicitly instruct the agent to send the dated `Accept` version header itself** (Mintkey forwards agent headers unchanged; it does NOT inject the version header).
- **A new ADR (0029)** records the two new auth schemes and the read-scoped method-gating semantic; the change references it.

## Capabilities

### New Capabilities
- `oauth2-client-credentials-auth`: live client-credentials token exchange (form + Basic auth), cached and auto-refreshed by the proxy, injected as `Authorization: Bearer`.
- `http-digest-auth`: RFC 2617 Digest challenge-response for upstreams authenticated by a public/private key pair.
- `read-scoped-proxy-actions`: a read-only proxy action that restricts the agent to safe HTTP methods, gated in the proxy from the JWT `scope`.
- `mongodb-atlas-service-templates`: one-click registration of the Atlas Administration API via either credential type, with explicit agent-facing version-header guidance.

### Modified Capabilities
<!-- none — no existing capability spec covers these surfaces at requirement level -->

## Impact

- **Contracts**: `docs/architecture/contracts/vault-adapter/vault.proto` (+`AUTH_SCHEME_HTTP_DIGEST = 18`, +`reserved 17`); `docs/architecture/contracts/rest/openapi.yaml` (+`http_digest` in the `AuthScheme` enum); `docs/architecture/contracts/mcp/tools.yaml` (+`http_digest`); `apps/admin-api/tests/.../openapi_snapshot.json` regenerated; audit/change event schemas if they enumerate schemes. `oauth2_client_credentials` already present in all enums — no enum addition for it.
- **Proxy (Go)** — `apps/proxy-plugin/`: client-credentials follows the established password-grant footprint (`internal/credential/types.go` struct, `internal/credential/exchanger.go` exchange method, `internal/egress/` handler, `cmd/proxy-plugin/main.go` dispatch); digest follows an injector-style footprint (a new `internal/credential/digest.go` transport, the scheme const, `main.go` dispatch); read-scoped gating is a small guard in `main.go`. New module dependency: `github.com/icholy/digest`.
- **admin-api (Python)**: `apps/admin-api/src/admin_api/services/credential_service.py` (new `OAuth2ClientCredentialsPayload`, `HTTPDigestPayload`); `apps/admin-api/src/admin_api/api/credentials.py` (two validation blocks mirroring `oauth2_password_grant`, never echoing plaintext); the auth_scheme string→int map for `http_digest`; `apps/admin-api/src/admin_api/templates/service_templates.yaml` (two templates).
- **MCP server (Python)**: `apps/mcp-server/src/mcp_server/auth_schemes.py` injection-hint entries for `http_digest` and a real `oauth2_client_credentials` hint (enum-parity gate); bootstrap cheat-sheet regenerated (bootstrap-parity gate).
- **Docs**: new `docs/HOW-TO.md` §MongoDB Atlas; ADR-0029 (+ `adrs/` symlink + README row); the routing-table "How to add an X" row for auth schemes already covers the proxy ≤3-files guidance (see design for the S-MOD-1 note).
- **Tests**: Go unit tests for the client-credentials exchanger, the digest transport, and the read-scoped gate; admin-api unit tests for the two payload validators (incl. plaintext-never-echoed); enum-parity + bootstrap-parity gates green; a live smoke against the real Atlas Administration API with an operator-supplied Service Account and Programmatic API Key.
- **Out of scope**: reading collection documents / any MongoDB wire-protocol data path; a MongoDB-wire proxy component; injecting the Atlas version header on the agent's behalf; a per-service `default_headers`/`usage_notes` column; mTLS; admin-ui form work beyond what template instantiation already provides.
