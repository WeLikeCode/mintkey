# Adversarial Security Review — `feature/service-templates` (commit 828bd7c)

Reviewer lens: attacker + data-protection. Read-only review. Scope = the diff
`main...feature/service-templates` (service-template catalog + instantiation API,
and the OAuth2 Password Grant auth scheme: token exchange in the Go proxy plugin,
token cache, audit event, and Admin API credential validation).

Source-of-truth checked: `.kiro/specs/service-templates/requirements.md`
(Req 19–23), `design.md` (S-SEC-1 / Property 12 / Security Invariants P-1).

Navigation: used Serena-adjacent grep + direct Read across both the Python
admin-api and the Go proxy-plugin / vault-adapter. Not navigating blind.

---

## Summary of severity counts

- CRITICAL: 2
- HIGH: 3
- MEDIUM: 4
- LOW: 3

The two CRITICALs are the load-bearing ones: the SSRF allowlist for `token_url`
(S-SEC-1, Req 19.4 / Property 3) is **dead code that is never invoked on any
write path**, and the Go-side token exchange has **no SSRF guard at all and
follows redirects**, so a tenant-controlled `token_url` reaches arbitrary
internal hosts (cloud metadata, loopback, internal services) from inside the
proxy with the proxy's network identity.

---

## CONFIRMED findings

### [SEV: CRITICAL] [confidence: CONFIRMED] `token_url` SSRF allowlist (S-SEC-1) is never enforced — validation code is dead

**file:** `apps/admin-api/src/admin_api/services/credential_service.py:38,103,142`
plus `apps/admin-api/src/admin_api/api/credentials.py:132-182` and
`apps/admin-api/src/admin_api/api/services.py:464-621`

`OAuth2PasswordGrantPayload` (with the `validate_https` + `validate_ssrf`
field validators) and `validate_token_url_ssrf()` are defined but **never
imported or called anywhere in the codebase**. Grep for `OAuth2PasswordGrantPayload`
and `validate_token_url_ssrf` returns only their definition sites — zero call
sites in any router, service, or test.

The actual credential write path is `POST .../services/{sid}/credentials`
(`credentials.py:create_credential`). It accepts `CredentialCreate.value: str`
(credentials.py:104-107) and passes it verbatim to `vault.put_credential(...)`
(credentials.py:174-182). For `auth_scheme=oauth2_password_grant`, `value` is the
JSON blob `{token_url, credential_fields, token_response_path, ...}`. **Nothing
parses that blob, nothing enforces HTTPS, nothing runs the SSRF allowlist.**

Design.md §Security Invariant 4 explicitly relies on this: *"SSRF validation on
token_url happens at registration time (Admin API). The proxy trusts the stored
URL because it was validated at write time."* That invariant is false — the
validation does not run, and the proxy (see next finding) does not compensate.

**Exploit:** Register/instantiate an `oauth2_password_grant` service, then POST a
credential whose `token_url` is `https://169.254.169.254/latest/meta-data/...`,
`https://127.0.0.1:<port>/...`, or any internal hostname. At first proxied
request the proxy POSTs `credential_fields` to that URL and injects whatever
comes back as a Bearer token upstream. Direct SSRF to cloud metadata / internal
services, plus a token-extraction oracle (JSONPath over the response body).

**Fix direction:** In `create_credential`/`rotate_credential`, when
`auth_scheme == "oauth2_password_grant"`, parse `body.value` through
`OAuth2PasswordGrantPayload` (this triggers `validate_https` + `validate_ssrf`)
and 422 on failure. Do the same in any from-template credential pre-population
path. Wire it; right now the protection is decorative.

---

### [SEV: CRITICAL] [confidence: CONFIRMED] Proxy-side token exchange has no SSRF guard and follows redirects (TOCTOU + redirect/DNS-rebind bypass)

**file:** `apps/proxy-plugin/internal/credential/exchanger.go:66-117`
(`NewTokenExchanger`, `Exchange`)

The Go `TokenExchanger` builds an `http.Client{Timeout: 10s}` with:
- **No `CheckRedirect`** → Go's default follows up to 10 redirects. Even if the
  stored `token_url` were validated, a 302 to `http://169.254.169.254/...` or
  `http://127.0.0.1/...` is followed automatically.
- **No `DialContext`/transport-level IP allowlist** → no per-connection check
  that the resolved address is public.
- **No re-validation of `cred.TokenURL`** before the POST. The proxy fully
  trusts the stored URL (per design invariant 4), but as shown above the write
  path never validated it.

Even in the hypothetical where finding #1 is fixed, this is still a real bypass:
(a) **DNS rebinding** — write-time validation resolves a hostname to a public IP;
the proxy re-resolves at request time to `127.0.0.1`. (b) **Redirect-based SSRF**
— `token_url` points at an attacker-controlled public host that 302-redirects to
an internal address. Both reach internal services from the proxy's vantage point.

**Exploit:** As above, but works even with a "valid" public `token_url` via a
redirect or short-TTL rebinding record. The proxy is typically the most
network-privileged component (it egresses to the internet *and* sits next to
internal services), making this high-value.

**Fix direction:** On the proxy's exchange client set
`CheckRedirect: func(...) error { return http.ErrUseLastResponse }` (or block
non-allowlisted redirect targets), and add a `DialContext` that rejects dialing
any private/loopback/link-local/metadata IP (post-resolution check, closing the
rebind window). Treat the stored URL as untrusted at request time.

---

### [SEV: HIGH] [confidence: CONFIRMED] No operator authentication on the new (and existing) state-changing endpoints — only a double-submit CSRF check gates them

**file:** `apps/admin-api/src/admin_api/main.py:63-108`,
`apps/admin-api/src/admin_api/middleware/csrf.py:46-75`,
`apps/admin-api/src/admin_api/api/services.py:464` (`from-template`),
`apps/admin-api/src/admin_api/api/credentials.py:132` (`create_credential`)

The new routers (`services_router`, `service_templates_router`) and the
credential router are included with **no authentication dependency**. The only
gate on state-changing requests is `CsrfMiddleware`, which is a pure
double-submit check: it requires `csrf_token` cookie == `x-mintkey-csrf` header
via `hmac.compare_digest` (csrf.py:67) — both fully attacker-suppliable on a
non-browser client. There is no call to `validate_session` / no operator-session
dependency on these handlers (grep for `OperatorSession`/`validate_session` in
`api/` finds only the docstring claim in `service_templates.py:8`, no code).

`create_service_from_template` takes `tenant_id` straight from the URL path and
never checks it against an authenticated operator's tenant scope (services.py:465).

**Exploit:** Any client that can reach the admin-api (no session needed) can
`POST /v1/tenants/{ARBITRARY_TID}/services/from-template` and
`POST /v1/tenants/{ARBITRARY_TID}/services/{sid}/credentials` with self-chosen
matching cookie+header. Cross-tenant service creation and credential write —
directly the "AuthZ on new endpoints / cross-tenant isolation" threat (concern 8).

**Caveat / scope note:** this auth posture is *pre-existing* (the same gap exists
on `agents`/`tenants`/`credentials` routers — none take an auth dependency). It
is not introduced by this branch. But the branch adds two new write surfaces
(`from-template`, oauth2 credential storage) that inherit it, and design Req 4.3
explicitly claims "RLS enforcement" / tenant scoping that the code does not
implement at the API layer. Flagging as HIGH because it is load-bearing for the
SSRF findings (an unauthenticated attacker can reach the SSRF primitive). If a
network/gateway layer enforces operator auth outside this repo, downgrade to a
documentation gap — but that should be verified, not assumed.

**Fix direction:** Add an operator-session (or operator-bearer) dependency to the
services/credentials/service-template routers and assert the session's tenant
matches the `{tenant_id}` path param (or that the operator is a platform admin).

---

### [SEV: HIGH] [confidence: CONFIRMED] `token_response_path` JSONPath extraction has no depth/segment bound and trusts hostile JSON shape — DoS surface; also numeric-token coercion

**file:** `apps/proxy-plugin/internal/credential/exchanger.go:155-200`
(`extractJSONPath`)

`extractJSONPath` does `json.Unmarshal(body, &current)` over the **full** (up to
1 MB) response body into `any`, then walks `strings.Split(path[2:], ".")`
segments. `token_response_path` is tenant-controlled. While the 1 MB
`io.LimitReader` (exchanger.go:121) caps body size, a 1 MB deeply-nested JSON
document unmarshalled into `map[string]any` is a CPU/allocation amplification
the token endpoint (which can be attacker-controlled per finding #2) fully
governs. There is no cap on path segment count and no guard against
pathological nesting. Combined with the cache-miss path being reachable per
request near expiry, this is a repeatable amplification.

Separately (exchanger.go:194-196): a numeric `float64` token is coerced to a
string via `fmt.Sprintf("%v", v)` and injected as a Bearer token — silently
turning a non-string field into a credential is surprising and can mask
extraction bugs.

**Fix direction:** Bound segment count and JSON nesting depth (or use a vetted
JSONPath lib with limits); reject non-string token values rather than coercing.
Lower the body limit toward a realistic token-response size (e.g. 64 KB).

---

### [SEV: HIGH] [confidence: LIKELY] JWT `exp` is decoded **without signature verification** and used to set cache TTL — attacker-controlled token endpoint can pin a far-future expiry, defeating refresh

**file:** `apps/proxy-plugin/internal/cache/token_cache.go:119-176`
(`DetermineExpiry` / `extractJWTExp`)

`extractJWTExp` base64url-decodes `parts[1]` and reads `exp` with **no signature
check** (by design — the proxy can't verify the upstream's signing key, which is
acceptable). The risk is the *use*: `DetermineExpiry` lets the token's own
(unverified) `exp` dictate how long Mintkey caches and re-injects it. If the
token endpoint is attacker-influenced (see #2) or simply returns a token whose
`exp` is years out, Mintkey caches it for that whole window and will keep
injecting a stale/rotated/revoked credential upstream, never refreshing
(Req 21.2 priority chain makes JWT `exp` win over `expires_in`).

There is also no upper clamp: a malicious/buggy `exp` of e.g. year 9999 is
accepted verbatim (`time.Unix(int64(v), 0)`), so the cache entry effectively
never expires for the process lifetime.

No panic/DoS was found here: `len(parts) != 3` and base64 errors fail closed to
the next priority; an oversized middle segment is bounded by the 1 MB body
limit upstream, and `json.Unmarshal` of a huge segment is the same amplification
as #4 rather than a crash.

**Fix direction:** Clamp the derived expiry to a sane max (e.g.
`min(jwtExp, now+maxTTL)`), and prefer the smaller of JWT `exp` and any
server-asserted `expires_in`. Consider ignoring unverified `exp` entirely and
relying on `expires_in` + a conservative default.

---

### [SEV: MEDIUM] [confidence: CONFIRMED] `base_url` SSRF check only inspects IP literals, not DNS names — instantiation/registration accepts internal hostnames

**file:** `apps/admin-api/src/admin_api/api/services.py:98-115`
(`_is_forbidden_destination`), used at `services.py:367,507,1112`

`_is_forbidden_destination` returns `False` (allowed) for any hostname that is
not a bare IP literal — `ipaddress.ip_address(host)` raises `ValueError` for a
DNS name and the function swallows it ("DNS resolution happens at request time").
So `base_url=https://localhost.internal/...`, `https://metadata.google.internal/`,
or a hostname resolving to RFC1918 passes the check at create/`from-template`
time. Note the *other* SSRF helper in this same file (`_validate_test_url`,
services.py:271) *does* resolve DNS — the inconsistency shows the gap is an
oversight. Lower than the `token_url` findings because `base_url` is only fetched
by the proxy on a real proxied request (and that path may have its own egress
controls), but it is still a tenant-controlled fetch target.

**Fix direction:** Make `_is_forbidden_destination` resolve DNS and check the
resolved addresses (mirror `_validate_test_url`), honoring
`MINTKEY_SSRF_ALLOW_PRIVATE` consistently.

---

### [SEV: MEDIUM] [confidence: CONFIRMED] SSRF allowlist is bypassable via a single env var in shared/prod-ish environments

**file:** `apps/admin-api/src/admin_api/services/credential_service.py:62-64`
and `apps/admin-api/src/admin_api/api/services.py:293`

Both SSRF gates short-circuit to "safe" when `MINTKEY_SSRF_ALLOW_PRIVATE=1`.
That is a reasonable dev affordance, but it is an all-or-nothing global kill
switch for S-SEC-1 with no scoping (per-tenant, per-env). If it is ever set in a
shared environment the entire SSRF allowlist is disabled for every tenant. Worth
calling out given S-SEC-1 is a core security control. (And per finding #1 the
`credential_service.py` copy is unreachable today regardless.)

**Fix direction:** Gate the opt-out behind an explicit non-prod env assertion,
log loudly at startup when enabled, and never honor it when `MINTKEY_ENV=prod`.

---

### [SEV: MEDIUM] [confidence: CONFIRMED] 502 error body returned to the agent is built with `fmt.Fprintf` and a `%s` format — and the exchange error path is the only thing keeping response bodies out

**file:** `apps/proxy-plugin/cmd/proxy-plugin/main.go:477-480`

`fmt.Fprintf(w, `{"error":"%s"}`, errCode)` — `errCode` comes from
`egress.ClassifyError`, which only ever returns fixed strings
(`token_exchange_failed` / `token_endpoint_unreachable` / `token_parse_failed`),
so today there is no injection and no body/credential leak. This is fine *now*
but fragile: it is a `%s`-into-JSON pattern one refactor away from reflecting an
error string (which `exchanger.go` builds with `fmt.Errorf("...HTTP %d", ...)`
and could later include response detail) straight into the agent-visible body —
which would violate Req 22.6/22.7. Flagging as a latent contract risk, not a
live leak.

**Fix direction:** Marshal the error envelope with `json.Marshal` of a fixed
struct rather than `Fprintf` with `%s`; keep the allowed error-code set an
explicit enum.

---

### [SEV: MEDIUM] [confidence: SUSPECTED] Token cache has no eviction / size bound — memory-growth DoS keyed by `(tenant_id, service_id)`

**file:** `apps/proxy-plugin/internal/cache/token_cache.go:48-113`

`TokenCache.entries` is an unbounded `map[cacheKey]*cacheEntry`. Entries are
written on every successful exchange and **never deleted** (no TTL sweep, no max
size; expired entries linger until overwritten). An attacker who can cause
exchanges across many distinct `(tenant_id, service_id)` pairs (or just many
services) grows the map without bound. Per-process memory only (Req 21.5/21.6
memory-only is honored — no persistence, empty on restart), so impact is a slow
OOM rather than data exposure. Marked SUSPECTED on exploitability because the key
space is bounded by registered services, but there is no defensive cap.

**Fix direction:** Add a periodic sweep of expired entries and/or an LRU cap.

---

### [SEV: LOW] [confidence: CONFIRMED] `token_request_headers` are tenant-controlled and applied verbatim, can override `Content-Type`/`Authorization` on the exchange request

**file:** `apps/proxy-plugin/internal/credential/exchanger.go:101-107`

The default `Content-Type: application/json` is set first, then every entry of
`token_request_headers` is applied via `httpReq.Header.Set(name, value)` with no
allowlist — so the operator's stored headers can override `Content-Type`,
add/override `Authorization`, etc. CRLF/header-splitting is *not* exploitable:
Go's net/http rejects header values containing `\r`/`\n` at write time, and
`Header.Set("Host", ...)` does not change the real request Host (that needs
`req.Host`). Impact is limited because these headers go only to the operator's
own configured token endpoint. Noted for completeness (concern 5).

**Fix direction:** Optional — restrict overridable header names, or at least
forbid overriding `Host`/`Authorization` if not intended.

---

### [SEV: LOW] [confidence: CONFIRMED] `extractHost` audit redaction drops the port but design says "host only" — minor; and host can still reveal internal target on a failed/blocked exchange

**file:** `apps/proxy-plugin/internal/egress/oauth2_handler.go:155-168`
and `apps/proxy-plugin/internal/audit/emitter.go:220-226`

`token.exchanged` audit carries `token_url_host = u.Hostname()` (no path, no
query, no creds) — this satisfies Property 11 / Req 22.1 (path redaction is
correct; no credential or token value is emitted; verified across emitter.go and
main.go:457-471). Minor note: if SSRF were ever permitted (e.g. `_ALLOW_PRIVATE`),
the host field would record the internal hostname in audit — acceptable, but
worth knowing it is the one place an internal token-endpoint host name surfaces.
No fix required; documenting that redaction itself is implemented correctly.

---

### [SEV: LOW] [confidence: CONFIRMED] DB migration `017-services-template-id.yaml` — no plaintext-secret column, but note RLS is not re-asserted for the new column

**file:** `apps/admin-api/db/changelog/017-services-template-id.yaml:1-17`

The migration only adds `services.template_id VARCHAR(128) NULL`. No secret, no
PII, no new table — clean. The `services` table's existing RLS policy covers the
row, and `template_id` is non-sensitive seed metadata. No issue with the column
itself. (The real authz gap is at the API layer — finding #3 — not the schema.)

---

## Items checked and found OK (negative results worth recording)

- **`vault.read` scope enforcement (Req 22.5, concern 3):** real and fail-closed.
  `scopeInterceptor` (vault-adapter `grpc.go:62-95`) requires the
  `x-mintkey-service-token`, validates it via `VaultService.ValidateServiceIdentity`
  (`vault.go:425-444`, argon2id + `subtle.ConstantTimeCompare`, dummy-hash on
  unknown identity to resist timing enumeration), and denies on missing scope.
  An empty identity ID (missing header) maps to a non-existent identity →
  PERMISSION_DENIED. Good.
- **Cross-tenant token-cache collision (concern 3):** cache key is a struct
  `{TenantID, ServiceID}` compared by value (token_cache.go:35-38); no path/string
  concatenation, no collision. `main.go:268-272` rejects empty `serviceID`/`tenantID`
  before the OAuth2 path, so the empty-key collision is not reachable.
- **Credential/token leakage into logs/audit/OTel (Property 12, concern 2):**
  the failure log (`oauth2_handler.go:119-135`) logs only ids + host + error
  *class*; the audit event (`main.go:457-471`, `emitter.go:43-57`) carries only
  ids/host/success/latency; OTel span attrs (`emitter.go:160-169`) are ids +
  success bool. `Inject` errors are sanitized via `safeInjectErr`
  (`main.go:704-714`). No credential-struct or token value reaches a sink that I
  could find. This property holds.
- **`expires_in` negative/zero:** guarded by `expiresIn > 0` (token_cache.go:128)
  before use; falls through to the 300s default. OK.
- **`alg:none` / malformed JWT panic:** `extractJWTExp` fails closed on bad
  base64 / non-3-part / non-numeric `exp`; no panic. (TTL-trust concern is #5,
  not a crash.)
