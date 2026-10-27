# Verification: openspec:proxy-budget-check: PASS (round 1)

traceability: 5/5 criteria covered by a discriminating test

- Base: `981d46b5e635ff3492828fe0ba270bd050a197c5`
- Head: `1a958ee0821675e7e4c23918772981a3cb569f6b`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `3baa11a8d7618047681a722c21e5be365a7be4f9e65b9ed9da7833803850c4bb`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.7179

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base staging@981d46b5e6 contained |
| 1 | integrity | ok | 294.8 | 10 sub-checks; scope: 8 changed file(s) |
| 2 | build | ok | 80.0 |  |
| 3 | tests | ok | 110.7 |  |
| 4 | traceability | ok | 0.1 | 5/5 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/proxy-plugin/cmd/proxy-plugin/budget_wiring.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/budget/store.go |
| 8 | s1 judge | ok | 0.8 | 5/5 criteria judged by jev |
| 9 | judge | ok | 22.7 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261027T0603Z-1870/064-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261027T0603Z-1870/065-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261027T0603Z-1870/066-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261027T0603Z-1870/067-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261027T0603Z-1870/068-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261027T0603Z-1870/069-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261027T0603Z-1870/070-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261027T0603Z-1870/071-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261027T0603Z-1870/072-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261027T0603Z-1870/073-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261027T0603Z-1870/074-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261027T0603Z-1870/075-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261027T0603Z-1870/076-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | skipped | no test file changed |
| red-green freeze | ok | 1 task(s): red and green compared |
| test path freeze | ok | 1 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/proxy-plugin/cmd/proxy-plugin/budget_wiring.go, apps/proxy-plugin/cmd/proxy-plugin/budget_wiring_test.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/budget/store.go |
| tdd history | ok | 1 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2739 of 2739 base tests pass on the unit's code with its 1 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-f99d7123 | proxy-budget-enforcement › The proxy enforces the budget of the grant of the token's action › the grant's budget is counted and enforced | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetIsReadFromTheGrantOfTheTokenAction_C_f99d7123 (passed, red_assertion) | - | 0.94 |
| C-5de8ad4b | proxy-budget-enforcement › The proxy enforces the budget of the grant of the token's action › a configuration change clears the cache | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetGrantCacheIsClearedByConfigUpdate_C_5de8ad4b (passed, red_assertion) | - | 0.92 |
| C-a925216c | proxy-budget-enforcement › Budget statements run in a transaction scoped to the token's tenant › the lookup and the counter run inside tenant transactions | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetStatementsRunInTenantTransaction_C_a925216c (passed, red_assertion) | - | 0.94 |
| C-08746266 | proxy-budget-enforcement › The budget check fails open › a lookup error lets the request through | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetLookupFailureFailsOpen_C_08746266 (passed, red_assertion) | - | 0.90 |
| C-04da2393 | proxy-budget-enforcement › The budget check fails open › identifiers that are not UUIDs are not looked up | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetLookupSkippedForNonUUIDIdentifiers_C_04da2393 (passed, red_assertion) | - | 0.86 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/proxy-plugin/cmd/proxy-plugin/budget_wiring.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/budget_wiring_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/budget/store.go` | proxy-plugin | relevant | named in the spec |
| `openspec/changes/proxy-budget-check/.l4/ledger/r-20261027T0558Z-d4a7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-budget-check/.l4/ledger/r-20261027T0603Z-1870.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-budget-check/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-budget-check/tasks.md` |  | none | exempt: harness, spec or documentation path |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/proxy-plugin/cmd/proxy-plugin/budget_wiring.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/budget/store.go

### Tests

2745 of 2799 passed, 0 failed, 0 errored, 54 skipped.
5 of 5 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-f99d7123 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5de8ad4b | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a925216c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-08746266 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-04da2393 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-f99d7123 | proxy-budget-enforcement › The proxy enforces the budget of the grant of the token's action › the grant's budget is counted and enforced | pass | pass | the judge passed it and a discriminating test passes |
| C-5de8ad4b | proxy-budget-enforcement › The proxy enforces the budget of the grant of the token's action › a configuration change clears the cache | pass | pass | the judge passed it and a discriminating test passes |
| C-a925216c | proxy-budget-enforcement › Budget statements run in a transaction scoped to the token's tenant › the lookup and the counter run inside tenant transactions | pass | pass | the judge passed it and a discriminating test passes |
| C-08746266 | proxy-budget-enforcement › The budget check fails open › a lookup error lets the request through | pass | pass | the judge passed it and a discriminating test passes |
| C-04da2393 | proxy-budget-enforcement › The budget check fails open › identifiers that are not UUIDs are not looked up | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Cache TTL and failure-not-retried not tested by time (spec gap) (criterion C-08746266): No test advances time to show the 5 s expiry; the TTL is verified only by code reading. Also, a lookup with a timeout or ErrNoTenant is cached as none.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetGrantCacheIsClearedByConfigUpdate_C_5de8ad4b` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetIsReadFromTheGrantOfTheTokenAction_C_f99d7123` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetLookupFailureFailsOpen_C_08746266` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetLookupSkippedForNonUUIDIdentifiers_C_04da2393` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestBudgetStatementsRunInTenantTransaction_C_a925216c` (task 1.1): passed
