# Verification: openspec:token-request-scope-claims: PASS (round 1)

traceability: 8/8 criteria covered by a discriminating test

- Base: `3a1e7ed2db7adec379542ccf1abd0acd39aa45dd`
- Head: `6ae1115b70c97d1020729a1c42f1c89617fcfbd3`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `6efddf3ec2676def4e9cfb9d1616eebc9e0716ef53ab992d92a80af0727bcdbb`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.7507

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base staging@3a1e7ed2db contained |
| 1 | integrity | ok | 478.7 | 10 sub-checks; scope: 15 changed file(s) |
| 2 | build | ok | 97.8 |  |
| 3 | tests | ok | 137.7 |  |
| 4 | traceability | ok | 0.1 | 8/8 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 0.8 | 8/8 criteria judged by jev |
| 9 | judge | ok | 16.4 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261026T1251Z-70e0/166-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261026T1251Z-70e0/167-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261026T1251Z-70e0/168-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261026T1251Z-70e0/169-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261026T1251Z-70e0/170-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261026T1251Z-70e0/171-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261026T1251Z-70e0/172-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261026T1251Z-70e0/173-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261026T1251Z-70e0/174-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261026T1251Z-70e0/175-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261026T1251Z-70e0/176-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261026T1251Z-70e0/177-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261026T1251Z-70e0/178-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 1 test file(s) compared with the base |
| red-green freeze | ok | 3 task(s): red and green compared |
| test path freeze | ok | 3 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/broker/internal/api/issue/issue.go, apps/broker/internal/api/issue/issue_scope_claims_test.go, apps/broker/internal/issuer/issuer.go, apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/routing.go (+2 more) |
| tdd history | ok | 3 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2658 of 2658 base tests pass on the unit's code with its 3 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-95b500fb | token-scope-claims › The broker signs optional methods and path_prefix claims › the limits are signed as claims | covered | github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssueSignsMethodsAndPathPrefixClaims_C_95b500fb (passed, red_assertion) | - | 0.95 |
| C-f5923c53 | token-scope-claims › The broker refuses invalid limits › each invalid limit is refused | covered | github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssueRefusesInvalidScopeClaims_C_f5923c53 (passed, red_assertion) | - | 0.94 |
| C-60d4b695 | token-scope-claims › The proxy enforces the limits before the credential fetch › other methods and paths are refused, the permitted call goes through | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestScopeClaimsRefuseOtherMethodAndPathBeforeVault_C_60d4b695 (passed, red_assertion) | - | 0.94 |
| C-97127a0e | token-scope-claims › The proxy enforces the limits before the credential fetch › dot segments and malformed claims are refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestScopeClaimsRefuseDotSegmentsAndMalformedClaims_C_97127a0e (passed, red_assertion) | - | 0.90 |
| C-8bb63508 | token-scope-claims › The MCP server passes the limits to the broker › the fields reach the broker only when given | covered | apps.mcp-server.tests.test_request_token_scope_claims::test_C_8bb63508_request_token_forwards_scope_claims_only_when_given (passed, red_assertion) | - | 0.94 |
| C-046d6912 | token-scope-claims › The MCP server passes the limits to the broker › a broker validation error is answered 400 | covered | apps.mcp-server.tests.test_request_token_scope_claims::test_C_046d6912_request_token_answers_broker_validation_error_with_400 (passed, red_assertion) | - | 0.94 |
| C-23b6e29a | token-scope-claims › The MCP server passes the limits to the broker › the limits are refused for SSH and email services | covered | apps.mcp-server.tests.test_request_token_scope_claims::test_C_23b6e29a_request_token_refuses_scope_claims_for_ssh_and_email_services (passed, red_assertion) | - | 0.93 |
| C-408d5385 | token-scope-claims › The MCP server passes the limits to the broker › the JSON-RPC tool and the contract carry the fields | covered | apps.mcp-server.tests.test_request_token_scope_claims::test_C_408d5385_jsonrpc_request_token_forwards_scope_claims (passed, red_assertion) | - | 0.82 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/broker/internal/api/issue/issue.go` | broker | relevant | named in the spec |
| `apps/broker/internal/api/issue/issue_scope_claims_test.go` |  | relevant | new test file |
| `apps/broker/internal/issuer/issuer.go` | broker | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/tools/jsonrpc.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/tools/request_token.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/tests/test_request_token_scope_claims.py` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/routing.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/scope_claims.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/scope_claims_test.go` |  | relevant | new test file |
| `docs/architecture/contracts/mcp/tools.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/token-request-scope-claims/.l4/ledger/r-20261026T1246Z-5d24.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/token-request-scope-claims/.l4/ledger/r-20261026T1251Z-70e0.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/token-request-scope-claims/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/token-request-scope-claims/tasks.md` |  | none | exempt: harness, spec or documentation path |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2689 of 2743 passed, 0 failed, 0 errored, 54 skipped.
8 of 8 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-95b500fb | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f5923c53 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-60d4b695 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-97127a0e | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8bb63508 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-046d6912 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-23b6e29a | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-408d5385 | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-95b500fb | token-scope-claims › The broker signs optional methods and path_prefix claims › the limits are signed as claims | pass | pass | the judge passed it and a discriminating test passes |
| C-f5923c53 | token-scope-claims › The broker refuses invalid limits › each invalid limit is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-60d4b695 | token-scope-claims › The proxy enforces the limits before the credential fetch › other methods and paths are refused, the permitted call goes through | pass | pass | the judge passed it and a discriminating test passes |
| C-97127a0e | token-scope-claims › The proxy enforces the limits before the credential fetch › dot segments and malformed claims are refused | pass | pass | the judge passed it and a discriminating test passes |
| C-8bb63508 | token-scope-claims › The MCP server passes the limits to the broker › the fields reach the broker only when given | pass | pass | the judge passed it and a discriminating test passes |
| C-046d6912 | token-scope-claims › The MCP server passes the limits to the broker › a broker validation error is answered 400 | pass | pass | the judge passed it and a discriminating test passes |
| C-23b6e29a | token-scope-claims › The MCP server passes the limits to the broker › the limits are refused for SSH and email services | pass | pass | the judge passed it and a discriminating test passes |
| C-408d5385 | token-scope-claims › The MCP server passes the limits to the broker › the JSON-RPC tool and the contract carry the fields | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] methods: null treated as absent (spec gap) (criterion C-95b500fb): A JSON null for methods decodes to nil and is treated as absent; not pinned by any scenario.

## New tests (red then green, `task.red_ok` in the ledger)

- `apps.mcp-server.tests.test_request_token_scope_claims::test_C_046d6912_request_token_answers_broker_validation_error_with_400` (task 3.1): passed
- `apps.mcp-server.tests.test_request_token_scope_claims::test_C_23b6e29a_request_token_refuses_scope_claims_for_ssh_and_email_services` (task 3.1): passed
- `apps.mcp-server.tests.test_request_token_scope_claims::test_C_408d5385_jsonrpc_request_token_forwards_scope_claims` (task 3.1): passed
- `apps.mcp-server.tests.test_request_token_scope_claims::test_C_8bb63508_request_token_forwards_scope_claims_only_when_given` (task 3.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssueRefusesInvalidScopeClaims_C_f5923c53` (task 1.1): passed
- `github.com/mintkey/mintkey/services/broker/internal/api/issue::TestIssueSignsMethodsAndPathPrefixClaims_C_95b500fb` (task 1.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestScopeClaimsRefuseDotSegmentsAndMalformedClaims_C_97127a0e` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestScopeClaimsRefuseOtherMethodAndPathBeforeVault_C_60d4b695` (task 2.1): passed
