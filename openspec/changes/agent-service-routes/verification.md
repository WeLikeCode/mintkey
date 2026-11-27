# Verification: openspec:agent-service-routes: PASS (round 1)

traceability: 21/21 criteria covered by a discriminating test

- Base: `128a5a77e2907c2a6a03faffcb462d2c4528e5ae`
- Head: `741cce46f753966e80d563c2a46de12918677cbc`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), judged in 2 parts, prompt sha256 `cb9339de56b7bfbd4786f98f30c3d800ed659f0c8e32f0c5f2215a355be812d3`
  - part 1: 7 file(s), 96758 characters, profile claude-judge, reply valid
  - part 2: 7 file(s), 53202 characters, profile claude-judge, reply valid
- Judge replies of claude-judge (this unit, all rounds): valid 2, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $1.8971

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base merged: staging@128a5a77e2 as 741cce46f7 (1 commit) |
| 1 | integrity | ok | 365.1 | 11 sub-checks; scope: 18 changed file(s) |
| 2 | build | ok | 104.2 |  |
| 3 | tests | ok | 131.3 |  |
| 4 | traceability | ok | 0.2 | 21/21 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 1.2 | 18/21 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 48.4 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261127T2226Z-441e/039-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261127T2226Z-441e/040-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261127T2226Z-441e/041-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261127T2226Z-441e/042-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261127T2226Z-441e/043-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261127T2226Z-441e/044-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261127T2226Z-441e/045-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261127T2226Z-441e/046-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261127T2226Z-441e/047-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261127T2226Z-441e/048-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261127T2226Z-441e/049-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261127T2226Z-441e/050-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261127T2226Z-441e/051-test.log |

## Files by part

- part 1: apps/admin-api/src/admin_api/api/agent.py (768 characters)
- part 1: apps/admin-api/src/admin_api/services/agent_publishing.py (5874 characters)
- part 1: tests/unit/admin_api/test_agent_publishing_service.py (9867 characters)
- part 1: apps/admin-api/src/admin_api/api/agent_services.py (23968 characters)
- part 1: tests/unit/admin_api/test_agent_credential.py (25389 characters)
- part 1: tests/unit/admin_api/test_agent_service_error_bodies.py (10795 characters)
- part 1: tests/unit/admin_api/test_agent_services_create.py (20097 characters)
- part 2: tests/unit/admin_api/test_agent_services_update.py (23639 characters)
- part 2: docs/architecture/contracts/events/audit-event.schema.json (3738 characters)
- part 2: tests/unit/admin_api/test_audit_schema_agent_services.py (5449 characters)
- part 2: apps/admin-api/src/admin_api/main.py (2087 characters)
- part 2: tests/unit/admin_api/test_agent_routes_isolation.py (13492 characters)
- part 2: tests/acceptance/openapi_snapshot.json (436 characters)
- part 2: openspec/changes/agent-service-routes/tasks.md (4361 characters)

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 7 test file(s) compared with the base; 1 other test file(s) are checked by the run of pre-existing tests |
| red-green freeze | ok | 6 task(s): red and green compared |
| test path freeze | ok | 6 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 3 new suppression(s), 3 declared |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |
| python encoding | ok | 11 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 3009 of 3009 base tests pass on the unit's code with its 7 test and support files at the base (base: base worktree) |

Declared suppressions:
- tests/unit/admin_api/test_agent_publishing_service.py:39 # noqa: E402 (declared: Import follows sys.path setup for the admin-api and mintkey-models sources, as the existing unit tests do.)
- tests/unit/admin_api/test_agent_publishing_service.py:40 # noqa: E402 (declared: Import follows sys.path setup for the admin-api and mintkey-models sources, as the existing unit tests do.)
- tests/unit/admin_api/test_agent_publishing_service.py:45 # noqa: E402 (declared: Import follows sys.path setup for the admin-api and mintkey-models sources, as the existing unit tests do.)

## Pre-existing tests changed with an allowance (L4-VER-031)

- tests/acceptance/openapi_snapshot.json kept at head for the run (task 6.1: unfrozen by Q-001)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-4b7e8c8f | agent-service-credential › A credential is written, never read, and bound to its target › a bearer credential | covered | tests.unit.admin_api.test_agent_credential::test_C_4b7e8c8f_bearer_credential_is_written_and_never_echoed (passed, zero_value) | - | 0.93 |
| C-3be566fb | agent-service-credential › A credential is written, never read, and bound to its target › header and query names | covered | tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_header] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_query] (passed, zero_value); tests.unit.admi... | - | - |
| C-08831467 | agent-service-credential › A credential is written, never read, and bound to its target › bad values, other owners, a failing vault, an unsupported scheme | covered | tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[array] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[extra_key] (passed, zero_value); tests.unit.admin_api.test_agent_... | - | - |
| C-6d26cd39 | agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write | covered | tests.unit.admin_api.test_agent_credential::test_C_6d26cd39_row_is_locked_before_the_vault_write (passed, zero_value) | - | 0.82 |
| C-e79dc506 | agent-service-credential › The new events are in the audit contract › the contract lists them | covered | tests.unit.admin_api.test_audit_schema_agent_services::test_C_e79dc506_credential_cleared_definition (passed, red_assertion); tests.unit.admin_api.test_audit_schema_agent_services::test_C_e79dc506_credential_events_mapped_and_in_one_of (passed, red_assertion); tests.unit.admin_api.test_audit_schema_... | - | 0.92 |
| C-48021709 | agent-service-routes › The agent routes are separate from the operator routes › the route table | covered | tests.unit.admin_api.test_agent_routes_isolation::test_C_48021709_agent_route_table_and_snapshot (passed, red_assertion) | - | 0.89 |
| C-96185b5c | agent-service-routes › The agent routes are separate from the operator routes › a cookie-less POST reaches authentication | covered | tests.unit.admin_api.test_agent_routes_isolation::test_C_96185b5c_cookieless_post_reaches_agent_authentication (passed, red_assertion) | - | 0.95 |
| C-25c5b05b | agent-service-routes › The agent routes are separate from the operator routes › a consumer key is refused | covered | tests.unit.admin_api.test_agent_routes_isolation::test_C_25c5b05b_consumer_is_refused_on_each_route (passed, red_assertion) | - | 0.94 |
| C-00b5d763 | agent-service-routes › Every error of the service routes has one body › one body shape | covered | tests.unit.admin_api.test_agent_service_error_bodies::test_C_00b5d763_every_refusal_has_one_exact_body (passed, zero_value) | - | 0.94 |
| C-b64100a4 | agent-service-routes › The owned service lookup is one function › references | covered | tests.unit.admin_api.test_agent_publishing_service::test_C_b64100a4_parse_service_ref_decodes_ids_and_passes_slugs (passed, zero_value) | - | 0.93 |
| C-404b5f68 | agent-service-routes › The owned service lookup is one function › ownership | covered | tests.unit.admin_api.test_agent_publishing_service::test_C_404b5f68_require_owned_service_returns_owned_and_refuses_others (passed, zero_value) | - | 0.94 |
| C-7d79dfe4 | agent-service-routes › The owned service lookup is one function › the view | covered | tests.unit.admin_api.test_agent_publishing_service::test_C_7d79dfe4_service_view_has_twelve_keys_and_nullable_timestamps (passed, zero_value) | - | 0.90 |
| C-a7c250ac | agent-service-routes › A publisher creates a service › a service is created | covered | tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_returns_returning_row_and_writes_event (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_uses_the_name_as_display_name (passed, zero_value) | - | 0.84 |
| C-b190eac4 | agent-service-routes › A publisher creates a service › refused bodies | covered | tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[bad_name] (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[extra_owner] (passed, zero_value); tests.unit.... | - | - |
| C-c7dc1fce | agent-service-routes › A publisher creates a service › a taken slug | covered | tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_existing_slug_conflicts_without_an_insert (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_integrity_error_conflicts (passed, zero_value) | - | 0.94 |
| C-c4f8c198 | agent-service-routes › A publisher lists its own services › the list is the caller's | covered | tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_returns_the_callers_services (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_without_owned_services_is_empty (passed, zero_value) | - | 0.92 |
| C-d225b1e7 | agent-service-routes › A publisher updates only its own services › a metadata edit keeps the credential, a changed target clears it | covered | tests.unit.admin_api.test_agent_services_update::test_C_d225b1e7_auth_scheme_change_clears_the_credential (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_d225b1e7_base_url_change_clears_the_credential (passed, zero_value); tests.unit.admin_api.test_agent_services_update... | - | 0.94 |
| C-ce4c7660 | agent-service-routes › A publisher updates only its own services › a changed target without a credential, nothing changed, refused | covered | tests.unit.admin_api.test_agent_services_update::test_C_ce4c7660_changed_target_without_credential_deletes_without_event (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_ce4c7660_refused_target_writes_nothing (passed, zero_value); tests.unit.admin_api.test_agent_services... | - | 0.86 |
| C-f996158c | agent-service-routes › A publisher updates only its own services › not the owner | covered | tests.unit.admin_api.test_agent_services_update::test_C_f996158c_not_owned_patch_is_refused_without_update[no_owner] (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_f996158c_not_owned_patch_is_refused_without_update[other_agent] (passed, zero_value); tests.unit.admin_ap... | - | 0.94 |
| C-9092a793 | agent-service-routes › A publisher updates only its own services › refused bodies | covered | tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[empty] (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[name_key] (passed, zero_value);... | - | 0.90 |
| C-ec735b1d | agent-service-routes › A publisher updates only its own services › the row is locked first | covered | tests.unit.admin_api.test_agent_services_update::test_C_ec735b1d_row_is_locked_before_every_update_and_delete (passed, zero_value) | - | 0.86 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/agent.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/agent_services.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/main.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/services/agent_publishing.py` | admin-api | relevant | named in the spec |
| `docs/architecture/contracts/events/audit-event.schema.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261127T1729Z-559f.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261127T2004Z-3d36.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261127T2226Z-441e.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `tests/acceptance/openapi_snapshot.json` |  | relevant | named in the spec |
| `tests/unit/admin_api/test_agent_credential.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_publishing_service.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_routes_isolation.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_service_error_bodies.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_services_create.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_services_update.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_audit_schema_agent_services.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

3079 of 3133 passed, 0 failed, 0 errored, 54 skipped.
69 of 69 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-4b7e8c8f | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3be566fb | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-08831467 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-6d26cd39 | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e79dc506 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-48021709 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-96185b5c | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-25c5b05b | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-00b5d763 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b64100a4 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-404b5f68 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7d79dfe4 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a7c250ac | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b190eac4 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-c7dc1fce | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c4f8c198 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d225b1e7 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ce4c7660 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f996158c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9092a793 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ec735b1d | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-4b7e8c8f | agent-service-credential › A credential is written, never read, and bound to its target › a bearer credential | pass | pass | the judge passed it and a discriminating test passes |
| C-3be566fb | agent-service-credential › A credential is written, never read, and bound to its target › header and query names | pass | pass | the judge passed it and a discriminating test passes |
| C-08831467 | agent-service-credential › A credential is written, never read, and bound to its target › bad values, other owners, a failing vault, an unsupported scheme | pass | pass | the judge passed it and a discriminating test passes |
| C-6d26cd39 | agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write | pass | pass | the judge passed it and a discriminating test passes |
| C-e79dc506 | agent-service-credential › The new events are in the audit contract › the contract lists them | pass | pass | the judge passed it and a discriminating test passes |
| C-48021709 | agent-service-routes › The agent routes are separate from the operator routes › the route table | pass | pass | the judge passed it and a discriminating test passes |
| C-96185b5c | agent-service-routes › The agent routes are separate from the operator routes › a cookie-less POST reaches authentication | pass | pass | the judge passed it and a discriminating test passes |
| C-25c5b05b | agent-service-routes › The agent routes are separate from the operator routes › a consumer key is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-00b5d763 | agent-service-routes › Every error of the service routes has one body › one body shape | pass | pass | the judge passed it and a discriminating test passes |
| C-b64100a4 | agent-service-routes › The owned service lookup is one function › references | pass | pass | the judge passed it and a discriminating test passes |
| C-404b5f68 | agent-service-routes › The owned service lookup is one function › ownership | pass | pass | the judge passed it and a discriminating test passes |
| C-7d79dfe4 | agent-service-routes › The owned service lookup is one function › the view | pass | pass | the judge passed it and a discriminating test passes |
| C-a7c250ac | agent-service-routes › A publisher creates a service › a service is created | pass | pass | the judge passed it and a discriminating test passes |
| C-b190eac4 | agent-service-routes › A publisher creates a service › refused bodies | pass | pass | the judge passed it and a discriminating test passes |
| C-c7dc1fce | agent-service-routes › A publisher creates a service › a taken slug | pass | pass | the judge passed it and a discriminating test passes |
| C-c4f8c198 | agent-service-routes › A publisher lists its own services › the list is the caller's | pass | pass | the judge passed it and a discriminating test passes |
| C-d225b1e7 | agent-service-routes › A publisher updates only its own services › a metadata edit keeps the credential, a changed target clears it | pass | pass | the judge passed it and a discriminating test passes |
| C-ce4c7660 | agent-service-routes › A publisher updates only its own services › a changed target without a credential, nothing changed, refused | pass | pass | the judge passed it and a discriminating test passes |
| C-f996158c | agent-service-routes › A publisher updates only its own services › not the owner | pass | pass | the judge passed it and a discriminating test passes |
| C-9092a793 | agent-service-routes › A publisher updates only its own services › refused bodies | pass | pass | the judge passed it and a discriminating test passes |
| C-ec735b1d | agent-service-routes › A publisher updates only its own services › the row is locked first | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] PATCH with an explicit null field is a silent no-op (spec gap) (criterion C-ce4c7660): Fields set to null are skipped in `changed`, so {"display_name": null} answers 200 with no change.

## New tests (red then green, `task.red_ok` in the ledger)

- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[array]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[extra_key]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[unreadable_json]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[carriage_return]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[empty]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[line_feed]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[nul]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[too_long]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_failing_vault_answers_502_before_metadata` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_other_owner_answers_403_without_a_write` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_unsupported_scheme_answers_422_without_a_vault_call` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_header]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_query]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_bad_characters]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_connection]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_content_length]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_host]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_missing]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_transfer_encoding]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_valid]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_x_mintkey]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_x_mintkey_lower]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[query_missing]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[query_valid]` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_4b7e8c8f_bearer_credential_is_written_and_never_echoed` (task 4.1): passed
- `tests.unit.admin_api.test_agent_credential::test_C_6d26cd39_row_is_locked_before_the_vault_write` (task 4.1): passed
- `tests.unit.admin_api.test_agent_publishing_service::test_C_404b5f68_require_owned_service_returns_owned_and_refuses_others` (task 1.1): passed
- `tests.unit.admin_api.test_agent_publishing_service::test_C_7d79dfe4_service_view_has_twelve_keys_and_nullable_timestamps` (task 1.1): passed
- `tests.unit.admin_api.test_agent_publishing_service::test_C_b64100a4_parse_service_ref_decodes_ids_and_passes_slugs` (task 1.1): passed
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_25c5b05b_consumer_is_refused_on_each_route` (task 6.1): passed
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_48021709_agent_route_table_and_snapshot` (task 6.1): passed
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_96185b5c_cookieless_post_reaches_agent_authentication` (task 6.1): passed
- `tests.unit.admin_api.test_agent_service_error_bodies::test_C_00b5d763_every_refusal_has_one_exact_body` (task 3.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_returns_returning_row_and_writes_event` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_uses_the_name_as_display_name` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[bad_name]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[extra_owner]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[extra_status]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[http_url]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[oauth2_client_credentials]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[private_url]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[ssh_private_key]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[svc_name]` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_returns_the_callers_services` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_without_owned_services_is_empty` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_existing_slug_conflicts_without_an_insert` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_integrity_error_conflicts` (task 2.1): passed
- `tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[empty]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[name_key]` (task 3.1): passed
- `tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[none]` (task 3.1): passed

## Guard events

- guard.violation: apps/admin-api/src/admin_api/services/agent_publishing.py
- guard.violation: apps/admin-api/src/admin_api/services/agent_publishing.py
- guard.violation: apps/admin-api/src/admin_api/api/agent.py
- guard.violation: apps/admin-api/src/admin_api/api/agent.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.test_tamper: tests/acceptance/openapi_snapshot.json
