# Verification: openspec:proxy-revocation-enforced: PASS (round 1)

traceability: 9/9 criteria covered by a discriminating test

- Base: `1f1c9b4ea58eaa88154cfea8e91bb996d758405d`
- Head: `2ff5da29a503d703e7baeaa98d47bd0977ad818a`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `587b51a551676c2af1b0145b4156048b09ce3ea00265ad70376ea1c0057dae4f`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.7580

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base staging@1f1c9b4ea5 contained |
| 1 | integrity | ok | 426.4 | 10 sub-checks; scope: 15 changed file(s) |
| 2 | build | ok | 132.2 |  |
| 3 | tests | ok | 161.0 |  |
| 4 | traceability | ok | 0.1 | 9/9 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 0.7 | 9/9 criteria judged by jev |
| 9 | judge | ok | 19.9 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261026T1024Z-90d7/217-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261026T1024Z-90d7/218-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261026T1024Z-90d7/219-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261026T1024Z-90d7/220-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261026T1024Z-90d7/221-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261026T1024Z-90d7/222-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261026T1024Z-90d7/223-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261026T1024Z-90d7/224-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261026T1024Z-90d7/225-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261026T1024Z-90d7/226-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261026T1024Z-90d7/227-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261026T1024Z-90d7/228-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261026T1024Z-90d7/229-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 1 test file(s) compared with the base |
| red-green freeze | ok | 4 task(s): red and green compared |
| test path freeze | ok | 4 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/revocation_enforced_test.go, apps/proxy-plugin/internal/changes/subscriber.go, apps/proxy-plugin/internal/changes/subscriber_event_key_test.go, apps/proxy-plugin/interna... |
| tdd history | ok | 4 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2671 of 2671 base tests pass on the unit's code with its 5 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-a33ad25b | proxy-token-revocation › The proxy refuses a revoked token before the credential fetch › a token revoked through the change channel is refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevokedJTIIsRefusedBeforeVault_C_a33ad25b (passed, red_assertion) | - | 0.94 |
| C-958f74fb | proxy-token-revocation › The proxy refuses a revoked token before the credential fetch › an agent revoked by its wire id is refused when the token carries its UUID | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevokedAgentIsRefusedAcrossIDForms_C_958f74fb (passed, red_assertion) | - | 0.89 |
| C-668cad91 | proxy-token-revocation › admin-api's change notifications carry event_type › notify_change adds event_type and keeps the rest | covered | tests.unit.admin_api.test_notify_event_type::test_C_668cad91_notify_change_adds_event_type_and_keeps_the_rest (passed, red_assertion) | - | 0.93 |
| C-dd48286f | proxy-token-revocation › admin-api's change notifications carry event_type › the agent revocation publishers carry event_type | covered | tests.unit.admin_api.test_notify_event_type::test_C_dd48286f_agent_revocation_publishers_carry_event_type (passed, red_assertion) | - | 0.91 |
| C-af7468de | proxy-token-revocation › admin-api's change notifications carry event_type › the API key revocation publisher carries event_type | covered | tests.unit.admin_api.test_notify_event_type::test_C_af7468de_api_key_revocation_publisher_carries_event_type (passed, red_assertion) | - | 0.93 |
| C-c9a9a91e | proxy-token-revocation › The change subscriber reads the event type from event_type or event › payloads keyed by event are applied, and event_type wins over event | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/changes::TestHandleNotificationAcceptsEventKey_C_c9a9a91e (passed, red_assertion) | - | 0.93 |
| C-f100318b | proxy-token-revocation › The agent revocation set treats every form of an agent id as one id › the wire forms and the UUID form match | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation::TestAgentSetMatchesWireAndUUIDForms_C_f100318b (passed, red_assertion) | - | 0.95 |
| C-3d2301c4 | proxy-token-revocation › The agent revocation set treats every form of an agent id as one id › a UUID added matches its wire form, and an empty id is never added | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation::TestAgentSetAddedUUIDMatchesWireFormAndIgnoresEmpty_C_3d2301c4 (passed, red_assertion) | - | 0.90 |
| C-bb2b48de | proxy-token-revocation › Revoked token ids are evicted after the longest token lifetime › entries older than the retention are evicted and the loop stops | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation::TestJTIRunEvictionDropsEntriesPastRetention_C_bb2b48de (passed, red_assertion) | - | 0.93 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/changes/publisher.py` | admin-api | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/revocation_enforced_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/internal/changes/subscriber.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/changes/subscriber_event_key_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/internal/revocation/agent_set.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/revocation/agent_set_id_forms_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/internal/revocation/jti_eviction_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/internal/revocation/jti_set.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/wireid/wireid.go` | proxy-plugin | relevant | named in the spec |
| `openspec/changes/proxy-revocation-enforced/.l4/ledger/r-20261026T1011Z-7216.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-revocation-enforced/.l4/ledger/r-20261026T1024Z-90d7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-revocation-enforced/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-revocation-enforced/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `tests/unit/admin_api/test_notify_event_type.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2681 of 2735 passed, 0 failed, 0 errored, 54 skipped.
9 of 9 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-a33ad25b | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-958f74fb | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-668cad91 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-dd48286f | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-af7468de | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c9a9a91e | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f100318b | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3d2301c4 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bb2b48de | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-a33ad25b | proxy-token-revocation › The proxy refuses a revoked token before the credential fetch › a token revoked through the change channel is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-958f74fb | proxy-token-revocation › The proxy refuses a revoked token before the credential fetch › an agent revoked by its wire id is refused when the token carries its UUID | pass | pass | the judge passed it and a discriminating test passes |
| C-668cad91 | proxy-token-revocation › admin-api's change notifications carry event_type › notify_change adds event_type and keeps the rest | pass | pass | the judge passed it and a discriminating test passes |
| C-dd48286f | proxy-token-revocation › admin-api's change notifications carry event_type › the agent revocation publishers carry event_type | pass | pass | the judge passed it and a discriminating test passes |
| C-af7468de | proxy-token-revocation › admin-api's change notifications carry event_type › the API key revocation publisher carries event_type | pass | pass | the judge passed it and a discriminating test passes |
| C-c9a9a91e | proxy-token-revocation › The change subscriber reads the event type from event_type or event › payloads keyed by event are applied, and event_type wins over event | pass | pass | the judge passed it and a discriminating test passes |
| C-f100318b | proxy-token-revocation › The agent revocation set treats every form of an agent id as one id › the wire forms and the UUID form match | pass | pass | the judge passed it and a discriminating test passes |
| C-3d2301c4 | proxy-token-revocation › The agent revocation set treats every form of an agent id as one id › a UUID added matches its wire form, and an empty id is never added | pass | pass | the judge passed it and a discriminating test passes |
| C-bb2b48de | proxy-token-revocation › Revoked token ids are evicted after the longest token lifetime › entries older than the retention are evicted and the loop stops | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] wireid has no direct tests (spec gap) (criterion C-f100318b): The wireid package is only exercised through the agent set tests; edge inputs such as invalid Crockford characters, 130-bit masking and 36-character non-dashed strings are untested.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevokedAgentIsRefusedAcrossIDForms_C_958f74fb` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevokedJTIIsRefusedBeforeVault_C_a33ad25b` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/changes::TestHandleNotificationAcceptsEventKey_C_c9a9a91e` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation::TestAgentSetAddedUUIDMatchesWireFormAndIgnoresEmpty_C_3d2301c4` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation::TestAgentSetMatchesWireAndUUIDForms_C_f100318b` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation::TestJTIRunEvictionDropsEntriesPastRetention_C_bb2b48de` (task 3.1): passed
- `tests.unit.admin_api.test_notify_event_type::test_C_668cad91_notify_change_adds_event_type_and_keeps_the_rest` (task 2.1): passed
- `tests.unit.admin_api.test_notify_event_type::test_C_af7468de_api_key_revocation_publisher_carries_event_type` (task 2.1): passed
- `tests.unit.admin_api.test_notify_event_type::test_C_dd48286f_agent_revocation_publishers_carry_event_type` (task 2.1): passed
