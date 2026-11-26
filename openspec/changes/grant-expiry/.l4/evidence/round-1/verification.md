# Verification: openspec:grant-expiry: FAIL (round 1)

traceability: not checked (an earlier step failed)

- Base: `8e8999377566a6450daca896c6e64250dc0f4954`
- Head: `928b53e1b8f8c25a5b8990546b4b849def7d66f5`
- Implementer profiles: deepseek, glm
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base merged: staging@8e89993775 as 928b53e1b8 (1 commit) |
| 1 | integrity | ok | 401.8 | 11 sub-checks; scope: 26 changed file(s) |
| 2 | build | ok | 88.9 |  |
| 3 | tests | failed | 112.4 | `sh .l4/gates/test.sh` failed: exit code 1; failing: apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants, apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants; apps.mcp-server.tests.test_grant_expiry_di... |
| 4 | traceability | not_run | 0.0 | an earlier step failed |
| 4a | audit sampling | not_run | 0.0 | an earlier step failed |
| 5 | ui test generation | not_run | 0.0 | an earlier step failed |
| 6 | quality | not_run | 0.0 | an earlier step failed |
| 8 | s1 judge | not_run | 0.0 | an earlier step failed |
| 9 | judge | not_run | 0.0 | an earlier step failed |
| 10 | aggregation | ok | 0.0 | FAIL |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261126T1923Z-1f47/195-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261126T1923Z-1f47/196-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261126T1923Z-1f47/197-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261126T1923Z-1f47/198-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261126T1923Z-1f47/199-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261126T1923Z-1f47/200-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261126T1923Z-1f47/201-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261126T1923Z-1f47/202-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261126T1923Z-1f47/203-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261126T1923Z-1f47/204-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261126T1923Z-1f47/205-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261126T1923Z-1f47/206-typecheck.log |
| test | fail | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261126T1923Z-1f47/207-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 9 test file(s) compared with the base; changed in place, named by the task text: tests.unit.admin_api.test_permissions::test_revoke_returns_204_and_notifies (named by the task text, plan:agent-governance@eaa790f81c1e3e73) |
| red-green freeze | ok | 8 task(s): red and green compared |
| test path freeze | ok | 8 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 5 new suppression(s), 5 declared |
| tdd history | ok | 8 task(s); red tests passing at head: step 3 |
| python encoding | ok | 18 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 2872 of 2872 base tests pass on the unit's code with its 9 test and support files at the base (base: base worktree) |

Declared suppressions:
- tests/unit/admin_api/test_grant_expiry_rules.py:27 # noqa: E402 (declared: import of admin_api.services.grant_expiry must follow the sys.path insertion for apps/admin-api/src)
- tests/unit/admin_api/test_grants_service.py:46 # noqa: E402 (declared: import follows the sys.path insertion that makes the admin-api sources importable, matching the other unit tests)
- tests/unit/admin_api/test_grants_service.py:47 # noqa: E402 (declared: import follows the sys.path insertion that makes the admin-api sources importable, matching the other unit tests)
- tests/unit/admin_api/test_grants_service.py:58 # noqa: E402 (declared: import follows the sys.path insertion that makes the admin-api sources importable, matching the other unit tests)
- tests/unit/admin_api/test_permissions_expiry.py:43 # noqa: E402 (declared: import after the repo source directories are added to sys.path, as the existing admin_api tests do)

## Pre-existing tests changed with an allowance (L4-VER-031)

- tests.unit.admin_api.test_permissions::test_revoke_returns_204_and_notifies (named by the task text, plan:agent-governance@eaa790f81c1e3e73)

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment
- blocker: new tests failed: apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants, apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/db/changelog/030-grant-expiry.yaml` | admin-api | relevant | named in the spec |
| `apps/admin-api/db/changelog/db.changelog-master.yaml` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/agents.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/api_keys.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/permissions.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/db/tables.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/services/grant_expiry.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/services/grants.py` | admin-api | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/policy/grant_expiry.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/tools/discovery.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/tools/request_token.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/tests/test_grant_expiry_discovery.py` |  | relevant | new test file |
| `apps/mcp-server/tests/test_grant_expiry_tokens.py` |  | relevant | new test file |
| `docs/architecture/contracts/events/audit-event.schema.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T1714Z-e646.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T1716Z-d1d6.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T1923Z-1f47.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `tests/unit/admin_api/test_audit_schema_grants.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grant_expiry_migration.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grant_expiry_readers.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grant_expiry_rules.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grants_service.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_permissions.py` |  | relevant | named in the spec |
| `tests/unit/admin_api/test_permissions_expiry.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2912 of 2968 passed, 2 failed, 0 errored, 54 skipped.
39 of 41 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## Criteria

None judged.

## Findings

- [blocker, deterministic] test gate failed: `sh .l4/gates/test.sh` failed: exit code 1; failing: apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants, apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants Log: `.l4-out/gates/r-20261126T1923Z-1f47/207-test.log`.
- [blocker, deterministic] new tests failed: apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants, apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants

## Fix unit

Fix unit 1 is created for these tasks:
- F-b5f87b40, F-7e9a81fb test gate failed (+1 more)

## New tests (red then green, `task.red_ok` in the ledger)

- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_filters_expired_grants` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_grant_reads_hide_expired_rows` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants` (task 4.2): failed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_grant_reads_hide_expired_rows` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants` (task 4.2): failed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_grant_reads_hide_expired_rows` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_1494d103_expired_grant_is_denied` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_18424d96_grant_select_is_ordered` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_9398f128_C_b4dd4c2b_no_expiry_behaves_as_before` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_b4dd4c2b_lifetime_function` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_f1c29313_broker_receives_shortened_lifetime` (task 4.1): passed
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_granted_payload_lists_expiry_and_grantor` (task 5.1): passed
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_revoked_payload_lists_grantor_and_revoker` (task 5.1): passed
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_token_denied_lists_grant_expired_reason` (task 5.1): passed
- `tests.unit.admin_api.test_grant_expiry_migration::test_C_48b97ae8_changelog_adds_expiry_and_grantor_columns` (task 1.1): passed
- `tests.unit.admin_api.test_grant_expiry_migration::test_C_efc458dc_core_table_has_columns_and_model_does_not` (task 1.1): passed
- `tests.unit.admin_api.test_grant_expiry_readers::test_C_b5050c3c_other_readers_ignore_expired_grants` (task 4.3): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-5-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[0-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[3600-3600]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[604800-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[99999999-7776000]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[None-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[abc-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_a3ba81c6_expiry_boundary` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_c0408375_operator_and_agent_rules` (task 2.1): passed
- `tests.unit.admin_api.test_grants_service::test_C_099f4d96_delete_returns_record_or_nothing` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_1bd65fd0_two_concurrent_writes_of_one_grant` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_20d077ee_notify_payload_pins_the_revoked_at_format` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_22b26d27_operator_and_agent_write_grants` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_7a27cadf_payload_builders` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_a6b59772_identical_returned_other_refused_expired_replaced` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[-10-expires_at_in_past]` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[604801-expires_at_too_far]` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[None-expires_at_required]` (task 2.2): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_31cf8071_revoke_names_what_it_revoked` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_52a42138_the_lists_and_the_single_grant_show_the_new_fields` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_b2b19611_invalid_and_conflicting_requests` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_c4e8685f_grantor_filter_and_unchanged_bodies` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_c997909a_a_grant_with_an_expiry` (task 3.1): passed

## Guard events

- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
