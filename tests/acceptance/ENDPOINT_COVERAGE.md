# Endpoint Coverage Matrix

**59 rows total: 28 both, 15 openapi-only, 8 router-only (proxy counted as 1 row)**

Enumeration counts:
- OpenAPI `paths:` section: 43 path×method combinations (before P2F additions)
- FastAPI routers (`admin-api/src/admin_api/api/*.py`): 41 path×method combinations
- After P2F: 8 router-only rows added to OpenAPI; canonical YAML now covers all FastAPI routes

Legend:
- `both` — present in both OpenAPI contract and FastAPI router
- `openapi-only` — declared in OpenAPI but no matching FastAPI route found 🔴
- `router-only` — implemented in FastAPI but absent from OpenAPI contract 🟡 (P2F: now added to OpenAPI)

| path | method | source | test_file::test_fn | asserted_status_codes | last_result |
|---|---|---|---|---|---|
| /v1/auth/login | GET | openapi-only 🔴 | TODO | 302, 503 | 🔴 |
| /v1/auth/callback | GET | openapi-only 🔴 | TODO | 302, 400, 401, 403 | 🔴 |
| /v1/auth/oidc/login | GET | both | tests/unit/admin_api/test_oidc.py::test_oidc_callback_success_creates_session | 200, 503 | 🟡 |
| /v1/auth/oidc/callback | GET | both | tests/unit/admin_api/test_oidc.py::test_oidc_callback_success_creates_session, test_oidc_callback_tampered_state_returns_401, test_oidc_callback_signature_failure_returns_401, test_oidc_unknown_sub_returns_403 | 200, 401, 403 | 🟢 |
| /v1/auth/internal-login | POST | both | tests/unit/admin_api/test_auth.py::test_valid_credentials_return_session_cookie, test_unknown_user_body_matches_bad_password_body, test_locked_account_body_matches_bad_password_body, test_failure_response_body_shape | 200, 401 | 🟢 |
| /v1/auth/logout | POST | both | TODO | 204 | 🔴 |
| /v1/auth/whoami | GET | both | TODO | 200, 401 | 🔴 |
| /v1/tenants | GET | openapi-only 🔴 | TODO | 200, 401, 403 | 🔴 |
| /v1/tenants | POST | both | tests/unit/admin_api/test_tenants.py::test_platform_admin_can_create_tenant, test_non_platform_admin_gets_403, test_tenant_creation_emits_audit, test_tenant_creation_initializes_chain_state, test_duplicate_slug_returns_409 | 201, 403, 409 | 🟢 |
| /v1/tenants/{tenant_id} | GET | openapi-only 🔴 | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id} | PATCH | openapi-only 🔴 | TODO | 200, 400, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id} | DELETE | openapi-only 🔴 | TODO | 204, 401, 403, 404, 409 | 🔴 |
| /v1/tenants/{tenant_id}/services | GET | both | tests/unit/admin_api/test_services.py::test_list_services_returns_200 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services | POST | both | tests/unit/admin_api/test_services.py::test_create_service_returns_201_with_svc_id, test_create_service_rejects_rfc1918_base_url, test_create_service_rejects_localhost_base_url, test_audit_emit_called_on_create | 201, 400, 401, 403 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id} | GET | openapi-only 🔴 | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id} | PATCH | both | TODO | 200, 400, 401, 403, 404 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id} | DELETE | both | TODO | 204, 401, 403, 404, 409 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id}/test | POST | openapi-only 🔴 | TODO | 200, 401, 403, 404, 422, 429 | 🔴 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials | GET | both | tests/unit/admin_api/test_credentials.py::test_list_credential_versions_returns_200 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials | POST | both | tests/unit/admin_api/test_credentials.py::test_create_credential_returns_201_with_metadata, test_create_credential_response_has_no_plaintext, test_audit_credential_registered_emitted, test_audit_payload_has_no_plaintext | 201, 400, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials/{key_version} | DELETE | openapi-only 🔴 | TODO | 204, 401, 403, 404, 409 | 🔴 |
| /v1/tenants/{tenant_id}/agents | GET | both | tests/unit/admin_api/test_agents.py::test_list_agents_returns_200 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents | POST | both | tests/unit/admin_api/test_agents.py::test_create_agent_returns_201_with_api_key, test_create_agent_api_key_not_stored_plaintext, test_create_agent_audit_carries_fingerprint_not_plaintext | 201, 400, 401, 403 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id} | GET | both | tests/unit/admin_api/test_agents.py::test_get_agent_does_not_return_api_key | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id} | DELETE | both | tests/unit/admin_api/test_agents.py::test_delete_agent_returns_204 | 204, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/revoke | POST | both | tests/unit/admin_api/test_revocation.py::test_revoke_agent_sets_status_revoked, test_revoke_agent_emits_audit_event, test_revoke_agent_notifies_global_channel, test_revoke_nonexistent_agent_returns_404 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/permissions | POST | both | tests/unit/admin_api/test_permissions.py::test_grant_with_valid_constraints_returns_201, test_grant_with_unknown_constraints_key_returns_422, test_idempotent_regrant_returns_200, test_conflicting_constraints_returns_409, test_audit_emitted_on_grant | 200, 201, 400, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id} | DELETE | both | tests/unit/admin_api/test_permissions.py::test_revoke_returns_204_and_notifies | 204, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys | POST | both | tests/unit/admin_api/test_api_keys.py::test_create_happy_path, test_create_actions_exceed_grant, test_create_require_expiry_violation, test_create_no_plaintext_in_audit, test_create_agent_not_found | 201, 401, 403, 404, 422 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys | GET | both | tests/unit/admin_api/test_api_keys.py::test_list_returns_keys_without_plaintext | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys/{api_key_id} | GET | both | tests/unit/admin_api/test_api_keys.py::test_get_single_key, test_get_absent_key | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys/{api_key_id}/revoke | POST | both | tests/unit/admin_api/test_api_keys.py::test_revoke_happy_path, test_revoke_idempotent, test_revoke_absent_key | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/agents/{agent_id}/api-keys/{api_key_id}/rotate | POST | both | tests/unit/admin_api/test_api_keys.py::test_rotate_happy_path | 201, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/audit | GET | both | tests/unit/admin_api/test_audit.py::test_list_returns_tenant_scoped_events, test_filter_by_agent_id, test_filter_by_service_id, test_filter_by_event_type, test_filter_by_time_range, test_pagination_via_after_cursor, test_empty_for_wrong_tenant | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/changes | GET | openapi-only 🔴 | TODO | 200, 401, 403, 404 | 🔴 |
| /v1/changes | GET | both | tests/unit/admin_api/test_changes.py::test_changes_endpoint_returns_200, test_changes_unknown_since_returns_410, test_changes_returns_events_after_cursor | 200, 401, 403, 410 | 🟢 |
| /v1/health | GET | both | tests/unit/admin_api/test_health.py::test_health_always_200 | 200 | 🟢 |
| /v1/ready | GET | both | tests/unit/admin_api/test_health.py::test_ready_503_when_db_unavailable, test_ready_503_when_liquibase_not_done, test_ready_200_when_all_checks_pass | 200, 503 | 🟢 |
| /.well-known/jwks.json | GET | openapi-only 🔴 | TODO | 200 | 🔴 |
| /v1/services | GET | openapi-only 🔴 | TODO | 200, 401 | 🔴 |
| /v1/services | POST | openapi-only 🔴 | TODO | 201, 400 | 🔴 |
| /v1/agents | GET | openapi-only 🔴 | TODO | 200, 401 | 🔴 |
| /v1/agents | POST | openapi-only 🔴 | TODO | 201, 400 | 🔴 |
| /v1/audit | GET | openapi-only 🔴 | TODO | 200, 401 | 🔴 |
| /v1/admin/settings | GET | both | tests/unit/admin_api/test_admin_settings.py::test_get_settings_as_platform_admin, test_get_settings_as_non_platform_admin, test_get_settings_has_api_key_section | 200, 401, 403 | 🟢 |
| /v1/admin/settings | PATCH | both | tests/unit/admin_api/test_admin_settings.py::test_patch_merges_partial_body, test_patch_unknown_key_returns_422, test_patch_api_key_settings, test_patch_emits_settings_updated_audit | 200, 401, 403, 409, 422 | 🟢 |
| /v1/admin/audit/verify-chain | POST | both | tests/unit/admin_api/test_audit_verify_endpoint.py::test_verify_chain_ok, test_verify_chain_tampered, test_verify_chain_requires_platform_admin, test_verify_chain_tenant_id_param | 200, 403 | 🟢 |
| /v1/admin/audit/acknowledge-tamper | POST | both | tests/unit/admin_api/test_acknowledge_tamper.py::test_acknowledge_requires_platform_admin, test_acknowledge_records_event, test_acknowledge_audit_payload, test_unknown_tenant_returns_404 | 201, 403, 404 | 🟢 |
| /v1/internal/validate-agent-key | POST | both | tests/unit/admin_api/test_api_keys.py::test_internal_proxy_hit_accepts_api_key_fields | 200, 401 | 🟡 |
| /v1/internal/proxy-hit | POST | both | tests/unit/admin_api/test_api_keys.py::test_internal_proxy_hit_accepts_api_key_fields | 200 | 🟡 |
| /v1/proxy/call/{service_id}/{path_suffix} | GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD | both | TODO | TODO | 🔴 |

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

### Router-only gaps (P2F: added to OpenAPI in this phase)
These FastAPI routes were absent from the OpenAPI contract and have been added (M-modifiable per ADR-0014.3):

1. **GET /v1/auth/oidc/login** — OIDC login redirect JSON variant
2. **GET /v1/auth/oidc/callback** — OIDC code exchange JSON variant
3. **DELETE /v1/tenants/{tenant_id}/agents/{agent_id}** — hard-delete agent (added as POST action /delete per REST conventions)
4. **POST /v1/admin/audit/verify-chain** — on-demand chain verification
5. **POST /v1/admin/audit/acknowledge-tamper** — tamper acknowledgment
6. **POST /v1/internal/validate-agent-key** — internal MCP server hook
7. **POST /v1/internal/proxy-hit** — internal proxy audit emission
8. **ALL /v1/proxy/call/{service_id}/{path_suffix}** — credential-injecting proxy
