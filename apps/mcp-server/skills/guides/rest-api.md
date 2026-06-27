# Guide: Calling a REST/HTTP service through Mintkey

URI: `mintkey://guides/rest-api` · also `mintkey_bootstrap(section="rest-api")`

REST/HTTP services are handled by the **Kong egress proxy** (port `:8000`). You
discover services, request a short-lived brokered JWT, then call the proxy URL.
The proxy verifies your JWT, injects the real upstream credential, and forwards
your request to the backend. You never hold the upstream secret.

## The 3-step flow

### Step 1 — Discover (find the svc_ id; never hardcode it)
```json
{ "tool": "mintkey_discover", "arguments": {} }
// or
{ "tool": "mintkey_list_services", "arguments": {} }
```
Each service in the response has `id` (e.g. `svc_01HX...`), `connect_type`,
`auth_scheme`, and a `how_to_call` hint. For REST/HTTP services,
`connect_type == "http"`.

Also useful: `mintkey_describe_service` returns `explicit_proxy_url` (the exact
URL to use), `auth_scheme_details` (injection point, header name, format), and
`your_constraints` (rate limit, time window, path prefix, source IP).

### Step 2 — Request a brokered token
```json
{ "tool": "mintkey_request_token",
  "arguments": { "service_id": "svc_01HX...", "action": "call" } }
// → { "token": "<JWT>", "expires_at": <unix>, "service_id": "svc_01HX..." }
```
`action` defaults to `"call"`. The JWT has a ~10-minute TTL. Track `expires_at`
and refresh before expiry (call `mintkey_request_token` again).

### Step 3 — Call the PROXY (NOT the upstream directly)
```
{proxy_url}/v1/call/{service_id}/{upstream_path...}
```
Example:
```bash
curl -X GET \
  -H "Authorization: Bearer $JWT" \
  -H "Accept: application/json" \
  "http://localhost:8000/v1/call/svc_01HX.../v1/customers/42"
```
Python (`httpx`):
```python
import httpx
r = httpx.get(
    f"{proxy_url}/v1/call/{service_id}/v1/customers/42",
    headers={"Authorization": f"Bearer {jwt}"},
    timeout=30.0,
)
r.raise_for_status()
```

The proxy URL comes from:
1. `MINTKEY_PROXY_URL` env var (preferred)
2. `proxy_url` field in the `mintkey_bootstrap` index response
3. `explicit_proxy_url` in `mintkey_describe_service`

## THE invariant

**Never add the upstream service's own credential header.**

Do NOT send `X-API-Key`, `Authorization: Bearer <upstream-key>`, `api_key=…`
query params, or any credential the upstream normally expects. The proxy holds
those — it is silently stripped and overwritten — the proxy unconditionally
deletes any inbound `Authorization` header (proxy-plugin injector.go) before
injecting the real credential, so a header you send is simply dropped, never
forwarded, and there is no passthrough-rejection error to handle.

The ONLY `Authorization` header you send is the brokered JWT that authenticates
YOU to Mintkey.

## Auth scheme cheat-sheet (what the proxy injects)

| `auth_scheme` | What the proxy injects | What you must NOT send |
|---|---|---|
| `api_key_header` | `X-API-Key: <key>` (or operator-configured header) | your own `X-API-Key` |
| `api_key_query` | `?api_key=<key>` (or operator-configured param) | your own `api_key` query param |
| `bearer_token` | `Authorization: Bearer <secret>` | your own `Authorization` to the upstream |
| `basic_auth` | `Authorization: Basic base64(user:pass)` | your own `Authorization` |
| `oauth2_client_credentials` | `Authorization: Bearer <access_token>` | your own `Authorization` |
| `oidc_client_secret` | `Authorization: Bearer <id_or_access_token>` | your own `Authorization` |
| `oauth2_password_grant` | `Authorization: Bearer <access_token>` | your own `Authorization` |
| `apple_jwt` | `Authorization: Bearer <apple_jwt>` (ES256, generated per-request) | your own `Authorization` |
| `google_service_account` | `Authorization: Bearer <google_access_token>` | your own `Authorization` |

Check `mintkey_describe_service` → `auth_scheme_details` for the exact header
name, query param name, and format for the specific service you're calling.

## Supported HTTP methods

All methods pass through: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`,
`OPTIONS`. Body is forwarded unmodified. Standard headers (`Content-Type`,
`Accept`, custom domain headers) pass through — only the upstream credential
header is replaced.

## Error handling

| HTTP status | `mintkey:code` | Meaning | Action |
|---|---|---|---|
| 401 `token_expired` | JWT TTL elapsed | call `mintkey_request_token` again |
| 401 `token_invalid` | bad signature or unknown `kid` | refresh; check API key |
| 401 `agent_revoked` | operator revoked the agent | stop; tell operator |
| 403 `permission_denied` | no active grant for this service | ask operator to grant |
| 403 `constraint_violated` | rate limit / time window / path / IP violation | check `your_constraints` |
| 404 `unknown_service` | `service_id` not found or not visible | re-discover |
| 5xx `upstream_error` | backend returned 5xx | retry with backoff; Mintkey does NOT auto-retry |

Every 403 from `mintkey_request_token` carries `agent_id`, `service_id`,
`action`, and a `hint` — echo the hint verbatim to whoever is operating you.

## Complete example (Python)

```python
import os, httpx

MK_MCP = os.environ["MINTKEY_MCP_URL"]      # e.g. http://localhost:8082
MK_KEY  = os.environ["MK_AGENT_KEY"]        # mk_agent_...
PROXY   = os.environ["MINTKEY_PROXY_URL"]   # e.g. http://localhost:8000

headers = {"Authorization": f"Bearer {MK_KEY}"}

# 1. Discover
services = httpx.get(f"{MK_MCP}/v1/tools/discover", headers=headers).json()
svc = next(s for s in services["services"] if s["slug"] == "my-crm")
svc_id = svc["id"]

# 2. Token
token_resp = httpx.post(
    f"{MK_MCP}/v1/tools/request_token",
    headers=headers,
    json={"service_id": svc_id, "action": "call"},
).json()
jwt = token_resp["token"]

# 3. Proxy call — only send the brokered JWT; no upstream auth
r = httpx.get(
    f"{PROXY}/v1/call/{svc_id}/v1/customers/42",
    headers={"Authorization": f"Bearer {jwt}"},
    timeout=30.0,
)
r.raise_for_status()
print(r.json())
```

## Anti-patterns
- Sending an upstream credential header alongside the JWT → it is silently stripped.
- Calling the upstream `base_url` directly → `base_url` is informational; the JWT is audience-bound to the proxy and only works there.
- Hardcoding `svc_` IDs → they live in Postgres; re-discover every session.
- Caching `mintkey_discover` results for longer than 5 minutes → grants can be revoked within seconds.
