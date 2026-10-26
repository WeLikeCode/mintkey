# Verification: openspec:vault-method-scopes: PASS (round 4)

traceability: 15/15 criteria covered by a discriminating test

- Base: `ea16cf59f307ae5b659d636ff2f3b5fde8270456`
- Head: `6879392200e967e207e05d08e2587d13450266a4`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `f0fe4be95bc1a149e34af390761f919f40b2243483d2196263ca8f99b4f47629`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $0.8037

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 1.3 | base merged: staging@ea16cf59f3 as 6879392200 (1 commit) |
| 1 | integrity | ok | 584.3 | 10 sub-checks; scope: 33 changed file(s) |
| 2 | build | ok | 152.5 |  |
| 3 | tests | ok | 165.1 |  |
| 4 | traceability | ok | 0.2 | 15/15 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/vault-adapter/internal/server/grpc.go, apps/vault-adapter/internal/server/grpc_agent_secrets.go, apps/vault-adapter/internal/server/grpc_ssh.go, apps/vault-adapter/internal/server/identities.go |
| 8 | s1 judge | ok | 1.2 | 15/15 criteria judged by jev |
| 9 | judge | ok | 15.2 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261026T0933Z-2477/014-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261026T0933Z-2477/015-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261026T0933Z-2477/016-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261026T0933Z-2477/017-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261026T0933Z-2477/018-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261026T0933Z-2477/019-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261026T0933Z-2477/020-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261026T0933Z-2477/021-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261026T0933Z-2477/022-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261026T0933Z-2477/023-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261026T0933Z-2477/024-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261026T0933Z-2477/025-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261026T0933Z-2477/026-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | skipped | no Python test file changed; 2 other test file(s) are checked by the run of pre-existing tests |
| red-green freeze | ok | 1 task(s): red and green compared |
| test path freeze | ok | 3 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/vault-adapter/internal/server/grpc.go, apps/vault-adapter/internal/server/grpc_agent_secrets.go, apps/vault-adapter/internal/server/grpc_ssh.go, apps/vault-adapter/internal/server/grpc_ssh_test.go, apps/vault-adapter/internal/server/grpc_test.... |
| tdd history | ok | 2 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2656 of 2656 base tests pass on the unit's code with its 4 test and support files at the base (base: base worktree) |

## Test changes made by humans (allowed, L4-SEC-004)

- github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestGRPCValidateServiceIdentity_MissingToken fails with the base version of its files (changed by d8dbca5f02, 306917785f)
- github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestSSHVault_GetAgentByFingerprint_MissingToken fails with the base version of its files (changed by d8dbca5f02, 306917785f)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-c547eb9c | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › no identity on any listed method | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_NoIdentityRefusedOnEveryListedMethod_C_c547eb9c (passed, red_assertion) | - | 0.94 |
| C-e4e95bdb | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › a wrong token on any listed method | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_WrongTokenRefusedOnEveryListedMethod_C_e4e95bdb (passed, red_assertion) | - | 0.94 |
| C-377bc9e7 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › an unlisted method | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_HealthMethodsNeedNoIdentity_C_ac51d472_C_377bc9e7 (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_UnlistedMethodRefused_C_377bc9e7 (passed, red_ass... | - | 0.94 |
| C-56f4739c | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › registering a service leaves the table as it was | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_NotWrittenByRegistration_C_56f4739c (passed, red_assertion) | - | 0.95 |
| C-ac51d472 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › health methods need no identity | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_HealthMethodsNeedNoIdentity_C_ac51d472_C_377bc9e7 (passed, red_assertion) | - | 0.91 |
| C-2d4f1ec1 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › ListVersions needs an identity | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestListVersions_RequiresIdentity_C_2d4f1ec1 (passed, red_assertion) | - | 0.93 |
| C-08b38088 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › ValidateServiceIdentity needs an identity but no scope | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_RequiresIdentityButNoScope_C_08b38088 (passed, red_assertion) | - | 0.92 |
| C-8c1bdc49 | vault-method-authorization › Each vault method requires its own scope › the table holds these scopes | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_ScopePerMethod_C_8c1bdc49 (passed, red_assertion) | - | 0.94 |
| C-78d436a5 | vault-method-authorization › Each vault method requires its own scope › a read-only identity cannot write | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_ReadOnlyIdentityCannotWrite_C_78d436a5 (passed, red_assertion) | - | 0.95 |
| C-70816534 | vault-method-authorization › Each vault method requires its own scope › an identity holding every scope is served everywhere | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_FullIdentityServedEverywhere_C_70816534 (passed, red_assertion) | - | 0.91 |
| C-8bf69f2c | vault-method-authorization › The method table covers every method the vault serves › the served methods and the table agree | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_CoversEveryServedMethod_C_8bf69f2c (passed, red_assertion) | - | 0.91 |
| C-6484c16c | vault-method-authorization › The method table covers every method the vault serves › streams other than the health watch are refused | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestBuiltServer_OnlyHealthWatchStreams_C_6484c16c (passed, red_assertion) | - | 0.94 |
| C-5ecd45eb | vault-method-authorization › Each boot identity holds only the scopes its component uses › the scopes are exactly these | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestBootIdentities_LeastPrivilegeScopes_C_5ecd45eb (passed, pre_satisfied) | - | 0.91 |
| C-b2d83dba | vault-method-authorization › Each boot identity holds only the scopes its component uses › the proxy cannot write a credential and the admin identity can | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestProxyIdentity_CannotPutCredential_AdminCan_C_b2d83dba (passed, pre_satisfied) | - | 0.95 |
| C-35dca710 | vault-method-authorization › Each boot identity holds only the scopes its component uses › the SSH proxy stores a host key but cannot write a credential | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestSSHProxyIdentity_StoresHostKeyButCannotPutCredential_C_35dca710 (passed, pre_satisfied) | - | 0.95 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/vault-adapter/internal/server/grpc.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_agent_secrets.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_ssh.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_ssh_test.go` |  | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_test.go` |  | relevant | named in the spec |
| `apps/vault-adapter/internal/server/identities.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/identity_scopes_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/server/method_scopes_test.go` |  | relevant | new test file |
| `openspec/changes/vault-method-scopes-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-2/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-2/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-2/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes-fix-2/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-3/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-3/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/evidence/round-3/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/ledger/r-20261026T0311Z-4b41.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/ledger/r-20261026T0313Z-8028.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/ledger/r-20261026T0545Z-4e2f.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/ledger/r-20261026T0931Z-3f93.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/verification.md` |  | none | exempt: harness, spec or documentation path |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/vault-adapter/internal/server/grpc.go, apps/vault-adapter/internal/server/grpc_agent_secrets.go, apps/vault-adapter/internal/server/grpc_ssh.go, apps/vault-adapter/internal/server/identities.go

### Tests

2672 of 2726 passed, 0 failed, 0 errored, 54 skipped.
15 of 15 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-c547eb9c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e4e95bdb | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-377bc9e7 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-56f4739c | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ac51d472 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2d4f1ec1 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-08b38088 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8c1bdc49 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-78d436a5 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-70816534 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8bf69f2c | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6484c16c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5ecd45eb | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b2d83dba | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-35dca710 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-c547eb9c | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › no identity on any listed method | pass | pass | the judge passed it and a discriminating test passes |
| C-e4e95bdb | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › a wrong token on any listed method | pass | pass | the judge passed it and a discriminating test passes |
| C-377bc9e7 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › an unlisted method | pass | pass | the judge passed it and a discriminating test passes |
| C-56f4739c | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › registering a service leaves the table as it was | pass | pass | the judge passed it and a discriminating test passes |
| C-ac51d472 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › health methods need no identity | pass | pass | the judge passed it and a discriminating test passes |
| C-2d4f1ec1 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › ListVersions needs an identity | pass | pass | the judge passed it and a discriminating test passes |
| C-08b38088 | vault-method-authorization › Every vault method requires a valid service identity, except the health methods › ValidateServiceIdentity needs an identity but no scope | pass | pass | the judge passed it and a discriminating test passes |
| C-8c1bdc49 | vault-method-authorization › Each vault method requires its own scope › the table holds these scopes | pass | pass | the judge passed it and a discriminating test passes |
| C-78d436a5 | vault-method-authorization › Each vault method requires its own scope › a read-only identity cannot write | pass | pass | the judge passed it and a discriminating test passes |
| C-70816534 | vault-method-authorization › Each vault method requires its own scope › an identity holding every scope is served everywhere | pass | pass | the judge passed it and a discriminating test passes |
| C-8bf69f2c | vault-method-authorization › The method table covers every method the vault serves › the served methods and the table agree | pass | pass | the judge passed it and a discriminating test passes |
| C-6484c16c | vault-method-authorization › The method table covers every method the vault serves › streams other than the health watch are refused | pass | pass | the judge passed it and a discriminating test passes |
| C-5ecd45eb | vault-method-authorization › Each boot identity holds only the scopes its component uses › the scopes are exactly these | pass | pass | the judge passed it and a discriminating test passes |
| C-b2d83dba | vault-method-authorization › Each boot identity holds only the scopes its component uses › the proxy cannot write a credential and the admin identity can | pass | pass | the judge passed it and a discriminating test passes |
| C-35dca710 | vault-method-authorization › Each boot identity holds only the scopes its component uses › the SSH proxy stores a host key but cannot write a credential | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] task 1.1: fix tasks are placeholders: Fix-1/fix-2 task changes only add proposals; the actual test edits (grpc_test.go, grpc_ssh_test.go) are in the main diff. The SSH helper omits vault.put as the answer requires; fine.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestBootIdentities_LeastPrivilegeScopes_C_5ecd45eb` (task 2.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestBuiltServer_OnlyHealthWatchStreams_C_6484c16c` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestListVersions_RequiresIdentity_C_2d4f1ec1` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_CoversEveryServedMethod_C_8bf69f2c` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_NotWrittenByRegistration_C_56f4739c` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_ScopePerMethod_C_8c1bdc49` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestProxyIdentity_CannotPutCredential_AdminCan_C_b2d83dba` (task 2.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestSSHProxyIdentity_StoresHostKeyButCannotPutCredential_C_35dca710` (task 2.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_FullIdentityServedEverywhere_C_70816534` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_HealthMethodsNeedNoIdentity_C_ac51d472_C_377bc9e7` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_NoIdentityRefusedOnEveryListedMethod_C_c547eb9c` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_ReadOnlyIdentityCannotWrite_C_78d436a5` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_UnlistedMethodRefused_C_377bc9e7` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_WrongTokenRefusedOnEveryListedMethod_C_e4e95bdb` (task 1.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_RequiresIdentityButNoScope_C_08b38088` (task 1.1): passed

## Guard events

- guard.test_tamper: apps/vault-adapter/internal/server/grpc_ssh_test.go
- guard.test_tamper: apps/vault-adapter/internal/server/grpc_test.go
- guard.test_tamper: apps/vault-adapter/internal/server/grpc_ssh_test.go
- guard.test_tamper: apps/vault-adapter/internal/server/grpc_test.go
