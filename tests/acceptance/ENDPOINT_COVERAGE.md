# Endpoint Coverage Matrix

**51 rows total: 28 both, 15 openapi-only, 8 router-only**

Enumeration counts:
- OpenAPI `paths:` section: 43 path×method combinations
- FastAPI routers (`admin-api/src/admin_api/api/*.py`): 36 path×method combinations
- Union: 51 unique entries

Legend:
- `both` — present in both OpenAPI contract and FastAPI router
- `openapi-only` — declared in OpenAPI but no matching FastAPI route found 🔴
- `router-only` — implemented in FastAPI but absent from OpenAPI contract 🟡

| path | method | source | test_file::test_fn | asserted_status_codes | last_result |
|---|---|---|---|---|---|
| /v1/auth/login | GET | openapi-only 🔴 | TODO | 302, 503 | 🔴 |
| /v1/auth/callback | GET | openapi-only 🔴 | TODO | 302, 400, 401, 403 | 🔴 |
| /v1/auth/oidc/login | GET | router-only 🟡 | TODO | TODO | 🔴 |
| /v1/auth/oidc/callback | GET | router-only 🟡 | TODO | TODO | 🔴 |
| /v1/auth/internal-login | POST | both | TODO | 200, 401, 429 | 🔴 |
| /v1/auth/logout | POST | both | TODO | 204 | 🔴 |
| /v1/auth/whoami | GET | both | TODO | 200, 401 | 🔴 |
| /v1/tenants | GET | openapi-only 🔴 | TODO | 200, 401, 403 | 🔴 |
| /v1/tenants | POST | both | TODO | 201, 400, 401, 403, 409 | 🔴 |
| /v1/tenants/{tenant_id} | GET | openapi-only 🔴 | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id} | PATCH | openapi-only 🔴 | TODO | 200, 400, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id} | DELETE | openapi-only 🔴 | TODO | 204, 401, 403, 404, 409 | 🔴 |
| /v1/tenants/{tenant_id}/services | GET | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/services | POST | both | TODO | 201, 400, 401, 403, 409 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id} | GET | openapi-only 🔴 | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id} | PATCH | both | TODO | 200, 400, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id} | DELETE | both | TODO | 204, 401, 403, 404, 409 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id}/test | POST | openapi-only 🔴 | TODO | 200, 401, 403, 404, 422, 429 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials | GET | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials | POST | both | TODO | 201, 400, 401, 403, 404, 409 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials/{key_version} | DELETE | openapi-only 🔴 | TODO | 204, 401, 403, 404, 409 | 🔴 |
| /v1/tenants/{tenant_id}/agents | GET | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents | POST | both | TODO | 201, 400, 401, 403, 409 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id} | GET | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id} | DELETE | router-only 🟡 | TODO | TODO | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/revoke | POST | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/permissions | POST | both | TODO | 200, 201, 400, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id} | DELETE | both | TODO | 204, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys | POST | both | TODO | 201, 401, 403, 404, 422 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys | GET | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys/{api_key_id} | GET | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys/{api_key_id}/revoke | POST | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys/{api_key_id}/rotate | POST | both | TODO | 201, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/audit | GET | both | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/changes | GET | openapi-only 🔴 | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/changes | GET | both | TODO | 200, 401, 403 | 🔴 |
| /v1/health | GET | both | TODO | 200 | 🔴 |
| /v1/ready | GET | both | TODO | 200, 503 | 🔴 |
| /.well-known/jwks.json | GET | openapi-only 🔴 | TODO | 200 | 🔴 |
| /v1/services | GET | openapi-only 🔴 | TODO | 200, 401 | 🔴 |
| /v1/services | POST | openapi-only 🔴 | TODO | 201, 400 | 🔴 |
| /v1/agents | GET | openapi-only 🔴 | TODO | 200, 401 | 🔴 |
| /v1/agents | POST | openapi-only 🔴 | TODO | 201, 400 | 🔴 |
| /v1/audit | GET | openapi-only 🔴 | TODO | 200, 401 | 🔴 |
| /v1/admin/settings | GET | both | TODO | 200, 401, 403 | 🔴 |
| /v1/admin/settings | PATCH | both | TODO | 200, 401, 403, 409 | 🔴 |
| /v1/admin/audit/verify-chain | POST | router-only 🟡 | TODO | TODO | 🔴 |
| /v1/admin/audit/acknowledge-tamper | POST | router-only 🟡 | TODO | TODO | 🔴 |
| /v1/internal/validate-agent-key | POST | router-only 🟡 | TODO | TODO | 🔴 |
| /v1/internal/proxy-hit | POST | router-only 🟡 | TODO | TODO | 🔴 |
| /v1/proxy/call/{service_id}/{path_suffix} | GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD | router-only 🟡 | TODO | TODO | 🔴 |

---

## Gap Analysis Notes

### OpenAPI-only gaps (not implemented in FastAPI)
These routes are specified in the OpenAPI contract but have no matching FastAPI handler:

1. **GET /v1/auth/login** — FastAPI implements `GET /v1/auth/oidc/login` instead (path mismatch)
2. **GET /v1/auth/callback** — FastAPI implements `GET /v1/auth/oidc/callback` instead (path mismatch)
3. **GET /v1/tenants** — list all tenants (PlatformAdmin only); no handler in tenants.py
4. **GET /v1/tenants/{tenant_id}** — get single tenant; no handler
5. **PATCH /v1/tenants/{tenant_id}** — update tenant metadata; no handler
6. **DELETE /v1/tenants/{tenant_id}** — soft-delete tenant; no handler
7. **GET /v1/tenants/{tenant_id}/services/{service_id}** — get single service; no handler
8. **POST /v1/tenants/{tenant_id}/services/{service_id}/test** — test service connectivity; no handler
9. **DELETE /v1/tenants/{tenant_id}/services/{service_id}/credentials/{key_version}** — revoke credential version; no handler
10. **GET /v1/tenants/{tenant_id}/changes** — tenant-scoped changes feed; no handler
11. **GET /.well-known/jwks.json** — broker JWKS; no handler
12. **GET /v1/services** — implicit list services; no handler
13. **POST /v1/services** — implicit create service; no handler
14. **GET /v1/agents** — implicit list agents; no handler
15. **POST /v1/agents** — implicit create agent; no handler
16. **GET /v1/audit** — implicit audit query; no handler (only explicit `/v1/tenants/{id}/audit` exists)

### Router-only gaps (implemented but not in OpenAPI)
These FastAPI routes have no corresponding OpenAPI contract entry:

1. **GET /v1/auth/oidc/login** — OIDC login redirect (OpenAPI has `/v1/auth/login` instead)
2. **GET /v1/auth/oidc/callback** — OIDC code exchange (OpenAPI has `/v1/auth/callback` instead)
3. **DELETE /v1/tenants/{tenant_id}/agents/{agent_id}** — hard-delete agent (OpenAPI only has revoke)
4. **POST /v1/admin/audit/verify-chain** — on-demand chain verification (not in OpenAPI)
5. **POST /v1/admin/audit/acknowledge-tamper** — tamper acknowledgment (not in OpenAPI)
6. **POST /v1/internal/validate-agent-key** — internal MCP server hook (intentionally undocumented)
7. **POST /v1/internal/proxy-hit** — internal proxy audit emission (intentionally undocumented)
8. **ALL /v1/proxy/call/{service_id}/{path_suffix}** — credential-injecting proxy (intentionally undocumented)
