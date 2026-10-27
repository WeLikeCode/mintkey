# Design: proxy-data-plane-paths

## Context

- After `token-request-scope-claims`, `cmd/proxy-plugin/routing.go` holds `upstreamPath(reqPath, serviceID string)
  string` (removes a leading `"/"+serviceID`), and each JWT director (in `ServeHTTP`, `handleOAuth2ClientCredentials`,
  `handleHTTPDigest`, `handleOAuth2PasswordGrant`) runs `originalDirector(req)` (which joins the target URL's path in
  front of the request path), then `req.Host = req.URL.Host`, `req.Header.Del("X-Mintkey-Target")`, then
  `req.URL.Path = upstreamPath(req.URL.Path, serviceID)`. The scope-claims check calls
  `upstreamPath(r.URL.Path, serviceID)` on the request path.
- The audience check in `ServeHTTP` (after the `read:atlas` gate, before the budget block) runs only when
  `urlServiceID(r.URL.Path)` is non-empty: the first segment after `/v1/call/` (or the first segment) when it is
  UUID-shaped. On a mismatch it logs `event=aud_check ... result=reject|warn`; strict mode emits
  `proxy.aud_mismatch_rejected` (`jti`, `aud`, `url_service_id`, `mode`) and answers 403 `{"error":"scope mismatch"}`.
- Kong-syncer (`apps/kong-syncer/internal/kong/yaml.go`, `GenerateDeclarativeYAML`) gives each service a path route
  `/v1/call/<svc wire id>` (`strip_path: true`, plugin `request-transformer` adding `X-Mintkey-Service-ID:<id>` and
  `X-Mintkey-Tenant-ID:<tenant>`) and a virtual-host route `<slug>.<tenant slug>.proxy.local` without plugins.
- From `proxy-revocation-enforced`: `wireid.ToUUID` / `wireid.Canonical`. From `token-request-scope-claims`:
  `upstreamPath`, the scope-claims check, the test helper `buildScopeClaimsJWT`. From `proxy-budget-check`: the budget
  block (unchanged here).

## Interfaces

`cmd/proxy-plugin/routing.go`:

```go
// upstreamPath returns the path the upstream receives for reqPath, the request path as the proxy received it:
//   "/v1/call/<seg>[/<rest>]" -> "/<rest>" when wireid.Canonical(seg, "svc_") == wireid.Canonical(serviceID, "svc_")
//                                ("/" when there is no rest)
//   otherwise the rule before this change: a leading "/"+serviceID is removed and the result starts with "/".
func upstreamPath(reqPath, serviceID string) string

// addressedServiceID returns the service a request addresses: serviceHeader when it is not empty; else, for a path
// starting with "/v1/call/", the segment after it (any form, possibly ""); else urlServiceID(reqPath).
func addressedServiceID(reqPath, serviceHeader string) string
```

`urlServiceID` and `isUUIDShape` are unchanged.

Directors: in each of the four JWT directors, `req.URL.Path = upstreamPath(req.URL.Path, serviceID)` moves to the
first statement, before `originalDirector(req)`, and `req.Header.Del("X-Mintkey-Service-ID")` and
`req.Header.Del("X-Mintkey-Tenant-ID")` follow `req.Header.Del("X-Mintkey-Target")`. The classical-key director is not
changed.

The audience check in `ServeHTTP` becomes:

```go
addressed := addressedServiceID(r.URL.Path, r.Header.Get("X-Mintkey-Service-ID"))
switch {
case addressed == "":
	if h.cfg.AudEnforcement == config.AudEnforcementStrict {
		// log: event=aud_check service_id_url= aud=<safeID(serviceID)> mode=strict result=reject
		// audit (when h.audit != nil): proxy.aud_mismatch_rejected, payload {jti, aud: serviceID, url_service_id: "", mode}
		// metrics: IncProxyDenied(serviceID, "permission_denied")
		// 403, Content-Type application/json, body {"error":"service not addressed"}
		return
	}
case wireid.Canonical(addressed, "svc_") != wireid.Canonical(serviceID, "svc_"):
	// the existing mismatch handling, with addressed in place of urlSvcID
}
```

Kong-syncer, `yaml.go`: the virtual-host route gets the same `Plugins` value as the path route (one helper,
`routingHeaderPlugins(svc ServiceEntry) []kongPlugin`, used by both routes). Nothing else in the YAML changes.

New page `docs/guides/data-plane-only.md`, plain Markdown, no Mermaid (the gates cannot render it). Sections and the
facts each must state (each quoted name appears verbatim; the test checks them):
1. **What runs**: `broker`, `proxy-plugin`, and `vault-adapter` with `MINTKEY_VAULT_BACKEND=sqlite` and
   `MINTKEY_VAULT_FILE_PATH`; what does not: `admin-api`, `Kong`, `kong-syncer`, `mcp-server`, `Keycloak`, the admin UI.
2. **Keys and identities**: `MINTKEY_VAULT_KEK_FILE`, `MINTKEY_BROKER_SIGNING_KEY_FILE`; the proxy's vault identity
   `MINTKEY_VAULT_PROXY_IDENTITY_ID` / `MINTKEY_VAULT_PROXY_TOKEN`; credentials are written with `PutCredential` under
   the admin identity `MINTKEY_VAULT_ADMIN_IDENTITY_ID` / `MINTKEY_VAULT_ADMIN_TOKEN`; the proxy finds the others
   through `BROKER_ADDR` (JWKS) and `VAULT_GRPC_ADDR`, and listens on `PLUGIN_PORT`. Every token is a long random value
   provisioned as a secret; the page shows no values.
3. **Issuing tokens**: the application calls `POST /v1/issue` with `X-Mintkey-Service-Token` set to the broker's
   `MINTKEY_MCP_SERVICE_TOKEN`; body fields `agent_id`, `service_id`, `tenant_id`, `scope`, `ttl_seconds`, and the
   optional `methods` and `path_prefix`.
4. **Calling a service**: `/v1/call/<service id>/<path>` on the proxy; `<service id>` is the token's `service_id` or
   its `svc_` form. With `MINTKEY_ENV=production` the audience check is strict (`MINTKEY_AUD_ENFORCEMENT` overrides):
   a request must address its service, else 403 `service not addressed`.
5. **Audit events**: `MINTKEY_ADMIN_API_URL` on broker and proxy points at the application, which answers
   `POST /v1/internal/audit/emit` with a 2xx and checks `X-Mintkey-Service-Token` against
   `MINTKEY_BROKER_SERVICE_TOKEN` (broker) or `MINTKEY_PROXY_SERVICE_TOKEN` (proxy); the body is one JSON event
   (`event_type`, `tenant_id`, `actor_id`, `actor_type`, `target_id`, `target_type`, `payload`).
6. **What needs Postgres**: revocation and budgets need the proxy's `DATABASE_URL`; without it tokens stay valid until
   `exp` plus 30 s, and no budget applies. With it, the application revokes by `NOTIFY` on `mintkey:agent` with
   `{"event_type":"token.revoked","jti":...}` or `{"event_type":"agent.revoked","agent_id":...}`. Classical service API
   keys need the broker's `DATABASE_URL` too.
7. **Not provided**: a compose file for this profile and an end-to-end test of it.

## Decisions

**D1. Strict mode refuses an unaddressed request.** Strict mode promises that the service a request names is the
token's audience; a request that names none cannot be checked, so strict fails closed. Permissive keeps proceeding.
Behind Kong every route now supplies the header, so Kong-routed traffic is always addressed.

**D2. The header wins over the path.** Behind Kong's path route the path no longer holds the id, and the remaining
upstream path may start with a UUID-shaped segment of the upstream's own API, which today's rule takes for an
address. A caller that sets the header itself names a service as it would in the path; either way the credential and
the upstream come from the token's audience, so the header cannot widen what a token reaches.

**D3. The prefix is removed before the base path is joined.** That is the only order in which both URL forms reach a
service whose base URL has a path. For a service at the root, and for every Kong-routed request, the result is the
same as today.

**D4. Ids are compared in canonical form.** The token's audience is a UUID when the MCP server requested it; the URL
and the header may carry the `svc_` form. `wireid.Canonical` makes the forms equal and leaves other ids as they are.

**D5. Tests reach the code through functions that exist before the change**: `upstreamPath`, `ServeHTTP`,
`handleHTTPDigest` (called directly with a digest credential and a test upstream, as
`oauth2_client_credentials_dispatch_test.go` does for client credentials), `GenerateDeclarativeYAML`, and a pytest that
reads the page. No red test names a symbol this change adds (scaffold: none): `addressedServiceID` is reached
through `ServeHTTP`, and `upstreamPath` (same signature) and `buildScopeClaimsJWT` come from
`token-request-scope-claims`, so they exist once it is merged. Go tests are top-level functions without `t.Run`; their failures are reported as
`<failure message="Failed">`, which the gate counts as assertion failures.

## Failure cases

- Permissive mode, unaddressed request: proceeds, no log line, as today.
- `X-Mintkey-Service-ID` names another service: mismatch (strict 403 `scope mismatch`, permissive warning).
- `/v1/call/<id of another service>/x`: not stripped; mismatch as above; in permissive mode the upstream receives the
  path unchanged, as today for `/<other id>/x`.
- Kong-syncer not yet redeployed, strict proxy: virtual-host requests answer 403 `service not addressed` until it is
  (see the proposal's migration).
- The page is missing a required name: the acceptance test names it.

## Relation to the other changes

Assumes `proxy-revocation-enforced`, `token-request-scope-claims` and `proxy-budget-check` are merged (see Context).
Every earlier test that runs in strict mode addresses its service in the path, so none changes.

## Open questions

- If `service-token-files` lands after this change, its `*_FILE` variables should be added to the page's section 2.
