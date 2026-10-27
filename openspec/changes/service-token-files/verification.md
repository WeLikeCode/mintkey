# Verification: openspec:service-token-files: PASS (round 1)

traceability: 16/16 criteria covered by a discriminating test

- Base: `336c1fc9221631d5b26feeef91d811913ab7c62d`
- Head: `269b29cb04debb668d81e3cbacaecdbf39d9c48e`
- Implementer profiles: deepseek, glm
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `7ca16e3be036693df10593db968f411b6843ca655afd186a438471d48a4998d9`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared)
- Cost: $0.7872

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base staging@336c1fc922 contained |
| 1 | integrity | ok | 336.9 | 10 sub-checks; scope: 17 changed file(s) |
| 2 | build | ok | 99.1 |  |
| 3 | tests | ok | 119.0 |  |
| 4 | traceability | ok | 0.2 | 16/16 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/broker/cmd/broker/main.go, apps/broker/internal/config/config.go, apps/email-proxy/internal/config/config.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/config/config.go and 3 more |
| 8 | s1 judge | ok | 1.8 | 16/16 criteria judged by jev |
| 9 | judge | ok | 23.2 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261027T0842Z-e819/241-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261027T0842Z-e819/242-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261027T0842Z-e819/243-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261027T0842Z-e819/244-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261027T0842Z-e819/245-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261027T0842Z-e819/246-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261027T0842Z-e819/247-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261027T0842Z-e819/248-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261027T0842Z-e819/249-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261027T0842Z-e819/250-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261027T0842Z-e819/251-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261027T0842Z-e819/252-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261027T0842Z-e819/253-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | skipped | no test file changed |
| red-green freeze | ok | 4 task(s): red and green compared |
| test path freeze | ok | 4 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/broker/cmd/broker/main.go, apps/broker/internal/config/config.go, apps/broker/internal/config/config_files_test.go, apps/email-proxy/internal/config/config.go, apps/email-proxy/internal/config/config_files_test.go (+8 more) |
| tdd history | ok | 4 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2752 of 2752 base tests pass on the unit's code with its 5 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-c880ceda | service-token-files › A secret can come from a file named by NAME_FILE › the variable alone | covered | github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFromVariableOrFile_C_c880ceda_C_1056cd39 (passed, red_assertion) | - | 0.92 |
| C-1056cd39 | service-token-files › A secret can come from a file named by NAME_FILE › the file alone | covered | github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFileWithOnlyANewline_C_de531293_C_1056cd39 (passed, red_assertion); github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFromVariableOrFile_C_c880ceda_C_1056cd39 (passed, red_assertio... | - | 0.75 |
| C-9703c3fc | service-token-files › A secret can come from a file named by NAME_FILE › trailing line ends are removed | covered | github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFileTrailingLineEndsRemoved_C_9703c3fc (passed, red_assertion) | - | 0.91 |
| C-de531293 | service-token-files › A secret can come from a file named by NAME_FILE › a file that holds only a newline | covered | github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFileWithOnlyANewline_C_de531293_C_1056cd39 (passed, red_assertion) | - | 0.83 |
| C-aa113b10 | service-token-files › A secret can come from a file named by NAME_FILE › both are set | covered | github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenSetTwice_C_aa113b10 (passed, red_assertion) | - | 0.95 |
| C-6f684b90 | service-token-files › A secret can come from a file named by NAME_FILE › the file cannot be read | covered | github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_UnreadableSSHProxyTokenFile_C_6f684b90 (passed, red_assertion) | - | 0.86 |
| C-d2cf4459 | service-token-files › The broker and the egress proxy read their tokens from files too › broker tokens from files | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestLoad_BrokerTokensFromFiles_C_d2cf4459 (passed, red_assertion) | - | 0.94 |
| C-f379fedb | service-token-files › The broker and the egress proxy read their tokens from files too › broker tokens from variables, as before | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestLoad_BrokerTokensFromVariables_C_f379fedb (passed, red_assertion) | - | 0.93 |
| C-64df9824 | service-token-files › The broker and the egress proxy read their tokens from files too › an unreadable broker token file | covered | github.com/mintkey/mintkey/services/broker/internal/config::TestLoad_UnreadableBrokerTokenFile_C_64df9824 (passed, red_assertion) | - | 0.86 |
| C-1c3d4087 | service-token-files › The broker and the egress proxy read their tokens from files too › egress proxy tokens from files | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestLoad_ProxyTokensFromFiles_C_1c3d4087 (passed, red_assertion) | - | 0.93 |
| C-002035f6 | service-token-files › The broker and the egress proxy read their tokens from files too › an egress proxy token set twice | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestLoad_ProxyTokenSetTwice_C_002035f6 (passed, red_assertion) | - | 0.90 |
| C-5c46e7e4 | service-token-files › The vault adapter reads its identity variables from files too › an identity token from a file | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentitiesFromEnv_TokenFromFile_C_5c46e7e4 (passed, red_assertion) | - | 0.94 |
| C-48ed3d61 | service-token-files › The vault adapter reads its identity variables from files too › an unreadable identity token file | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentitiesFromEnv_UnreadableTokenFile_C_48ed3d61 (passed, red_assertion) | - | 0.92 |
| C-5f8ede28 | service-token-files › The email proxy reads its tokens from files too › email proxy tokens from files | covered | github.com/mintkey/mintkey/services/email-proxy/internal/config::TestLoad_EmailProxyTokenFileWithOnlyANewline_C_75341d48_C_5f8ede28 (passed, red_assertion); github.com/mintkey/mintkey/services/email-proxy/internal/config::TestLoad_EmailProxyTokensFromFiles_C_5f8ede28 (passed, red_assertion) | - | 0.93 |
| C-427d1fb9 | service-token-files › The email proxy reads its tokens from files too › an unreadable email proxy token file | covered | github.com/mintkey/mintkey/services/email-proxy/internal/config::TestLoad_UnreadableEmailProxyTokenFile_C_427d1fb9 (passed, red_assertion) | - | 0.90 |
| C-75341d48 | service-token-files › The email proxy reads its tokens from files too › an email proxy token file that holds only a newline | covered | github.com/mintkey/mintkey/services/email-proxy/internal/config::TestLoad_EmailProxyTokenFileWithOnlyANewline_C_75341d48_C_5f8ede28 (passed, red_assertion) | - | 0.89 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/broker/cmd/broker/main.go` | broker | relevant | named in the spec |
| `apps/broker/internal/config/config.go` | broker | relevant | named in the spec |
| `apps/broker/internal/config/config_files_test.go` |  | relevant | new test file |
| `apps/email-proxy/internal/config/config.go` | email-proxy | relevant | named in the spec |
| `apps/email-proxy/internal/config/config_files_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/config/config.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/config/config_files_test.go` |  | relevant | new test file |
| `apps/ssh-proxy/internal/config/config.go` | ssh-proxy | relevant | named in the spec |
| `apps/ssh-proxy/internal/config/config_files_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/server/identities.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/identities_files_test.go` |  | relevant | new test file |
| `openspec/changes/service-token-files/.l4/ledger/r-20261027T0840Z-5a10.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/service-token-files/.l4/ledger/r-20261027T0842Z-e819.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/service-token-files/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/service-token-files/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/go/svcid/fromenv.go` | go | relevant | named in the spec |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/broker/cmd/broker/main.go, apps/broker/internal/config/config.go, apps/email-proxy/internal/config/config.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/config/config.go and 3 more

### Tests

2768 of 2822 passed, 0 failed, 0 errored, 54 skipped.
15 of 15 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-c880ceda | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1056cd39 | ok | 0.750 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9703c3fc | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-de531293 | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-aa113b10 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6f684b90 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d2cf4459 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f379fedb | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-64df9824 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1c3d4087 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-002035f6 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5c46e7e4 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-48ed3d61 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5f8ede28 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-427d1fb9 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-75341d48 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-c880ceda | service-token-files › A secret can come from a file named by NAME_FILE › the variable alone | pass | pass | the judge passed it and a discriminating test passes |
| C-1056cd39 | service-token-files › A secret can come from a file named by NAME_FILE › the file alone | pass | pass | the judge passed it and a discriminating test passes |
| C-9703c3fc | service-token-files › A secret can come from a file named by NAME_FILE › trailing line ends are removed | pass | pass | the judge passed it and a discriminating test passes |
| C-de531293 | service-token-files › A secret can come from a file named by NAME_FILE › a file that holds only a newline | pass | pass | the judge passed it and a discriminating test passes |
| C-aa113b10 | service-token-files › A secret can come from a file named by NAME_FILE › both are set | pass | pass | the judge passed it and a discriminating test passes |
| C-6f684b90 | service-token-files › A secret can come from a file named by NAME_FILE › the file cannot be read | pass | pass | the judge passed it and a discriminating test passes |
| C-d2cf4459 | service-token-files › The broker and the egress proxy read their tokens from files too › broker tokens from files | pass | pass | the judge passed it and a discriminating test passes |
| C-f379fedb | service-token-files › The broker and the egress proxy read their tokens from files too › broker tokens from variables, as before | pass | pass | the judge passed it and a discriminating test passes |
| C-64df9824 | service-token-files › The broker and the egress proxy read their tokens from files too › an unreadable broker token file | pass | pass | the judge passed it and a discriminating test passes |
| C-1c3d4087 | service-token-files › The broker and the egress proxy read their tokens from files too › egress proxy tokens from files | pass | pass | the judge passed it and a discriminating test passes |
| C-002035f6 | service-token-files › The broker and the egress proxy read their tokens from files too › an egress proxy token set twice | pass | pass | the judge passed it and a discriminating test passes |
| C-5c46e7e4 | service-token-files › The vault adapter reads its identity variables from files too › an identity token from a file | pass | pass | the judge passed it and a discriminating test passes |
| C-48ed3d61 | service-token-files › The vault adapter reads its identity variables from files too › an unreadable identity token file | pass | pass | the judge passed it and a discriminating test passes |
| C-5f8ede28 | service-token-files › The email proxy reads its tokens from files too › email proxy tokens from files | pass | pass | the judge passed it and a discriminating test passes |
| C-427d1fb9 | service-token-files › The email proxy reads its tokens from files too › an unreadable email proxy token file | pass | pass | the judge passed it and a discriminating test passes |
| C-75341d48 | service-token-files › The email proxy reads its tokens from files too › an email proxy token file that holds only a newline | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] task 1.1: test names differ from tasks.md (criterion C-c880ceda): Task 1.1 lists six separate tests (e.g. TestLoad_SSHProxyTokenFromVariable, TestLoad_SSHProxyTokenFromFile); the diff merges them into TestLoad_SSHProxyTokenFromVariableOrFile and adds criterion-id suffixes. Coverage is equivalent.
- [minor, judge] Value of NAME_FILE that names a directory or an empty file (spec gap) (criterion C-6f684b90): No scenario pins a path that exists but is a directory; the code returns the os.ReadFile error as 'cannot read'.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/broker/internal/config::TestLoad_BrokerTokensFromFiles_C_d2cf4459` (task 2.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/config::TestLoad_BrokerTokensFromVariables_C_f379fedb` (task 2.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/config::TestLoad_UnreadableBrokerTokenFile_C_64df9824` (task 2.1): passed
- `github.com/mintkey/mintkey/services/email-proxy/internal/config::TestLoad_EmailProxyTokenFileWithOnlyANewline_C_75341d48_C_5f8ede28` (task 4.1): passed
- `github.com/mintkey/mintkey/services/email-proxy/internal/config::TestLoad_EmailProxyTokensFromFiles_C_5f8ede28` (task 4.1): passed
- `github.com/mintkey/mintkey/services/email-proxy/internal/config::TestLoad_UnreadableEmailProxyTokenFile_C_427d1fb9` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestLoad_ProxyTokenSetTwice_C_002035f6` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestLoad_ProxyTokensFromFiles_C_1c3d4087` (task 2.1): passed
- `github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFileTrailingLineEndsRemoved_C_9703c3fc` (task 1.1): passed
- `github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFileWithOnlyANewline_C_de531293_C_1056cd39` (task 1.1): passed
- `github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenFromVariableOrFile_C_c880ceda_C_1056cd39` (task 1.1): passed
- `github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_SSHProxyTokenSetTwice_C_aa113b10` (task 1.1): passed
- `github.com/mintkey/mintkey/services/ssh-proxy/internal/config::TestLoad_UnreadableSSHProxyTokenFile_C_6f684b90` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentitiesFromEnv_TokenFromFile_C_5c46e7e4` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterBootIdentitiesFromEnv_UnreadableTokenFile_C_48ed3d61` (task 3.1): passed
