# Verification: openspec:audit-queue-durable: PASS (round 4)

traceability: 18/19 criteria covered by a discriminating test

- Base: `cdfdc23e35c24fd391cf18c5aedfb0f0cd8c0813`
- Head: `299dc8dc51f1c8c2ce8df9c06ff48d9738fb9efd`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `fd523f3ed0f43579d00e363abf456d724a9c5f9e33937fc9b2dcea46c60166e8`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.8964

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | reused | 0.0 | reused (round 3) |
| 1 | integrity | reused | 0.0 | reused (round 3) |
| 2 | build | reused | 0.0 | reused (round 3) |
| 3 | tests | reused | 0.0 | reused (round 3) |
| 4 | traceability | reused | 0.0 | reused (round 3) |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | reused | 0.0 | reused (round 3) |
| 8 | s1 judge | reused | 0.0 | reused (round 3) |
| 9 | judge | reused | 0.0 | reused (round 3) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261027T0505Z-eb94/039-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261027T0505Z-eb94/040-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261027T0505Z-eb94/041-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261027T0505Z-eb94/042-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261027T0505Z-eb94/043-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261027T0505Z-eb94/044-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261027T0505Z-eb94/045-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261027T0505Z-eb94/046-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261027T0505Z-eb94/047-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261027T0505Z-eb94/048-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261027T0505Z-eb94/049-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261027T0505Z-eb94/050-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261027T0505Z-eb94/051-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | skipped | no Python test file changed; 1 other test file(s) are checked by the run of pre-existing tests |
| red-green freeze | ok | 4 task(s): red and green compared |
| test path freeze | ok | 6 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: packages/go/auditq/backlog_test.go, packages/go/auditq/compact_test.go, packages/go/auditq/durable_test.go, packages/go/auditq/metrics.go, packages/go/auditq/queue.go (+2 more) |
| tdd history | ok | 4 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2721 of 2721 base tests pass on the unit's code with its 4 test and support files at the base (base: base worktree) |

## Test changes made by humans (allowed, L4-SEC-004)

- packages/go/auditq/compact_test.go kept at head for the run (people changed it last (50bf0daea8, 35dea71388))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-ff7aad7b | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › the sink is down, then returns | covered | github.com/mintkey/mintkey/packages/go/auditq::TestSinkDownThenBack_C_ff7aad7b (passed, red_assertion) | - | 0.95 |
| C-339a52c5 | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › more failures than the old limit of five | covered | github.com/mintkey/mintkey/packages/go/auditq::TestRetriesPastFiveFailures_C_339a52c5 (passed, red_assertion) | - | 0.94 |
| C-377ec4fd | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › closing while the sink is down keeps the events | covered | github.com/mintkey/mintkey/packages/go/auditq::TestCloseWhileSinkDownKeepsEvents_C_377ec4fd (passed, red_assertion) | - | 0.95 |
| C-aa2619c2 | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › a WAL that cannot be written | covered | github.com/mintkey/mintkey/packages/go/auditq::TestUnwritableWALDeliversFromMemory_C_aa2619c2 (passed, red_assertion) | - | 0.93 |
| C-ea45dc31 | audit-queue › Retries wait a capped delay that progress resets › the defaults | covered | github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsDefaults_C_ea45dc31 (passed, red_assertion) | - | 0.95 |
| C-be765c63 | audit-queue › Retries wait a capped delay that progress resets › set values, and a maximum below the initial delay | covered | github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsFromEnvironment_C_be765c63 (passed, red_assertion) | - | 0.93 |
| C-0b97502f | audit-queue › Retries wait a capped delay that progress resets › invalid values | covered | github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsInvalidValues_C_0b97502f (passed, red_assertion) | - | 0.94 |
| C-e8b4f95d | audit-queue › Retries wait a capped delay that progress resets › the delay doubles up to the cap | covered | github.com/mintkey/mintkey/packages/go/auditq::TestRetryDelayDoublesUpToCap_C_e8b4f95d (passed, red_assertion) | - | 0.92 |
| C-d0d6b92f | audit-queue › Deliveries run concurrently up to a bound, and failing events do not hold up the others › the number of requests in flight is bounded | covered | github.com/mintkey/mintkey/packages/go/auditq::TestConcurrencyIsBounded_C_d0d6b92f (passed, red_assertion) | - | 0.94 |
| C-2ea77966 | audit-queue › Deliveries run concurrently up to a bound, and failing events do not hold up the others › events the sink keeps answering with 403 | covered | github.com/mintkey/mintkey/packages/go/auditq::TestRefusedEventsDoNotHoldUpOthers_C_2ea77966 (passed, red_assertion) | - | 0.95 |
| C-f33bec22 | audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › which statuses are a refusal | covered | github.com/mintkey/mintkey/packages/go/auditq::TestRefusalStatuses_C_f33bec22 (passed, red_assertion) | - | 0.95 |
| C-8c6da99a | audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the record of a refused event | covered | github.com/mintkey/mintkey/packages/go/auditq::TestRefusedEventRecord_C_8c6da99a (passed, red_assertion) | - | 0.95 |
| C-fad8c50f | audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the dead-letter metrics follow refused events | uncovered | - | - | 0.15 |
| C-c0a8fbe4 | audit-queue › The WAL keeps the format the current code reads › a WAL in today's format drains in place | covered | github.com/mintkey/mintkey/packages/go/auditq::TestCurrentFormatWALDrainsInPlace_C_c0a8fbe4 (passed, red_assertion) | - | 0.95 |
| C-88d9b9f7 | audit-queue › The WAL keeps the format the current code reads › compaction between the read and the tombstone | covered | github.com/mintkey/mintkey/packages/go/auditq::TestCompactionBetweenReadAndTombstone_C_88d9b9f7 (passed, pre_satisfied) | - | 0.95 |
| C-84b4a061 | audit-queue › The WAL keeps the format the current code reads › an unreadable line | covered | github.com/mintkey/mintkey/packages/go/auditq::TestUnreadableLineDeadLettered_C_84b4a061 (passed, red_assertion) | - | 0.94 |
| C-306d3e39 | audit-queue › The WAL keeps the format the current code reads › an append after a partial last line | covered | github.com/mintkey/mintkey/packages/go/auditq::TestAppendAfterPartialLineStartsNewLine_C_306d3e39 (passed, red_assertion) | - | 0.93 |
| C-93344fde | audit-queue › The backlog is a metric › the backlog in the exposition | covered | github.com/mintkey/mintkey/packages/go/auditq::TestBacklogInExposition_C_93344fde (passed, red_assertion) | - | 0.93 |
| C-933c705a | audit-queue › The backlog is a metric › Replay counts the pending events | covered | github.com/mintkey/mintkey/packages/go/auditq::TestReplayCountsPendingEvents_C_933c705a (passed, red_assertion) | - | 0.91 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `openspec/changes/audit-queue-durable-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-2/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-2/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-2/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-2/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-2/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2007Z-6906.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2013Z-81cc.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2243Z-71a7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2310Z-1139.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261027T0505Z-eb94.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/go/auditq/backlog_test.go` |  | relevant | new test file |
| `packages/go/auditq/compact_test.go` |  | relevant | named in the spec |
| `packages/go/auditq/durable_test.go` |  | relevant | new test file |
| `packages/go/auditq/metrics.go` | go | relevant | named in the spec |
| `packages/go/auditq/queue.go` | go | relevant | named in the spec |
| `packages/go/auditq/settings_test.go` |  | relevant | new test file |
| `packages/go/auditq/walformat_test.go` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: diff coverage measures python only; changed code outside it: packages/go/auditq/metrics.go, packages/go/auditq/queue.go

### Tests

2740 of 2794 passed, 0 failed, 0 errored, 54 skipped.
18 of 18 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-ff7aad7b | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-339a52c5 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-377ec4fd | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-aa2619c2 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ea45dc31 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-be765c63 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0b97502f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e8b4f95d | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d0d6b92f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2ea77966 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f33bec22 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8c6da99a | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fad8c50f | ok | 0.150 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c0a8fbe4 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-88d9b9f7 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-84b4a061 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-306d3e39 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-93344fde | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-933c705a | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Answers to verdict questions

- Q-004 accept C-fad8c50f by the delegate (claude-fable-5-1 via claude-code): The criterion is satisfied as it stands. TestDeadLetterMetrics in packages/go/auditq/compact_test.go runs the scenario word for word: an httptest sink that answers 422 to every request, 3 events enqueued on a started queue with compaction disabled, then it waits until DeadLetterTotal reaches 3, fail...

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-ff7aad7b | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › the sink is down, then returns | pass | pass | the judge passed it and a discriminating test passes |
| C-339a52c5 | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › more failures than the old limit of five | pass | pass | the judge passed it and a discriminating test passes |
| C-377ec4fd | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › closing while the sink is down keeps the events | pass | pass | the judge passed it and a discriminating test passes |
| C-aa2619c2 | audit-queue › An undelivered event stays in the WAL until the sink accepts or refuses it › a WAL that cannot be written | pass | pass | the judge passed it and a discriminating test passes |
| C-ea45dc31 | audit-queue › Retries wait a capped delay that progress resets › the defaults | pass | pass | the judge passed it and a discriminating test passes |
| C-be765c63 | audit-queue › Retries wait a capped delay that progress resets › set values, and a maximum below the initial delay | pass | pass | the judge passed it and a discriminating test passes |
| C-0b97502f | audit-queue › Retries wait a capped delay that progress resets › invalid values | pass | pass | the judge passed it and a discriminating test passes |
| C-e8b4f95d | audit-queue › Retries wait a capped delay that progress resets › the delay doubles up to the cap | pass | pass | the judge passed it and a discriminating test passes |
| C-d0d6b92f | audit-queue › Deliveries run concurrently up to a bound, and failing events do not hold up the others › the number of requests in flight is bounded | pass | pass | the judge passed it and a discriminating test passes |
| C-2ea77966 | audit-queue › Deliveries run concurrently up to a bound, and failing events do not hold up the others › events the sink keeps answering with 403 | pass | pass | the judge passed it and a discriminating test passes |
| C-f33bec22 | audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › which statuses are a refusal | pass | pass | the judge passed it and a discriminating test passes |
| C-8c6da99a | audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the record of a refused event | pass | pass | the judge passed it and a discriminating test passes |
| C-fad8c50f | audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the dead-letter metrics follow refused events | pass | pass | accepted by the delegate (claude-fable-5-1 via claude-code): The criterion is satisfied as it stands. TestDeadLetterMetrics in packages/go/auditq/compact_test.go runs the scenario word for word: an httptest sink that answers 422 to every request, 3 events enqueued on a started queue with compaction ... |
| C-c0a8fbe4 | audit-queue › The WAL keeps the format the current code reads › a WAL in today's format drains in place | pass | pass | the judge passed it and a discriminating test passes |
| C-88d9b9f7 | audit-queue › The WAL keeps the format the current code reads › compaction between the read and the tombstone | pass | pass | the judge passed it and a discriminating test passes |
| C-84b4a061 | audit-queue › The WAL keeps the format the current code reads › an unreadable line | pass | pass | the judge passed it and a discriminating test passes |
| C-306d3e39 | audit-queue › The WAL keeps the format the current code reads › an append after a partial last line | pass | pass | the judge passed it and a discriminating test passes |
| C-93344fde | audit-queue › The backlog is a metric › the backlog in the exposition | pass | pass | the judge passed it and a discriminating test passes |
| C-933c705a | audit-queue › The backlog is a metric › Replay counts the pending events | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] New tests skip unless -short is passed (criterion C-ff7aad7b): skipOutsideShortMode makes every new scenario test skip under plain `go test`, so the behaviour is only checked by a gate that passes -short.
- [minor, judge] Unterminated final line is not counted or delivered (spec gap) (criterion C-933c705a): Replay and readBatch ignore an unterminated final fragment until an append terminates it; no scenario states this for Replay's count.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/packages/go/auditq::TestAppendAfterPartialLineStartsNewLine_C_306d3e39` (task 3.2): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestBacklogInExposition_C_93344fde` (task 1.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestCloseWhileSinkDownKeepsEvents_C_377ec4fd` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionBetweenReadAndTombstone_C_88d9b9f7` (task 3.2): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestConcurrencyIsBounded_C_d0d6b92f` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestCurrentFormatWALDrainsInPlace_C_c0a8fbe4` (task 3.2): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsDefaults_C_ea45dc31` (task 2.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsFromEnvironment_C_be765c63` (task 2.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsInvalidValues_C_0b97502f` (task 2.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestRefusalStatuses_C_f33bec22` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestRefusedEventRecord_C_8c6da99a` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestRefusedEventsDoNotHoldUpOthers_C_2ea77966` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestReplayCountsPendingEvents_C_933c705a` (task 1.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestRetriesPastFiveFailures_C_339a52c5` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestRetryDelayDoublesUpToCap_C_e8b4f95d` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestSinkDownThenBack_C_ff7aad7b` (task 3.1): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestUnreadableLineDeadLettered_C_84b4a061` (task 3.2): passed
- `github.com/mintkey/mintkey/packages/go/auditq::TestUnwritableWALDeliversFromMemory_C_aa2619c2` (task 3.1): passed
