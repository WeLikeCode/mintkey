# Remediation: native `apple_jwt` auth scheme (.p8 + ES256 JWT)

**Session:** 2026-05-31-apple-jwt
**Branch:** feat/apple-jwt-auth-scheme
**Spec:** `.claude/prompts/feature-apple-jwt.md` (filed via PR #132, merged b77768d)
**Pattern:** orchestrator (Sonnet implementer + fresh Opus reviewer; 3-strike hard-stop; per-chunk)

## Issue intake (all 9 fields)
Per the filed prompt §6 — see `.claude/prompts/feature-apple-jwt.md`. Reproduced briefly:
1. Problem: no native apple_jwt; operators must rotate Apple JWTs every 20m manually.
2. Symptom: UI screenshot 2026-05-31 — `apple-app-store-connect` template prefills name/base_url/openapi-url but auth_scheme dropdown lacks `apple_jwt`, falls back to bearer_token.
3. Expected: operator uploads `.p8` + key_id + issuer_id once; vault generates fresh ES256 JWT (aud=appstoreconnect-v1, 19m TTL) per RetrieveCredential call.
4. Risk: HIGH — touches credential boundary, vault encryption path, proxy injection, OpenAPI contract. Reviewer required per chunk.
5. DoD: 12 checks in spec §5.

## Chunk plan (this session's reordering of spec §7 — code-first, docs-last)
- **Chunk 1 (FOUNDATION CONTRACTS)** — propagate `apple_jwt` enum value across OpenAPI, proto CredentialType, MCP tools.yaml, Python Pydantic AuthScheme. Mechanical edits; verify with OpenAPI lint, proto compile, ruff/mypy. → DISPATCHED.
- **Chunk 2 (Go applejwt pkg)** — create `apps/vault-adapter/internal/applejwt/` with Generate(p8KeyPEM, keyID, issuerID) → JWT string + unit tests (happy path, bad PEM, non-EC key, TTL = 19m strict <20m).
- **Chunk 3 (Vault Adapter handler)** — extend RetrieveCredential to detect apple_jwt type, decrypt blob, call applejwt.Generate, return JWT in bearer_value, zeroize PEM. SEPARATE chunk from Chunk 2 per spec §7 anti-combine rule.
- **Chunk 4 (Admin API)** — extend Pydantic CredentialCreate w/ AppleJWTFields model_validator; admin endpoint serializes to JSON blob, calls Vault StoreCredential; audit emission hides `p8_key_pem`/JWT.
- **Chunk 5 (Proxy plugin)** — add `case "apple_jwt"` in inject switch; ≤3 files (S-MOD-1).
- **Chunk 6 (Admin UI)** — add apple_jwt to dropdown (AUTH_SCHEMES at `apps/admin-ui/src/lib/auth-scheme.ts`); conditional fields p8_key_pem (textarea), key_id, issuer_id.
- **Chunk 7 (Template + smoke + docs)** — update `apple-app-store-connect` template to auth_scheme=apple_jwt; transient-test extension; red-team grep checks 10/11; docs/guides/appstoreconnect-quickstart.md; defer Kiro spec + ADR-0021 to follow-up unless trivial.

## Hard rules carried from spec
- Proto enum APPEND-ONLY (never renumber).
- Generated JWT NEVER persisted (no DB column, no cache beyond request).
- `p8_key_pem` NEVER in logs, OTel spans, audit payloads, HTTP responses.
- Proxy plugin ≤3 file changes (S-MOD-1).
- aud="appstoreconnect-v1" is a named const in applejwt pkg, nowhere else.
- 19-minute TTL (1m buffer; Apple max=20m).

## Round history
- R1: dispatched Chunk 1 implementer (Sonnet).
- R2–R7: all 7 chunks completed across subsequent sessions (Chunks 1–7).

## Outcome — CLOSED 2026-05-31

All 7 chunks landed on `feat/apple-jwt-auth-scheme`, merged into `integration/applejwt-googlesa-local`, then cherry-picked to main. Commits on main: foundation contracts (Chunk 1), applejwt pkg (Chunk 2), vault-adapter handler (Chunk 3, `57f7f4a`), admin-api validation (Chunk 4, `271f686`), proxy-plugin (Chunk 5, `7f08e87`), admin-ui, template + docs (Chunk 7, `477b362`). Remote branch `feat/apple-jwt-auth-scheme` retained for reference. All 12 DoD checks satisfied.
