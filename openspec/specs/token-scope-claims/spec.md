# token-scope-claims Specification

## Purpose
How an issuer caller limits a brokered token to HTTP methods and a path prefix, how the broker signs the limits, and
how the egress proxy enforces them before it fetches a credential.

## Requirements

### Requirement: The broker signs optional methods and path_prefix claims
`POST /v1/issue` SHALL accept the optional fields `methods` (a list) and `path_prefix` (a string). When `methods` is
present and valid the token SHALL carry the claim `methods` with the entries uppercased in request order; when
`path_prefix` is present and valid the token SHALL carry the claim `path_prefix` with the value unchanged. A request
without the fields SHALL issue a token with neither claim.

#### Scenario: the limits are signed as claims
- **WHEN** a valid issue request carries `"methods": ["get", "POST"]` and `"path_prefix": "/v1/messages"`, and a
  second valid request carries neither field
- **THEN** both answer 200; the first token's claims hold `methods` = `["GET", "POST"]` and `path_prefix` =
  `/v1/messages`; the second token's claims have neither key

### Requirement: The broker refuses invalid limits
`POST /v1/issue` SHALL answer 400 with `mintkey:code` `validation_failed` and issue no token when `methods` is an
empty list, has more than 7 entries, repeats an entry ignoring case, or names a method other than `GET`, `HEAD`,
`POST`, `PUT`, `PATCH`, `DELETE` or `OPTIONS`; when `path_prefix` does not start with `/`, is longer than 512 bytes,
or contains `?`, `#`, `%`, `\`, `//`, a control or space character, or a `.` or `..` segment; and when either field is
given together with `service_kind`.

#### Scenario: each invalid limit is refused
- **WHEN** issue requests carry, one at a time, `methods` `[]`, `["FETCH"]`, `["GET", "get"]`, `path_prefix`
  `v1/messages`, `/v1/../admin`, `/v1/messages?x=1`, `/v1//x`, `/v1/%2e%2e`, and `methods` `["GET"]` with
  `service_kind` `email`
- **THEN** each answers 400 with `mintkey:code` `validation_failed`

### Requirement: The proxy enforces the limits before the credential fetch
The egress proxy SHALL answer a JWT request with 403 and the JSON body `{"error":"method not permitted"}` when the
token carries a `methods` claim that does not contain the request method, and with 403 and `{"error":"path not
permitted"}` when the token carries a `path_prefix` claim and the upstream path (`upstreamPath(request path, aud)`)
contains a `.` or `..` segment or is neither the prefix nor below it on a segment boundary. A `methods` claim that is
not a non-empty list of strings, or a `path_prefix` claim that is not a string starting with `/`, SHALL refuse the
request the same way. The check SHALL run directly after the revocation check, so a refused request never reaches
the vault. The upstream path SHALL be computed by `func upstreamPath(reqPath, serviceID string) string`
(`cmd/proxy-plugin/routing.go`), which the four JWT directors also use and a later change extends; the proxy tests
sign their tokens with the test helper `func buildScopeClaimsJWT(t *testing.T, aud string, extra map[string]any)
(string, ed25519.PublicKey)` (`cmd/proxy-plugin/scope_claims_test.go`), which later changes' tests reuse.

#### Scenario: other methods and paths are refused, the permitted call goes through
- **WHEN** a token carries `methods` `["GET"]` and `path_prefix` `/v1/messages`
- **THEN** `POST /v1/messages/x` and `HEAD /v1/messages/x` answer 403 `method not permitted`; `GET /v1/other` and
  `GET /v1/messagesX` answer 403 `path not permitted`; `GET /v1/messages/x`, `GET /v1/messages` and
  `GET /<aud>/v1/messages/x` reach the credential fetch (502 from the unreachable test vault)

#### Scenario: dot segments and malformed claims are refused
- **WHEN** a token with `path_prefix` `/v1/messages` sends `GET /v1/messages/../admin` and `GET /v1/messages/./x`,
  and tokens whose `methods` claim is the string `GET` or an empty list, or whose `path_prefix` claim is the number
  5 or the string `v1`, send `GET /v1/messages/x`
- **THEN** the dot-segment requests and the `path_prefix` claims answer 403 `path not permitted`, and the `methods`
  claims answer 403 `method not permitted`

### Requirement: The MCP server passes the limits to the broker
`request_token` (REST) SHALL accept optional `methods` and `path_prefix`, send each to the broker only when it is
given, and answer a broker 400 with 400 `{"code": "mintkey:validation_failed", "title": <the broker's title>}`. It
SHALL answer 400 with `reason_code` `scope_claims_http_only`, without calling the broker, when either field is given
for an SSH or an email service. The JSON-RPC tool `mintkey_request_token` SHALL declare both fields in its input
schema and forward each only when given. The tool contract `docs/architecture/contracts/mcp/tools.yaml` SHALL list
both as optional properties of `request_token`.

#### Scenario: the fields reach the broker only when given
- **WHEN** an agent with a grant calls `request_token` for an HTTP service with `methods` `["GET"]` and
  `path_prefix` `/v1/messages`, and again without them
- **THEN** both answer 200; the first broker request body holds `"methods": ["GET"]` and
  `"path_prefix": "/v1/messages"`, the second holds neither key

#### Scenario: a broker validation error is answered 400
- **WHEN** the broker answers 400 `{"mintkey:code": "validation_failed", "title": "methods may contain only GET, HEAD,
  POST, PUT, PATCH, DELETE and OPTIONS"}`
- **THEN** `request_token` answers 400 with `code` `mintkey:validation_failed` and that title

#### Scenario: the limits are refused for SSH and email services
- **WHEN** an agent asks for `methods` `["GET"]` on a service whose `auth_scheme` is `ssh_private_key`, and on an
  email service
- **THEN** both answer 400 with `code` `mintkey:validation_failed` and `reason_code` `scope_claims_http_only`, and the
  broker is not called

#### Scenario: the JSON-RPC tool and the contract carry the fields
- **WHEN** `_dispatch_tool` handles `mintkey_request_token` with `service_id` `svc_x`, `methods` `["GET"]` and
  `path_prefix` `/v1/messages`, and the tool list and `tools.yaml` are read
- **THEN** the posted JSON is `{"service_id": "svc_x", "action": "call", "methods": ["GET"], "path_prefix":
  "/v1/messages"}`, and both the `mintkey_request_token` input schema and the `request_token` `input_schema` of
  `tools.yaml` have the properties `methods` and `path_prefix`, neither of them required
