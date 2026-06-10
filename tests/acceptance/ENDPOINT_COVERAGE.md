# Endpoint Coverage Matrix

## WS-8 Cross-Stack Golden-Path E2E Test

`test_golden_path.py` is the single test that exercises the complete production data flow end-to-end:
agent → MCP bootstrap → MCP request_token → admin-api validate-agent-key → broker JWT issuance →
Kong/proxy-plugin JWT verification → vault-adapter credential fetch → mock-backend upstream.

To run:
```sh
# Requires the docker-compose stack to be running
make dev            # start the stack (first time)
make test-golden    # run the golden-path test
# or directly:
MINTKEY_INTEGRATION_TEST=true python3 -m pytest tests/acceptance/test_golden_path.py -v -s
```

**Current status (WS-8):** The test surfaces a cross-stack regression at Hop 4 (proxy→vault).
`admin-api/src/admin_api/services/vault_client.py` uses an in-memory stub instead of calling the
real vault-adapter gRPC endpoint. Credentials stored via admin-api are never written to vault-adapter's
SQLite store, so proxy-plugin's `GetCredential` returns "not found" and the proxy returns
`502 bad gateway: vault error`. Fix tracked as WS-9: wire the real gRPC client.

The 4 structural tests (`test_golden_path_chain_components_exist`,
`test_golden_path_bootstrap_skill_has_required_sections`,
`test_golden_path_admin_api_vault_client_is_stub`,
`test_golden_path_broker_jwt_claims_present`) always run (no Docker required).



**59 rows total: 36 both, 7 openapi-only (OQ-escalated), 8 router-only (proxy counted as 1 row)**

Enumeration counts:
- OpenAPI `paths:` section: 43 path×method combinations (before P2F additions)
- FastAPI routers (`admin-api/src/admin_api/api/*.py`): 41 path×method combinations
- After P2F: 8 router-only rows added to OpenAPI; canonical YAML now covers all FastAPI routes
- After P2G: GET/PATCH/DELETE /v1/tenants/{tid} and GET /v1/tenants implemented; DELETE credentials/{kv} implemented; OQs opened for 4 routes

Legend:
- `both` — present in both OpenAPI contract and FastAPI router
- `openapi-only` — declared in OpenAPI but no matching FastAPI route found 🔴
- `router-only` — implemented in FastAPI but absent from OpenAPI contract 🟡 (P2F: now added to OpenAPI)

| path | method | source | test_file::test_fn | asserted_status_codes | last_result |
|---|---|---|---|---|---|
| /v1/auth/login | GET | openapi-only 🔴 | OQ-AUTH-01 (path mismatch — implemented as /v1/auth/oidc/login) | 302, 503 | 🔴 |
| /v1/auth/callback | GET | openapi-only 🔴 | OQ-AUTH-01 (path mismatch — implemented as /v1/auth/oidc/callback) | 302, 400, 401, 403 | 🔴 |
| /v1/auth/oidc/login | GET | both | tests/unit/admin_api/test_oidc.py::test_oidc_callback_success_creates_session, tests/integration/admin_api/test_auth.py::test_oidc_login_returns_auth_url, test_oidc_login_each_call_produces_unique_state | 200, 503 | 🟢 |
| /v1/auth/oidc/callback | GET | both | tests/unit/admin_api/test_oidc.py::test_oidc_callback_success_creates_session, test_oidc_callback_tampered_state_returns_401, test_oidc_callback_signature_failure_returns_401, test_oidc_unknown_sub_returns_403 | 200, 401, 403 | 🟢 |
| /v1/auth/internal-login | POST | both | tests/unit/admin_api/test_auth.py::test_valid_credentials_return_session_cookie, test_unknown_user_body_matches_bad_password_body, test_locked_account_body_matches_bad_password_body, test_failure_response_body_shape, tests/integration/admin_api/test_auth.py::test_internal_login_unknown_user_returns_401, test_internal_login_wrong_password_returns_401, test_internal_login_valid_credentials_returns_session_cookie | 200, 401 | 🟢 |
| /v1/auth/logout | POST | both | tests/integration/admin_api/test_auth.py::test_logout_returns_204_and_clears_cookie, test_logout_without_session_still_returns_204 | 204 | 🟢 |
| /v1/auth/whoami | GET | both | tests/integration/admin_api/test_auth.py::test_whoami_unauthenticated_returns_operator_null | 200, 401 | 🟢 |
| /v1/tenants | GET | both | tests/integration/admin_api/test_tenants.py::test_list_tenants_without_platform_admin_returns_403, test_list_tenants_returns_200_with_data | 200, 401, 403 | 🟢 |
| /v1/tenants | POST | both | tests/unit/admin_api/test_tenants.py::test_platform_admin_can_create_tenant, test_non_platform_admin_gets_403, test_tenant_creation_emits_audit, test_tenant_creation_initializes_chain_state, test_duplicate_slug_returns_409, tests/integration/admin_api/test_tenants.py::test_create_tenant_returns_201, test_create_tenant_duplicate_slug_returns_409 | 201, 403, 409 | 🟢 |
| /v1/tenants/{tenant_id} | GET | both | tests/integration/admin_api/test_tenants.py::test_get_tenant_returns_200, test_get_tenant_not_found_returns_404 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id} | PATCH | both | tests/integration/admin_api/test_tenants.py::test_patch_tenant_without_platform_admin_returns_403, test_patch_tenant_updates_display_name, test_patch_tenant_not_found_returns_404 | 200, 400, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id} | DELETE | both | tests/integration/admin_api/test_tenants.py::test_delete_tenant_without_platform_admin_returns_403, test_delete_tenant_returns_204, test_delete_tenant_not_found_returns_404, test_delete_tenant_already_deleted_returns_409 | 204, 401, 403, 404, 409 | 🟢 |
| /v1/tenants/{tenant_id}/services | GET | both | tests/unit/admin_api/test_services.py::test_list_services_returns_200 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services | POST | both | tests/unit/admin_api/test_services.py::test_create_service_returns_201_with_svc_id, test_create_service_rejects_rfc1918_base_url, test_create_service_rejects_localhost_base_url, test_audit_emit_called_on_create | 201, 400, 401, 403 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id} | GET | both | tests/integration/admin_api/test_services.py::test_get_single_service_returns_200, test_get_single_service_not_found_returns_404 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id} | PATCH | both | tests/integration/admin_api/test_services.py::test_patch_service_updates_display_name, test_patch_service_rejects_rfc1918_base_url | 200, 400, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id} | DELETE | both | tests/integration/admin_api/test_services.py::test_delete_service_returns_204 | 204, 401, 403, 404, 409 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id}/test | POST | both | tests/integration/admin_api/test_services.py::test_post_service_test_returns_ok | 200, 401, 403, 404, 422, 429 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials | GET | both | tests/unit/admin_api/test_credentials.py::test_list_credential_versions_returns_200, tests/integration/admin_api/test_credentials.py::test_list_credentials_returns_200 | 200, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials | POST | both | tests/unit/admin_api/test_credentials.py::test_create_credential_returns_201_with_metadata, test_create_credential_response_has_no_plaintext, test_audit_credential_registered_emitted, test_audit_payload_has_no_plaintext, tests/integration/admin_api/test_credentials.py::test_create_credential_returns_201 | 201, 400, 401, 403, 404 | 🟢 |
| /v1/tenants/{tenant_id}/services/{service_id}/credentials/{key_version} | DELETE | both | tests/integration/admin_api/test_credentials.py::test_delete_credential_version_returns_204, test_delete_credential_version_not_found_returns_404, test_delete_credential_version_already_revoked_returns_409 | 204, 401, 403, 404, 409 | 🟢 |
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
| /v1/tenants/{tenant_id}/changes | GET | openapi-only 🔴 | OQ-026 (SSE feed deferred — design needed) | 200, 401, 403, 404 | 🔴 |
| /v1/changes | GET | both | tests/unit/admin_api/test_changes.py::test_changes_endpoint_returns_200, test_changes_unknown_since_returns_410, test_changes_returns_events_after_cursor | 200, 401, 403, 410 | 🟢 |
| /v1/health | GET | both | tests/unit/admin_api/test_health.py::test_health_always_200 | 200 | 🟢 |
| /v1/ready | GET | both | tests/unit/admin_api/test_health.py::test_ready_503_when_db_unavailable, test_ready_503_when_liquibase_not_done, test_ready_200_when_all_checks_pass | 200, 503 | 🟢 |
| /.well-known/jwks.json | GET | openapi-only 🔴 | OQ-023 (belongs to broker service, not admin-api) | 200 | 🔴 |
| /v1/services | GET | openapi-only 🔴 | OQ-024 (tenant-prefix-less implicit route — deferred) | 200, 401 | 🔴 |
| /v1/services | POST | openapi-only 🔴 | OQ-024 (tenant-prefix-less implicit route — deferred) | 201, 400 | 🔴 |
| /v1/agents | GET | openapi-only 🔴 | OQ-024 (tenant-prefix-less implicit route — deferred) | 200, 401 | 🔴 |
| /v1/agents | POST | openapi-only 🔴 | OQ-024 (tenant-prefix-less implicit route — deferred) | 201, 400 | 🔴 |
| /v1/audit | GET | openapi-only 🔴 | OQ-025 (tenant-prefix-less audit — deferred) | 200, 401 | 🔴 |
| /v1/admin/settings | GET | both | tests/unit/admin_api/test_admin_settings.py::test_get_settings_as_platform_admin, test_get_settings_as_non_platform_admin, test_get_settings_has_api_key_section | 200, 401, 403 | 🟢 |
| /v1/admin/settings | PATCH | both | tests/unit/admin_api/test_admin_settings.py::test_patch_merges_partial_body, test_patch_unknown_key_returns_422, test_patch_api_key_settings, test_patch_emits_settings_updated_audit | 200, 401, 403, 409, 422 | 🟢 |
| /v1/admin/audit/verify-chain | POST | both | tests/unit/admin_api/test_audit_verify_endpoint.py::test_verify_chain_ok, test_verify_chain_tampered, test_verify_chain_requires_platform_admin, test_verify_chain_tenant_id_param | 200, 403 | 🟢 |
| /v1/admin/audit/acknowledge-tamper | POST | both | tests/unit/admin_api/test_acknowledge_tamper.py::test_acknowledge_requires_platform_admin, test_acknowledge_records_event, test_acknowledge_audit_payload, test_unknown_tenant_returns_404 | 201, 403, 404 | 🟢 |
| /v1/internal/validate-agent-key | POST | both | tests/unit/admin_api/test_api_keys.py::test_internal_proxy_hit_accepts_api_key_fields | 200, 401 | 🟡 |
| /v1/internal/proxy-hit | POST | both | tests/unit/admin_api/test_api_keys.py::test_internal_proxy_hit_accepts_api_key_fields | 200 | 🟡 |
| /v1/proxy/call/{service_id}/{path_suffix} | GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD | both | TODO (proxy call — requires Kong/egress proxy in acceptance suite) | TODO | 🔴 |
| /v1/tenants/{tenant_id}/agent-secrets | GET | both | scripts/e2e_smoke.py::step_agent_secrets (operator metadata list — no canary) | 200 | 🟡 |
| /v1/tenants/{tenant_id}/agent-secrets/{secret_id} | GET | both | scripts/e2e_smoke.py::step_agent_secrets (operator metadata get) | 200, 404 | 🟡 |
| /v1/tenants/{tenant_id}/agent-secrets/{secret_id} | DELETE | both | scripts/e2e_smoke.py::step_agent_secrets (operator hard-delete, idempotent 204) | 204 | 🟡 |
| /v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants | POST | both | scripts/e2e_smoke.py::step_agent_secrets (operator grant to B) | 201, 409 | 🟡 |
| /v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants | GET | both | tests/unit/admin_api/test_agent_secrets.py | 200, 404 | 🟡 |
| /v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants/{grant_id} | DELETE | both | scripts/e2e_smoke.py::step_agent_secrets (operator revoke, idempotent 204) | 204 | 🟡 |
| /v1/tools/secret_put | POST | both (MCP server) | scripts/e2e_smoke.py::step_agent_secrets (A put canary) | 200, 401, 422 | 🟡 |
| /v1/tools/secret_get | GET | both (MCP server) | scripts/e2e_smoke.py::step_agent_secrets (A owner read, B shared read, B post-revocation 404) | 200, 401, 404 | 🟡 |
| /v1/tools/secret_list | GET | both (MCP server) | scripts/e2e_smoke.py::step_agent_secrets (A owner list, B shared list) | 200, 401 | 🟡 |
| /v1/tools/secret_delete | DELETE | both (MCP server) | scripts/e2e_smoke.py::step_agent_secrets (A delete, idempotent re-delete) | 200, 401 | 🟡 |

---

## Gap Analysis Notes

### OQ-escalated openapi-only routes (not to be implemented in admin-api)

1. **GET /v1/auth/login** — path mismatch; FastAPI implements `/v1/auth/oidc/login` (OQ-AUTH-01)
2. **GET /v1/auth/callback** — path mismatch; FastAPI implements `/v1/auth/oidc/callback` (OQ-AUTH-01)
3. **GET /v1/tenants/{tenant_id}/changes** — SSE feed; deferred (OQ-026)
4. **GET /.well-known/jwks.json** — belongs to broker service, not admin-api (OQ-023)
5. **GET /v1/services**, **POST /v1/services** — implicit tenant-prefix-less routes; deferred (OQ-024)
6. **GET /v1/agents**, **POST /v1/agents** — implicit tenant-prefix-less routes; deferred (OQ-024)
7. **GET /v1/audit** — tenant-prefix-less audit; deferred (OQ-025)

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
