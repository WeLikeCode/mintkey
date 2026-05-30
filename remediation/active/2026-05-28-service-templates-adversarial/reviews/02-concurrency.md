# Review 02 — Concurrency & Correctness Adversary

- **Scope:** `feature/service-templates` @ `828bd7c`; OAuth2 Password Grant egress flow.
- **Lens:** data races, TOCTOU / thundering herd, the 30s-refresh + graceful-degradation state machine, `DetermineExpiry` priority chain, context/timeout/leak issues, error-path correctness.
- **Mode:** Serena MCP available; symbol nav done with grep + Read (Serena not strictly needed for this surface — every cache caller was enumerable). `go test -race` **was run** (go1.26.2) — output inline below.
- Files: `apps/proxy-plugin/internal/cache/token_cache.go`, `internal/credential/exchanger.go`, `internal/egress/oauth2_handler.go`, `cmd/proxy-plugin/main.go`, `internal/vault/client.go`, `apps/vault-adapter/internal/server/grpc.go`.

## `go test -race` output

```
$ (apps/proxy-plugin)  go test -race ./internal/cache/... ./internal/egress/... ./internal/credential/...
ok   github.com/mintkey/mintkey/services/proxy-plugin/internal/cache       1.185s
ok   github.com/mintkey/mintkey/services/proxy-plugin/internal/egress      1.498s
ok   github.com/mintkey/mintkey/services/proxy-plugin/internal/credential  1.300s

$ (apps/vault-adapter)  go test -race ./internal/server/...
ok   github.com/mintkey/mintkey/services/vault-adapter/internal/server     2.300s
```

No `DATA RACE` reports. The cache's own mutex discipline is clean (see CACHE-OK). The serious findings are at the **orchestration / cross-service integration / expiry-math** layers, which the existing tests do not exercise concurrently or with adversarial inputs.

---

# CONFIRMED

## [CRITICAL] [high] scopeInterceptor breaks ALL proxy egress — production vault client sends no usable service token

**`apps/vault-adapter/internal/server/grpc.go:62-95`, `:222-224`** (interceptor + wiring, both NEW in this branch) vs **`apps/proxy-plugin/cmd/proxy-plugin/main.go:79`** and **`apps/proxy-plugin/internal/vault/client.go:94`** (both PRE-EXISTING, unchanged in branch).

**Bug.** This branch adds `grpc.UnaryInterceptor(scopeInterceptor(svc))` to `ListenAndServe` and registers `GetCredential → vault.read` in `methodScopes`. The interceptor rejects the call unless `x-mintkey-service-token` metadata is present, non-empty, validates against a registered identity, and carries `vault.read`. But the production proxy plugin:
- constructs its vault client with an **empty** token: `vault.NewClient(cfg.VaultAddrGRPC, "")` (`main.go:79`) — note `cfg.ProxyServiceToken` is loaded and passed to the audit queue and classical-key handler, but NOT to the vault client; and
- `client.go:94` attaches only `metadata.Pairs("x-mintkey-service-token", c.serviceToken)` (so the value is `""`) and **never sends `x-mintkey-service-identity`**, so `extractIdentityID` returns `""`.

Interceptor path: `tokens := md.Get(...)` → `tokens[0] == ""` → returns `PERMISSION_DENIED "missing service token"` (`grpc.go:80-82`). Even if the token were non-empty, `ValidateServiceIdentity(ctx, "", token)` looks up `identities[""]`, which is unregistered → `false` → `PERMISSION_DENIED "invalid service token"`.

**Trigger (no concurrency needed).** Any real egress request → `main.go` `ServeHTTP` → `h.vaultClient.GetCredential` (`main.go:314`) → interceptor returns `PERMISSION_DENIED` → `main.go:319-325` logs "vault error" and returns **HTTP 502** to the agent. This breaks every auth scheme, not just oauth2_password_grant.

**Why tests miss it.** The OAuth2 round-trip gRPC tests use `newTestGRPCServer` (`grpc_test.go:29-66`) which registers the server with a bare `grpc.NewServer()` — **no interceptor**. The scope tests use a *separate* harness `newTestGRPCServerWithAuth` and hand-build metadata with both headers (`grpc_test.go:498-501`) that the real client never produces. So unit tests are green while the integrated service is broken. There is no test that drives `proxy-plugin/internal/vault.Client` against an interceptor-enabled server.

**Fix.** Pass `cfg.ProxyServiceToken` into `vault.NewClient` and have `client.go` attach `x-mintkey-service-identity` (the proxy's identity id, e.g. `svcid_proxy`) alongside the token; register that identity with `vault.read` scope at vault-adapter boot. Add an integration test wiring the real `vault.Client` through an interceptor-enabled server.

---

## [HIGH] [high] `DetermineExpiry` integer overflow on large `expires_in` → cache poisoned with past expiry → exchange storm

**`apps/proxy-plugin/internal/cache/token_cache.go:128-129`** (also `extractExpiresInFromBody:195-206`, and `exchanger.go:204-225`).

```go
if expiresIn, ok := extractExpiresInFromBody(responseBody); ok && expiresIn > 0 {
    return now.Add(time.Duration(expiresIn) * time.Second)
}
```

**Bug.** `time.Duration` is `int64` nanoseconds. `time.Duration(expiresIn) * time.Second` overflows for `expires_in` ≳ `9.22e9` seconds (~292 years). Verified empirically:
- `expires_in = 9_300_000_000` → duration `-2540762h…` (**negative**) → `expiresAt = now.Add(negative)` is **in the past**.
- `expires_in = 99_999_999_999_999` → silently wraps to a wrong, much smaller positive (~6.3 years), i.e. silent corruption.

The `expiresIn > 0` guard does not help — the overflow happens in the multiply *after* the guard.

**Trigger / impact.** A token endpoint (misconfigured, compromised, or hostile — `token_url` is operator-supplied per Req 19/22) returns `{"expires_in": 9300000000, "access_token": "..."}`. `Put` caches the token with a past `ExpiresAt`. Immediately:
- `Get` (`token_cache.go:73`): `time.Until(past) <= 30s` → true → cache miss → **every** subsequent request re-exchanges. Self-inflicted thundering herd against the token endpoint (cost + rate-limit/DoS).
- `GetForDegradation` (`token_cache.go:96`): `time.Now().After(past)` → true → returns false → graceful degradation (Req 21.7) is **defeated**; the first refresh failure goes straight to 502.

**Fix.** Clamp `expiresIn` to a sane ceiling (e.g. `min(expiresIn, 86400*365)`) before the multiply, or compute with overflow check. Same overflow exists for the JWT `exp` path indirectly via `time.Unix(int64(v), 0)` but that is bounded by float64 of a real timestamp; the `expires_in` path is the exploitable one.

---

## [HIGH] [medium] JWT `exp` in the past is cached verbatim → never usable, no degradation, refresh storm

**`apps/proxy-plugin/internal/cache/token_cache.go:139-176`** (`extractJWTExp`) consumed by `DetermineExpiry:123-125` and stored by `oauth2_handler.go:146-147`.

**Bug.** `extractJWTExp` returns the raw `exp` with **no check that it is in the future**. `DetermineExpiry` takes JWT `exp` as top priority unconditionally. If a token endpoint returns a JWT whose `exp` is already past (clock skew, a backend bug, or a server that hands out short-lived tokens with `exp` < `now + 30s`), the handler caches it with that past/near expiry.

**Interleaving / scenario.** Exchange succeeds, token is a valid JWT with `exp = now + 10s` (legitimately short-lived, or skewed). `Put` stores it. Next request: `Get` sees `time.Until(exp) <= 30s` → miss → re-exchange. This repeats on **every** request for that (tenant,service): the 30s buffer can never be satisfied by a token whose true lifetime is ≤30s, so the cache provides zero benefit and the proxy hammers the token endpoint. If `exp` is already in the past, `GetForDegradation` also returns false, so the degradation path is dead too.

This is the precise opposite failure mode of OVERFLOW above but reached through the JWT branch; both stem from "trust the upstream's expiry number without sanity bounds."

**Fix.** After extracting `exp` (JWT) or computing `now+expires_in`, if the resulting expiry is `<= now` (or `<= now + RefreshBuffer`), fall through to / floor at the default. At minimum, log+metric a warning when a freshly exchanged token is already within the refresh buffer to surface the storm.

---

## [HIGH] [high] No singleflight / per-key locking → thundering herd of concurrent token exchanges (TOCTOU)

**`apps/proxy-plugin/internal/egress/oauth2_handler.go:92-147`**; cache has only `sync.RWMutex` around individual ops (`token_cache.go`).

**Bug.** The check-then-act sequence "`Cache.Get` miss → `Exchanger.Exchange` → `Cache.Put`" is **not** guarded by any per-key in-flight lock or `golang.org/x/sync/singleflight`. The cache mutex only serializes each `Get`/`Put`; it is released between them.

**Interleaving.** Cold cache (process restart → Req 21.6 guarantees empty) or a key that just crossed the 30s buffer. N concurrent agent requests for the same (tenant, service) all call `Get` (all miss), all fire `Exchange` to the same `token_url` concurrently, all `Put`. Consequences:
- **Cost / rate-limit / DoS:** N simultaneous POSTs to the upstream credential endpoint per cold key; on a burst this can trip the upstream's lockout or rate limiter and lock out the *real* credential.
- **Security-adjacent:** amplifies credential use; an attacker who can induce a burst (or a restart) gets a built-in fan-out multiplier on the protected credential.
- Last-writer-wins on `Put` is benign for correctness but wasteful.

The design (design.md §TokenCache / Egress Handler) does **not** specify singleflight, so this is a design gap rather than a spec violation — but it is a real correctness/cost/security concern and worth flagging to the spec owner.

**Fix.** Add `singleflight.Group` keyed by `(tenant_id, service_id)` around the miss→exchange→put critical section, or a per-key `sync.Mutex` map. Collapses N concurrent refreshes into one upstream call.

---

## [MEDIUM] [high] TokenExchanger HTTP client has no per-phase timeouts; slow `token_url` can be held open up to the full 10s, with no header timeout

**`apps/proxy-plugin/internal/credential/exchanger.go:66-72`, `110-129`.**

**Bug.** The client is `&http.Client{Timeout: 10 * time.Second}` only. `Client.Timeout` is a *whole-request* deadline (it does cover the body read at `:121`, so there is no body-read leak — good). But there is **no** `Transport.ResponseHeaderTimeout`, `DialContext` timeout, `TLSHandshakeTimeout`, or `ExpectContinueTimeout`, and the default `Transport` is shared/`nil` → uses `http.DefaultTransport` characteristics. A hostile/slow `token_url` (operator- or template-supplied) can:
- trickle response headers for nearly the full 10s, occupying a goroutine + connection per request — combined with the missing singleflight (above) this is a connection-exhaustion amplifier;
- the request context IS propagated (`http.NewRequestWithContext(ctx, …)` at `:96`, ctx flows from `r.Context()` via `oauth2_handler.go:108` ← `main.go:453`), so client cancellation works — but there is no *response-header* timeout shorter than 10s to fail fast on a stalling server.

**Trigger.** `token_url` host returns a 200 status line then dribbles headers; each egress request burns ~10s and a connection. Under load (no singleflight) this saturates.

**Fix.** Configure an explicit `http.Transport` with `ResponseHeaderTimeout` (e.g. 5s), `TLSHandshakeTimeout`, and a `DialContext` deadline; keep the 10s overall `Timeout` (Req 20.7) as the outer bound.

---

## [LOW] [high] Unbounded cache growth — no eviction of expired/stale entries (memory leak under high key cardinality)

**`apps/proxy-plugin/internal/cache/token_cache.go:48-58, 104-113`.**

**Bug.** `entries map[cacheKey]*cacheEntry` only ever grows. `Get`/`GetForDegradation` treat expired entries as misses but never delete them; `Put` overwrites a key but nothing reaps keys that are never requested again. Every distinct `(tenant_id, service_id)` ever seen lives forever. For a broker with many tenants/services and churn, this is an unbounded in-process memory leak (and an ever-growing secret-bearing map — minor blast-radius concern for Req 21.5/22.4's "short-lived memory" intent, since fully-expired tokens linger indefinitely).

**Fix.** Lazy-delete on expired read, and/or a background janitor (or a bounded LRU) that evicts entries past `ExpiresAt`. Tie a metric to cache size.

---

# SUSPECTED

## [LOW] [medium] `expires_in` from body is `int64(float64)` truncation; JSON numbers decode as float64 with no `UseNumber()`

**`token_cache.go:197` and `exchanger.go:215`.** Both `switch` on `float64` first; the `json.Number` arm is dead because neither decoder calls `UseNumber()`. Harmless for realistic `expires_in`/`exp` (< 2^53 exactly representable), but a fractional `expires_in` (e.g. `599.9`) truncates to 599. Not a correctness bug for spec-conformant inputs; noting for completeness. No fix required unless you want to honor `json.Number`.

## [INFO] [high] Two redundant host-extraction helpers with divergent behavior on ports

`egress.extractHost` (`oauth2_handler.go:155`) uses `u.Hostname()` (strips port) and returns `"unknown"` on failure; `audit.ExtractHost` (`emitter.go:220`) also uses `u.Hostname()` but returns `""` on failure. The handler uses its own `extractHost` and main.go builds the audit payload from `oauthResult.TokenURLHost`, so `audit.ExtractHost` is dead on this path. Not a bug; flag for dedup to avoid future drift on the Req 22.1 host-only redaction guarantee.

## [INFO] State-machine trace (Req 21.7 / Property 10) — otherwise CORRECT

Branch-by-branch, ignoring the expiry-math bugs above, the degradation FSM in `oauth2_handler.go:92-149` is correct:
- cache hit (>30s): return cached, no exchange ✓
- miss/near-expiry → exchange OK: `Put` + return fresh ✓
- exchange fails + `GetForDegradation` (not fully expired): return cached, `err=nil`, `ExchangeSuccess=false` ✓ (502 NOT returned — Req 21.7 ✓)
- exchange fails + fully expired/absent: return `err` → `main.go:473-481` maps to 502 ✓
The 30s boundary uses `<= RefreshBuffer` (Get) and `time.Now().After(ExpiresAt)` (degradation), consistent with Property 9's "more than 30s" and Property 10's "absolute expiry has not yet passed." No sign/UTC/ms errors in the comparisons themselves (`time.Time`/`time.Duration` are TZ-agnostic). The defect is upstream: the `ExpiresAt` value fed into this FSM can be poisoned (OVERFLOW / past-JWT-exp findings), which silently disables the otherwise-correct degradation logic.

## CACHE-OK — mutex discipline is clean

Every read (`Get`, `GetForDegradation`) is under `RLock`; every write (`Put`) under `Lock`; no map access outside the lock; no read-modify-write under `RLock` (`Put` replaces the `*cacheEntry` rather than mutating in place, so readers holding an old pointer are safe). `go test -race` confirms (output above). The TOCTOU finding is at the *handler* layer (cross-call), not the cache's internal locking.

---

## Severity summary

| Sev | Count | Items |
|---|---|---|
| CRITICAL | 1 | scopeInterceptor vs empty vault-client token → all egress 502 |
| HIGH | 3 | `expires_in` overflow; JWT past-`exp`; no singleflight (thundering herd) |
| MEDIUM | 1 | no response-header timeout on exchanger |
| LOW | 2 | unbounded cache growth; float64 truncation |
| INFO | 3 | dead `ExtractHost`; FSM-correct note; cache mutex clean |
