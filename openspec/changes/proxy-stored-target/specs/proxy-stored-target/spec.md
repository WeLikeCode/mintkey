# Proxy stored target

## Purpose

How the egress proxy chooses where a request goes (only the target stored with the credential), how stored targets of
older credentials are filled in, and how every proxied response is cleaned of credential echoes before it reaches the
caller.

## ADDED Requirements

### Requirement: The proxy sends a request only to the target stored with the credential
For every flow that builds an upstream request (the generic injection path of `proxyHandler.ServeHTTP`,
`handleOAuth2ClientCredentials`, `handleHTTPDigest`, `handleOAuth2PasswordGrant` and `handleClassicalKey` in
`apps/proxy-plugin/cmd/proxy-plugin/main.go`) the upstream SHALL be `vault.GetCredentialResponse.TargetURL`, and nothing
else: neither the request header `X-Mintkey-Target` nor `config.Config.DefaultTarget` SHALL influence it, and the header
SHALL NOT reach the upstream. The new function in `apps/proxy-plugin/cmd/proxy-plugin/target.go`

```go
// resolveTarget returns the parsed target, or nil and the text of the 502 answer. The target must parse, use the scheme
// http or https and have a host; a nil credResp or an empty target gives "bad gateway: no target URL stored for this
// credential" and any other failure "bad gateway: invalid target URL".
func resolveTarget(credResp *vault.GetCredentialResponse) (*url.URL, string)
```

SHALL be the one place that decides it, and each flow SHALL answer 502 with that text and contact no upstream when it
returns nil.

#### Scenario: the stored target wins over the header and the default
- **WHEN** a credential with `TargetURL` equal to upstream A's URL is used by each of the five flows while the request
  carries `X-Mintkey-Target: <upstream B URL>` and `cfg.DefaultTarget` is upstream C's URL
- **THEN** upstream A receives exactly one request and B and C receive none, and the request A receives has no
  `X-Mintkey-Target` header

#### Scenario: a credential with no stored target is refused
- **WHEN** a credential whose `TargetURL` is empty is used by each of the five flows, with `X-Mintkey-Target` and
  `cfg.DefaultTarget` both naming a running upstream
- **THEN** each answer is 502 with the body `bad gateway: no target URL stored for this credential`, and no upstream
  receives a request

#### Scenario: a missing credential response has no target
- **WHEN** `resolveTarget(nil)` is called, and a second time with a response whose `TargetURL` is `https://api.example.test/base`
- **THEN** the first returns a nil URL and `bad gateway: no target URL stored for this credential`; the second returns the
  parsed URL and an empty text

#### Scenario: a stored target that is not an http or https URL is refused
- **WHEN** the stored target is `ssh://host:22`, `/relative/path`, `http://` or `://x`
- **THEN** each answer is 502 with the body `bad gateway: invalid target URL` and no request leaves the proxy

### Requirement: Stored targets of existing credentials are filled from the service's base URL
The changelog `apps/admin-api/db/changelog/033-credential-target-backfill.yaml`, included once in
`db.changelog-master.yaml`, SHALL set `vault.credentials.target_url` to the service's `base_url` for every row whose
`target_url` is empty, whose service exists in the same tenant and whose `base_url` starts with `http://` or `https://`
(case-insensitive); it SHALL set `app.platform_admin_view` for the transaction so row-level security does not hide rows,
SHALL change no row with a non-empty `target_url`, and SHALL be safe to run again.

#### Scenario: the changelog fills empty targets only
- **WHEN** the changelog file is parsed as YAML and the master changelog is read
- **THEN** the file holds one SQL change whose text contains `UPDATE vault.credentials`, `SET target_url`, a join on
  `public.services` by `id` and `tenant_id`, the conditions `target_url = ''` and a case-insensitive `^https?://` match
  of `base_url`, and a `set_config` of `app.platform_admin_view`; it has a `tableExists` precondition on
  `vault.credentials` with `onFail: MARK_RAN` and a rollback; and the master has exactly one include whose file name is
  `033-credential-target-backfill.yaml`

### Requirement: Every proxied response is scrubbed before it reaches the caller
Each of the five flows SHALL build its reverse proxy with `func (h *proxyHandler) newUpstreamProxy(target *url.URL, base
http.RoundTripper, injected ...[]byte) *httputil.ReverseProxy` (`apps/proxy-plugin/cmd/proxy-plugin/upstream.go`), whose
`ModifyResponse` calls `scrubber.ScrubWith(resp, h.cfg.ScrubPatterns, injected...)`. `injected` holds the bytes the flow put
on the upstream request: the credential value in the generic and classical-key flows and the exchanged token in the two
OAuth2 flows (the digest flow passes none). `scrubber.ScrubWith(resp *http.Response, patterns bool, secrets ...[]byte)
ScrubResult` SHALL replace every occurrence, in the scanned body and in every header value, of each secret of at least 8
bytes in its raw, standard-base64 and URL-query-escaped forms with `[REDACTED]`, for every service. Only when `patterns` is
true SHALL it also apply the pattern rules of `Scrub`: removal of the response headers `Authorization`, `Cookie`,
`Set-Cookie`, `X-Auth-Token` and `X-Api-Key`, and replacement in the body of JWT-shaped strings, `api_key=<value>` and
`sk_`/`pk_` tokens, with the markers `Scrub` already writes: `[REDACTED_JWT]` for a JWT, `api_key=[REDACTED]` (the name and
separator are kept) and `[REDACTED]` for an `sk_`/`pk_` token. Only the matching text of a header value or a body is
replaced, and each value of a header with several values is scrubbed on its own. `Scrub(resp)` SHALL equal
`ScrubWith(resp, true)`. `ScrubResult` SHALL gain `Err error`, the error of reading the scanned part of the body. `config.Config` SHALL gain `ScrubPatterns bool`
(`apps/proxy-plugin/internal/config/config.go`), set by `Load` from `MINTKEY_PROXY_SCRUB_PATTERNS` through
`strconv.ParseBool`, false when the variable is unset, empty or not a boolean. A detected echo SHALL be logged with the
service id and the locations (`header:<Name>` or `body`), never with a value. An upstream failure (a failed round trip) SHALL answer 502 with the
body `bad gateway: upstream unreachable`; a response whose scanned part cannot be read (`ScrubResult.Err` set, for example
a gzip body that does not decode) SHALL answer 502 with the body `bad gateway: upstream response unreadable`.

#### Scenario: a credential echoed by the upstream does not reach the caller
- **WHEN** the generic flow (bearer value `opaque-token-0123456789`) and the classical-key flow call an upstream that
  answers 200 with the JSON body `{"echo":"Bearer opaque-token-0123456789","other":"fine"}`, the header
  `X-Echo: opaque-token-0123456789` and the header `Set-Cookie: sid=abc12345`, with `ScrubPatterns` false (the default)
  and again true
- **THEN** in both runs the caller's body is `{"echo":"Bearer [REDACTED]","other":"fine"}`, the `X-Echo` value is
  `[REDACTED]`, the status is 200, and neither the body nor the headers contain the token; the `Set-Cookie` header is
  present with its value in the first run and absent in the second

#### Scenario: the pattern rules apply only when the setting is on
- **WHEN** the generic flow calls an upstream that answers 200 with the header `Set-Cookie: sid=abc12345` and the body
  `{"jwt":"eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl","key":"sk_live_abcdefghijkl","q":"api_key=abcdefgh12345678"}`
  (a real three-part base64url JWT shape; the body echoes no injected value), once with `ScrubPatterns` false and once true
- **THEN** the first caller receives the same body byte for byte and the `Set-Cookie` header unchanged; the second receives no
  `Set-Cookie` header and the body `{"jwt":"[REDACTED_JWT]","key":"[REDACTED]","q":"api_key=[REDACTED]"}`

#### Scenario: a secret inside a longer value and in a multi-value header
- **WHEN** the generic flow (bearer value `opaque-token-0123456789`) calls an upstream that answers with the header
  `X-Echo: Bearer opaque-token-0123456789` and two `X-Multi` values, `first=opaque-token-0123456789` and `second=clean`
- **THEN** the caller's `X-Echo` is `Bearer [REDACTED]`, its `X-Multi` values are `first=[REDACTED]` and `second=clean`
  in that order

#### Scenario: the setting is read from the environment
- **WHEN** `config.Load()` runs with `MINTKEY_PROXY_SCRUB_PATTERNS` unset, `""`, `true`, `TRUE`, `1`, `false`, `0`, `yes`
  and `banana`
- **THEN** `ScrubPatterns` is false, false, true, true, true, false, false, false and false

#### Scenario: the exchanged token of the OAuth2 flows is redacted too
- **WHEN** `handleOAuth2ClientCredentials` and `handleOAuth2PasswordGrant` exchange the token `exchanged-token-ABCDEF123`
  and the upstream echoes it in its body
- **THEN** the caller's body contains `[REDACTED]` and not `exchanged-token-ABCDEF123`

#### Scenario: a clean response passes through unchanged
- **WHEN** the upstream answers 404 with a header `X-Request-Id: r-1` and a JSON body that contains no secret and no
  pattern the scrubber matches, in each of the five flows
- **THEN** the caller receives status 404, that header, the same body bytes, and the `Content-Length` of the upstream

#### Scenario: a body that fails to decode is refused
- **WHEN** an upstream answers 200 with `Content-Encoding: gzip` (set only when it was offered gzip) and the body bytes
  `not gzip at all`
- **THEN** the answer is 502 with the body `bad gateway: upstream response unreadable`, not `upstream unreachable`

#### Scenario: an unreachable upstream answers 502 with a text
- **WHEN** the stored target is a closed local port
- **THEN** the answer is 502 with the body `bad gateway: upstream unreachable`

### Requirement: The scrub keeps the whole body and a consistent length
`scrubber.Scrub` and `ScrubWith` SHALL scan the first 256 KiB of a body and SHALL pass the bytes after it on unchanged.
They SHALL leave the `Content-Length` header and `resp.ContentLength` as they were when the scanned part is unchanged,
and SHALL remove the header and set `resp.ContentLength` to -1 when it changed.

#### Scenario: Scrub keeps the tail of a large body and the length stays consistent
- **WHEN** `scrubber.Scrub` runs on a response with `Content-Length: 307200` whose body is 307200 bytes of spaces with the
  text `api_key=abcdefgh12345678` followed by a newline at byte 100 and the text `sk_live_abcdefghijkl` followed by a
  newline at byte 296960 (290 KiB, past the scan bound); and on a second response of 307200 spaces
- **THEN** the first body reads to its end with 307194 bytes, holds `api_key=[REDACTED]`, still holds
  `sk_live_abcdefghijkl` at its place after the shortened part, and the response has no `Content-Length` header and
  `ContentLength` -1; the second body is returned byte for byte with `Content-Length` 307200 and `ContentLength` 307200

### Requirement: Bodies the proxy cannot scan are streamed or refused explicitly
The transport of `newUpstreamProxy` SHALL remove the caller's `Accept-Encoding` before the upstream call (the Go transport
then asks for gzip itself and decodes it). A response that still carries a `Content-Encoding` other than `identity`
(and is not a bodiless answer: HEAD, 204, 304) SHALL be refused with 502 and the body `bad gateway: encoded response not
supported`: `ModifyResponse` returns an unexported `errEncodedResponse` and `ErrorHandler` answers with that text when
`errors.Is(err, errEncodedResponse)`, and with `upstream unreachable` for any other error that is not `errBodyUnreadable`. A response whose `Content-Type` is `text/event-stream` SHALL have its headers scrubbed and its body streamed
without buffering.

#### Scenario: encoded bodies are decoded or refused
- **WHEN** the caller sends `Accept-Encoding: br`, an upstream that records the header answers gzip when it is offered
  gzip and echoes the token in the compressed body; and another upstream answers `Content-Encoding: br` whatever it is
  offered
- **THEN** the first upstream saw `Accept-Encoding: gzip` only, and the caller's body is the plain text with
  `[REDACTED]`; the second answer is 502 with the body `bad gateway: encoded response not supported`

#### Scenario: an event stream is not buffered
- **WHEN** an upstream answers `Content-Type: text/event-stream`, writes one event, flushes, and waits until the test
  releases it; the caller reads through a running instance of the handler (generic flow)
- **THEN** the caller reads the first event within 5 seconds, before the upstream finishes
