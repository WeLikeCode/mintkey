# A token can be limited to HTTP methods and a path prefix

## Why

A brokered token is bound to one service (`aud`), one tenant (`tnt`) and one action (`scope`). Within that service it
reaches every method and every path: the only method gate in the egress proxy is the read-only gate for the literal
scope `read:atlas`. ADR-0006's verification flow asks the proxy to check that the scope matches "the action implied by
the request (path/method)" (step 6), but the token has no way to say which path or method that is. A caller that knows
the one request it needs (for example `GET` under `/v1/messages`) cannot ask for a token that allows only that, so
every token is as broad as the whole service for its lifetime. Least privilege for a credential broker means the
issuer caller can narrow a token, the narrowing is signed, and the proxy enforces it before it touches the credential.

## What Changes

- The broker's `POST /v1/issue` accepts two optional fields: `methods` (1 to 7 distinct HTTP methods out of `GET`,
  `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`, case-insensitive, signed uppercase) and `path_prefix` (an
  absolute path without query, fragment, percent-encoding, empty or dot segments, at most 512 bytes). It signs them as
  the claims `methods` and `path_prefix`. An invalid value answers 400 `validation_failed`; either field together
  with `service_kind` (the email path) answers 400 as well. A request without them issues the same token as today.
- The egress proxy refuses with 403 `{"error":"method not permitted"}` a request whose method is not in a token's
  `methods` claim, and with 403 `{"error":"path not permitted"}` a request whose upstream path is not the
  `path_prefix` or below it on a segment boundary, or contains a `.` or `..` segment. Both checks run right after the
  revocation check, before the credential fetch. A malformed claim refuses the request.
- The path the upstream receives is computed once, by a new function `upstreamPath`, for the check and for the four
  JWT reverse-proxy directors (today's rule: a leading `/<service id>` is removed).
- The MCP server's `request_token` (REST and the JSON-RPC tool `mintkey_request_token`) accepts the same two optional
  fields and passes them to the broker only when present; it answers a broker 400 with 400
  `mintkey:validation_failed`, and refuses the fields for SSH and email services. The MCP tool contract
  (`docs/architecture/contracts/mcp/tools.yaml`) gains the two optional properties.

## Capabilities

### New Capabilities
- `token-scope-claims`: requesting, signing and enforcing a token's optional method and path-prefix limits.

## Impact

- Changed: `apps/broker/internal/api/issue/issue.go`, `apps/broker/internal/issuer/issuer.go`,
  `apps/proxy-plugin/cmd/proxy-plugin/main.go` (`ServeHTTP` and the directors of `ServeHTTP`,
  `handleOAuth2ClientCredentials`, `handleHTTPDigest`, `handleOAuth2PasswordGrant`),
  `apps/mcp-server/src/mcp_server/tools/request_token.py`, `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`,
  `docs/architecture/contracts/mcp/tools.yaml`.
- New modules: `apps/proxy-plugin/cmd/proxy-plugin/scope_claims.go`, `apps/proxy-plugin/cmd/proxy-plugin/routing.go`.
- New tests: `apps/broker/internal/api/issue/issue_scope_claims_test.go`,
  `apps/proxy-plugin/cmd/proxy-plugin/scope_claims_test.go`,
  `apps/mcp-server/tests/test_request_token_scope_claims.py`.
- Callers: opt-in. Tokens issued without the fields carry no new claim and behave as before; existing MCP clients
  send neither field. The SSH and email proxies do not read the claims, which is why the fields are refused there.
- Operators: no migration. Deploy the proxy before or with the broker, so that no proxy that ignores the claims
  receives a narrowed token.
- Out of scope: a request-body digest claim, deriving `path_prefix` from a grant's `request_path_prefix` constraint,
  and the `token.issued` audit payload (its schema is closed; the claims are not added to it).

## Issue Intake (remediation gate)

1. **Problem statement**: a brokered token cannot be limited below a whole service.
2. **User-visible symptom**: a caller that needs one read call holds a token that also allows writes and every other
   path of the service until it expires.
3. **Expected behavior**: a token issued with `methods` and `path_prefix` works only for those methods and paths;
   other requests get 403 before the credential is fetched.
4. **Evidence**: `issueRequest` in `issue.go` has no such fields; `ServeHTTP` in the proxy gates methods only for
   `read:atlas`.
5. **Scope**: the files under Impact.
6. **Out of scope**: as listed under Impact.
7. **Risk level**: security (narrowing only; a token without the claims is unchanged).
8. **Verification target**: the Go suites of `apps/broker` and `apps/proxy-plugin`, and the MCP server's pytest suite.
9. **Owner decisions needed**: none; see design.md, Decisions.
