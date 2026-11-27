# Verification: openspec:agent-principal-and-egress: PASS (round 4)

traceability: 16/16 criteria covered by a discriminating test

- Base: `0c676fec3046d36705bfcfb5f6cb6ec193ef2f5d`
- Head: `9040cfcf04bd4dfdebc48c0ac7a967e6022bc69e`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `db7fc1bf1f5cc64b1c4934e236eeb464ae42d769451bd44c576268aa1ce4eea2`
- Judge replies of claude-judge (this unit, all rounds): valid 2, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $0.9801

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.9 | base staging@0c676fec30 contained |
| 1 | integrity | ok | 310.0 | 11 sub-checks; scope: 34 changed file(s) |
| 2 | build | ok | 92.4 |  |
| 3 | tests | ok | 113.6 |  |
| 4 | traceability | ok | 0.2 | 16/16 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 0.9 | 16/16 criteria judged by jev |
| 9 | judge | ok | 33.2 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261127T1554Z-53c9/165-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261127T1554Z-53c9/166-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261127T1554Z-53c9/167-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261127T1554Z-53c9/168-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261127T1554Z-53c9/169-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261127T1554Z-53c9/170-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261127T1554Z-53c9/171-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261127T1554Z-53c9/172-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261127T1554Z-53c9/173-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261127T1554Z-53c9/174-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261127T1554Z-53c9/175-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261127T1554Z-53c9/176-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261127T1554Z-53c9/177-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 7 test file(s) compared with the base |
| red-green freeze | ok | 8 task(s): red and green compared |
| test path freeze | ok | 9 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 8 new suppression(s), 8 declared |
| tdd history | ok | 8 task(s); red tests passing at head: step 3 |
| python encoding | ok | 10 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 2966 of 2966 base tests pass on the unit's code with its 7 test and support files at the base (base: evidence) |

Declared suppressions:
- tests/unit/admin_api/test_agent_principal.py:39 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:40 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:41 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:46 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:47 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_role_refusal.py:32 # noqa: E402 (declared: The import must follow the test's repository sys.path bootstrap; a fix task may not edit the test file, so the comment i)
- tests/unit/admin_api/test_agent_role_refusal.py:33 # noqa: E402 (declared: The import must follow the test's repository sys.path bootstrap; a fix task may not edit the test file, so the comment i)
- tests/unit/admin_api/test_agent_role_refusal.py:38 # noqa: E402 (declared: The import must follow the test's repository sys.path bootstrap; a fix task may not edit the test file, so the comment i)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-90151371 | agent-egress-policy › Agent-supplied URLs must be public https targets › refused URLs | covered | packages.python.mintkey-models.tests.test_egress::test_C_90151371_refused_urls (passed, zero_value) | - | 0.93 |
| C-3a64dd27 | agent-egress-policy › Agent-supplied URLs must be public https targets › names that resolve badly, and accepted URLs | covered | packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_accepted_urls (passed, zero_value); packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_address_is_public (passed, zero_value); packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_names_that_resolve_badly (... | - | 0.94 |
| C-97e80bfe | agent-egress-policy › Agent-supplied URLs must be public https targets › the deny list reader | covered | packages.python.mintkey-models.tests.test_egress::test_C_97e80bfe_deny_names_reader (passed, zero_value) | - | 0.96 |
| C-9a0d1912 | agent-principal › The key check is one function › the check returns the row or the answer | covered | tests.unit.admin_api.test_agent_key_check::test_C_083b1a5a_C_9a0d1912_validate_agent_key_issues_no_statement_itself (passed, zero_value); tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_expired_key_returns_the_expired_401 (passed, zero_value); tests.unit.admin_api.test_agent_key_check::te... | - | 0.92 |
| C-083b1a5a | agent-principal › The key check is one function › the endpoint is unchanged | covered | tests.unit.admin_api.test_agent_key_check::test_C_083b1a5a_C_9a0d1912_validate_agent_key_issues_no_statement_itself (passed, zero_value) | - | 0.84 |
| C-3c508836 | agent-principal › An agent key yields a principal › a publisher key | covered | tests.unit.admin_api.test_agent_principal::test_C_3c508836_publisher_key_yields_the_principal (passed, zero_value) | - | 0.92 |
| C-5b21f986 | agent-principal › An agent key yields a principal › no usable credential | covered | tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[basic_auth] (passed, zero_value); tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[bearer_not_an_agent_key] (passed, zero_value); tests.uni... | - | 0.94 |
| C-5861b2ec | agent-principal › An agent key yields a principal › rejected keys | covered | tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[expired_key_401] (passed, zero_value); tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[unknown_key_401] (passed, zero_value); tests.unit.admin_api.test_... | - | 0.94 |
| C-70750b4d | agent-principal › An agent key yields a principal › the database fails while the key is checked | covered | tests.unit.admin_api.test_agent_principal::test_C_70750b4d_key_check_failure_is_503_and_closes_the_session (passed, zero_value); tests.unit.admin_api.test_agent_principal::test_C_70750b4d_session_factory_failure_is_503 (passed, zero_value) | - | 0.93 |
| C-acbb978c | agent-principal › An agent key yields a principal › the route's session never sees the platform view | covered | tests.unit.admin_api.test_agent_principal::test_C_acbb978c_route_session_never_sees_the_platform_view (passed, zero_value) | - | 0.95 |
| C-882edc8c | agent-principal › A role that is too low is refused and recorded › the wrong role is refused with a literal operation | covered | tests.unit.admin_api.test_agent_role_refusal::test_C_882edc8c_consumer_is_refused_and_the_denial_is_recorded (passed, zero_value); tests.unit.admin_api.test_agent_role_refusal::test_C_882edc8c_publisher_passes_and_records_nothing (passed, zero_value) | - | 0.94 |
| C-aa34abc8 | agent-principal › A role that is too low is refused and recorded › the record itself fails | covered | tests.unit.admin_api.test_agent_role_refusal::test_C_aa34abc8_audit_failure_still_answers_403_and_logs (passed, zero_value); tests.unit.admin_api.test_agent_role_refusal::test_C_aa34abc8_session_failure_still_answers_403_and_logs (passed, zero_value) | - | 0.94 |
| C-c66906b5 | agent-principal › The contract lists the denied-operation event › the contract lists it | covered | tests.unit.admin_api.test_audit_schema_agent_denied::test_C_c66906b5_definition_states_event_and_payload (passed, red_assertion); tests.unit.admin_api.test_audit_schema_agent_denied::test_C_c66906b5_mapping_one_of_and_envelope_actor (passed, red_assertion) | - | 0.94 |
| C-0ed78ab3 | agent-egress-policy › Refuse the IPv6 forms that carry an IPv4 address — feedback FB-001 › Refuse the IPv6 forms that carry an IPv4 address | covered | packages.python.mintkey-models.tests.test_egress::test_C_0ed78ab3_ipv4_embedding_ipv6_ranges_are_refused (passed, red_assertion) | - | 0.90 |
| C-879687b1 | agent-egress-policy › A malformed agent-supplied URL is refused, never an error — feedback FB-002 › A malformed agent-supplied URL is refused, never an error | covered | packages.python.mintkey-models.tests.test_egress_malformed_url::test_C_879687b1_bad_host_labels_are_refused (passed, red_assertion); packages.python.mintkey-models.tests.test_egress_malformed_url::test_C_879687b1_forbidden_characters_are_refused (passed, red_assertion); packages.python.mintkey-model... | - | 0.94 |
| C-41b9e69f | agent-egress-policy › The deny list matches names however they are written — feedback FB-003 › The deny list matches names however they are written | covered | packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_deny_entry_trailing_dots_match_host (passed, red_assertion); packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_host_trailing_dots_match_deny_entry (passed, red_assertion); packages.python.mintkey-... | - | 0.95 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/internal.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/auth/agent_principal.py` | admin-api | relevant | named in the spec |
| `docs/architecture/contracts/events/audit-event.schema.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-2/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-2/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-2/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-2/specs/agent-egress-policy/spec.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress-fix-2/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-3/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/evidence/round-3/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/ledger/r-20261127T1106Z-019e.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/ledger/r-20261127T1336Z-73e4.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/ledger/r-20261127T1554Z-53c9.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/feedback.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/python/mintkey-models/mintkey_models/egress.py` | python | relevant | named in the spec |
| `packages/python/mintkey-models/tests/test_egress.py` |  | relevant | new test file |
| `packages/python/mintkey-models/tests/test_egress_deny_names.py` |  | relevant | new test file |
| `packages/python/mintkey-models/tests/test_egress_malformed_url.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_key_check.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_principal.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_role_refusal.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_audit_schema_agent_denied.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

3010 of 3064 passed, 0 failed, 0 errored, 54 skipped.
43 of 43 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-90151371 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3a64dd27 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-97e80bfe | ok | 0.960 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9a0d1912 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-083b1a5a | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3c508836 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5b21f986 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5861b2ec | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-70750b4d | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-acbb978c | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-882edc8c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-aa34abc8 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c66906b5 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0ed78ab3 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-879687b1 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-41b9e69f | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-90151371 | agent-egress-policy › Agent-supplied URLs must be public https targets › refused URLs | pass | pass | the judge passed it and a discriminating test passes |
| C-3a64dd27 | agent-egress-policy › Agent-supplied URLs must be public https targets › names that resolve badly, and accepted URLs | pass | pass | the judge passed it and a discriminating test passes |
| C-97e80bfe | agent-egress-policy › Agent-supplied URLs must be public https targets › the deny list reader | pass | pass | the judge passed it and a discriminating test passes |
| C-9a0d1912 | agent-principal › The key check is one function › the check returns the row or the answer | pass | pass | the judge passed it and a discriminating test passes |
| C-083b1a5a | agent-principal › The key check is one function › the endpoint is unchanged | pass | pass | the judge passed it and a discriminating test passes |
| C-3c508836 | agent-principal › An agent key yields a principal › a publisher key | pass | pass | the judge passed it and a discriminating test passes |
| C-5b21f986 | agent-principal › An agent key yields a principal › no usable credential | pass | pass | the judge passed it and a discriminating test passes |
| C-5861b2ec | agent-principal › An agent key yields a principal › rejected keys | pass | pass | the judge passed it and a discriminating test passes |
| C-70750b4d | agent-principal › An agent key yields a principal › the database fails while the key is checked | pass | pass | the judge passed it and a discriminating test passes |
| C-acbb978c | agent-principal › An agent key yields a principal › the route's session never sees the platform view | pass | pass | the judge passed it and a discriminating test passes |
| C-882edc8c | agent-principal › A role that is too low is refused and recorded › the wrong role is refused with a literal operation | pass | pass | the judge passed it and a discriminating test passes |
| C-aa34abc8 | agent-principal › A role that is too low is refused and recorded › the record itself fails | pass | pass | the judge passed it and a discriminating test passes |
| C-c66906b5 | agent-principal › The contract lists the denied-operation event › the contract lists it | pass | pass | the judge passed it and a discriminating test passes |
| C-0ed78ab3 | agent-egress-policy › Refuse the IPv6 forms that carry an IPv4 address — feedback FB-001 › Refuse the IPv6 forms that carry an IPv4 address | pass | pass | the judge passed it and a discriminating test passes |
| C-879687b1 | agent-egress-policy › A malformed agent-supplied URL is refused, never an error — feedback FB-002 › A malformed agent-supplied URL is refused, never an error | pass | pass | the judge passed it and a discriminating test passes |
| C-41b9e69f | agent-egress-policy › The deny list matches names however they are written — feedback FB-003 › The deny list matches names however they are written | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, deterministic] a pre-existing test is flaky on the unit's code: tests.acceptance.test_async_audit_emission::test_auditq_unit_tests_pass
- [minor, judge] Unusable deny entry is logged on every check, not once per process (spec gap) (criterion C-41b9e69f): egress_deny_names() warns each time it is called, and check_agent_target_url calls it per URL, so an unusable entry is logged repeatedly across checks. The spec's 'reported once' is not pinned for repeated calls.

## Feedback

- FB-001: addressed at 9040cfcf04: egress.py _IPV4_EMBEDDING_V6 and address_is_public refuse 64:ff9b::/96, 2002::/16, 2001::/32; test_C_0ed78ab3
- FB-002: addressed at 9040cfcf04: egress.py _has_forbidden_character, _labels_are_valid, _NUMERIC_LAST_LABEL, and except (OSError, UnicodeError) around resolve_host
- FB-003: addressed at 9040cfcf04: egress.py egress_deny_names rstrip('.') and _deny_entry_is_usable warning; host.endswith('.localhost') check in check_agent_target_url

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.python.mintkey-models.tests.test_egress::test_C_0ed78ab3_ipv4_embedding_ipv6_ranges_are_refused` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_accepted_urls` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_address_is_public` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_names_that_resolve_badly` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_egress::test_C_90151371_refused_urls` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_egress::test_C_97e80bfe_deny_names_reader` (task 1.1): passed
- `packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_deny_entry_trailing_dots_match_host` (task 1.3): passed
- `packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_host_trailing_dots_match_deny_entry` (task 1.3): passed
- `packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_localhost_and_names_under_it_are_refused` (task 1.3): passed
- `packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_unusable_entry_is_logged_once_as_ignored[*.]` (task 1.3): passed
- `packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_unusable_entry_is_logged_once_as_ignored[*]` (task 1.3): passed
- `packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_unusable_entry_is_logged_once_as_ignored[*example.com]` (task 1.3): passed
- `packages.python.mintkey-models.tests.test_egress_deny_names::test_C_41b9e69f_unusable_entry_is_logged_once_as_ignored[.example.com]` (task 1.3): passed
- `packages.python.mintkey-models.tests.test_egress_malformed_url::test_C_879687b1_bad_host_labels_are_refused` (task 1.2): passed
- `packages.python.mintkey-models.tests.test_egress_malformed_url::test_C_879687b1_forbidden_characters_are_refused` (task 1.2): passed
- `packages.python.mintkey-models.tests.test_egress_malformed_url::test_C_879687b1_numeric_last_labels_are_refused` (task 1.2): passed
- `packages.python.mintkey-models.tests.test_egress_malformed_url::test_C_879687b1_resolver_error_on_malformed_host_never_escapes` (task 1.2): passed
- `tests.unit.admin_api.test_agent_key_check::test_C_083b1a5a_C_9a0d1912_validate_agent_key_issues_no_statement_itself` (task 2.1): passed
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_expired_key_returns_the_expired_401` (task 2.1): passed
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_unknown_key_returns_the_invalid_key_401` (task 2.1): passed
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_valid_key_returns_the_row_and_none` (task 2.1): passed
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_verify_failure_returns_the_503` (task 2.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_3c508836_publisher_key_yields_the_principal` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[expired_key_401]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[unknown_key_401]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[verify_unavailable_503]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_rejected_key_raises_agent_api_error[expired_key_401]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_rejected_key_raises_agent_api_error[unknown_key_401]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_rejected_key_raises_agent_api_error[verify_unavailable_503]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[basic_auth]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[bearer_not_an_agent_key]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[cookie_only]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[no_header]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[x_api_key_only]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_70750b4d_key_check_failure_is_503_and_closes_the_session` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_70750b4d_session_factory_failure_is_503` (task 3.1): passed
- `tests.unit.admin_api.test_agent_principal::test_C_acbb978c_route_session_never_sees_the_platform_view` (task 3.1): passed
- `tests.unit.admin_api.test_agent_role_refusal::test_C_882edc8c_consumer_is_refused_and_the_denial_is_recorded` (task 3.2): passed
- `tests.unit.admin_api.test_agent_role_refusal::test_C_882edc8c_publisher_passes_and_records_nothing` (task 3.2): passed
- `tests.unit.admin_api.test_agent_role_refusal::test_C_aa34abc8_audit_failure_still_answers_403_and_logs` (task 3.2): passed
- `tests.unit.admin_api.test_agent_role_refusal::test_C_aa34abc8_session_failure_still_answers_403_and_logs` (task 3.2): passed
- `tests.unit.admin_api.test_audit_schema_agent_denied::test_C_c66906b5_definition_states_event_and_payload` (task 4.1): passed
- `tests.unit.admin_api.test_audit_schema_agent_denied::test_C_c66906b5_mapping_one_of_and_envelope_actor` (task 4.1): passed

## Guard events

- guard.test_tamper: tests/unit/admin_api/test_agent_role_refusal.py
