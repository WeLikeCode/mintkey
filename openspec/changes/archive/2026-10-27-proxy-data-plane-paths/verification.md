# Verification: openspec:proxy-data-plane-paths: PASS (round 1)

traceability: 7/7 criteria covered by a discriminating test

- Base: `e3527af5cd44e0b3fcc66fed2c33052fa2b0459b`
- Head: `195aac58c8feb12a5c6bc09f42c80e3687566d1e`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `afd84f6c6b647fcbd7d0a4819e7af121524e7676f4b479c0ae018dc8a29c6740`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.7638

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base staging@e3527af5cd contained |
| 1 | integrity | ok | 335.6 | 10 sub-checks; scope: 11 changed file(s) |
| 2 | build | ok | 100.2 |  |
| 3 | tests | ok | 119.4 |  |
| 4 | traceability | ok | 0.1 | 7/7 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/kong-syncer/internal/kong/yaml.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/routing.go |
| 8 | s1 judge | ok | 0.9 | 7/7 criteria judged by jev |
| 9 | judge | ok | 17.6 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261027T0653Z-1d9c/217-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261027T0653Z-1d9c/218-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261027T0653Z-1d9c/219-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261027T0653Z-1d9c/220-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261027T0653Z-1d9c/221-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261027T0653Z-1d9c/222-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261027T0653Z-1d9c/223-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261027T0653Z-1d9c/224-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261027T0653Z-1d9c/225-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261027T0653Z-1d9c/226-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261027T0653Z-1d9c/227-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261027T0653Z-1d9c/228-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261027T0653Z-1d9c/229-test.log |

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
| suppressions | skipped | not checked: python only; changed files outside it: apps/kong-syncer/internal/kong/yaml.go, apps/kong-syncer/internal/kong/yaml_vhost_headers_test.go, apps/proxy-plugin/cmd/proxy-plugin/data_plane_paths_test.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/routing.g... |
| tdd history | ok | 4 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2744 of 2744 base tests pass on the unit's code with its 3 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-186f98fb | proxy-data-plane-routing › Both URL forms reach the upstream as the bare path › the call prefix is removed for the token's service only | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUpstreamPathStripsCallPrefixOfTheTokensService_C_186f98fb (passed, red_assertion) | - | 0.94 |
| C-a40d5e55 | proxy-data-plane-routing › Both URL forms reach the upstream as the bare path › the upstream receives the bare path under its base path, without routing headers | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestDigestDirectorForwardsBarePathWithoutRoutingHeaders_C_a40d5e55 (passed, red_assertion) | - | 0.89 |
| C-c6932f9e | proxy-data-plane-routing › Both URL forms reach the upstream as the bare path › a path_prefix claim matches the call form | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPathPrefixClaimMatchesCallForm_C_c6932f9e (passed, red_assertion) | - | 0.81 |
| C-12f2e366 | proxy-data-plane-routing › Strict mode compares the addressed service in any form and refuses an unaddressed request › an unaddressed request is refused in strict mode only | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStrictModeRefusesUnaddressedRequest_C_12f2e366 (passed, red_assertion) | - | 0.88 |
| C-842c06af | proxy-data-plane-routing › Strict mode compares the addressed service in any form and refuses an unaddressed request › the header and the wire form are compared with the audience | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStrictModeComparesHeaderAndWireFormWithAudience_C_842c06af (passed, red_assertion) | - | 0.94 |
| C-a3a11a7d | proxy-data-plane-routing › Kong-syncer adds the routing headers to every route of a service › the virtual-host route carries the headers | covered | github.com/mintkey/mintkey/services/kong-syncer/internal/kong::TestVirtualHostRouteCarriesRoutingHeaders_C_a3a11a7d (passed, red_assertion) | - | 0.94 |
| C-f81bbc6f | proxy-data-plane-routing › The data-plane-only profile is documented › the page names the profile's settings and limits | covered | tests.acceptance.test_data_plane_only_doc::test_data_plane_doc_has_no_mermaid_and_no_credential_values (passed, red_assertion); tests.acceptance.test_data_plane_only_doc::test_data_plane_doc_names_every_setting (passed, red_assertion) | - | 0.94 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/kong-syncer/internal/kong/yaml.go` | kong-syncer | relevant | named in the spec |
| `apps/kong-syncer/internal/kong/yaml_vhost_headers_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/data_plane_paths_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/routing.go` | proxy-plugin | relevant | named in the spec |
| `docs/guides/data-plane-only.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-data-plane-paths/.l4/ledger/r-20261027T0651Z-62b6.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-data-plane-paths/.l4/ledger/r-20261027T0653Z-1d9c.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-data-plane-paths/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-data-plane-paths/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `tests/acceptance/test_data_plane_only_doc.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/kong-syncer/internal/kong/yaml.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/routing.go

### Tests

2753 of 2807 passed, 0 failed, 0 errored, 54 skipped.
8 of 8 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-186f98fb | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a40d5e55 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c6932f9e | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-12f2e366 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-842c06af | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a3a11a7d | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f81bbc6f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-186f98fb | proxy-data-plane-routing › Both URL forms reach the upstream as the bare path › the call prefix is removed for the token's service only | pass | pass | the judge passed it and a discriminating test passes |
| C-a40d5e55 | proxy-data-plane-routing › Both URL forms reach the upstream as the bare path › the upstream receives the bare path under its base path, without routing headers | pass | pass | the judge passed it and a discriminating test passes |
| C-c6932f9e | proxy-data-plane-routing › Both URL forms reach the upstream as the bare path › a path_prefix claim matches the call form | pass | pass | the judge passed it and a discriminating test passes |
| C-12f2e366 | proxy-data-plane-routing › Strict mode compares the addressed service in any form and refuses an unaddressed request › an unaddressed request is refused in strict mode only | pass | pass | the judge passed it and a discriminating test passes |
| C-842c06af | proxy-data-plane-routing › Strict mode compares the addressed service in any form and refuses an unaddressed request › the header and the wire form are compared with the audience | pass | pass | the judge passed it and a discriminating test passes |
| C-a3a11a7d | proxy-data-plane-routing › Kong-syncer adds the routing headers to every route of a service › the virtual-host route carries the headers | pass | pass | the judge passed it and a discriminating test passes |
| C-f81bbc6f | proxy-data-plane-routing › The data-plane-only profile is documented › the page names the profile's settings and limits | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Header takes precedence over path when both present (spec gap) (criterion C-842c06af): addressedServiceID returns the header if non-empty even when the path names a different service; the path service is then ignored for the audience check.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/kong-syncer/internal/kong::TestVirtualHostRouteCarriesRoutingHeaders_C_a3a11a7d` (task 3.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestDigestDirectorForwardsBarePathWithoutRoutingHeaders_C_a40d5e55` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPathPrefixClaimMatchesCallForm_C_c6932f9e` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStrictModeComparesHeaderAndWireFormWithAudience_C_842c06af` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStrictModeRefusesUnaddressedRequest_C_12f2e366` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUpstreamPathStripsCallPrefixOfTheTokensService_C_186f98fb` (task 1.1): passed
- `tests.acceptance.test_data_plane_only_doc::test_data_plane_doc_has_no_mermaid_and_no_credential_values` (task 4.1): passed
- `tests.acceptance.test_data_plane_only_doc::test_data_plane_doc_names_every_setting` (task 4.1): passed
