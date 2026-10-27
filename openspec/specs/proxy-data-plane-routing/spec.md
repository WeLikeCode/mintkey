# proxy-data-plane-routing Specification

## Purpose
The path an upstream receives for each URL form the egress proxy accepts, the service a request addresses for the
audience check, and the documented profile that runs the broker, the proxy and a SQLite vault without the control
plane.

## Requirements

### Requirement: Both URL forms reach the upstream as the bare path
`upstreamPath(reqPath, serviceID)` SHALL remove a leading `/v1/call/<seg>` when `<seg>` names the token's service
(equal after `wireid.Canonical(…, "svc_")`), leaving `/` when nothing follows, and SHALL otherwise apply the rule it
had before (remove a leading `/<serviceID>`). The four JWT directors SHALL apply it to the request path before the
target's base path is joined, and SHALL remove `X-Mintkey-Service-ID` and `X-Mintkey-Tenant-ID` before forwarding.

#### Scenario: the call prefix is removed for the token's service only
- **WHEN** `upstreamPath` is called with the service `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` and the paths
  `/v1/call/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/v1/messages`, `/v1/call/svc_5ANANANANANANANANANANANANA/v1/messages`,
  `/v1/call/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`, `/v1/call/svc_5VQEXVQEXVQEXVQEXVQEXVQEXV/v1/messages` and
  `/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/v1/messages`
- **THEN** it returns `/v1/messages`, `/v1/messages`, `/`, the fourth path unchanged, and `/v1/messages`

#### Scenario: the upstream receives the bare path under its base path, without routing headers
- **WHEN** `handleHTTPDigest` forwards `GET /v1/call/svc_5ANANANANANANANANANANANANA/v1/messages` carrying
  `X-Mintkey-Service-ID` and `X-Mintkey-Tenant-ID` for the service `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` to a target
  whose URL ends in `/base`
- **THEN** the upstream receives the path `/base/v1/messages` and neither header

#### Scenario: a path_prefix claim matches the call form
- **WHEN** a token for the service `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` with `path_prefix` `/v1/messages` sends
  `GET /v1/call/svc_5ANANANANANANANANANANANANA/v1/messages/x`
- **THEN** the request reaches the credential fetch (502 from the unreachable test vault), not 403

### Requirement: Strict mode compares the addressed service in any form and refuses an unaddressed request
The service a JWT request addresses SHALL be the `X-Mintkey-Service-ID` header when present, else the segment after
`/v1/call/`, else a UUID-shaped first path segment. It SHALL be compared with the token's `aud` after
`wireid.Canonical(…, "svc_")`. In strict mode a request that addresses no service SHALL be answered 403 with
`{"error":"service not addressed"}`, before the credential fetch, and SHALL emit `proxy.aud_mismatch_rejected` with an
empty `url_service_id` when audit is wired; a mismatch SHALL be answered as before (403 `scope mismatch`).

#### Scenario: an unaddressed request is refused in strict mode only
- **WHEN** a valid token for the service `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` sends `GET /v1/messages` without
  `X-Mintkey-Service-ID` to a strict handler with an audit queue, and the same request to a permissive handler
- **THEN** the strict handler answers 403 `{"error":"service not addressed"}` and records one
  `proxy.aud_mismatch_rejected` event whose `url_service_id` is empty and `mode` is `strict`; the permissive handler
  reaches the credential fetch (502)

#### Scenario: the header and the wire form are compared with the audience
- **WHEN** a strict handler receives, with a token for `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`, `GET /v1/messages` with
  `X-Mintkey-Service-ID: svc_5ANANANANANANANANANANANANA`, the same with `svc_5VQEXVQEXVQEXVQEXVQEXVQEXV`,
  `GET /v1/call/svc_5VQEXVQEXVQEXVQEXVQEXVQEXV/x` and `GET /v1/call/svc_5ANANANANANANANANANANANANA/x`
- **THEN** the first and the last reach the credential fetch (502), the second and the third answer 403
  `{"error":"scope mismatch"}`

### Requirement: Kong-syncer adds the routing headers to every route of a service
`GenerateDeclarativeYAML` SHALL attach the `request-transformer` plugin adding `X-Mintkey-Service-ID:<service id>` and
`X-Mintkey-Tenant-ID:<tenant id>` to the virtual-host route as it does to the path route.

#### Scenario: the virtual-host route carries the headers
- **WHEN** the YAML for one service `svc_01HX1234567890ABCDEFGHIJKL` of tenant `tenant_01HX1234567890ABCDEFGHIJKL` is
  generated and parsed
- **THEN** both of its routes have one `request-transformer` plugin whose `config.add.headers` are
  `X-Mintkey-Service-ID:svc_01HX1234567890ABCDEFGHIJKL` and `X-Mintkey-Tenant-ID:tenant_01HX1234567890ABCDEFGHIJKL`

### Requirement: The data-plane-only profile is documented
`docs/guides/data-plane-only.md` SHALL describe running `broker`, `proxy-plugin` and a SQLite `vault-adapter` without
the control plane, naming every setting and fact listed in this change's design.md, SHALL contain no Mermaid block
and no credential value.

#### Scenario: the page names the profile's settings and limits
- **WHEN** the acceptance test reads `docs/guides/data-plane-only.md`
- **THEN** the file exists, contains every name of design.md's list, contains no ```` ```mermaid ```` fence, and
  contains none of the values that `infra/compose/docker-compose.yml` gives the `proxy-plugin` service's variables
  whose names end in `_TOKEN` (only values that are strings of at least 16 characters and contain no `${`: an empty value, an interpolation
  such as `${MINTKEY_PROXY_SERVICE_TOKEN}` and a short placeholder are skipped, since the page names the variables)
