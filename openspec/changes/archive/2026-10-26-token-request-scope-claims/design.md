# Design: token-request-scope-claims

## Context

- Broker: `issue.Handler.ServeHTTP` (`apps/broker/internal/api/issue/issue.go`) checks `X-Mintkey-Service-Token`,
  decodes `issueRequest{agent_id, service_id, tenant_id, scope, service_kind, ttl_seconds}` (unknown JSON fields are
  ignored), validates `ttl_seconds`, and calls `issuer.Issue(issuer.TokenRequest{...})`, which adds the optional claim
  `service_kind` only when it is set. Errors use `writeErr(w, status, code, title)` → `{"mintkey:code", "title"}`.
- Proxy: after this unit's predecessor `proxy-revocation-enforced`, `ServeHTTP` reads the claims, refuses a token
  without `aud`/`tnt`, then runs the revocation gate, the `read:atlas` gate, the audience check, the budget check and
  `GetCredential`. Each of the four JWT directors (generic, client credentials, digest, password grant) removes a
  leading `"/"+serviceID` with an inline `strings.TrimPrefix` block; the classical-key director has its own copy.
- MCP: `request_token` (`apps/mcp-server/src/mcp_server/tools/request_token.py`) checks the grant, then reads the
  service's `auth_scheme` (`is_ssh`), then POSTs to the broker with `{agent_id, service_id, tenant_id, scope,
  ttl_seconds}` and answers any non-200 with 502 `mintkey:broker_error`. The email path
  (`_handle_email_service_token`) is reached when no HTTP grant matches and the id is an email service. The JSON-RPC
  tool `mintkey_request_token` (`jsonrpc.py`: `TOOLS` and `_dispatch_tool`) forwards only `service_id` and `action`.

## Interfaces

Broker, `issue.go`:

```go
type issueRequest struct {
	// ... existing fields ...
	Methods    []string `json:"methods"`     // nil when absent or null
	PathPrefix string   `json:"path_prefix"` // "" when absent
}

// scopeClaims checks the optional limits of an issue request. It returns the methods to sign (uppercased, in
// request order) and "", or nil and the 400 title.
func scopeClaims(methods []string, pathPrefix, serviceKind string) ([]string, string)
```

Checks, in this order, each answering the title shown:
1. `methods != nil || pathPrefix != ""` and `serviceKind != ""` → `methods and path_prefix apply to HTTP services only`.
2. `methods != nil` and (`len(methods) == 0`, `len(methods) > 7`, or two entries equal after `strings.ToUpper`) →
   `methods must list 1 to 7 distinct HTTP methods`; an entry whose upper case is not one of `GET HEAD POST PUT PATCH
   DELETE OPTIONS` → `methods may contain only GET, HEAD, POST, PUT, PATCH, DELETE and OPTIONS`.
3. `pathPrefix != ""` and (it does not start with `/`, is longer than 512 bytes, contains `?`, `#`, `%`, `\`, `//`,
   a byte at or below 0x20 or 0x7f, or a segment `.` or `..`) → `path_prefix must be an absolute path without query,
   fragment, percent-encoding, empty or dot segments`.

`ServeHTTP` calls it after the `ttl_seconds` check and answers a problem with `writeErr(w, 400, "validation_failed",
title)`. `issuer.TokenRequest` gains `Methods []string` and `PathPrefix string`; `Issue` sets `claims["methods"] =
req.Methods` when `len(req.Methods) > 0` and `claims["path_prefix"] = req.PathPrefix` when it is not empty.

Proxy, new file `cmd/proxy-plugin/routing.go`:

```go
// upstreamPath returns the path the upstream receives for reqPath: a leading "/"+serviceID is removed and the
// result starts with "/" (exactly the directors' rule before this change).
func upstreamPath(reqPath, serviceID string) string {
	stripped := strings.TrimPrefix(reqPath, "/"+serviceID)
	if stripped == reqPath {
		return reqPath
	}
	if stripped == "" || stripped[0] != '/' {
		stripped = "/" + stripped
	}
	return stripped
}
```

In the four JWT directors the inline block becomes `req.URL.Path = upstreamPath(req.URL.Path, serviceID)`. The
classical-key director is not changed.

New file `cmd/proxy-plugin/scope_claims.go`:

```go
const (
	refusalMethod = "method not permitted"
	refusalPath   = "path not permitted"
)

// checkScopeClaims returns "" when method and path are within the token's optional methods and path_prefix
// claims, else refusalMethod or refusalPath.
func checkScopeClaims(claims map[string]any, method, path string) string
```

- `methods` present (key exists): it must be a non-empty `[]any` of strings and contain `method` exactly
  (case-sensitive), else `refusalMethod`.
- `path_prefix` present: it must be a string starting with `/`, else `refusalPath`. `path` is refused when one of its
  `/`-separated segments is `.` or `..`, or when it is neither equal to the prefix nor starts with
  `strings.TrimSuffix(prefix, "/") + "/"`.
- The methods check runs first.

In `ServeHTTP`, directly after the revocation gate:

```go
if refusal := checkScopeClaims(claims, r.Method, upstreamPath(r.URL.Path, serviceID)); refusal != "" {
	h.metrics.IncProxyDenied(serviceID, "permission_denied")
	body, _ := json.Marshal(map[string]string{"error": refusal})
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusForbidden)
	_, _ = w.Write(body)
	return
}
```

MCP: `TokenRequest` gains `methods: Optional[list[str]] = None` and `path_prefix: Optional[str] = None`. A module
function `_scope_claims_http_only() -> JSONResponse` answers 400 `{"code": "mintkey:validation_failed",
"reason_code": "scope_claims_http_only", "hint": "methods and path_prefix apply to HTTP services only; omit them for
SSH and email services."}`. It is returned (1) in the email fallback, before `_handle_email_service_token`, when
either field is not `None`, and (2) right after `is_ssh` is computed, when `is_ssh` and either field is not `None`.
The broker payload gets `"methods"` / `"path_prefix"` only for a field that is not `None`. A broker answer 400 becomes
400 `{"code": "mintkey:validation_failed", "title": <the broker body's "title", or "Invalid token request" when the
body is not JSON or has none>}`; any other non-200 stays 502. In `jsonrpc.py` the `mintkey_request_token` input schema
gains `methods` (`{"type": "array", "items": {"type": "string"}}`) and `path_prefix` (`{"type": "string"}`), and
`_dispatch_tool` adds each to the posted JSON only when the argument is present. `tools.yaml` `request_token`
`input_schema.properties` gains `methods` (array, 1–7 unique items, enum of the seven methods) and `path_prefix`
(string, `pattern: "^/"`, 1–512 characters), both optional, each with a one-line description.

## Decisions

**D1. The MCP server passes the fields through.** In the full stack the MCP server is the only caller of
`/v1/issue`, so without it no agent could ask for a narrowed token; an application that calls the broker directly
needs nothing more. Narrowing never widens a grant: the grant check runs first and is unchanged.

**D2. Matching is on the path the upstream receives,** after the service id is removed and before the service's own
base path is joined in front by the reverse proxy. Segments, not characters: `/v1/messagesX` is outside
`/v1/messages`. A `.` or `..` segment is refused outright instead of being resolved, because the upstream may resolve
it differently. A prefix with a trailing slash covers only the paths below it.

**D3. Fail closed on a malformed claim.** The broker never signs one; a claim of the wrong type means the token was
not issued by this broker's rules, so the request is refused.

**D4. The claims are refused where nothing enforces them.** The SSH and email proxies verify the same JWTs but do not
read the claims, so the broker (`service_kind`) and the MCP server (SSH and email services) refuse them rather than
issue a token that looks narrower than it is.

**D5. Tests reach new code only through existing entry points** (the repository's test gate runs new tests against
the code before the change): the broker test posts JSON to `issue.NewHandler` and decodes the returned token; the
proxy test signs its own tokens and calls `ServeHTTP`; the MCP tests call `request_token` and `_dispatch_tool`
directly. No red test names a symbol this change adds (scaffold: none): the Go tests use `newTestHandler`,
`testMCPToken`, `testHandler`, `mustMarshalJSON`, `testSvcUUIDA` and `ServeHTTP`, never `scopeClaims`,
`checkScopeClaims` or `upstreamPath`, and the MCP tests construct `TokenRequest` with the new fields, which the model
ignores before the change. Go tests are top-level functions without `t.Run`; their `t.Fatal`/`t.Errorf` failures are reported by
`gotestsum` as `<failure message="Failed">`, which the gate counts as assertion failures.

## Failure cases

- No `methods`/`path_prefix` in the request: no claim is signed and the token is identical in form to today's
  (covered by the broker test's request without the fields, and by every existing proxy test).
- `methods: null`: treated as absent. `methods: []`: 400.
- Broker unreachable or 5xx while the MCP server forwards the fields: 502 `mintkey:broker_error`, as today.
- A narrowed token on the classical-key path: not applicable (classical keys are not JWTs).
- `read:atlas` with `methods: ["DELETE"]`: both gates apply; the request is refused by the `read:atlas` gate.

## Relation to the other changes

Assumes `proxy-revocation-enforced` is merged (the revocation gate, after which the new check goes). The change
`broker-service-token-required` edits the service-token check at the top of `issue.Handler.ServeHTTP`; this change
edits the request struct and adds a check after `ttl_seconds`, a different part of the same function.
`proxy-data-plane-paths` extends `upstreamPath` and `proxy-budget-check` runs after this check.

## Open questions

- Whether the MCP server should later derive `path_prefix` from a grant's `request_path_prefix` constraint (enforced
  today only on the classical-key path) is left to its own change.
