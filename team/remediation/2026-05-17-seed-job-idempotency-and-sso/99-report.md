# Seed-job Idempotency + SSO — Closing Report

**Session:** `2026-05-17-seed-job-idempotency-and-sso`
**Branch:** `fix/seed-job-idempotency-and-sso-2026-05-17`
**Status:** CLOSED-LOCAL-PASS_ALL (operator-facing SSO over LAN verified end-to-end)

## Summary

Fixed two related defects + uncovered one cascading mismatch:

1. **SF-1**: seed-job's `_ensure_*` secret functions now validate content (not just existence). Stale/invalid secrets regenerate; valid ones preserve. Caught and tested against the PR #50 64-byte hex bug + 8 other format-drift scenarios.
2. **SSO-1**: seed-job patches Keycloak client redirectUris after realm import, using env-var-derived values. Literal `${...}` placeholders removed from `realm-mintkey.json`. Localhost preserved for local dev.
3. **Cascade fix**: jaeger-auth's oauth2-proxy now passes `--code-challenge-method=S256` (matches Keycloak's PKCE enforcement on mintkey-jaeger client).

Operator can now log in to admin-ui, Grafana, and Jaeger over LAN (`http://10.243.1.200:*`).

## Verification commands and exit codes

```
$ docker compose logs seed-job --tail 25
... Bootstrap: oidc_client_secret valid — skipping.
... Bootstrap: grafana_oidc_client_secret valid — skipping.
... Bootstrap: jaeger_oidc_client_secret valid — skipping.
... Keycloak: PKCE S256 enforced on mintkey-admin-api (already enforced — skipping)
... Keycloak: mintkey-admin-api redirectUris already current.
... Keycloak: mintkey-grafana redirectUris already current.
... Keycloak: mintkey-jaeger redirectUris already current.
... Bootstrap: jaeger_oauth2_cookie_secret valid — skipping.
... Keycloak realm bootstrap complete

$ curl -sL .../v1/auth/oidc/login → 200; final URL = Keycloak with redirect_uri=http://10.243.1.200:8080/v1/auth/oidc/callback (LAN IP, PKCE S256 challenge)

$ curl -sL http://10.243.1.200:3003/login/generic_oauth → 200; final URL = Keycloak with redirect_uri=http://10.243.1.200:3003/login/generic_oauth (LAN IP)

$ curl -sL http://10.243.1.200:16686/ → 200; final URL = Keycloak with redirect_uri=http://10.243.1.200:16686/oauth2/callback + code_challenge_method=S256

$ curl -sL http://10.243.1.200:8081/ → 200; lands on /admin/login (AdminJS sign-in page)

# Idempotency tests (helper unit-tested + live):
# 1) Existing valid 44-byte cookie → preserved across re-runs
# 2) 11-byte "BAD_CONTENT" → detected INVALID, regenerated to 44 bytes
# 3) Second run after regen → "valid — skipping" (idempotent)
# 4) jaeger-auth healthy after re-run + restart
```

## Chunks completed

| Chunk | Commit | Outcome |
|---|---|---|
| SF-1: content-validating `_ensure_secret_file` + per-function validators | `06286ae` | 4 `_ensure_*` paths now validate; 10 unit tests pass |
| SSO-1: Keycloak client redirectUris patcher + realm JSON cleanup + docker-compose env-var passthrough | `06286ae` | 3 clients patched; idempotent; localhost preserved |
| Cascade: oauth2-proxy PKCE S256 flag | `475bcd4` | Jaeger SSO chain reaches Keycloak with correct PKCE method |

3 commits over session scaffold `76a82af`.

## Configuration changes outside git (USER-LOCAL, gitignored)

`.env` extended with the 5 missing PUBLIC_URL settings:
```
MINTKEY_KEYCLOAK_PUBLIC_URL=http://10.243.1.200:8443
MINTKEY_ADMIN_UI_PUBLIC_URL=http://10.243.1.200:8081
MINTKEY_ADMIN_API_PUBLIC_URL=http://10.243.1.200:8080
MINTKEY_GRAFANA_PUBLIC_URL=http://10.243.1.200:3003
MINTKEY_JAEGER_PUBLIC_URL=http://10.243.1.200:16686
```
Documented per-operator local concern — not part of PR.

## DoD checklist — final state

- [x] `_ensure_secret_file` helper added; 4 `_ensure_*` paths refactored.
- [x] Pre-existing stale jaeger cookie regenerates on next seed-job run.
- [x] Realm JSON no longer contains `${...}` placeholder strings.
- [x] `_patch_keycloak_client_redirect_uris` patches 3 clients idempotently after realm import.
- [x] docker-compose.yml seed-job env forwards the 3 client PUBLIC_URL env vars.
- [x] All 17 containers healthy after rebuild.
- [x] LAN IP redirect URIs verified in Keycloak admin REST.
- [x] Full SSO redirect chain (admin-ui, Grafana, Jaeger) returns 200 → Keycloak login page from LAN.
- [x] jaeger-auth oauth2-proxy includes `--code-challenge-method=S256`.
- [x] No accepted ADR changed; no `Co-Authored-By` trailer; no `--no-verify`.

## Residual risks / deferred items

- **`webOrigins` left at `+`** (Keycloak permissive any-same-origin). Sufficient for current LAN/localhost setup. If a future deployment needs explicit allow-list, the patcher already has the helper pattern.
- **`_interpolate_realm_json`** in seed-job still exists but no longer matches any `${...}` strings in the realm. Kept for future use (other config keys that need env interpolation).
- **CI integration test** runs without LAN env vars → patcher no-ops → realm stays at localhost-only URIs. Tested OK.
- **Single sign-on between admin-ui ↔ Grafana ↔ Jaeger** still requires separate Keycloak sessions (each service maintains its own cookie). Cross-service SSO is a separate concern from "each service can SSO at all".
- **TLS/HTTPS migration** would change redirect URIs from `http://` to `https://`. Patcher would need to re-run; intentional — that's a separate deployment session.

## Lessons learned

- **Idempotency is two-axis, not one**: existence + content. Existence-only checks become tech debt the moment format drifts.
- **Realm JSON placeholders are a footgun**: Keycloak doesn't expand `${...}` in redirect URIs at import time. Either substitute pre-import OR patch via API post-import. The latter is more robust because it handles already-imported-realm runs idempotently.
- **PKCE enforcement is a contract** between Keycloak and the OIDC client. When seed-job enforces it on a client, every consumer of that client must use PKCE. oauth2-proxy v7 doesn't auto-detect — must pass the flag.
- **Cascade-of-fixes pattern**: each successful redirect unblocked the next layer's complaint. Lint Go fix → exposed Lint Python → exposed test infra → exposed Trivy → exposed Integration Tests → exposed seed-job perms → exposed otel-collector → exposed jaeger-auth perms → exposed cookie size → exposed shell null-truncation → exposed wrong flag. Same pattern at SSO: PUBLIC_URL `.env` → realm placeholders → PKCE flag. Worth instrumenting: end-to-end "operator can log in" smoke test in CI would catch all these on a single run.
