# Verification: openspec:broker-service-token-required: PASS (round 1)

traceability: 19/19 criteria covered by a discriminating test

- Base: `15919f7685eb781fea84c15d2596bdc5f42a23ec`
- Head: `c1fb7c7d4137fa626d3669287cf3b741204d5fe4`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `46bd055dfaf5c6d3f53eb745f85a44c09795261781cffb3ae66b565259aa68ca`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.7729

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base staging@15919f7685 contained |
| 1 | integrity | ok | 467.8 | 10 sub-checks; scope: 15 changed file(s) |
| 2 | build | ok | 134.0 |  |
| 3 | tests | ok | 169.0 |  |
| 4 | traceability | ok | 0.2 | 19/19 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/broker/cmd/broker/main.go, apps/broker/internal/api/issue/issue.go, apps/broker/internal/api/resolve/resolve.go, apps/broker/internal/config/config.go, apps/vault-adapter/cmd/vault-adapter/main.go and 2 more |
| 8 | s1 judge | ok | 2.1 | 19/19 criteria judged by jev |
| 9 | judge | ok | 17.3 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261025T2113Z-59fd/173-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261025T2113Z-59fd/174-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261025T2113Z-59fd/175-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261025T2113Z-59fd/176-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261025T2113Z-59fd/177-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261025T2113Z-59fd/178-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261025T2113Z-59fd/179-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261025T2113Z-59fd/180-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261025T2113Z-59fd/181-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261025T2113Z-59fd/182-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261025T2113Z-59fd/183-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261025T2113Z-59fd/184-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261025T2113Z-59fd/185-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | skipped | no test file changed |
| red-green freeze | ok | 3 task(s): red and green compared |
| test path freeze | ok | 3 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/broker/cmd/broker/main.go, apps/broker/internal/api/issue/issue.go, apps/broker/internal/api/issue/issue_empty_token_test.go, apps/broker/internal/api/resolve/resolve.go, apps/broker/internal/api/resolve/resolve_empty_token_test.go (+6 more) |
| tdd history | ok | 3 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2625 of 2625 base tests pass on the unit's code with its 4 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-912521e8 | service-token-enforcement › A broker endpoint with no configured service token refuses every request › issue with no configured token and no header | covered | github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssue_EmptyConfiguredToken_AnyHeader_Returns401_C_71da8c1f_C_912521e8 (passed, red_assertion); github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssue_EmptyConfiguredToken_NoHeader_Returns401_C_912521e8 (passed, red_... | - | 0.94 |
| C-8cc6b8bf | service-token-enforcement › A broker endpoint with no configured service token refuses every request › issue with no configured token and an empty header | covered | github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssue_EmptyConfiguredToken_EmptyHeader_Returns401_C_8cc6b8bf (passed, red_assertion) | - | 0.94 |
| C-71da8c1f | service-token-enforcement › A broker endpoint with no configured service token refuses every request › issue with no configured token and a non-empty header | covered | github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssue_EmptyConfiguredToken_AnyHeader_Returns401_C_71da8c1f_C_912521e8 (passed, red_assertion) | - | 0.89 |
| C-db03b7e7 | service-token-enforcement › A broker endpoint with no configured service token refuses every request › resolve with no configured token | covered | github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestResolve_EmptyConfiguredToken_RefusesEveryRequest_C_db03b7e7 (passed, red_assertion) | - | 0.94 |
| C-4a3dcd7f | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › both tokens missing | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestMissingServiceTokens_BothMissing_C_4a3dcd7f (passed, red_assertion) | - | 0.95 |
| C-7811225a | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › one token missing | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestMissingServiceTokens_OneMissing_C_7811225a (passed, red_assertion) | - | 0.95 |
| C-c7136482 | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › production with a token missing | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestValidate_ProductionWithTokenMissing_C_c7136482 (passed, red_assertion) | - | 0.93 |
| C-5cf49df9 | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › production with both tokens set | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestValidate_ProductionWithBothTokens_C_5cf49df9 (passed, red_assertion) | - | 0.93 |
| C-60346d8f | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › development with tokens missing | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestValidate_DevWithTokensMissing_C_60346d8f (passed, red_assertion) | - | 0.92 |
| C-bb56de98 | service-token-enforcement › The vault adapter registers its boot identities from one table › every token set | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_EveryTokenSet_C_bb56de98 (passed, red_assertion) | - | 0.92 |
| C-d7a0bdd1 | service-token-enforcement › The vault adapter registers its boot identities from one table › an id variable is set | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_IDVariableSet_C_d7a0bdd1 (passed, red_assertion) | - | 0.92 |
| C-03905893 | service-token-enforcement › The vault adapter registers its boot identities from one table › an empty token leaves its identity unregistered | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_EmptyTokenNotRegistered_C_03905893 (passed, red_assertion) | - | 0.86 |
| C-75a979b4 | service-token-enforcement › The vault adapter registers its boot identities from one table › a lookup error registers nothing | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_LookupErrorRegistersNothing_C_75a979b4 (passed, red_assertion) | - | 0.92 |
| C-312b2c0e | service-token-enforcement › The vault adapter registers its boot identities from one table › the environment variant | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentitiesFromEnv_ReadsEnvironment_C_312b2c0e (passed, red_assertion) | - | 0.91 |
| C-93d873f6 | service-token-enforcement › The vault adapter refuses to start in production without the proxy and admin tokens › production without the proxy and admin tokens | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_ProductionRequiresProxyAndAdmin_C_93d873f6 (passed, red_assertion) | - | 0.92 |
| C-57495bbe | service-token-enforcement › The vault adapter refuses to start in production without the proxy and admin tokens › production without the optional tokens | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_ProductionWithoutOptionalTokens_C_57495bbe (passed, red_assertion) | - | 0.90 |
| C-869146df | service-token-enforcement › The vault adapter refuses to start in production without the proxy and admin tokens › development without the proxy token | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_DevWithoutProxyToken_C_869146df (passed, red_assertion) | - | 0.94 |
| C-aed1806a | service-token-enforcement › An identity cannot be registered with an empty id or token › empty token | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_EmptyTokenRefused_C_aed1806a (passed, red_assertion) | - | 0.90 |
| C-138aad20 | service-token-enforcement › An identity cannot be registered with an empty id or token › empty id | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_EmptyIDRefused_C_138aad20 (passed, red_assertion) | - | 0.93 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/broker/cmd/broker/main.go` | broker | relevant | named in the spec |
| `apps/broker/internal/api/issue/issue.go` | broker | relevant | named in the spec |
| `apps/broker/internal/api/issue/issue_empty_token_test.go` |  | relevant | new test file |
| `apps/broker/internal/api/resolve/resolve.go` | broker | relevant | named in the spec |
| `apps/broker/internal/api/resolve/resolve_empty_token_test.go` |  | relevant | new test file |
| `apps/broker/internal/config/config.go` | broker | relevant | named in the spec |
| `apps/broker/internal/config/config_test.go` |  | relevant | new test file |
| `apps/vault-adapter/cmd/vault-adapter/main.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/identities.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/identities_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/server/vault.go` | vault-adapter | relevant | named in the spec |
| `openspec/changes/broker-service-token-required/.l4/ledger/r-20261025T2101Z-cc64.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/broker-service-token-required/.l4/ledger/r-20261025T2113Z-59fd.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/broker-service-token-required/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/broker-service-token-required/tasks.md` |  | none | exempt: harness, spec or documentation path |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/broker/cmd/broker/main.go, apps/broker/internal/api/issue/issue.go, apps/broker/internal/api/resolve/resolve.go, apps/broker/internal/config/config.go, apps/vault-adapter/cmd/vault-adapter/main.go and 2 more

### Tests

2645 of 2699 passed, 0 failed, 0 errored, 54 skipped.
19 of 19 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-912521e8 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8cc6b8bf | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-71da8c1f | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-db03b7e7 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4a3dcd7f | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7811225a | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c7136482 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5cf49df9 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-60346d8f | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bb56de98 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d7a0bdd1 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-03905893 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-75a979b4 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-312b2c0e | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-93d873f6 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-57495bbe | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-869146df | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-aed1806a | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-138aad20 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-912521e8 | service-token-enforcement › A broker endpoint with no configured service token refuses every request › issue with no configured token and no header | pass | pass | the judge passed it and a discriminating test passes |
| C-8cc6b8bf | service-token-enforcement › A broker endpoint with no configured service token refuses every request › issue with no configured token and an empty header | pass | pass | the judge passed it and a discriminating test passes |
| C-71da8c1f | service-token-enforcement › A broker endpoint with no configured service token refuses every request › issue with no configured token and a non-empty header | pass | pass | the judge passed it and a discriminating test passes |
| C-db03b7e7 | service-token-enforcement › A broker endpoint with no configured service token refuses every request › resolve with no configured token | pass | pass | the judge passed it and a discriminating test passes |
| C-4a3dcd7f | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › both tokens missing | pass | pass | the judge passed it and a discriminating test passes |
| C-7811225a | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › one token missing | pass | pass | the judge passed it and a discriminating test passes |
| C-c7136482 | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › production with a token missing | pass | pass | the judge passed it and a discriminating test passes |
| C-5cf49df9 | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › production with both tokens set | pass | pass | the judge passed it and a discriminating test passes |
| C-60346d8f | service-token-enforcement › The broker refuses to start in production without its inbound service tokens › development with tokens missing | pass | pass | the judge passed it and a discriminating test passes |
| C-bb56de98 | service-token-enforcement › The vault adapter registers its boot identities from one table › every token set | pass | pass | the judge passed it and a discriminating test passes |
| C-d7a0bdd1 | service-token-enforcement › The vault adapter registers its boot identities from one table › an id variable is set | pass | pass | the judge passed it and a discriminating test passes |
| C-03905893 | service-token-enforcement › The vault adapter registers its boot identities from one table › an empty token leaves its identity unregistered | pass | pass | the judge passed it and a discriminating test passes |
| C-75a979b4 | service-token-enforcement › The vault adapter registers its boot identities from one table › a lookup error registers nothing | pass | pass | the judge passed it and a discriminating test passes |
| C-312b2c0e | service-token-enforcement › The vault adapter registers its boot identities from one table › the environment variant | pass | pass | the judge passed it and a discriminating test passes |
| C-93d873f6 | service-token-enforcement › The vault adapter refuses to start in production without the proxy and admin tokens › production without the proxy and admin tokens | pass | pass | the judge passed it and a discriminating test passes |
| C-57495bbe | service-token-enforcement › The vault adapter refuses to start in production without the proxy and admin tokens › production without the optional tokens | pass | pass | the judge passed it and a discriminating test passes |
| C-869146df | service-token-enforcement › The vault adapter refuses to start in production without the proxy and admin tokens › development without the proxy token | pass | pass | the judge passed it and a discriminating test passes |
| C-aed1806a | service-token-enforcement › An identity cannot be registered with an empty id or token › empty token | pass | pass | the judge passed it and a discriminating test passes |
| C-138aad20 | service-token-enforcement › An identity cannot be registered with an empty id or token › empty id | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] task 1.1: tasks.md checkbox state / scope: Diff includes unrelated gofmt reformatting in config.go and vault.go; harmless.
- [minor, judge] Empty id with non-empty token via env (spec gap) (criterion C-d7a0bdd1): An id variable set to an empty string falls back to DefaultID; whitespace-only ids are registered as-is.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssue_EmptyConfiguredToken_AnyHeader_Returns401_C_71da8c1f_C_912521e8` (task 1.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssue_EmptyConfiguredToken_EmptyHeader_Returns401_C_8cc6b8bf` (task 1.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssue_EmptyConfiguredToken_NoHeader_Returns401_C_912521e8` (task 1.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestResolve_EmptyConfiguredToken_RefusesEveryRequest_C_db03b7e7` (task 1.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/config::TestMissingServiceTokens_BothMissing_C_4a3dcd7f` (task 2.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/config::TestMissingServiceTokens_OneMissing_C_7811225a` (task 2.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/config::TestValidate_DevWithTokensMissing_C_60346d8f` (task 2.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/config::TestValidate_ProductionWithBothTokens_C_5cf49df9` (task 2.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/config::TestValidate_ProductionWithTokenMissing_C_c7136482` (task 2.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentitiesFromEnv_ReadsEnvironment_C_312b2c0e` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_DevWithoutProxyToken_C_869146df` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_EmptyTokenNotRegistered_C_03905893` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_EveryTokenSet_C_bb56de98` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_IDVariableSet_C_d7a0bdd1` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_LookupErrorRegistersNothing_C_75a979b4` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_ProductionRequiresProxyAndAdmin_C_93d873f6` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentities_ProductionWithoutOptionalTokens_C_57495bbe` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_EmptyIDRefused_C_138aad20` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_EmptyTokenRefused_C_aed1806a` (task 3.1): passed
