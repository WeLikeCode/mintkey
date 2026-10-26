# Verification: openspec:audit-chain-verifiable: PASS (round 3)

traceability: 21/21 criteria covered by a discriminating test

- Base: `6a9f98b9b2eefee31839fad0c32fa618cb0164e7`
- Head: `f96a4395e88ffa45b2fa65ef313d835117d70e1a`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `c76fa5717ec3a94f148e8a3c4fcd7e0c4c1c298f312019ff26297125400cfb4b`
- Judge replies of claude-judge (this unit, all rounds): valid 2, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $0.8576

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.9 | base staging@6a9f98b9b2 contained |
| 1 | integrity | ok | 247.2 | 10 sub-checks; scope: 32 changed file(s) |
| 2 | build | ok | 135.8 |  |
| 3 | tests | ok | 169.8 |  |
| 4 | traceability | ok | 0.2 | 21/21 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 2.1 | 20/21 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 14.5 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261026T1918Z-d8e0/033-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261026T1918Z-d8e0/034-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261026T1918Z-d8e0/035-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261026T1918Z-d8e0/036-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261026T1918Z-d8e0/037-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261026T1918Z-d8e0/038-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261026T1918Z-d8e0/039-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261026T1918Z-d8e0/040-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261026T1918Z-d8e0/041-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261026T1918Z-d8e0/042-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261026T1918Z-d8e0/043-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261026T1918Z-d8e0/044-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261026T1918Z-d8e0/045-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 6 test file(s) compared with the base (+5 by humans, listed) (+3 allowed, listed) |
| red-green freeze | ok | 4 task(s): red and green compared |
| test path freeze | ok | 4 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 5 new suppression(s), 5 declared |
| tdd history | ok | 4 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2688 of 2688 base tests pass on the unit's code with its 4 test and support files at the base (base: evidence) |

Declared suppressions:
- tests/unit/admin_api/test_audit_verify_endpoint.py:35 # noqa: E402 (declared: Import must follow the sys.path setup that makes mintkey_models/audit_hash importable.)
- tests/unit/admin_api/test_audit_verify_endpoint_chain.py:33 # noqa: E402 (declared: Import follows sys.path setup for the admin-api and mintkey-models sources, as the job-chain test does.)
- tests/unit/admin_api/test_audit_verify_endpoint_chain.py:34 # noqa: E402 (declared: Import follows sys.path setup for the admin-api and mintkey-models sources, as the job-chain test does.)
- tests/unit/admin_api/test_audit_verify_job_chain.py:36 # noqa: E402 (declared: the import must follow the sys.path setup that puts the audit-verify-job directory and mintkey_models on the path)
- tests/unit/admin_api/test_audit_verify_job_chain.py:37 # noqa: E402 (declared: the import must follow the sys.path setup that puts the audit-verify-job directory and mintkey_models on the path)

## Test changes made by humans (allowed, L4-SEC-004)

- tests/unit/audit_verify/test_chain_verify.py::test_empty_chain_is_ok changed by 3e5a1ea8f3
- tests/unit/audit_verify/test_chain_verify.py::test_genesis_hash_value changed by 3e5a1ea8f3
- tests/unit/audit_verify/test_chain_verify.py::test_genesis_hash_verification changed by 3e5a1ea8f3
- tests/unit/audit_verify/test_chain_verify.py::test_intact_chain_returns_ok changed by 3e5a1ea8f3
- tests/unit/audit_verify/test_chain_verify.py::test_tampered_chain_detects_first_bad_event changed by 3e5a1ea8f3
- tests/unit/audit_verify/test_chain_verify.py kept at head for the run (only people's commits changed it (3e5a1ea8f3))

## Pre-existing tests changed with an allowance (L4-VER-031)

- tests/unit/admin_api/test_audit_verify_endpoint.py::test_verify_chain_ok changed (task 2.2: unfrozen by Q-002, Q-004)
- tests/unit/admin_api/test_audit_verify_endpoint.py::test_verify_chain_tampered changed (task 2.2: unfrozen by Q-002, Q-004)
- tests/unit/admin_api/test_audit_verify_endpoint.py::test_verify_chain_tenant_id_param changed (task 2.2: unfrozen by Q-002, Q-004)
- tests/unit/admin_api/test_audit_verify_endpoint.py kept at head for the run (task 2.2: unfrozen by Q-002, Q-004)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-f7069358 | audit-chain › One canonical form for the audit event hash › the canonical bytes of a fixed event | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_f7069358_canonical_bytes_of_a_fixed_event (passed, zero_value) | - | 0.95 |
| C-f3d1852b | audit-chain › One canonical form for the audit event hash › the writer's hash function keeps its result | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_f3d1852b_writers_hash_function_keeps_its_result (passed, zero_value) | - | 0.92 |
| C-7c9b66d2 | audit-chain › One canonical form for the audit event hash › the forms of a time | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_7c9b66d2_forms_of_a_time (passed, zero_value) | - | 0.94 |
| C-17e74dc9 | audit-chain › One canonical form for the audit event hash › the forms of an id | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_17e74dc9_forms_of_an_id (passed, zero_value) | - | 0.93 |
| C-3aaa99e2 | audit-chain › The chain is verified from the stored columns by its links › an event written by audit_emit verifies from its stored row | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_3aaa99e2_event_written_by_audit_emit_verifies_from_its_row (passed, zero_value) | - | 0.95 |
| C-5090a0a4 | audit-chain › The chain is verified from the stored columns by its links › a chain of three verifies in any order | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_5090a0a4_chain_of_three_verifies_in_any_order (passed, zero_value) | - | 0.93 |
| C-80a7cb05 | audit-chain › The chain is verified from the stored columns by its links › a time read back in another zone verifies | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_80a7cb05_time_read_back_in_another_zone_verifies (passed, zero_value) | - | 0.89 |
| C-e60cb8cf | audit-chain › The chain is verified from the stored columns by its links › a payload read back as JSON text verifies | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_e60cb8cf_payload_read_back_as_json_text_verifies (passed, zero_value) | - | 0.91 |
| C-2113cf48 | audit-chain › The chain is verified from the stored columns by its links › an event that does not follow the chain | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_2113cf48_event_that_does_not_follow_the_chain (passed, zero_value) | - | 0.94 |
| C-8fdf2bca | audit-chain › The chain is verified from the stored columns by its links › two events that follow the same hash | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_8fdf2bca_two_events_that_follow_the_same_hash (passed, zero_value) | - | 0.94 |
| C-7b97d875 | audit-chain › The chain is verified from the stored columns by its links › no events | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_7b97d875_no_events (passed, zero_value) | - | 0.93 |
| C-3c3643e2 | audit-chain › Altering any stored field of an event fails its verification › each stored field altered in turn | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[actor_id] (passed, zero_value); packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[actor_type] (passed, zero_value); packages.python.mintkey-models... | - | - |
| C-7537b2bd | audit-chain › Altering any stored field of an event fails its verification › a payload change reports both hashes | covered | packages.python.mintkey-models.tests.test_audit_hash::test_C_7537b2bd_payload_change_reports_both_hashes (passed, zero_value) | - | 0.94 |
| C-eaabd043 | audit-chain › The verify job checks a chain with the canonical form › the job verifies an event written by audit_emit | covered | tests.unit.admin_api.test_audit_verify_job_chain::test_C_eaabd043_job_verifies_an_event_written_by_audit_emit (passed, zero_value) | - | 0.94 |
| C-6e72b396 | audit-chain › The verify job checks a chain with the canonical form › the job reports an altered field | covered | tests.unit.admin_api.test_audit_verify_job_chain::test_C_6e72b396_job_reports_an_altered_field (passed, zero_value) | - | 0.94 |
| C-7a6282bc | audit-chain › The verify job checks a chain with the canonical form › a dataclass chain verifies, and an event without a time is refused | covered | tests.unit.admin_api.test_audit_verify_job_chain::test_C_7a6282bc_dataclass_chain_verifies_and_event_without_time_is_refused (passed, zero_value) | - | 0.95 |
| C-7d0c268b | audit-chain › The verify job checks a chain with the canonical form › main.py reads the 13 columns and exits by the result | covered | tests.unit.admin_api.test_audit_verify_job_chain::test_C_7d0c268b_main_reads_the_13_columns_and_exits_by_the_result (passed, zero_value) | - | 0.94 |
| C-7c6781a5 | audit-chain › The verify-chain endpoint checks a chain with the canonical form › the endpoint verifies an event written by audit_emit | covered | tests.unit.admin_api.test_audit_verify_endpoint_chain::test_C_7c6781a5_endpoint_verifies_event_written_by_audit_emit (passed, red_assertion) | - | 0.91 |
| C-e8293d4d | audit-chain › The verify-chain endpoint checks a chain with the canonical form › the endpoint reports an altered payload | covered | tests.unit.admin_api.test_audit_verify_endpoint_chain::test_C_e8293d4d_endpoint_reports_altered_payload (passed, red_assertion) | - | 0.93 |
| C-e5cc56fd | audit-chain › The verify-chain endpoint checks a chain with the canonical form › the endpoint reports an event that does not follow the chain | covered | tests.unit.admin_api.test_audit_verify_endpoint_chain::test_C_e5cc56fd_endpoint_reports_event_that_does_not_follow_chain (passed, red_assertion) | - | 0.94 |
| C-9e5600b1 | audit-chain › task 2.1: tests/unit/audit_verify/test_chain_verify.py set-up not changed — finding F-0b7e7198 › task 2.1: tests/unit/audit_verify/test_chain_verify.py set-up not changed | covered | tests.unit.admin_api.test_audit_verify_chain_setup::test_C_9e5600b1_chain_verify_setup_adds_model_path_and_builds_events_with_at (passed, red_assertion) | - | 0.85 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/audit_admin.py` | admin-api | relevant | named in the spec |
| `apps/audit-verify-job/main.py` | audit-verify-job | relevant | named in the spec |
| `apps/audit-verify-job/verify.py` | audit-verify-job | relevant | named in the spec |
| `openspec/changes/audit-chain-verifiable-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable-fix-1/specs/audit-chain/spec.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/ledger/r-20261026T1445Z-e448.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/ledger/r-20261026T1503Z-0ff1.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/ledger/r-20261026T1730Z-c15c.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/ledger/r-20261026T1813Z-f0d4.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/ledger/r-20261026T1842Z-289d.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/.l4/ledger/r-20261026T1918Z-d8e0.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-chain-verifiable/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/python/mintkey-models/mintkey_models/audit.py` | python | relevant | named in the spec |
| `packages/python/mintkey-models/mintkey_models/audit_hash.py` | python | relevant | named in the spec |
| `packages/python/mintkey-models/tests/test_audit_hash.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_audit_verify_chain_setup.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_audit_verify_endpoint.py` |  | relevant | named in the spec |
| `tests/unit/admin_api/test_audit_verify_endpoint_chain.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_audit_verify_job_chain.py` |  | relevant | new test file |
| `tests/unit/audit_verify/test_chain_verify.py` |  | none | changed by human commit 3e5a1ea8f3 |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2722 of 2776 passed, 0 failed, 0 errored, 54 skipped.
33 of 33 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-f7069358 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f3d1852b | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7c9b66d2 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-17e74dc9 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3aaa99e2 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5090a0a4 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-80a7cb05 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e60cb8cf | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2113cf48 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8fdf2bca | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7b97d875 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3c3643e2 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-7537b2bd | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-eaabd043 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6e72b396 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7a6282bc | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7d0c268b | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7c6781a5 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e8293d4d | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e5cc56fd | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9e5600b1 | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-f7069358 | audit-chain › One canonical form for the audit event hash › the canonical bytes of a fixed event | pass | pass | the judge passed it and a discriminating test passes |
| C-f3d1852b | audit-chain › One canonical form for the audit event hash › the writer's hash function keeps its result | pass | pass | the judge passed it and a discriminating test passes |
| C-7c9b66d2 | audit-chain › One canonical form for the audit event hash › the forms of a time | pass | pass | the judge passed it and a discriminating test passes |
| C-17e74dc9 | audit-chain › One canonical form for the audit event hash › the forms of an id | pass | pass | the judge passed it and a discriminating test passes |
| C-3aaa99e2 | audit-chain › The chain is verified from the stored columns by its links › an event written by audit_emit verifies from its stored row | pass | pass | the judge passed it and a discriminating test passes |
| C-5090a0a4 | audit-chain › The chain is verified from the stored columns by its links › a chain of three verifies in any order | pass | pass | the judge passed it and a discriminating test passes |
| C-80a7cb05 | audit-chain › The chain is verified from the stored columns by its links › a time read back in another zone verifies | pass | pass | the judge passed it and a discriminating test passes |
| C-e60cb8cf | audit-chain › The chain is verified from the stored columns by its links › a payload read back as JSON text verifies | pass | pass | the judge passed it and a discriminating test passes |
| C-2113cf48 | audit-chain › The chain is verified from the stored columns by its links › an event that does not follow the chain | pass | pass | the judge passed it and a discriminating test passes |
| C-8fdf2bca | audit-chain › The chain is verified from the stored columns by its links › two events that follow the same hash | pass | pass | the judge passed it and a discriminating test passes |
| C-7b97d875 | audit-chain › The chain is verified from the stored columns by its links › no events | pass | pass | the judge passed it and a discriminating test passes |
| C-3c3643e2 | audit-chain › Altering any stored field of an event fails its verification › each stored field altered in turn | pass | pass | the judge passed it and a discriminating test passes |
| C-7537b2bd | audit-chain › Altering any stored field of an event fails its verification › a payload change reports both hashes | pass | pass | the judge passed it and a discriminating test passes |
| C-eaabd043 | audit-chain › The verify job checks a chain with the canonical form › the job verifies an event written by audit_emit | pass | pass | the judge passed it and a discriminating test passes |
| C-6e72b396 | audit-chain › The verify job checks a chain with the canonical form › the job reports an altered field | pass | pass | the judge passed it and a discriminating test passes |
| C-7a6282bc | audit-chain › The verify job checks a chain with the canonical form › a dataclass chain verifies, and an event without a time is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-7d0c268b | audit-chain › The verify job checks a chain with the canonical form › main.py reads the 13 columns and exits by the result | pass | pass | the judge passed it and a discriminating test passes |
| C-7c6781a5 | audit-chain › The verify-chain endpoint checks a chain with the canonical form › the endpoint verifies an event written by audit_emit | pass | pass | the judge passed it and a discriminating test passes |
| C-e8293d4d | audit-chain › The verify-chain endpoint checks a chain with the canonical form › the endpoint reports an altered payload | pass | pass | the judge passed it and a discriminating test passes |
| C-e5cc56fd | audit-chain › The verify-chain endpoint checks a chain with the canonical form › the endpoint reports an event that does not follow the chain | pass | pass | the judge passed it and a discriminating test passes |
| C-9e5600b1 | audit-chain › task 2.1: tests/unit/audit_verify/test_chain_verify.py set-up not changed — finding F-0b7e7198 › task 2.1: tests/unit/audit_verify/test_chain_verify.py set-up not changed | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Fork tie-breaking with duplicate prev_hash events depends on list order (spec gap) (criterion C-8fdf2bca): verify_events picks the first unvisited event in list order with matching prev_hash; ordering by at,id determines which fork is named.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.python.mintkey-models.tests.test_audit_hash::test_C_17e74dc9_forms_of_an_id` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_2113cf48_event_that_does_not_follow_the_chain` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3aaa99e2_event_written_by_audit_emit_verifies_from_its_row` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[actor_id]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[actor_type]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[at]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[event_type]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[hash]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[id]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[payload]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[prev_hash]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[request_id]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[target_id]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[target_type]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[tenant_id]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_3c3643e2_altering_one_stored_field_fails[trace_id]` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_5090a0a4_chain_of_three_verifies_in_any_order` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_7537b2bd_payload_change_reports_both_hashes` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_7b97d875_no_events` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_7c9b66d2_forms_of_a_time` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_80a7cb05_time_read_back_in_another_zone_verifies` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_8fdf2bca_two_events_that_follow_the_same_hash` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_e60cb8cf_payload_read_back_as_json_text_verifies` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_f3d1852b_writers_hash_function_keeps_its_result` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_audit_hash::test_C_f7069358_canonical_bytes_of_a_fixed_event` (task 1.1): passed
- `tests.unit.admin_api.test_audit_verify_chain_setup::test_C_9e5600b1_chain_verify_setup_adds_model_path_and_builds_events_with_at` (task 1.1): passed
- `tests.unit.admin_api.test_audit_verify_endpoint_chain::test_C_7c6781a5_endpoint_verifies_event_written_by_audit_emit` (task 2.2): passed
- `tests.unit.admin_api.test_audit_verify_endpoint_chain::test_C_e5cc56fd_endpoint_reports_event_that_does_not_follow_chain` (task 2.2): passed
- `tests.unit.admin_api.test_audit_verify_endpoint_chain::test_C_e8293d4d_endpoint_reports_altered_payload` (task 2.2): passed
- `tests.unit.admin_api.test_audit_verify_job_chain::test_C_6e72b396_job_reports_an_altered_field` (task 2.1): passed
- `tests.unit.admin_api.test_audit_verify_job_chain::test_C_7a6282bc_dataclass_chain_verifies_and_event_without_time_is_refused` (task 2.1): passed
- `tests.unit.admin_api.test_audit_verify_job_chain::test_C_7d0c268b_main_reads_the_13_columns_and_exits_by_the_result` (task 2.1): passed
- `tests.unit.admin_api.test_audit_verify_job_chain::test_C_eaabd043_job_verifies_an_event_written_by_audit_emit` (task 2.1): passed

## Guard events

- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.test_tamper: tests/unit/audit_verify/test_chain_verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.violation: apps/audit-verify-job/verify.py
- guard.test_tamper: tests/unit/audit_verify/test_chain_verify.py
- guard.test_tamper: tests/unit/audit_verify/test_chain_verify.py
- guard.test_tamper: tests/unit/admin_api/test_audit_verify_endpoint.py
- guard.test_tamper: tests/unit/audit_verify/test_chain_verify.py
