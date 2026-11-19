# Verification: openspec:agent-auth-unavailable: PASS (round 1)

traceability: 12/12 criteria covered by a discriminating test

- Base: `2bdc6c769afac3dfb9e6dc983171072caa633985`
- Head: `42941995b4cb6ddcfca954b7c5b7f8d376b88ab8`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `d9d4d8b2202110f0e3f4824a16abad3ac066c41c9d4de93e232c8c6117d5c86b`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $0.7231

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.5 | base merged: staging@2bdc6c769a as 42941995b4 (3 commits) |
| 1 | integrity | ok | 445.1 | 10 sub-checks; scope: 18 changed file(s) |
| 2 | build | ok | 130.8 |  |
| 3 | tests | ok | 169.1 |  |
| 4 | traceability | ok | 0.1 | 12/12 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 1.3 | 12/12 criteria judged by jev |
| 9 | judge | ok | 17.1 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261025T1532Z-ccf2/039-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261025T1532Z-ccf2/040-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261025T1532Z-ccf2/041-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261025T1532Z-ccf2/042-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261025T1532Z-ccf2/043-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261025T1532Z-ccf2/044-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261025T1532Z-ccf2/045-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261025T1532Z-ccf2/046-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261025T1532Z-ccf2/047-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261025T1532Z-ccf2/048-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261025T1532Z-ccf2/049-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261025T1532Z-ccf2/050-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261025T1532Z-ccf2/051-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base (+2 changed by humans, listed) |
| pre-existing tests | ok | 3 test file(s) compared with the base |
| red-green freeze | ok | 3 task(s): red and green compared |
| test path freeze | ok | 3 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 1 new suppression(s), 1 declared |
| tdd history | ok | 3 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2612 of 2612 base tests pass on the unit's code with its 2 test and support files at the base (base: base worktree) |

Declared suppressions:
- tests/acceptance/test_admin_api_verify_capacity.py:23 # noqa: E402 (declared: The import follows the sys.path setup that makes the local admin_api package importable without installation.)

## Protected paths changed by humans (allowed, L4-SEC-004)

- `infra/compose/docker-compose.ghcr.yml`: 1b1e9d2f72 by CiprianSpot
- `infra/compose/docker-compose.yml`: 1b1e9d2f72 by CiprianSpot

## Pre-existing tests changed with an allowance (L4-VER-031)

- apps/mcp-server/tests/test_rest_auth_unavailable.py kept at head for the run (task 1.1: unfrozen by Q-001)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-0bbc396d | agent-key-auth › A REST request whose agent key could not be checked gets 503 auth_unavailable › admin-api cannot judge the key on list_services | covered | apps.mcp-server.tests.test_rest_auth_unavailable::test_C_0bbc396d_list_services_unjudged_key_gets_503_without_using_session (passed, red_assertion) | - | 0.95 |
| C-9a964586 | agent-key-auth › A REST request whose agent key could not be checked gets 503 auth_unavailable › the same answer on request_token and with X-API-Key | covered | apps.mcp-server.tests.test_rest_auth_unavailable::test_C_9a964586_request_token_unjudged_x_api_key_gets_same_503 (passed, red_assertion) | - | 0.89 |
| C-b6439852 | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › an unexpected error in the verify of a known agent | covered | tests.unit.admin_api.test_validate_agent_key_errors::test_C_b6439852_unexpected_verify_error_answers_503 (passed, red_assertion) | - | 0.93 |
| C-51ef8acf | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › a mismatch is still a 401 | covered | tests.unit.admin_api.test_validate_agent_key_errors::test_C_51ef8acf_verify_mismatch_is_still_401 (passed, pre_satisfied) | - | 0.92 |
| C-60c778ab | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › an invalid stored hash is still a 401 | covered | tests.unit.admin_api.test_validate_agent_key_errors::test_C_60c778ab_invalid_stored_hash_is_still_401 (passed, pre_satisfied) | - | 0.89 |
| C-f73110db | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › an unknown key stays a 401 whatever the dummy verify raises | covered | tests.unit.admin_api.test_validate_agent_key_errors::test_C_f73110db_unknown_key_stays_401_when_dummy_verify_raises (passed, pre_satisfied) | - | 0.92 |
| C-55531051 | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › a cancelled request is not turned into an answer | covered | tests.unit.admin_api.test_validate_agent_key_errors::test_C_55531051_cancelled_verify_propagates (passed, pre_satisfied) | - | 0.92 |
| C-cbd20f5c | agent-key-auth › admin-api's memory limit fits its verify concurrency › the three definitions fit the rule | covered | tests.acceptance.test_admin_api_verify_capacity::test_C_cbd20f5c_three_definitions_fit_the_rule (passed, zero_value) | - | 0.84 |
| C-06752b13 | agent-key-auth › admin-api's memory limit fits its verify concurrency › a definition that does not fit is reported | covered | tests.acceptance.test_admin_api_verify_capacity::test_C_06752b13_capacity_problem_reports_a_definition_below_the_rule (passed, zero_value) | - | 0.88 |
| C-f6faf63f | agent-key-auth › admin-api's memory limit fits its verify concurrency › a definition without a limit is not checked | covered | tests.acceptance.test_admin_api_verify_capacity::test_C_f6faf63f_capacity_problem_ignores_a_definition_without_a_limit (passed, zero_value) | - | 0.89 |
| C-434fcc7f | agent-key-auth › admin-api's memory limit fits its verify concurrency › memory values convert, and others are refused | covered | tests.acceptance.test_admin_api_verify_capacity::test_C_434fcc7f_to_mib_converts_memory_units_and_refuses_others (passed, zero_value) | - | 0.88 |
| C-e54cc104 | agent-key-auth › admin-api's memory limit fits its verify concurrency › a broken definition fails the test, never skips it | covered | tests.acceptance.test_admin_api_verify_capacity::test_C_e54cc104_compose_concurrency_refuses_a_non_integer_value (passed, zero_value) | - | 0.91 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/internal.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/capacity.py` | admin-api | relevant | module `admin-api` is named in the spec |
| `apps/mcp-server/src/mcp_server/main.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/tests/test_rest_auth_unavailable.py` |  | relevant | new test file |
| `deploy/helm/mintkey/values.yaml` | deploy | relevant | named in the spec |
| `infra/compose/docker-compose.ghcr.yml` |  | none | changed by human commit 1b1e9d2f72 |
| `infra/compose/docker-compose.yml` |  | none | changed by human commit 1b1e9d2f72 |
| `openspec/changes/agent-auth-unavailable/.l4/ledger/r-20261025T0813Z-a663.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/.l4/ledger/r-20261025T0835Z-88e7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/.l4/ledger/r-20261025T1115Z-b78d.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/.l4/ledger/r-20261025T1532Z-ccf2.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/design.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/specs/agent-key-auth/spec.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-auth-unavailable/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `tests/acceptance/test_admin_api_verify_capacity.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_validate_agent_key_errors.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2625 of 2679 passed, 0 failed, 0 errored, 54 skipped.
12 of 12 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-0bbc396d | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9a964586 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b6439852 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-51ef8acf | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-60c778ab | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f73110db | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-55531051 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-cbd20f5c | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-06752b13 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f6faf63f | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-434fcc7f | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e54cc104 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-0bbc396d | agent-key-auth › A REST request whose agent key could not be checked gets 503 auth_unavailable › admin-api cannot judge the key on list_services | pass | pass | the judge passed it and a discriminating test passes |
| C-9a964586 | agent-key-auth › A REST request whose agent key could not be checked gets 503 auth_unavailable › the same answer on request_token and with X-API-Key | pass | pass | the judge passed it and a discriminating test passes |
| C-b6439852 | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › an unexpected error in the verify of a known agent | pass | pass | the judge passed it and a discriminating test passes |
| C-51ef8acf | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › a mismatch is still a 401 | pass | pass | the judge passed it and a discriminating test passes |
| C-60c778ab | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › an invalid stored hash is still a 401 | pass | pass | the judge passed it and a discriminating test passes |
| C-f73110db | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › an unknown key stays a 401 whatever the dummy verify raises | pass | pass | the judge passed it and a discriminating test passes |
| C-55531051 | agent-key-auth › admin-api answers 503 when the verify fails for a reason other than the key › a cancelled request is not turned into an answer | pass | pass | the judge passed it and a discriminating test passes |
| C-cbd20f5c | agent-key-auth › admin-api's memory limit fits its verify concurrency › the three definitions fit the rule | pass | pass | the judge passed it and a discriminating test passes |
| C-06752b13 | agent-key-auth › admin-api's memory limit fits its verify concurrency › a definition that does not fit is reported | pass | pass | the judge passed it and a discriminating test passes |
| C-f6faf63f | agent-key-auth › admin-api's memory limit fits its verify concurrency › a definition without a limit is not checked | pass | pass | the judge passed it and a discriminating test passes |
| C-434fcc7f | agent-key-auth › admin-api's memory limit fits its verify concurrency › memory values convert, and others are refused | pass | pass | the judge passed it and a discriminating test passes |
| C-e54cc104 | agent-key-auth › admin-api's memory limit fits its verify concurrency › a broken definition fails the test, never skips it | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Whitespace/negative inputs of to_mib and compose_concurrency not pinned (spec gap) (criterion C-434fcc7f): to_mib uses fullmatch with \d+, so '512m\n' is refused but unspecified cases like '0m' or int(' 4 ') in compose_concurrency are accepted by int(); no scenario pins them.

## New tests (red then green, `task.red_ok` in the ledger)

- `apps.mcp-server.tests.test_rest_auth_unavailable::test_C_0bbc396d_list_services_unjudged_key_gets_503_without_using_session` (task 1.1): passed
- `apps.mcp-server.tests.test_rest_auth_unavailable::test_C_9a964586_request_token_unjudged_x_api_key_gets_same_503` (task 1.1): passed
- `tests.acceptance.test_admin_api_verify_capacity::test_C_06752b13_capacity_problem_reports_a_definition_below_the_rule` (task 3.1): passed
- `tests.acceptance.test_admin_api_verify_capacity::test_C_434fcc7f_to_mib_converts_memory_units_and_refuses_others` (task 3.1): passed
- `tests.acceptance.test_admin_api_verify_capacity::test_C_cbd20f5c_three_definitions_fit_the_rule` (task 3.1): passed
- `tests.acceptance.test_admin_api_verify_capacity::test_C_e54cc104_compose_concurrency_refuses_a_non_integer_value` (task 3.1): passed
- `tests.acceptance.test_admin_api_verify_capacity::test_C_f6faf63f_capacity_problem_ignores_a_definition_without_a_limit` (task 3.1): passed
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_51ef8acf_verify_mismatch_is_still_401` (task 2.1): passed
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_55531051_cancelled_verify_propagates` (task 2.1): passed
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_60c778ab_invalid_stored_hash_is_still_401` (task 2.1): passed
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_b6439852_unexpected_verify_error_answers_503` (task 2.1): passed
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_f73110db_unknown_key_stays_401_when_dummy_verify_raises` (task 2.1): passed

## Guard events

- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: infra/compose/docker-compose.ghcr.yml
- guard.violation: infra/compose/docker-compose.yml
