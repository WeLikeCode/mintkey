# Design: proxy-stored-target

## Context

`proxyHandler.ServeHTTP` (`apps/proxy-plugin/cmd/proxy-plugin/main.go`) verifies the token, runs its gates, fetches the
credential with `vaultClient.GetCredential`, and then dispatches on `credResp.AuthScheme`: OAuth2 password grant
(`handleOAuth2PasswordGrant`), OAuth2 client credentials with an exchange-shaped payload (`handleOAuth2ClientCredentials`),
HTTP digest (`handleHTTPDigest`), and the generic injector in `ServeHTTP` itself. Classical service API keys take a
fifth path (`handleClassicalKey`). Each of the five has one block that chooses the upstream, parses it, builds
`httputil.NewSingleHostReverseProxy`, sets a Director that joins the path, removes the routing headers and injects the
credential, and calls `proxy.ServeHTTP`; `resolveTarget` replaces the choosing part and `newUpstreamProxy` the building
part. Four of the flows count `IncProxyDenied(serviceID, "backend_error")` on a refusal; the classical-key flow does not and
keeps that. `scrubber.Scrub` (`internal/scrubber/response.go`) is exercised by its own tests and is not yet part of any
flow.

`vault.credentials.target_url` is written by `PutCredential` (admin-api passes the service's `base_url`: `create_credential`
and `rotate_credential` in `apps/admin-api/src/admin_api/api/credentials.py`) and returned by `GetCredential` as `TargetUrl`;
`update_service` copies a changed `base_url` into `target_address` for SSH schemes only. The vault adapter has three
stores (PostgreSQL, SQLite, HashiCorp); the migration touches the PostgreSQL one.

The scrubber (`Scrub`) removes the response headers `Authorization`, `Cookie`, `Set-Cookie`, `X-Auth-Token` and
`X-Api-Key`, reads at most 256 KiB of the body, replaces JWT-shaped strings with `[REDACTED_JWT]`, `api_key=<value>` with `api_key=[REDACTED]` and `sk_`/`pk_` tokens with
`[REDACTED]` (the markers of `response.go`, kept as they are), and sets `resp.Body` to the scanned copy. Applied to live traffic it must also keep the bytes past 256 KiB
and the length headers right; both are specified here. These pattern rules and header removals apply to proxied traffic
only when `MINTKEY_PROXY_SCRUB_PATTERNS` is true (D8); the redaction of the injected credential applies always.

## Interfaces

```go
// target.go
func resolveTarget(credResp *vault.GetCredentialResponse) (*url.URL, string) // see the spec

// upstream.go
// newUpstreamProxy returns the reverse proxy of one request. base is the transport that carries the request (nil: the
// default transport). The returned proxy's Transport removes the caller's Accept-Encoding header and calls base;
// ModifyResponse refuses an encoded body, leaves an event stream unbuffered, and otherwise calls scrubber.ScrubWith(resp,
// h.cfg.ScrubPatterns, injected...) and logs a detected echo; ErrorHandler answers 502 with the texts of the spec. The flow sets its own
// Director after the call, as it does today.
//
// Two unexported errors tell the causes apart. ModifyResponse returns errEncodedResponse (an encoded body) or
// errBodyUnreadable (ScrubWith.Err set: the scanned part of the body could not be read, for example a gzip body that does
// not decode), after closing resp.Body. httputil.ReverseProxy passes any error of ModifyResponse to ErrorHandler, which
// checks errors.Is(err, errEncodedResponse), then errors.Is(err, errBodyUnreadable), and answers every other error
// (a failed round trip) with "upstream unreachable".
func (h *proxyHandler) newUpstreamProxy(target *url.URL, base http.RoundTripper, injected ...[]byte) *httputil.ReverseProxy

// scrubber/response.go
// patterns false: only the exact-value redaction of secrets; patterns true: also the header removals and body patterns of Scrub.
// ScrubResult gains Err error: the error of reading the scanned part of the body (nil otherwise); the body is then the
// bytes read so far and the caller must not forward it.
func ScrubWith(resp *http.Response, patterns bool, secrets ...[]byte) ScrubResult
func Scrub(resp *http.Response) ScrubResult // = ScrubWith(resp, true)
func ScrubHeaders(resp *http.Response, patterns bool, secrets ...[]byte) ScrubResult // header part only; ModifyResponse uses it for an event stream

// config/config.go
// Config.ScrubPatterns bool, from MINTKEY_PROXY_SCRUB_PATTERNS (strconv.ParseBool; unset, empty or unparsable: false)
```

`injected` per flow: generic and classical-key flows pass `credResp.Plaintext`; the client-credentials and password-grant
flows pass `[]byte(oauthResult.Token)` (the exchanged token, not the client secret, which is never sent upstream); the
digest flow passes nothing (it sends a hash, so only the pattern rules, when on, apply to its responses). Later
changes of the plan rely on `newUpstreamProxy` and on its `base` parameter (`proxy-public-egress` passes a guarded
transport as `base`, and in the digest flow as the inner transport of the digest transport) and on `resolveTarget`.

## Decisions

**D1. One source for the target.** `credResp.TargetURL` only. The header is no longer read; it is still deleted in each
Director so a caller's header never reaches an upstream. `DefaultTarget` and the `DEFAULT_TARGET` environment variable
stay in `config.Config` (compose and the Helm chart set it); only their comments change, so no deployment file is edited.

**D2. Typed 502 texts.** 502 already means a vault error, a missing target and an unreachable upstream. The new texts
(`no target URL stored for this credential`, `invalid target URL`, `upstream unreachable`, `encoded response not
supported`, `upstream response unreadable`) let a test and an operator tell them apart. The existing `bad gateway: vault error` is unchanged.

**D3. The backfill takes http(s) base URLs only and is a plain UPDATE.** An SSH service's `base_url` (`ssh://...`) is the
SSH proxy's concern and stays out of an HTTP target. `set_config('app.platform_admin_view', 'on', true)` makes the
statement independent of whether the migration role owns the table (the table has row-level security). Running again
changes nothing, because the filled rows are no longer empty. The rollback is a no-op: the filled value is the service's
own base URL.

**D4. Exact-value redaction next to the patterns.** The patterns (when on, D8) find credentials of a recognisable shape; an
opaque bearer value or a basic-auth password has none, and upstreams that echo request headers (debugging endpoints) return it as is. The
proxy knows the value it injected, so it removes that value; inside a header value or a body only the matching text is
replaced (`Bearer <token>` becomes `Bearer [REDACTED]`), and each value of a header with several values is scrubbed on its
own. Secrets shorter than 8 bytes are not matched, because they
would also match unrelated text; the three forms (raw, standard base64 for `Authorization: Basic ...`, query-escaped for
the query-parameter scheme) are the ones the injector writes.

**D5. Bodies the proxy can read.** The caller's `Accept-Encoding` is replaced by the Go transport's own `gzip`, which it
decodes before the scrub (the decoded response loses its `Content-Encoding` and `Content-Length`). An upstream that
encodes anyway (for example `br`) cannot be scanned, so the response is refused with 502 instead of forwarded. HEAD, 204
and 304 answers have no body and are not refused. An event stream (`Content-Type: text/event-stream`) is the exception to
buffering: waiting for 256 KiB or the end of the stream would hold the first event back, so only its headers are scrubbed
(`ScrubHeaders`), and a secret echoed in an event body is not redacted (a follow-up).

**D6. The scan bound stays 256 KiB** (ADR-0014.4). The bytes past it reach the caller unchanged; a secret that straddles
or lies beyond the bound is not matched.

**D7. No audit event yet.** The scrubber's `AuditEventCredentialEchoDetected` constant names `proxy.credential_echo_detected`.
Emitting it needs the type in `_ALLOWED_EVENT_TYPES` of `apps/admin-api/src/admin_api/api/internal.py` and a definition in
`docs/architecture/contracts/events/audit-event.schema.json`; this change logs the detection (service id and locations,
never a value) and leaves the event to a follow-up.

**D8. The pattern rules are off by default.** The exact value of the credential the proxy injected is redacted for every
service, because it is a value the proxy knows. The pattern rules (the `Set-Cookie`, `Cookie`, `Authorization`,
`X-Auth-Token` and `X-Api-Key` header removals, JWT-shaped strings, `api_key=` values and `sk_`/`pk_` strings) guess from
shape, and an existing operator service may return such a string on purpose (a session cookie, a token of its own, a
test key). They are therefore applied only when the proxy runs with `MINTKEY_PROXY_SCRUB_PATTERNS=true`
(`config.Config.ScrubPatterns`, default false), read once at start; `Scrub` keeps its behaviour for callers that name it.

## Risks and edge cases

- With the pattern rules on (D8), an upstream that returns a JWT, a `Set-Cookie` or an `sk_` string to its caller on
  purpose gets `[REDACTED_JWT]`, `[REDACTED]` or no header, as ADR-0014.4 describes; with the default, only the injected value is removed.
- Credentials of the SQLite or HashiCorp stores with an empty target (created before the target was recorded) answer 502
  after this change; the PostgreSQL store is the one the compose and Helm deployments use.
- Tests that call the flows directly pass a `GetCredentialResponse` with `TargetURL` set (`proxy_test.go`,
  `data_plane_paths_test.go`, `oauth2_client_credentials_dispatch_test.go`); they are unaffected.

- A body that fails while being read after the scanned 256 KiB (a truncated tail) is not refused: the status line is
  already sent, so `httputil.ReverseProxy` aborts the copy as it does for any proxied response. A body that fails inside the scanned
  256 KiB (a gzip body that does not decode) is refused with `upstream response unreadable`.
- The migration number 033 is a file name; Liquibase runs the includes in the master's order, and the change set reads only
  tables that exist at the base, so another unit taking 033 or running before or after it changes nothing.

## Follow-ups

- Emit `proxy.credential_echo_detected` (D7).
- Scrub event streams chunk by chunk.
