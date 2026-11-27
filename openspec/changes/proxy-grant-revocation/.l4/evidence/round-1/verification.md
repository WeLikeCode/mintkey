# Verification: openspec:proxy-grant-revocation: PASS (round 1)

traceability: 7/7 criteria covered by a discriminating test

- Base: `c9398e1bd95121ea52f3248a1b186844726869a4`
- Head: `c4578af671f8d94c1f7afb4097ca9d2f186260f0`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `1870961db028ac94da6507f5d4430648858d70a625f8446e6a3bdab5cf2b79c9`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.7804

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base merged: staging@c9398e1bd9 as c4578af671 (1 commit) |
| 1 | integrity | ok | 0.2 | 11 sub-checks (+1 unfrozen by human answers); scope: 8 changed file(s) |
| 2 | build | ok | 157.4 |  |
| 3 | tests | ok | 128.4 |  |
| 4 | traceability | ok | 0.1 | 7/7 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/changes/subscriber.go, apps/proxy-plugin/internal/revocation/grant_set.go |
| 8 | s1 judge | ok | 0.5 | 7/7 criteria judged by jev |
| 9 | judge | ok | 16.7 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261126T2353Z-644b/027-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261126T2353Z-644b/028-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261126T2353Z-644b/029-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261126T2353Z-644b/030-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261126T2353Z-644b/031-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261126T2353Z-644b/032-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261126T2353Z-644b/033-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261126T2353Z-644b/034-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261126T2353Z-644b/035-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261126T2353Z-644b/036-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261126T2353Z-644b/037-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261126T2353Z-644b/038-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261126T2353Z-644b/039-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | skipped | no test file changed |
| red-green freeze | ok | 1 task(s): red and green compared (+1 unfrozen by a delegate or an agent) |
| test path freeze | ok | 1 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/changes/subscriber.go, apps/proxy-plugin/internal/revocation/grant_set.go |
| tdd history | ok | 1 task(s); red tests passing at head: step 3 |
| python encoding | skipped | no Python file added or changed |
| pre-existing tests still pass | ok | all 1 changed test and support file(s) are allowed and kept at head (listed) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go kept at head for the run (task 1.1: unfrozen by Q-001)

## Tests unfrozen by a delegate or an agent (allowed, L4-IMP-002)

- apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go (task 1.1, unfrozen by Q-001 (agent))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-bbfa63fe | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › tokens issued before the revocation are refused, later ones and other pairs are not | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevokedGrantRefusesEarlierTokens_C_bbfa63fe (passed, red_assertion) | - | 0.94 |
| C-b304eac3 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › a token without a usable iat is refused while an entry exists | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestTokenWithoutUsableIatIsRefused_C_b304eac3 (passed, red_assertion) | - | 0.92 |
| C-650441f7 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › an old revocation adds nothing and a future one counts as received now | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestOldRevocationAddsNothingAndFutureCountsAsNow_C_650441f7 (passed, red_assertion) | - | 0.94 |
| C-21c34307 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › an event without revoked_at counts from its receipt | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevocationWithoutRevokedAtCountsFromReceipt_C_21c34307 (passed, red_assertion) | - | 0.93 |
| C-e8ef472b | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › the set keeps the later revocation, counts its entries and drops expired ones | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestGrantSetKeepsLaterAndDropsExpired_C_e8ef472b (passed, red_assertion) | - | 0.94 |
| C-7ac13f75 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › an event that names no agent or no service is not applied | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUnusableEventsAreNotApplied_C_7ac13f75 (passed, red_assertion) | - | 0.92 |
| C-9d6cd6b8 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › a subscriber built without the set ignores the event | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestSubscriberWithoutGrantSetIgnoresPermissionRevoked_C_9d6cd6b8 (passed, red_assertion) | - | 0.91 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/changes/subscriber.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/revocation/grant_set.go` | proxy-plugin | relevant | named in the spec |
| `openspec/changes/proxy-grant-revocation/.l4/ledger/r-20261126T2258Z-5ab7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-grant-revocation/.l4/ledger/r-20261126T2353Z-644b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-grant-revocation/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-grant-revocation/tasks.md` |  | none | exempt: harness, spec or documentation path |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/changes/subscriber.go, apps/proxy-plugin/internal/revocation/grant_set.go

### Tests

2921 of 2975 passed, 0 failed, 0 errored, 54 skipped.
7 of 7 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-bbfa63fe | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b304eac3 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-650441f7 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-21c34307 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e8ef472b | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7ac13f75 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9d6cd6b8 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-bbfa63fe | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › tokens issued before the revocation are refused, later ones and other pairs are not | pass | pass | the judge passed it and a discriminating test passes |
| C-b304eac3 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › a token without a usable iat is refused while an entry exists | pass | pass | the judge passed it and a discriminating test passes |
| C-650441f7 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › an old revocation adds nothing and a future one counts as received now | pass | pass | the judge passed it and a discriminating test passes |
| C-21c34307 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › an event without revoked_at counts from its receipt | pass | pass | the judge passed it and a discriminating test passes |
| C-e8ef472b | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › the set keeps the later revocation, counts its entries and drops expired ones | pass | pass | the judge passed it and a discriminating test passes |
| C-7ac13f75 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › an event that names no agent or no service is not applied | pass | pass | the judge passed it and a discriminating test passes |
| C-9d6cd6b8 | proxy-token-revocation › A revoked grant's earlier tokens stop working at the proxy › a subscriber built without the set ignores the event | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] task 1.1: changes-package test file not created (criterion C-9d6cd6b8): Task 1.1 asks for apps/proxy-plugin/internal/changes/subscriber_grant_revoked_test.go (package changes_test). The diff has no such file; the scenario test lives in the main-package test file instead.
- [minor, judge] Unparsable revoked_at behaviour not pinned by a scenario (spec gap) (criterion C-21c34307): The committed code treats an unparsable revoked_at as the receipt time; no scenario covers it.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestGrantSetKeepsLaterAndDropsExpired_C_e8ef472b` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestOldRevocationAddsNothingAndFutureCountsAsNow_C_650441f7` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevocationWithoutRevokedAtCountsFromReceipt_C_21c34307` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestRevokedGrantRefusesEarlierTokens_C_bbfa63fe` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestSubscriberWithoutGrantSetIgnoresPermissionRevoked_C_9d6cd6b8` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestTokenWithoutUsableIatIsRefused_C_b304eac3` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUnusableEventsAreNotApplied_C_7ac13f75` (task 1.1): passed
