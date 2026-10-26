# Verification: openspec:vault-service-identity-fast-check: PASS (round 1)

traceability: 12/12 criteria covered by a discriminating test

- Base: `ffa17a35e5254a8c7f0118bd1863baf5d68667b0`
- Head: `00336186e162a2d4be6f3af6f49e6ac69509aa20`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `6a81a0838fbac492e609aa6f494e7d8fd13bae367340b9d24702973987f98f7a`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $0.7293

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base staging@ffa17a35e5 contained |
| 1 | integrity | ok | 418.8 | 10 sub-checks; scope: 11 changed file(s) |
| 2 | build | ok | 113.4 |  |
| 3 | tests | ok | 150.9 |  |
| 4 | traceability | ok | 0.1 | 12/12 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/broker/internal/api/resolve/resolve.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/vault/client.go, apps/vault-adapter/internal/server/vault.go |
| 8 | s1 judge | ok | 0.9 | 12/12 criteria judged by jev |
| 9 | judge | ok | 14.6 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261026T0019Z-22e6/216-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261026T0019Z-22e6/217-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261026T0019Z-22e6/218-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261026T0019Z-22e6/219-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261026T0019Z-22e6/220-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261026T0019Z-22e6/221-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261026T0019Z-22e6/222-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261026T0019Z-22e6/223-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261026T0019Z-22e6/224-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261026T0019Z-22e6/225-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261026T0019Z-22e6/226-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261026T0019Z-22e6/227-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261026T0019Z-22e6/228-test.log |

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
| suppressions | skipped | not checked: python only; changed files outside it: apps/broker/internal/api/resolve/dummy_hash_lazy_test.go, apps/broker/internal/api/resolve/resolve.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/vault/client.go, apps/proxy-plugin/internal/vault/client_conn_test.go (+2 ... |
| tdd history | ok | 3 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2644 of 2644 base tests pass on the unit's code with its 3 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-ca32998a | vault-identity-verification › Verifying a service identity uses a keyed hash, not a memory-hard one › validations allocate little | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_AllocatesUnderOneMiB_C_ca32998a (passed, red_assertion) | - | 0.95 |
| C-526209eb | vault-identity-verification › Verifying a service identity uses a keyed hash, not a memory-hard one › registrations allocate little | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_AllocatesUnderOneMiB_C_526209eb (passed, red_assertion) | - | 0.95 |
| C-926d2b3e | vault-identity-verification › Verification outcomes stay as they were › the right token | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_RightToken_C_926d2b3e (passed, red_assertion) | - | 0.94 |
| C-208852d8 | vault-identity-verification › Verification outcomes stay as they were › tokens that are not the registered one | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_OtherTokensRefused_C_208852d8 (passed, red_assertion) | - | 0.95 |
| C-985b05b1 | vault-identity-verification › Verification outcomes stay as they were › an unknown identity | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_UnknownIdentity_C_985b05b1 (passed, red_assertion) | - | 0.86 |
| C-69da84c9 | vault-identity-verification › Verification outcomes stay as they were › the registered scopes are a copy | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_ScopesAreCopied_C_69da84c9 (passed, red_assertion) | - | 0.93 |
| C-2dee6bf7 | vault-identity-verification › The proxy reuses one connection to the vault › sequential calls share one connection | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_RecoversAfterVaultRestart_C_fdfe8e11_C_2dee6bf7 (passed, red_assertion); github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_SequentialCallsShareOneConnection_C_2dee6bf7 (passed, red_assertion) | - | 0.94 |
| C-51e2f67d | vault-identity-verification › The proxy reuses one connection to the vault › concurrent calls share one connection | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_ConcurrentCallsShareOneConnection_C_51e2f67d (passed, red_assertion) | - | 0.94 |
| C-fdfe8e11 | vault-identity-verification › The proxy reuses one connection to the vault › the client recovers after the vault restarts | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_RecoversAfterVaultRestart_C_fdfe8e11_C_2dee6bf7 (passed, red_assertion) | - | 0.94 |
| C-5933cf84 | vault-identity-verification › The proxy reuses one connection to the vault › a closed client does not connect | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_ClosedClientDoesNotConnect_C_5933cf84 (passed, red_assertion) | - | 0.95 |
| C-91d7b471 | vault-identity-verification › The broker computes its constant-time dummy hash on first use › initialising the package allocates little | covered | github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestPackageInit_AllocatesUnder32MiB_C_91d7b471 (passed, red_assertion) | - | 0.93 |
| C-89e65307 | vault-identity-verification › The broker computes its constant-time dummy hash on first use › the unknown-fingerprint path still answers the same | covered | github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestUnknownFingerprint_StillRefusedTwice_C_89e65307 (passed, red_assertion) | - | 0.79 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/broker/internal/api/resolve/dummy_hash_lazy_test.go` |  | relevant | new test file |
| `apps/broker/internal/api/resolve/resolve.go` | broker | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/vault/client.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/vault/client_conn_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/server/identity_check_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/server/vault.go` | vault-adapter | relevant | named in the spec |
| `openspec/changes/vault-service-identity-fast-check/.l4/ledger/r-20261026T0016Z-eac0.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-service-identity-fast-check/.l4/ledger/r-20261026T0019Z-22e6.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-service-identity-fast-check/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-service-identity-fast-check/tasks.md` |  | none | exempt: harness, spec or documentation path |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/broker/internal/api/resolve/resolve.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/internal/vault/client.go, apps/vault-adapter/internal/server/vault.go

### Tests

2657 of 2711 passed, 0 failed, 0 errored, 54 skipped.
12 of 12 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-ca32998a | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-526209eb | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-926d2b3e | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-208852d8 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-985b05b1 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-69da84c9 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2dee6bf7 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-51e2f67d | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fdfe8e11 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5933cf84 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-91d7b471 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-89e65307 | ok | 0.790 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-ca32998a | vault-identity-verification › Verifying a service identity uses a keyed hash, not a memory-hard one › validations allocate little | pass | pass | the judge passed it and a discriminating test passes |
| C-526209eb | vault-identity-verification › Verifying a service identity uses a keyed hash, not a memory-hard one › registrations allocate little | pass | pass | the judge passed it and a discriminating test passes |
| C-926d2b3e | vault-identity-verification › Verification outcomes stay as they were › the right token | pass | pass | the judge passed it and a discriminating test passes |
| C-208852d8 | vault-identity-verification › Verification outcomes stay as they were › tokens that are not the registered one | pass | pass | the judge passed it and a discriminating test passes |
| C-985b05b1 | vault-identity-verification › Verification outcomes stay as they were › an unknown identity | pass | pass | the judge passed it and a discriminating test passes |
| C-69da84c9 | vault-identity-verification › Verification outcomes stay as they were › the registered scopes are a copy | pass | pass | the judge passed it and a discriminating test passes |
| C-2dee6bf7 | vault-identity-verification › The proxy reuses one connection to the vault › sequential calls share one connection | pass | pass | the judge passed it and a discriminating test passes |
| C-51e2f67d | vault-identity-verification › The proxy reuses one connection to the vault › concurrent calls share one connection | pass | pass | the judge passed it and a discriminating test passes |
| C-fdfe8e11 | vault-identity-verification › The proxy reuses one connection to the vault › the client recovers after the vault restarts | pass | pass | the judge passed it and a discriminating test passes |
| C-5933cf84 | vault-identity-verification › The proxy reuses one connection to the vault › a closed client does not connect | pass | pass | the judge passed it and a discriminating test passes |
| C-91d7b471 | vault-identity-verification › The broker computes its constant-time dummy hash on first use › initialising the package allocates little | pass | pass | the judge passed it and a discriminating test passes |
| C-89e65307 | vault-identity-verification › The broker computes its constant-time dummy hash on first use › the unknown-fingerprint path still answers the same | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Client.mu is a pointer, deviating from design (criterion C-5933cf84): mu is *sync.Mutex initialised in NewClient; a zero-value Client{} would nil-deref. Only NewClient is used.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestPackageInit_AllocatesUnder32MiB_C_91d7b471` (task 3.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestUnknownFingerprint_StillRefusedTwice_C_89e65307` (task 3.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_ClosedClientDoesNotConnect_C_5933cf84` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_ConcurrentCallsShareOneConnection_C_51e2f67d` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_RecoversAfterVaultRestart_C_fdfe8e11_C_2dee6bf7` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/vault::TestClient_SequentialCallsShareOneConnection_C_2dee6bf7` (task 2.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_AllocatesUnderOneMiB_C_526209eb` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestRegisterServiceIdentity_ScopesAreCopied_C_69da84c9` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_AllocatesUnderOneMiB_C_ca32998a` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_OtherTokensRefused_C_208852d8` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_RightToken_C_926d2b3e` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_UnknownIdentity_C_985b05b1` (task 1.1): passed
