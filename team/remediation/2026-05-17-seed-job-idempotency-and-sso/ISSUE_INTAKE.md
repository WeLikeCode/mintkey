# Issue Intake — 2026-05-17-seed-job-idempotency-and-sso

**Session:** `team/remediation/2026-05-17-seed-job-idempotency-and-sso/`
**Branch:** `fix/seed-job-idempotency-and-sso-2026-05-17`
**Reported:** 2026-05-17
**Reporter:** Owner — "open a session to fix the seed-job idempotency footgun and also investigate why accessing admn ui over the network I get redirected to localhost, thus breaking the login via keycloak."

## Problem statement (required)

Two related defects in the bootstrap pipeline:

1. **Idempotency footgun in `_ensure_*` secret functions** (seed-job/main.py): functions check only for file existence, not content validity. After PR #50 wrote 32 raw bytes (invalid for oauth2-proxy), PR #52 fixed the generation to write 44-char base64. But local stacks with the OLD bad file still skip rewriting on subsequent seed-job runs. Owner had to manually wipe the file. Same trap exists for any future format change.

2. **Operator cannot SSO-login to admin-ui, Grafana, or Jaeger over the LAN** (e.g., from `http://10.243.1.200:8081/`). Two layered causes:

   a. **`.env` is incomplete** — only `MINTKEY_MCP_PUBLIC_URL` and `MINTKEY_PROXY_PUBLIC_URL` are set. The 5 PUBLIC_URL env vars that affect SSO (KEYCLOAK / ADMIN_UI / ADMIN_API / GRAFANA / JAEGER) all fall back to `localhost:NNNN` defaults from `docker-compose.yml`.

   b. **`seed-job/realm-mintkey.json` stores literal `${MINTKEY_ADMIN_API_PUBLIC_URL}` placeholder strings as redirect URIs** — Keycloak does NOT substitute these. `seed-job/main.py` does not patch them after import. So even when env vars ARE set correctly, the allow-listed redirect URIs in Keycloak contain literal `${...}` text that never matches a real redirect — login fails with `invalid_redirect_uri`.

## User-visible symptom (required)

- Operator opens `http://10.243.1.200:8081/` in a browser on a different machine on LAN
- Clicks "Sign in with Keycloak" → admin-ui sends to admin-api → admin-api builds redirect_uri based on `MINTKEY_ADMIN_API_PUBLIC_URL` env (falls back to `localhost:8080` if unset)
- Browser sent to `http://localhost:8443/realms/mintkey/...` (Keycloak browser-facing URL also defaults to localhost) → cannot resolve on operator's machine
- Even if user sets `MINTKEY_ADMIN_API_PUBLIC_URL=http://10.243.1.200:8080`, Keycloak rejects: `redirect_uri does not match any in client config` because the client only allow-lists `http://localhost:8080/v1/auth/oidc/callback` and the literal string `${MINTKEY_ADMIN_API_PUBLIC_URL}/v1/auth/oidc/callback`.
- Same pattern blocks Grafana login (`/login/generic_oauth`) and Jaeger login (`/oauth2/callback`).

Idempotency footgun: after any seed-job code change affecting secret content/format, existing local stack with the old secret in its named volume remains broken until operator manually wipes the secret file.

## Expected behavior (required)

### SF-1 (idempotency)
- `_ensure_jaeger_cookie_secret` (and other `_ensure_*` functions) validate existing file content (size + format), not just existence.
- If existing file is invalid for the current expected format → regenerate.
- If valid → preserve.

### SSO (combined)
- Operator opens `http://10.243.1.200:8081/`, clicks "Sign in with Keycloak", completes OIDC, lands back in admin-ui as authenticated `admin@mintkey.internal`.
- Same for `http://10.243.1.200:3003/` (Grafana) and `http://10.243.1.200:16686/` (Jaeger).
- seed-job patches each client's `redirectUris` and `webOrigins` based on actual env-var values after realm import.
- `.env` documents the full set of PUBLIC_URL env vars needed for over-LAN operation (operator updates local file; not in git).

## Evidence (required)

### Idempotency footgun
- Live observation 2026-05-17 ~06:11 (UTC): local jaeger-auth crashed on rebuild with `cookie_secret must be 16, 24, or 32 bytes to create an AES cipher, but is 64 bytes`. seed-job logs showed `Keycloak: jaeger_oauth2_cookie_secret already exists — skipping.` Manual `rm /secrets/jaeger_oauth2_cookie_secret` resolved.
- Pattern in `seed-job/main.py` `_ensure_*` functions: `if not file.exists(): write; chmod; ; else: log and skip`.

### SSO
- `docker-compose.yml` per-service env defaults all PUBLIC_URL vars to `localhost:NNNN`.
- Owner's `.env` contains only `MINTKEY_MCP_PUBLIC_URL` and `MINTKEY_PROXY_PUBLIC_URL`. Missing 5 (KEYCLOAK, ADMIN_UI, ADMIN_API, GRAFANA, JAEGER).
- `seed-job/realm-mintkey.json` clients have:
  ```
  redirectUris: ['http://localhost:8080/v1/auth/oidc/callback', '${MINTKEY_ADMIN_API_PUBLIC_URL}/v1/auth/oidc/callback']
  ```
  Same pattern for `mintkey-grafana`, `mintkey-jaeger`.
- `grep -n redirectUris seed-job/main.py` → empty (no post-import patching).
- `admin-api/src/admin_api/auth/oidc.py:104`: `os.getenv("MINTKEY_ADMIN_API_PUBLIC_URL", "http://localhost:8080")` — confirms localhost default in admin-api's redirect_uri builder.

## Scope (required)

May be changed:
- `seed-job/main.py` (idempotency `_ensure_*` validators + new realm patcher function)
- `seed-job/realm-mintkey.json` — keep `localhost:*` URIs (dev-default); seed-job adds operator-specified URIs on top
- `.env` (USER-LOCAL, gitignored — orchestrator updates outside git)
- Session folder
- `seed-job/Dockerfile` if a new dep is needed (unlikely; seed-job already uses requests-based Keycloak API client)

## Out of scope (required)

- Other services' code (admin-api, mcp-server, services/*) — they correctly read env vars; the issue is the env vars + realm config, not the services.
- Keycloak realm structural redesign (e.g., wildcard redirect URIs `http://10.243.1.200:*/*`) — wildcards are a security smell; deliberately avoided.
- TLS/HTTPS migration — separate concern.
- Single-sign-on session sharing across admin-ui/Grafana/Jaeger (separate from "can each log in at all").
- Production deployment patterns (this session targets a LAN-accessible dev/operator stack at 10.243.1.200).

## Risk level (required)

- **Security**: low-medium — seed-job patches redirect URIs based on env vars. If env vars are mis-set, the realm could allow attacker domains. Mitigation: env vars are only set by ops/owner; seed-job runs at bootstrap; redirect URI changes are auditable in seed-job logs.
- **Operator UX**: high positive — unblocks daily ops use of admin-ui/Grafana/Jaeger over LAN.
- **CI regression**: low — CI's integration test runs without env overrides → falls back to localhost (which CI uses); the new realm patcher only fires when env vars differ from realm content.

## Verification target (required)

### SF-1
- Write a file with bad content (e.g., 64 bytes) at `/run/secrets/mintkey/bootstrap-secrets/jaeger_oauth2_cookie_secret`.
- Run seed-job. Expect: seed-job validates, detects bad size, regenerates with 44-char base64.
- Re-run seed-job. Expect: validation passes (file is now correct); skip regeneration (idempotent for already-correct files).

### SSO
- Update local `.env` with full 7 PUBLIC_URL set (5 missing + 2 existing).
- `docker compose up -d --build seed-job`.
- Verify seed-job logs include `Keycloak: patched mintkey-admin-api redirectUris ...`, same for grafana and jaeger clients.
- Verify via Keycloak admin REST that client `mintkey-admin-api` `redirectUris` now includes literal `http://10.243.1.200:8080/v1/auth/oidc/callback` (no `${...}` placeholder).
- Operator opens `http://10.243.1.200:8081/` on a different LAN machine. Click "Sign in with Keycloak". Login completes. Land authenticated on admin-ui.
- Repeat for `http://10.243.1.200:3003/` (Grafana) and `http://10.243.1.200:16686/` (Jaeger).
- Re-run seed-job. Expect: idempotent — no churn on already-correct redirectUris.

## Owner decisions

- ✅ **Approach for realm redirect URIs**: seed-job patches client `redirectUris` + `webOrigins` AFTER realm import, using env-var-derived values. Realm JSON keeps `localhost:*` URIs as dev-default; patcher adds operator-specified URIs on top. Idempotent (no-op if already correct).
- ✅ **Approach for idempotency**: validate content (size for binary; basic format check for known structures). Regenerate if invalid; preserve if valid. Apply to ALL `_ensure_*` functions (not just jaeger cookie).
- ✅ **`.env` updates**: orchestrator writes the 5 missing PUBLIC_URL lines (since `.env` is gitignored and user-local; not part of PR).
- ✅ **Scope of redirect URIs added**: only operator's network IP (10.243.1.200). No wildcards. Localhost preserved for local dev.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions
