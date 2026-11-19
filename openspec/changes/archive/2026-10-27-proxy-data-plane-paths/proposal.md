# One path form for the proxy, a strict audience check that always has an address, and a data-plane-only guide

## Why

The broker, the egress proxy and the vault adapter can run without the control plane: an application that issues
tokens through the broker's `POST /v1/issue`, stores credentials in a SQLite vault and calls services through the
proxy. Three things keep that profile from being dependable.

1. **Two URL forms, one handled.** Agents address a service as `/v1/call/<service id>/<path>`. Behind Kong the
   generated route removes `/v1/call/<service id>` before the proxy sees the request; the older catch-all route leaves
   `/<service id>/<path>`, which the proxy removes itself. Without Kong the proxy receives `/v1/call/<service id>/...`
   and forwards it unchanged, so the upstream gets the wrong path. The proxy also removes the prefix after the
   service's base path has been joined in front, so a service whose base URL has a path never gets it removed.
2. **The strict audience check rarely has an address.** In strict mode (the production default, ADR-0004 addendum)
   the proxy compares the token's audience with the service id in the URL, but only for UUID-shaped segments. The
   routes Kong-syncer generates use the `svc_` wire form and are removed by Kong before the proxy sees them, and the
   virtual-host route carries no id at all, so the comparison is mostly skipped, and a request that names no service
   is accepted.
3. **The profile is not written down.** Which services run, which variables they need, where audit events go and what
   needs Postgres (revocation, budgets) has to be read from the code.

## What Changes

- `upstreamPath` (from `token-request-scope-claims`) also removes a leading `/v1/call/<id>` when `<id>` names the
  token's service (its UUID or its `svc_` wire form). The four JWT directors apply it to the request path before the
  service's base path is joined. The scope-claims check already uses the same function, so `path_prefix` matches the
  same path in both URL forms.
- The service a request addresses is the `X-Mintkey-Service-ID` header when present (Kong's generated routes add it),
  else the id after `/v1/call/`, else a UUID-shaped first path segment (today's rule). It is compared with the token's
  audience in canonical UUID form.
- In strict mode a request that addresses no service is refused with 403 `{"error":"service not addressed"}` and the
  `proxy.aud_mismatch_rejected` audit event (with an empty `url_service_id`), before the credential fetch. Permissive
  mode is unchanged.
- Kong-syncer adds the same `X-Mintkey-Service-ID` / `X-Mintkey-Tenant-ID` headers to each service's virtual-host
  route, so virtual-host requests are addressed too. The JWT directors remove both headers before forwarding.
- New page `docs/guides/data-plane-only.md`: running broker, proxy and a SQLite vault without admin-api, Kong,
  Kong-syncer, the MCP server and Keycloak, with the audit sink pointing at the embedding application.

## Capabilities

### New Capabilities
- `proxy-data-plane-routing`: the path the upstream receives, the service a request addresses, and the documented
  data-plane-only profile.

## Impact

- Changed: `apps/proxy-plugin/cmd/proxy-plugin/routing.go`, `apps/proxy-plugin/cmd/proxy-plugin/main.go`
  (`ServeHTTP`'s audience check, the four JWT directors), `apps/kong-syncer/internal/kong/yaml.go`.
- New page: `docs/guides/data-plane-only.md`.
- New tests: `apps/proxy-plugin/cmd/proxy-plugin/data_plane_paths_test.go`,
  `apps/kong-syncer/internal/kong/yaml_vhost_headers_test.go`, `tests/acceptance/test_data_plane_only_doc.py`.
- Callers: `/v1/call/<id>/<path>` now reaches the upstream as `/<path>` without Kong. In strict mode a request must
  address its service (path or header); a request to the wrong service is refused also when the path uses the `svc_`
  form or Kong supplies the header. Upstreams no longer receive the two routing headers.
- Operators (migration): deploy Kong-syncer (so virtual-host routes carry the header) before or with the proxy;
  during a rollout where that is not possible, set `MINTKEY_AUD_ENFORCEMENT=permissive` on the proxy until both are
  updated. A person may add a compose file for the data-plane-only profile under `infra/compose/` (outside this unit).
- Out of scope: a combined data-plane image, end-to-end tests of the profile (they need Docker), and the
  classical-key director (it needs Kong's tenant header anyway).

## Issue Intake (remediation gate)

1. **Problem statement**: without Kong the proxy forwards the `/v1/call/<id>` prefix to the upstream, and strict mode
   accepts requests that name no service.
2. **User-visible symptom**: the upstream answers 404 for `/v1/call/<id>/...` calls made directly to the proxy;
   strict deployments behind Kong compare no service id.
3. **Expected behavior**: both URL forms reach the upstream as the bare path; strict mode refuses an unaddressed or
   mismatched request with 403 before the credential fetch.
4. **Evidence**: the directors' `TrimPrefix(req.URL.Path, "/"+serviceID)` runs after the reverse proxy's path join;
   `urlServiceID` accepts only UUID shapes; `GenerateDeclarativeYAML` publishes `/v1/call/svc_<Crockford>` with
   `strip_path: true` and no header on the virtual-host route.
5. **Scope**: the files under Impact.
6. **Out of scope**: as listed under Impact.
7. **Risk level**: availability (strict mode refuses unaddressed requests) and docs.
8. **Verification target**: the Go suites of `apps/proxy-plugin` and `apps/kong-syncer`; the acceptance pytest suite.
9. **Owner decisions needed**: none; see design.md, Decisions.
