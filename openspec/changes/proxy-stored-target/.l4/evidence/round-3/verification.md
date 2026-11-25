# Verification: openspec:proxy-stored-target: FAIL (round 3)

traceability: 18/18 criteria covered by a discriminating test

- Base: `829f5704745a15392a83e86c2e5cb45196eebfb5`
- Head: `e0f040f3ce24053388bbbb04fece88ea3a3c96e1`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `21af4b1c94a3865b40f114247b784e3eab3262a76beee14434de6314cb04851e`
- Judge replies of claude-judge (this unit, all rounds): valid 2, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $0.9546

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.6 | base staging@829f570474 contained |
| 1 | integrity | ok | 163.7 | 11 sub-checks; scope: 38 changed file(s) |
| 2 | build | ok | 89.2 |  |
| 3 | tests | ok | 110.5 |  |
| 4 | traceability | ok | 0.1 | 18/18 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | not measured: diff coverage measures python only; changed code outside it: apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/target.go, apps/proxy-plugin/cmd/proxy-plugin/upstream.go, apps/proxy-plugin/internal/config/config.go, apps/proxy-plugin/internal/scrubber/respon... |
| 8 | s1 judge | ok | 1.4 | 17/18 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 24.0 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | FAIL |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261125T0745Z-3966/033-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261125T0745Z-3966/034-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261125T0745Z-3966/035-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261125T0745Z-3966/036-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261125T0745Z-3966/037-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261125T0745Z-3966/038-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261125T0745Z-3966/039-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261125T0745Z-3966/040-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261125T0745Z-3966/041-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261125T0745Z-3966/042-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261125T0745Z-3966/043-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261125T0745Z-3966/044-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261125T0745Z-3966/045-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 6 test file(s) compared with the base (+23 allowed, listed) |
| red-green freeze | ok | 5 task(s): red and green compared |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/response_scrubbing_test.go, apps/proxy-plugin/cmd/proxy-plugin/stored_target_test.go, apps/proxy-plugin/cmd/proxy-plugin/target.go, apps/proxy-plugin/cmd/proxy-plugin/up... |
| tdd history | ok | 5 task(s); red tests passing at head: step 3 |
| python encoding | ok | 6 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 2773 of 2773 base tests pass on the unit's code with its 5 test and support files at the base (base: evidence) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- tests/acceptance/test_classical_key.py::test_classical_key_admin_api_routers_exist changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_classical_key.py::test_classical_key_full_flow changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_classical_key.py::test_classical_key_prefix changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_classical_key.py::test_classical_key_request_transformer_in_yaml_generator changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_classical_key.py::test_classical_key_schema_exists changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_classical_key.py::test_proxy_plugin_classical_key_dispatch changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_data_plane_smoke.py::test_broker_smoke changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_data_plane_smoke.py::test_kong_smoke changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_data_plane_smoke.py::test_proxy_plugin_smoke changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_data_plane_smoke.py::test_vault_adapter_smoke changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_e2e_smoke.py::test_e2e_smoke_all_routers_registered changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_e2e_smoke.py::test_e2e_smoke_audit_chain_initialized changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_e2e_smoke.py::test_e2e_smoke_components_exist changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_e2e_smoke.py::test_e2e_smoke_mock_backend_has_all_endpoints changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_e2e_smoke.py::test_full_e2e_smoke_13_steps changed (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_golden_path.py::test_golden_path_admin_api_vault_client_is_grpc changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_golden_path.py::test_golden_path_bootstrap_skill_has_required_sections changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_golden_path.py::test_golden_path_broker_jwt_claims_present changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_golden_path.py::test_golden_path_chain_components_exist changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_golden_path.py::test_ws10_list_versions_end_to_end changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_golden_path.py::test_ws10_vault_client_list_versions_parses_metadata changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_golden_path.py::test_ws8_golden_path_agent_to_upstream changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_golden_path.py::test_ws9_vault_grpc_end_to_end changed (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_classical_key.py kept at head for the run (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_data_plane_smoke.py kept at head for the run (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_e2e_smoke.py kept at head for the run (task 1.1: unfrozen by Q-001)
- tests/acceptance/test_golden_path.py kept at head for the run (task 1.1: unfrozen by Q-001, Q-002)
- tests/acceptance/test_live_stack_redaction_assertions.py kept at head for the run (task 1.1: unfrozen by Q-001, Q-002)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-18de099e | proxy-stored-target › The proxy sends a request only to the target stored with the credential › the stored target wins over the header and the default | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStoredTargetWinsInEveryFlow_C_18de099e_C_e1860d3e (passed, red_assertion) | - | 0.91 |
| C-e1860d3e | proxy-stored-target › The proxy sends a request only to the target stored with the credential › a credential with no stored target is refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestMissingStoredTargetIsRefusedInEveryFlow_C_e1860d3e (passed, red_assertion); github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStoredTargetWinsInEveryFlow_C_18de099e_C_e1860d3e (passed, red_assertion) | - | 0.94 |
| C-d6cbb9f7 | proxy-stored-target › The proxy sends a request only to the target stored with the credential › a missing credential response has no target | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStoredTargetOfMissingAndPresentCredential_C_d6cbb9f7 (passed, red_assertion) | - | 0.95 |
| C-833affe8 | proxy-stored-target › The proxy sends a request only to the target stored with the credential › a stored target that is not an http or https URL is refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestNonHTTPStoredTargetIsRefused_C_833affe8 (passed, red_assertion) | - | 0.90 |
| C-7ac56330 | proxy-stored-target › Stored targets of existing credentials are filled from the service's base URL › the changelog fills empty targets only | covered | tests.unit.admin_api.test_credential_target_backfill::test_C_7ac56330_backfill_changelog_fills_empty_targets_only (passed, red_assertion) | - | 0.89 |
| C-d3007570 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a credential echoed by the upstream does not reach the caller | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUpstreamEchoDoesNotReachTheCaller_C_d3007570 (passed, red_assertion) | - | 0.94 |
| C-dbc89858 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › the pattern rules apply only when the setting is on | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPatternRulesFollowTheSetting_C_dbc89858 (passed, red_assertion) | - | 0.95 |
| C-b09ecf07 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a secret inside a longer value and in a multi-value header | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestSecretInsideLongerValueAndMultiValueHeader_C_b09ecf07 (passed, red_assertion) | - | 0.93 |
| C-821c31ba | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › short secrets, encoded forms and empty secrets | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestShortEncodedAndEmptySecrets_C_821c31ba (passed, red_assertion) | - | 0.93 |
| C-9048f97b | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › the setting is read from the environment | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b (passed, red_assertion); github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/banana (passed, red_assertion); github.com/mintkey/mint... | - | - |
| C-ff10cd06 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › the exchanged token of the OAuth2 flows is redacted too | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestExchangedTokenIsRedacted_C_ff10cd06 (passed, red_assertion) | - | 0.93 |
| C-c2fde988 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a clean response passes through unchanged | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestCleanResponsePassesThrough_C_c2fde988 (passed, red_assertion) | - | 0.91 |
| C-b99db4cf | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a body that fails to decode is refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUndecodableBodyIsRefused_C_b99db4cf (passed, red_assertion) | - | 0.90 |
| C-ccbb65b9 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › an unreachable upstream answers 502 with a text | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUnreachableUpstreamAnswersWithText_C_ccbb65b9 (passed, red_assertion) | - | 0.88 |
| C-f92ecc35 | proxy-stored-target › The scrub keeps the whole body and a consistent length › Scrub keeps the tail of a large body and the length stays consistent | covered | github.com/mintkey/mintkey/services/proxy-plugin/internal/scrubber::TestScrubKeepsBodyPastScanBound_C_f92ecc35 (passed, red_assertion); github.com/mintkey/mintkey/services/proxy-plugin/internal/scrubber::TestScrubUnchangedBodyKeepsLength_C_f92ecc35 (passed, red_assertion) | - | 0.95 |
| C-7d21b6f6 | proxy-stored-target › Bodies the proxy cannot scan are streamed or refused explicitly › encoded bodies are decoded or refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestEncodedBodiesAreDecodedOrRefused_C_7d21b6f6 (passed, red_assertion) | - | 0.92 |
| C-e1d174b7 | proxy-stored-target › Bodies the proxy cannot scan are streamed or refused explicitly › an event stream is not buffered | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestEventStreamIsNotBuffered_C_e1d174b7 (passed, red_assertion) | - | 0.91 |
| C-969b7732 | proxy-stored-target › task 4.1: live-stack acceptance tests not updated — finding F-3e53e4bd › task 4.1: live-stack acceptance tests not updated | covered | tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_classical_key.py] (passed, red_assertion); tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_data_plane_smok... | - | 0.93 |

## Evidence

### Needs attention

- major: existing tests are skipped in a changed test file: tests.acceptance.test_classical_key::test_classical_key_full_flow, tests.acceptance.test_data_plane_smoke::test_broker_smoke, tests.acceptance.test_data_plane_smoke::test_kong_smoke, tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke, tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke and 3 more

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/db/changelog/033-credential-target-backfill.yaml` | admin-api | relevant | named in the spec |
| `apps/admin-api/db/changelog/db.changelog-master.yaml` | admin-api | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/response_scrubbing_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/stored_target_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/target.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/upstream.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/config/config.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/config/scrub_patterns_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/internal/scrubber/response.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/scrubber/response_tail_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/internal/vault/client.go` | proxy-plugin | relevant | named in the spec |
| `openspec/changes/proxy-stored-target-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target-fix-1/specs/proxy-stored-target/spec.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/ledger/r-20261124T2241Z-cc55.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/ledger/r-20261125T0056Z-9676.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/ledger/r-20261125T0138Z-75d9.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/ledger/r-20261125T0625Z-c049.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/.l4/ledger/r-20261125T0745Z-3966.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-stored-target/verification.md` |  | none | exempt: harness, spec or documentation path |
| `tests/acceptance/test_classical_key.py` |  | relevant | named in the spec |
| `tests/acceptance/test_data_plane_smoke.py` |  | relevant | named in the spec |
| `tests/acceptance/test_e2e_smoke.py` |  | relevant | named in the spec |
| `tests/acceptance/test_golden_path.py` |  | relevant | named in the spec |
| `tests/acceptance/test_live_stack_redaction_assertions.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_credential_target_backfill.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/target.go, apps/proxy-plugin/cmd/proxy-plugin/upstream.go, apps/proxy-plugin/internal/config/config.go, apps/proxy-plugin/internal/scrubber/response.go and 1 more

### Tests

2805 of 2859 passed, 0 failed, 0 errored, 54 skipped.
31 of 31 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-18de099e | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e1860d3e | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d6cbb9f7 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-833affe8 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7ac56330 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d3007570 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-dbc89858 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b09ecf07 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-821c31ba | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9048f97b | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-ff10cd06 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c2fde988 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b99db4cf | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ccbb65b9 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f92ecc35 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7d21b6f6 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e1d174b7 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-969b7732 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-18de099e | proxy-stored-target › The proxy sends a request only to the target stored with the credential › the stored target wins over the header and the default | pass | pass | the judge passed it and a discriminating test passes |
| C-e1860d3e | proxy-stored-target › The proxy sends a request only to the target stored with the credential › a credential with no stored target is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-d6cbb9f7 | proxy-stored-target › The proxy sends a request only to the target stored with the credential › a missing credential response has no target | pass | pass | the judge passed it and a discriminating test passes |
| C-833affe8 | proxy-stored-target › The proxy sends a request only to the target stored with the credential › a stored target that is not an http or https URL is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-7ac56330 | proxy-stored-target › Stored targets of existing credentials are filled from the service's base URL › the changelog fills empty targets only | pass | pass | the judge passed it and a discriminating test passes |
| C-d3007570 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a credential echoed by the upstream does not reach the caller | pass | pass | the judge passed it and a discriminating test passes |
| C-dbc89858 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › the pattern rules apply only when the setting is on | pass | pass | the judge passed it and a discriminating test passes |
| C-b09ecf07 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a secret inside a longer value and in a multi-value header | pass | pass | the judge passed it and a discriminating test passes |
| C-821c31ba | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › short secrets, encoded forms and empty secrets | pass | pass | the judge passed it and a discriminating test passes |
| C-9048f97b | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › the setting is read from the environment | pass | pass | the judge passed it and a discriminating test passes |
| C-ff10cd06 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › the exchanged token of the OAuth2 flows is redacted too | pass | pass | the judge passed it and a discriminating test passes |
| C-c2fde988 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a clean response passes through unchanged | pass | pass | the judge passed it and a discriminating test passes |
| C-b99db4cf | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › a body that fails to decode is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-ccbb65b9 | proxy-stored-target › Every proxied response is scrubbed before it reaches the caller › an unreachable upstream answers 502 with a text | pass | pass | the judge passed it and a discriminating test passes |
| C-f92ecc35 | proxy-stored-target › The scrub keeps the whole body and a consistent length › Scrub keeps the tail of a large body and the length stays consistent | pass | pass | the judge passed it and a discriminating test passes |
| C-7d21b6f6 | proxy-stored-target › Bodies the proxy cannot scan are streamed or refused explicitly › encoded bodies are decoded or refused | pass | pass | the judge passed it and a discriminating test passes |
| C-e1d174b7 | proxy-stored-target › Bodies the proxy cannot scan are streamed or refused explicitly › an event stream is not buffered | pass | pass | the judge passed it and a discriminating test passes |
| C-969b7732 | proxy-stored-target › task 4.1: live-stack acceptance tests not updated — finding F-3e53e4bd › task 4.1: live-stack acceptance tests not updated | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [major, deterministic] existing tests are skipped in a changed test file: tests.acceptance.test_classical_key::test_classical_key_full_flow, tests.acceptance.test_data_plane_smoke::test_broker_smoke, tests.acceptance.test_data_plane_smoke::test_kong_smoke, tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke, tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke and 3 more
- [minor, judge] Body read failure after the scanned 256 KiB is not specified (spec gap) (criterion C-f92ecc35): A body that errors after the first 256 KiB is streamed through and the copy aborts; no criterion pins this.

## Fix unit

Fix unit 2 is created for these tasks:
- F-b0296656 existing tests are skipped in a changed test file

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestCleanResponsePassesThrough_C_c2fde988` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestEncodedBodiesAreDecodedOrRefused_C_7d21b6f6` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestEventStreamIsNotBuffered_C_e1d174b7` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestExchangedTokenIsRedacted_C_ff10cd06` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestMissingStoredTargetIsRefusedInEveryFlow_C_e1860d3e` (task 3.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestNonHTTPStoredTargetIsRefused_C_833affe8` (task 3.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPatternRulesFollowTheSetting_C_dbc89858` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestSecretInsideLongerValueAndMultiValueHeader_C_b09ecf07` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestShortEncodedAndEmptySecrets_C_821c31ba` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStoredTargetOfMissingAndPresentCredential_C_d6cbb9f7` (task 3.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestStoredTargetWinsInEveryFlow_C_18de099e_C_e1860d3e` (task 3.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUndecodableBodyIsRefused_C_b99db4cf` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUnreachableUpstreamAnswersWithText_C_ccbb65b9` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUpstreamEchoDoesNotReachTheCaller_C_d3007570` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/banana` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/empty` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/false` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/one` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/true` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/unset` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/upper` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/yes` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/config::TestScrubPatternsFromEnvironment_C_9048f97b/zero` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/scrubber::TestScrubKeepsBodyPastScanBound_C_f92ecc35` (task 2.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/scrubber::TestScrubUnchangedBodyKeepsLength_C_f92ecc35` (task 2.1): passed
- `tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_classical_key.py]` (task 1.1): passed
- `tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_data_plane_smoke.py]` (task 1.1): passed
- `tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_e2e_smoke.py]` (task 1.1): passed
- `tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_golden_path.py]` (task 1.1): passed
- `tests.unit.admin_api.test_credential_target_backfill::test_C_7ac56330_backfill_changelog_fills_empty_targets_only` (task 1.1): passed

## Guard events

- guard.test_tamper: tests/acceptance/test_classical_key.py
- guard.test_tamper: tests/acceptance/test_data_plane_smoke.py
- guard.test_tamper: tests/acceptance/test_e2e_smoke.py
- guard.test_tamper: tests/acceptance/test_golden_path.py
- guard.test_tamper: tests/acceptance/test_classical_key.py
- guard.test_tamper: tests/acceptance/test_data_plane_smoke.py
- guard.test_tamper: tests/acceptance/test_e2e_smoke.py
- guard.test_tamper: tests/acceptance/test_golden_path.py
