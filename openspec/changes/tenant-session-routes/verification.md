# Verification: openspec:tenant-session-routes: PASS (round 1)

traceability: 6/6 criteria covered by a discriminating test

- Base: `988b49fcbfbe2aaac52bb518cd4c5b2254cad7a0`
- Head: `7dab5fd21ee96da6e81582f1da4c3e4d3d977cf5`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `4a059ed8fb25592bb837cbcf6980b33f61b09d332a6237d856f0da445345c683`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.7480

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base staging@988b49fcbf contained |
| 1 | integrity | ok | 421.0 | 11 sub-checks; scope: 8 changed file(s) |
| 2 | build | ok | 139.8 |  |
| 3 | tests | ok | 157.1 |  |
| 4 | traceability | ok | 0.1 | 6/6 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 0.3 | 4/6 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 9.9 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261126T1105Z-063b/115-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261126T1105Z-063b/116-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261126T1105Z-063b/117-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261126T1105Z-063b/118-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261126T1105Z-063b/119-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261126T1105Z-063b/120-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261126T1105Z-063b/121-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261126T1105Z-063b/122-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261126T1105Z-063b/123-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261126T1105Z-063b/124-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261126T1105Z-063b/125-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261126T1105Z-063b/126-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261126T1105Z-063b/127-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 2 test file(s) compared with the base |
| red-green freeze | ok | 2 task(s): red and green compared |
| test path freeze | ok | 2 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 2 task(s); red tests passing at head: step 3 |
| python encoding | ok | 5 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 2804 of 2804 base tests pass on the unit's code with its 2 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-f8838ac0 | tenant-session-routes › Every tenant-scoped route requires the tenant session › every tenant-scoped route has the dependency | covered | tests.unit.admin_api.test_tenant_session_routes::test_every_tenant_scoped_route_has_the_tenant_session (passed, red_assertion) | - | 0.94 |
| C-b77996cc | tenant-session-routes › Every tenant-scoped route requires the tenant session › a request without a session is refused before any statement | covered | tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[get-budget-consumers] (passed, red_assertion); tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[get-budget] (passed, red_... | - | - |
| C-f7eab4f7 | tenant-session-routes › Every tenant-scoped route requires the tenant session › an unknown or expired session is refused before any statement | covered | tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[get-budget-consumers] (passed, red_assertion); tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[get-budget] (passed, ... | - | 0.91 |
| C-89b1b8a2 | tenant-session-routes › Every tenant-scoped route requires the tenant session › a session of another tenant is refused before any statement | covered | tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[get-budget-consumers] (passed, red_assertion); tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[get-budget] (passed, red_... | - | 0.94 |
| C-8284500b | tenant-session-routes › Every tenant-scoped route requires the tenant session › a session of the tenant, or a platform admin, reaches the handler | covered | tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[get-budget-consumers] (passed, pre_satisfied); tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[get-budget] (pass... | - | - |
| C-063b76ce | tenant-session-routes › A background document describes the governance model › the document has its shape | covered | tests.unit.admin_api.test_agent_governance_doc::test_document_has_its_shape (passed, red_assertion) | - | 0.93 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/budget_consumers.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/budgets.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/permissions.py` | admin-api | relevant | named in the spec |
| `docs/architecture/agent-governance.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/tenant-session-routes/.l4/ledger/r-20261126T1105Z-063b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/tenant-session-routes/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `tests/unit/admin_api/test_agent_governance_doc.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_tenant_session_routes.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2835 of 2889 passed, 0 failed, 0 errored, 54 skipped.
30 of 30 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-f8838ac0 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b77996cc | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-f7eab4f7 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-89b1b8a2 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8284500b | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-063b76ce | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-f8838ac0 | tenant-session-routes › Every tenant-scoped route requires the tenant session › every tenant-scoped route has the dependency | pass | pass | the judge passed it and a discriminating test passes |
| C-b77996cc | tenant-session-routes › Every tenant-scoped route requires the tenant session › a request without a session is refused before any statement | pass | pass | the judge passed it and a discriminating test passes |
| C-f7eab4f7 | tenant-session-routes › Every tenant-scoped route requires the tenant session › an unknown or expired session is refused before any statement | pass | pass | the judge passed it and a discriminating test passes |
| C-89b1b8a2 | tenant-session-routes › Every tenant-scoped route requires the tenant session › a session of another tenant is refused before any statement | pass | pass | the judge passed it and a discriminating test passes |
| C-8284500b | tenant-session-routes › Every tenant-scoped route requires the tenant session › a session of the tenant, or a platform admin, reaches the handler | pass | pass | the judge passed it and a discriminating test passes |
| C-063b76ce | tenant-session-routes › A background document describes the governance model › the document has its shape | pass | pass | the judge passed it and a discriminating test passes |

## Findings

None.

## New tests (red then green, `task.red_ok` in the ledger)

- `tests.unit.admin_api.test_agent_governance_doc::test_document_has_its_shape` (task 2.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[get-budget-consumers]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[get-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[get-permission-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[get-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[patch-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[post-budget-reset]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_another_tenant_is_refused_before_any_statement[post-permission-budget-reset]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[get-budget-consumers]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[get-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[get-permission-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[get-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[patch-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[post-budget-reset]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler[post-permission-budget-reset]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[get-budget-consumers]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[get-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[get-permission-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[get-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[patch-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[post-budget-reset]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_an_unknown_or_expired_session_is_refused_before_any_statement[post-permission-budget-reset]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_every_tenant_scoped_route_has_the_tenant_session` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[get-budget-consumers]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[get-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[get-permission-budget]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[get-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[patch-permission]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[post-budget-reset]` (task 1.1): passed
- `tests.unit.admin_api.test_tenant_session_routes::test_requests_without_a_session_are_refused_before_any_statement[post-permission-budget-reset]` (task 1.1): passed
