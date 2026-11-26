# Verification: openspec:proxy-public-egress: PASS (round 3)

traceability: 19/19 criteria covered by a discriminating test

- Base: `bc9151a1d442dd95296ea71d143770670dfc55e9`
- Head: `630ef8c953fce7b5ea5b55f80f8469e45467921d`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `ecb452a61f49ec104be669503a6c4a4ef7a1b6280e95e787969ef7e3c83b2d31`
- Judge replies of claude-judge (this unit, all rounds): valid 2, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $0.9949

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.9 | base staging@bc9151a1d4 contained |
| 1 | integrity | ok | 245.1 | 11 sub-checks; scope: 42 changed file(s) |
| 2 | build | ok | 140.8 |  |
| 3 | tests | ok | 155.2 |  |
| 4 | traceability | ok | 0.2 | 19/19 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 1.2 | 18/19 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 12.7 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261126T1609Z-1ffe/089-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261126T1609Z-1ffe/090-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261126T1609Z-1ffe/091-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261126T1609Z-1ffe/092-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261126T1609Z-1ffe/093-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261126T1609Z-1ffe/094-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261126T1609Z-1ffe/095-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261126T1609Z-1ffe/096-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261126T1609Z-1ffe/097-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261126T1609Z-1ffe/098-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261126T1609Z-1ffe/099-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261126T1609Z-1ffe/100-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261126T1609Z-1ffe/101-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 2 test file(s) compared with the base |
| red-green freeze | ok | 5 task(s): red and green compared |
| test path freeze | ok | 6 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/proxy-plugin/cmd/proxy-plugin/main.go, apps/proxy-plugin/cmd/proxy-plugin/public_egress_test.go, apps/proxy-plugin/cmd/proxy-plugin/public_ipv4_embedding_test.go, apps/proxy-plugin/cmd/proxy-plugin/upstream.go, apps/proxy-plugin/internal/egres... |
| tdd history | ok | 5 task(s); red tests passing at head: step 3 |
| python encoding | ok | 3 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 2834 of 2834 base tests pass on the unit's code with its 8 test and support files at the base (base: evidence) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-09049412 | proxy-public-egress › The vault stores an egress scope with each credential › the changelog adds the column | covered | tests.unit.admin_api.test_credential_egress_scope_changelog::test_C_09049412_changelog_adds_the_egress_scope_column (passed, red_assertion) | - | 0.89 |
| C-9f390972 | proxy-public-egress › The vault stores an egress scope with each credential › the admin-api client sends the scope | covered | tests.unit.admin_api.test_vault_client_put_egress_scope::test_C_9f390972_put_credential_sends_the_scope_metadata (passed, zero_value) | - | 0.92 |
| C-cbe614ee | proxy-public-egress › The vault adapter stores and returns the scope › put and get round-trip the scope | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRoundTrip_C_cbe614ee (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRoundTrip_C_cbe614ee/C-cbe614ee (passed, red_assertion) | - | 0.87 |
| C-b52d2f54 | proxy-public-egress › The vault adapter stores and returns the scope › a rotation keeps the scope unless it names one | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRotationKeepsScope_C_b52d2f54 (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRotationKeepsScope_C_b52d2f54/C-b52d2f54 (passed, red_assertion) | - | 0.93 |
| C-43146073 | proxy-public-egress › The vault adapter stores and returns the scope › a first put and concurrent puts | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073 (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073/C-43146073/concurrent (passed, red_as... | - | 0.95 |
| C-48ff464c | proxy-public-egress › The vault adapter stores and returns the scope › an unusable scope is refused | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeUnusableValueRefused_C_48ff464c (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeUnusableValueRefused_C_48ff464c/C-48ff464c (passed, red_assertion) | - | 0.93 |
| C-eac1baf3 | proxy-public-egress › The vault adapter stores and returns the scope › a failing lookup fails the put | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFailingLookupFailsPut_C_eac1baf3 (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFailingLookupFailsPut_C_eac1baf3/C-eac1baf3 (passed, red_assertion) | - | 0.92 |
| C-a4ac0a47 | proxy-public-egress › The vault adapter stores and returns the scope › every scheme's response carries the scope | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeEverySchemeResponse_C_a4ac0a47 (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeEverySchemeResponse_C_a4ac0a47/C-a4ac0a47 (passed, red_assertion) | - | 0.94 |
| C-adac8186 | proxy-public-egress › The vault adapter stores and returns the scope › the HashiCorp document tolerates a missing key | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestHashicorpDocEgressScope_C_adac8186 (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestHashicorpDocEgressScope_C_adac8186/C-adac8186 (passed, red_assertion) | - | 0.95 |
| C-1971e22f | proxy-public-egress › The vault adapter stores and returns the scope › no file that handles the stored target forgets the scope | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestEveryTargetURLFileHandlesEgressScope_C_1971e22f (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestEveryTargetURLFileHandlesEgressScope_C_1971e22f/C-1971e22f (passed, red_assertion) | - | 0.94 |
| C-0704866f | proxy-public-egress › The vault adapter stores and returns the scope › the not-found answers of the stores wrap one sentinel | covered | github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestStoreNotFoundIsSqlErrNoRows_C_0704866f (passed, red_assertion); github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestStoreNotFoundIsSqlErrNoRows_C_0704866f/C-0704866f (passed, red_assertion) | - | 0.93 |
| C-bd7857b1 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › a public credential is never sent to a non-public address | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesNonPublicTargets_C_bd7857b1 (passed, red_assertion) | - | 0.94 |
| C-37681a78 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › a name that resolves only to loopback is refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesLoopbackName_C_37681a78 (passed, red_assertion) | - | 0.94 |
| C-bd037c93 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › a name that answers no address is refused | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeNameWithoutAddress_C_bd037c93 (passed, red_assertion) | - | 0.92 |
| C-0770d694 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › an environment proxy is never used | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeIgnoresProxyEnvironment_C_0770d694 (passed, red_assertion) | - | 0.91 |
| C-e16db2b8 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › the other scopes are unchanged | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestOtherScopesAreUnchanged_C_e16db2b8 (passed, red_assertion) | - | 0.89 |
| C-ed224807 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › an unknown scope is treated as public | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUnknownScopeIsTreatedAsPublic_C_ed224807 (passed, red_assertion) | - | 0.86 |
| C-b5f6f1f1 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › the scope arrives from the vault | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestScopeArrivesFromVault_C_b5f6f1f1 (passed, red_assertion) | - | 0.94 |
| C-da414c83 | proxy-public-egress › Refuse IPv6 forms that carry an IPv4 address — feedback FB-002 › Refuse IPv6 forms that carry an IPv4 address | covered | github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83 (passed, red_assertion); github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83/6to4_2002::/16 (passed, r... | - | - |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/db/changelog/034-credential-egress-scope.yaml` | admin-api | relevant | named in the spec |
| `apps/admin-api/db/changelog/db.changelog-master.yaml` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/services/vault_client.py` | admin-api | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/main.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/cmd/proxy-plugin/public_egress_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/public_ipv4_embedding_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/cmd/proxy-plugin/upstream.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/egress/public.go` | proxy-plugin | relevant | named in the spec |
| `apps/proxy-plugin/internal/egress/public_ipv4_embedding_test.go` |  | relevant | new test file |
| `apps/proxy-plugin/internal/vault/client.go` | proxy-plugin | relevant | named in the spec |
| `apps/vault-adapter/cmd/vault-migrate-pg-to-hashicorp/main.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/cmd/vault-migrate-sqlite-to-pg/main.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/cache/dek_cache.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/egress_scope_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/server/grpc.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/vault.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/store/egress_scope_source_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/store/hashicorp_doc.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/store/hashicorp_egress_scope_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/store/postgres.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/store/sqlite.go` | vault-adapter | relevant | named in the spec |
| `docs/architecture/contracts/vault-adapter/vault.proto` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress-fix-1/specs/proxy-public-egress/spec.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/ledger/r-20261126T1224Z-202b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/ledger/r-20261126T1226Z-9797.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/ledger/r-20261126T1452Z-e476.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/.l4/ledger/r-20261126T1609Z-1ffe.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/feedback.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/proxy-public-egress/verification.md` |  | none | exempt: harness, spec or documentation path |
| `tests/unit/admin_api/test_credential_egress_scope_changelog.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_vault_client_put_egress_scope.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2873 of 2927 passed, 0 failed, 0 errored, 54 skipped.
38 of 38 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-09049412 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9f390972 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-cbe614ee | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b52d2f54 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-43146073 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-48ff464c | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-eac1baf3 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a4ac0a47 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-adac8186 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1971e22f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0704866f | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bd7857b1 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-37681a78 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bd037c93 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0770d694 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e16db2b8 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ed224807 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b5f6f1f1 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-da414c83 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-09049412 | proxy-public-egress › The vault stores an egress scope with each credential › the changelog adds the column | pass | pass | the judge passed it and a discriminating test passes |
| C-9f390972 | proxy-public-egress › The vault stores an egress scope with each credential › the admin-api client sends the scope | pass | pass | the judge passed it and a discriminating test passes |
| C-cbe614ee | proxy-public-egress › The vault adapter stores and returns the scope › put and get round-trip the scope | pass | pass | the judge passed it and a discriminating test passes |
| C-b52d2f54 | proxy-public-egress › The vault adapter stores and returns the scope › a rotation keeps the scope unless it names one | pass | pass | the judge passed it and a discriminating test passes |
| C-43146073 | proxy-public-egress › The vault adapter stores and returns the scope › a first put and concurrent puts | pass | pass | the judge passed it and a discriminating test passes |
| C-48ff464c | proxy-public-egress › The vault adapter stores and returns the scope › an unusable scope is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-eac1baf3 | proxy-public-egress › The vault adapter stores and returns the scope › a failing lookup fails the put | pass | pass | the judge passed it and a discriminating test passes |
| C-a4ac0a47 | proxy-public-egress › The vault adapter stores and returns the scope › every scheme's response carries the scope | pass | pass | the judge passed it and a discriminating test passes |
| C-adac8186 | proxy-public-egress › The vault adapter stores and returns the scope › the HashiCorp document tolerates a missing key | pass | pass | the judge passed it and a discriminating test passes |
| C-1971e22f | proxy-public-egress › The vault adapter stores and returns the scope › no file that handles the stored target forgets the scope | pass | pass | the judge passed it and a discriminating test passes |
| C-0704866f | proxy-public-egress › The vault adapter stores and returns the scope › the not-found answers of the stores wrap one sentinel | pass | pass | the judge passed it and a discriminating test passes |
| C-bd7857b1 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › a public credential is never sent to a non-public address | pass | pass | the judge passed it and a discriminating test passes |
| C-37681a78 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › a name that resolves only to loopback is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-bd037c93 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › a name that answers no address is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-0770d694 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › an environment proxy is never used | pass | pass | the judge passed it and a discriminating test passes |
| C-e16db2b8 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › the other scopes are unchanged | pass | pass | the judge passed it and a discriminating test passes |
| C-ed224807 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › an unknown scope is treated as public | pass | pass | the judge passed it and a discriminating test passes |
| C-b5f6f1f1 | proxy-public-egress › The proxy refuses non-public addresses for a public credential › the scope arrives from the vault | pass | pass | the judge passed it and a discriminating test passes |
| C-da414c83 | proxy-public-egress › Refuse IPv6 forms that carry an IPv4 address — feedback FB-002 › Refuse IPv6 forms that carry an IPv4 address | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] IPv6 ranges in IsPublicIP: To4 on 6to4/NAT64 not unwrapped (spec gap) (criterion C-b5f6f1f1): Nothing wrong found; but empty egress scope header value (one empty value) maps to "" i.e. any in proxy client, unspecified by spec.

## Feedback

- FB-001: addressed at 630ef8c953: public.go: defaults r/d resolved before returning the closure (`if r == nil { r = net.DefaultResolver }` outside closure).
- FB-002: addressed at 630ef8c953: public.go nonPublicRanges adds 64:ff9b::/96, 2002::/16, 2001::/32.

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestOtherScopesAreUnchanged_C_e16db2b8` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeIgnoresProxyEnvironmentChild` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeIgnoresProxyEnvironment_C_0770d694` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeNameWithoutAddress_C_bd037c93` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83` (task 1.2): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83/6to4_2002::/16` (task 1.2): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83/NAT64_64:ff9b::/96` (task 1.2): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83/Teredo_2001::/32` (task 1.2): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesLoopbackName_C_37681a78` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesNonPublicTargets_C_bd7857b1` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestScopeArrivesFromVault_C_b5f6f1f1` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUnknownScopeIsTreatedAsPublic_C_ed224807` (task 4.1): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/egress::TestPublicDialContextRefusesIPv4EmbeddingIPv6_C_da414c83` (task 1.2): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/egress::TestPublicDialContextRefusesIPv4EmbeddingIPv6_C_da414c83/6to4_2002::/16` (task 1.2): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/egress::TestPublicDialContextRefusesIPv4EmbeddingIPv6_C_da414c83/NAT64_64:ff9b::/96` (task 1.2): passed
- `github.com/mintkey/mintkey/services/proxy-plugin/internal/egress::TestPublicDialContextRefusesIPv4EmbeddingIPv6_C_da414c83/Teredo_2001::/32` (task 1.2): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeEverySchemeResponse_C_a4ac0a47` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeEverySchemeResponse_C_a4ac0a47/C-a4ac0a47` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFailingLookupFailsPut_C_eac1baf3` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFailingLookupFailsPut_C_eac1baf3/C-eac1baf3` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073/C-43146073/concurrent` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073/C-43146073/nil_nil` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073/C-43146073/no_rows_error` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRotationKeepsScope_C_b52d2f54` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRotationKeepsScope_C_b52d2f54/C-b52d2f54` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRoundTrip_C_cbe614ee` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRoundTrip_C_cbe614ee/C-cbe614ee` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeUnusableValueRefused_C_48ff464c` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeUnusableValueRefused_C_48ff464c/C-48ff464c` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestEveryTargetURLFileHandlesEgressScope_C_1971e22f` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestEveryTargetURLFileHandlesEgressScope_C_1971e22f/C-1971e22f` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestHashicorpDocEgressScope_C_adac8186` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestHashicorpDocEgressScope_C_adac8186/C-adac8186` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestStoreNotFoundIsSqlErrNoRows_C_0704866f` (task 3.1): passed
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestStoreNotFoundIsSqlErrNoRows_C_0704866f/C-0704866f` (task 3.1): passed
- `tests.unit.admin_api.test_credential_egress_scope_changelog::test_C_09049412_changelog_adds_the_egress_scope_column` (task 1.1): passed
- `tests.unit.admin_api.test_vault_client_put_egress_scope::test_C_9f390972_put_credential_sends_the_scope_metadata` (task 2.1): passed

## Guard events

- guard.violation: apps/admin-api/src/admin_api/services/vault_client.py
- guard.violation: apps/admin-api/src/admin_api/services/vault_client.py
- guard.violation: apps/admin-api/src/admin_api/services/vault_client.py
