# Verification: openspec:grant-expiry: PASS (round 6)

traceability: 25/25 criteria covered by a discriminating test

- Base: `8e8999377566a6450daca896c6e64250dc0f4954`
- Head: `3ae84ca15da8328f32ff72b717bdac7eb9472a1f`
- Implementer profiles: deepseek, glm
- Judge: claude-judge (claude-sonnet-5-5), 3 call(s), judged in 2 parts and 1 follow-up, prompt sha256 `619d722f5237b79280615565d4c05307df80b314daae3508e7f0e45b4ff78cd1`
  - part 1: 19 file(s), 102069 characters, profile claude-judge, reply valid
  - part 2: 12 file(s), 60136 characters, profile claude-judge, reply valid
  - follow-up 1: C-c4e8685f; files of parts 1 and 2: 4 file(s), 63682 characters, profile claude-judge, reply valid
- Judge replies of claude-judge (this unit, all rounds): valid 7, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared)
- Cost: $2.7633

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 1.3 | base staging@8e89993775 contained |
| 1 | integrity | ok | 340.7 | 11 sub-checks; scope: 55 changed file(s) |
| 2 | build | ok | 107.6 |  |
| 3 | tests | ok | 128.2 |  |
| 4 | traceability | ok | 0.2 | 25/25 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 1.8 | 25/25 criteria judged by jev |
| 9 | judge | ok | 65.3 | 3 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261126T2211Z-7bb9/034-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261126T2211Z-7bb9/035-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261126T2211Z-7bb9/036-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261126T2211Z-7bb9/037-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261126T2211Z-7bb9/038-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261126T2211Z-7bb9/039-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261126T2211Z-7bb9/040-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261126T2211Z-7bb9/041-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261126T2211Z-7bb9/042-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261126T2211Z-7bb9/043-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261126T2211Z-7bb9/044-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261126T2211Z-7bb9/045-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261126T2211Z-7bb9/046-test.log |

## Files by part

- part 1: openspec/changes/grant-expiry-fix-1/.openspec.yaml (310 characters)
- part 1: openspec/changes/grant-expiry-fix-2/.openspec.yaml (310 characters)
- part 1: openspec/changes/grant-expiry-fix-3/.openspec.yaml (310 characters)
- part 1: apps/admin-api/db/changelog/030-grant-expiry.yaml (3134 characters)
- part 1: apps/admin-api/src/admin_api/api/agents.py (3013 characters)
- part 1: apps/admin-api/src/admin_api/api/api_keys.py (587 characters)
- part 1: tests/unit/admin_api/test_grant_expiry_readers.py (6592 characters)
- part 1: docs/architecture/contracts/events/audit-event.schema.json (2606 characters)
- part 1: tests/unit/admin_api/test_audit_schema_grants.py (3341 characters)
- part 1: apps/admin-api/db/changelog/db.changelog-master.yaml (584 characters)
- part 1: apps/mcp-server/src/mcp_server/tools/discovery.py (1840 characters)
- part 1: apps/mcp-server/tests/test_grant_expiry_discovery.py (7795 characters)
- part 1: apps/admin-api/src/admin_api/services/grant_expiry.py (3283 characters)
- part 1: apps/mcp-server/src/mcp_server/policy/grant_expiry.py (1494 characters)
- part 1: tests/unit/admin_api/test_grants_service.py (22833 characters)
- part 1: tests/unit/admin_api/test_grant_expiry_rules.py (3716 characters)
- part 1: apps/admin-api/src/admin_api/services/grants.py (17433 characters)
- part 1: apps/admin-api/src/admin_api/api/permissions.py (21368 characters)
- part 1: tests/unit/admin_api/test_permissions.py (1520 characters)
- part 2: tests/unit/admin_api/test_permissions_expiry.py (23361 characters)
- part 2: openspec/changes/grant-expiry-fix-1/proposal.md (2373 characters)
- part 2: openspec/changes/grant-expiry-fix-2/proposal.md (3462 characters)
- part 2: openspec/changes/grant-expiry-fix-3/proposal.md (2052 characters)
- part 2: apps/mcp-server/src/mcp_server/tools/request_token.py (3837 characters)
- part 2: apps/mcp-server/tests/test_grant_expiry_tokens.py (9805 characters)
- part 2: apps/admin-api/src/admin_api/db/tables.py (582 characters)
- part 2: tests/unit/admin_api/test_grant_expiry_migration.py (7905 characters)
- part 2: openspec/changes/grant-expiry-fix-1/tasks.md (319 characters)
- part 2: openspec/changes/grant-expiry-fix-2/tasks.md (370 characters)
- part 2: openspec/changes/grant-expiry-fix-3/tasks.md (353 characters)
- part 2: openspec/changes/grant-expiry/tasks.md (5717 characters)

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 9 test file(s) compared with the base; changed in place, named by the task text: tests.unit.admin_api.test_permissions::test_revoke_returns_204_and_notifies (named by the task text, plan:agent-governance@eaa790f81c1e3e73) |
| red-green freeze | ok | 8 task(s): red and green compared |
| test path freeze | ok | 11 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 5 new suppression(s), 5 declared |
| tdd history | ok | 8 task(s); red tests passing at head: step 3 |
| python encoding | ok | 18 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 2872 of 2872 base tests pass on the unit's code with its 8 test and support files at the base (base: evidence) |

Declared suppressions:
- tests/unit/admin_api/test_grant_expiry_rules.py:27 # noqa: E402 (declared: import of admin_api.services.grant_expiry must follow the sys.path insertion for apps/admin-api/src)
- tests/unit/admin_api/test_grants_service.py:46 # noqa: E402 (declared: import follows the sys.path insertion that makes the admin-api sources importable, matching the other unit tests)
- tests/unit/admin_api/test_grants_service.py:47 # noqa: E402 (declared: import follows the sys.path insertion that makes the admin-api sources importable, matching the other unit tests)
- tests/unit/admin_api/test_grants_service.py:58 # noqa: E402 (declared: import follows the sys.path insertion that makes the admin-api sources importable, matching the other unit tests)
- tests/unit/admin_api/test_permissions_expiry.py:43 # noqa: E402 (declared: import after the repo source directories are added to sys.path, as the existing admin_api tests do)

## Test changes made by humans (allowed, L4-SEC-004)

- apps/mcp-server/tests/test_grant_expiry_discovery.py kept at head for the run (people changed it last (7eec741645, ccb08d4b14, e4cb8898c6))

## Pre-existing tests changed with an allowance (L4-VER-031)

- tests.unit.admin_api.test_permissions::test_revoke_returns_204_and_notifies (named by the task text, plan:agent-governance@eaa790f81c1e3e73)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-48b97ae8 | grant-expiry › The schema stores a grant's expiry and grantor › the changelog adds the columns | covered | tests.unit.admin_api.test_grant_expiry_migration::test_C_48b97ae8_changelog_adds_expiry_and_grantor_columns (passed, red_assertion) | - | 0.91 |
| C-efc458dc | grant-expiry › The schema stores a grant's expiry and grantor › the Core table knows the columns | covered | tests.unit.admin_api.test_grant_expiry_migration::test_C_efc458dc_core_table_has_columns_and_model_does_not (passed, red_assertion) | - | 0.95 |
| C-3dca655e | grant-expiry › The expiry rules and the cap have one implementation › the cap reader | covered | tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-5-604800] (passed, zero_value); tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-604800] (passed, zero_value); tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[0-604800] (passed... | - | 0.93 |
| C-c0408375 | grant-expiry › The expiry rules and the cap have one implementation › operator and agent rules | covered | tests.unit.admin_api.test_grant_expiry_rules::test_C_c0408375_operator_and_agent_rules (passed, zero_value) | - | 0.96 |
| C-a3ba81c6 | grant-expiry › The expiry rules and the cap have one implementation › the expiry boundary | covered | tests.unit.admin_api.test_grant_expiry_rules::test_C_a3ba81c6_expiry_boundary (passed, zero_value) | - | 0.96 |
| C-22b26d27 | grant-expiry › One write path creates and removes grants › an operator and an agent write grants | covered | tests.unit.admin_api.test_grants_service::test_C_22b26d27_operator_and_agent_write_grants (passed, zero_value) | - | 0.94 |
| C-a6b59772 | grant-expiry › One write path creates and removes grants › an identical grant is returned, another is refused, an expired one is replaced | covered | tests.unit.admin_api.test_grants_service::test_C_a6b59772_identical_returned_other_refused_expired_replaced (passed, zero_value) | - | 0.95 |
| C-1bd65fd0 | grant-expiry › One write path creates and removes grants › two concurrent writes of one grant | covered | tests.unit.admin_api.test_grants_service::test_C_1bd65fd0_two_concurrent_writes_of_one_grant (passed, zero_value) | - | 0.95 |
| C-bdb3718d | grant-expiry › One write path creates and removes grants › a rule violation writes nothing | covered | tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[-10-expires_at_in_past] (passed, zero_value); tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[604801-expires_at_too_far] (passed, zero_value); tests.unit.admin_api.test_gra... | - | 0.96 |
| C-099f4d96 | grant-expiry › One write path creates and removes grants › delete returns the record or nothing | covered | tests.unit.admin_api.test_grants_service::test_C_099f4d96_delete_returns_record_or_nothing (passed, zero_value) | - | 0.93 |
| C-7a27cadf | grant-expiry › One write path creates and removes grants › the payload builders | covered | tests.unit.admin_api.test_grants_service::test_C_7a27cadf_payload_builders (passed, zero_value) | - | 0.93 |
| C-20d077ee | grant-expiry › One write path creates and removes grants › the NOTIFY payload pins the revoked_at format | covered | tests.unit.admin_api.test_grants_service::test_C_20d077ee_notify_payload_pins_the_revoked_at_format (passed, zero_value) | - | 0.95 |
| C-c997909a | grant-expiry › The operator API takes an expiry and records the grantor › a grant with an expiry | covered | tests.unit.admin_api.test_permissions_expiry::test_C_c997909a_a_grant_with_an_expiry (passed, red_assertion) | - | 0.91 |
| C-b2b19611 | grant-expiry › The operator API takes an expiry and records the grantor › invalid and conflicting requests | covered | tests.unit.admin_api.test_permissions_expiry::test_C_b2b19611_invalid_and_conflicting_requests (passed, red_assertion) | - | 0.95 |
| C-52a42138 | grant-expiry › The operator API takes an expiry and records the grantor › the lists and the single grant show the new fields | covered | tests.unit.admin_api.test_permissions_expiry::test_C_52a42138_the_lists_and_the_single_grant_show_the_new_fields (passed, red_assertion) | - | 0.94 |
| C-c4e8685f | grant-expiry › The operator API takes an expiry and records the grantor › the grantor filter and the unchanged bodies | covered | tests.unit.admin_api.test_permissions_expiry::test_C_c4e8685f_grantor_filter_and_unchanged_bodies (passed, red_assertion) | - | 0.94 |
| C-31cf8071 | grant-expiry › The operator API takes an expiry and records the grantor › revoke names what it revoked | covered | tests.unit.admin_api.test_permissions_expiry::test_C_31cf8071_revoke_names_what_it_revoked (passed, red_assertion) | - | 0.88 |
| C-1494d103 | grant-expiry › An expired grant is absent for the agent › an expired grant is denied | covered | apps.mcp-server.tests.test_grant_expiry_tokens::test_C_1494d103_expired_grant_is_denied (passed, zero_value) | - | 0.92 |
| C-18424d96 | grant-expiry › An expired grant is absent for the agent › the grant select is ordered | covered | apps.mcp-server.tests.test_grant_expiry_tokens::test_C_18424d96_grant_select_is_ordered (passed, zero_value) | - | 0.92 |
| C-9398f128 | grant-expiry › An expired grant is absent for the agent › a grant without an expiry behaves as before | covered | apps.mcp-server.tests.test_grant_expiry_tokens::test_C_9398f128_C_b4dd4c2b_no_expiry_behaves_as_before (passed, zero_value) | - | 0.91 |
| C-e07d9989 | grant-expiry › An expired grant is absent for the agent › discovery hides what the database says is expired | covered | apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_filters_expired_grants (passed, red_assertion); apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_grant_reads_hide_expired_rows (passed, red_assertion); apps.mcp-server.tests.test_gr... | - | 0.94 |
| C-b5050c3c | grant-expiry › An expired grant is absent for the agent › the other readers ignore an expired grant | covered | tests.unit.admin_api.test_grant_expiry_readers::test_C_b5050c3c_other_readers_ignore_expired_grants (passed, red_assertion) | - | 0.88 |
| C-b4dd4c2b | grant-expiry › A token never outlives its grant › the lifetime function | covered | apps.mcp-server.tests.test_grant_expiry_tokens::test_C_9398f128_C_b4dd4c2b_no_expiry_behaves_as_before (passed, zero_value); apps.mcp-server.tests.test_grant_expiry_tokens::test_C_b4dd4c2b_lifetime_function (passed, zero_value) | - | 0.93 |
| C-f1c29313 | grant-expiry › A token never outlives its grant › the broker receives the shortened lifetime | covered | apps.mcp-server.tests.test_grant_expiry_tokens::test_C_f1c29313_broker_receives_shortened_lifetime (passed, zero_value) | - | 0.94 |
| C-29874427 | grant-expiry › The audit contract records the grantor and the expiry › the contract names them | covered | tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_granted_payload_lists_expiry_and_grantor (passed, red_assertion); tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_revoked_payload_lists_grantor_and_revoker (passed, red_assertion); tests.unit.admin_api.test_audit_schema_gr... | - | 0.91 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/db/changelog/030-grant-expiry.yaml` | admin-api | relevant | named in the spec |
| `apps/admin-api/db/changelog/db.changelog-master.yaml` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/agents.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/api_keys.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/permissions.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/db/tables.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/services/grant_expiry.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/services/grants.py` | admin-api | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/policy/grant_expiry.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/tools/discovery.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/src/mcp_server/tools/request_token.py` | mcp-server | relevant | named in the spec |
| `apps/mcp-server/tests/test_grant_expiry_discovery.py` |  | relevant | new test file |
| `apps/mcp-server/tests/test_grant_expiry_tokens.py` |  | relevant | new test file |
| `docs/architecture/contracts/events/audit-event.schema.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-2/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-2/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-2/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-2/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-3/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-3/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-3/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry-fix-3/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-3/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-3/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-4/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-4/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-4/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-5/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/evidence/round-5/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T1714Z-e646.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T1716Z-d1d6.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T1923Z-1f47.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T2132Z-c38f.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/.l4/ledger/r-20261126T2211Z-7bb9.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/feedback.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/grant-expiry/verification.md` |  | none | exempt: harness, spec or documentation path |
| `tests/unit/admin_api/test_audit_schema_grants.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grant_expiry_migration.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grant_expiry_readers.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grant_expiry_rules.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_grants_service.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_permissions.py` |  | relevant | named in the spec |
| `tests/unit/admin_api/test_permissions_expiry.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2914 of 2968 passed, 0 failed, 0 errored, 54 skipped.
41 of 41 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-48b97ae8 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-efc458dc | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3dca655e | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c0408375 | ok | 0.960 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a3ba81c6 | ok | 0.960 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-22b26d27 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a6b59772 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1bd65fd0 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bdb3718d | ok | 0.960 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-099f4d96 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7a27cadf | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-20d077ee | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c997909a | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b2b19611 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-52a42138 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c4e8685f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-31cf8071 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1494d103 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-18424d96 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9398f128 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e07d9989 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b5050c3c | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b4dd4c2b | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f1c29313 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-29874427 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-48b97ae8 | grant-expiry › The schema stores a grant's expiry and grantor › the changelog adds the columns | pass | pass | the judge passed it and a discriminating test passes |
| C-efc458dc | grant-expiry › The schema stores a grant's expiry and grantor › the Core table knows the columns | pass | pass | the judge passed it and a discriminating test passes |
| C-3dca655e | grant-expiry › The expiry rules and the cap have one implementation › the cap reader | pass | pass | the judge passed it and a discriminating test passes |
| C-c0408375 | grant-expiry › The expiry rules and the cap have one implementation › operator and agent rules | pass | pass | the judge passed it and a discriminating test passes |
| C-a3ba81c6 | grant-expiry › The expiry rules and the cap have one implementation › the expiry boundary | pass | pass | the judge passed it and a discriminating test passes |
| C-22b26d27 | grant-expiry › One write path creates and removes grants › an operator and an agent write grants | pass | pass | the judge passed it and a discriminating test passes |
| C-a6b59772 | grant-expiry › One write path creates and removes grants › an identical grant is returned, another is refused, an expired one is replaced | pass | pass | the judge passed it and a discriminating test passes |
| C-1bd65fd0 | grant-expiry › One write path creates and removes grants › two concurrent writes of one grant | pass | pass | the judge passed it and a discriminating test passes |
| C-bdb3718d | grant-expiry › One write path creates and removes grants › a rule violation writes nothing | pass | pass | the judge passed it and a discriminating test passes |
| C-099f4d96 | grant-expiry › One write path creates and removes grants › delete returns the record or nothing | pass | pass | the judge passed it and a discriminating test passes |
| C-7a27cadf | grant-expiry › One write path creates and removes grants › the payload builders | pass | pass | the judge passed it and a discriminating test passes |
| C-20d077ee | grant-expiry › One write path creates and removes grants › the NOTIFY payload pins the revoked_at format | pass | pass | the judge passed it and a discriminating test passes |
| C-c997909a | grant-expiry › The operator API takes an expiry and records the grantor › a grant with an expiry | pass | pass | the judge passed it and a discriminating test passes |
| C-b2b19611 | grant-expiry › The operator API takes an expiry and records the grantor › invalid and conflicting requests | pass | pass | the judge passed it and a discriminating test passes |
| C-52a42138 | grant-expiry › The operator API takes an expiry and records the grantor › the lists and the single grant show the new fields | pass | pass | the judge passed it and a discriminating test passes |
| C-c4e8685f | grant-expiry › The operator API takes an expiry and records the grantor › the grantor filter and the unchanged bodies | pass | pass | the judge passed it and a discriminating test passes; its evidence was split over parts 1 and 2 of the diff: follow-up call 1 judged its 4 files of those parts together and answered pass |
| C-31cf8071 | grant-expiry › The operator API takes an expiry and records the grantor › revoke names what it revoked | pass | pass | the judge passed it and a discriminating test passes |
| C-1494d103 | grant-expiry › An expired grant is absent for the agent › an expired grant is denied | pass | pass | the judge passed it and a discriminating test passes |
| C-18424d96 | grant-expiry › An expired grant is absent for the agent › the grant select is ordered | pass | pass | the judge passed it and a discriminating test passes |
| C-9398f128 | grant-expiry › An expired grant is absent for the agent › a grant without an expiry behaves as before | pass | pass | the judge passed it and a discriminating test passes |
| C-e07d9989 | grant-expiry › An expired grant is absent for the agent › discovery hides what the database says is expired | pass | pass | the judge passed it and a discriminating test passes |
| C-b5050c3c | grant-expiry › An expired grant is absent for the agent › the other readers ignore an expired grant | pass | pass | the judge passed it and a discriminating test passes |
| C-b4dd4c2b | grant-expiry › A token never outlives its grant › the lifetime function | pass | pass | the judge passed it and a discriminating test passes |
| C-f1c29313 | grant-expiry › A token never outlives its grant › the broker receives the shortened lifetime | pass | pass | the judge passed it and a discriminating test passes |
| C-29874427 | grant-expiry › The audit contract records the grantor and the expiry › the contract names them | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Filter test depends on SQLAlchemy literal rendering of the bound values (spec gap) (criterion C-c4e8685f): The test asserts the text "grantor_type = 'agent'" from a statement compiled with literal_binds, falling back to str(statement) if that fails. The code binds the values as parameters. If the compiler cannot render the UUID literal, the fallback text would not contain 'agent'. The gate passed, so it renders at head, but the check is fragile.

## Feedback

- FB-002: addressed at 3ae84ca15d: apps/admin-api/src/admin_api/api/permissions.py: grantor_uuid = uuid.UUID(...); stmt.where(pg_table.c.grantor_type == GRANTOR_AGENT, pg_table.c.grantor_id == grantor_uuid) — no literal_column.

## New tests (red then green, `task.red_ok` in the ledger)

- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_filters_expired_grants` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_grant_reads_hide_expired_rows` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_grant_reads_hide_expired_rows` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_grant_reads_hide_expired_rows` (task 4.2): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_1494d103_expired_grant_is_denied` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_18424d96_grant_select_is_ordered` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_9398f128_C_b4dd4c2b_no_expiry_behaves_as_before` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_b4dd4c2b_lifetime_function` (task 4.1): passed
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_f1c29313_broker_receives_shortened_lifetime` (task 4.1): passed
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_granted_payload_lists_expiry_and_grantor` (task 5.1): passed
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_revoked_payload_lists_grantor_and_revoker` (task 5.1): passed
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_token_denied_lists_grant_expired_reason` (task 5.1): passed
- `tests.unit.admin_api.test_grant_expiry_migration::test_C_48b97ae8_changelog_adds_expiry_and_grantor_columns` (task 1.1): passed
- `tests.unit.admin_api.test_grant_expiry_migration::test_C_efc458dc_core_table_has_columns_and_model_does_not` (task 1.1): passed
- `tests.unit.admin_api.test_grant_expiry_readers::test_C_b5050c3c_other_readers_ignore_expired_grants` (task 4.3): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-5-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[0-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[3600-3600]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[604800-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[99999999-7776000]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[None-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[abc-604800]` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_a3ba81c6_expiry_boundary` (task 2.1): passed
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_c0408375_operator_and_agent_rules` (task 2.1): passed
- `tests.unit.admin_api.test_grants_service::test_C_099f4d96_delete_returns_record_or_nothing` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_1bd65fd0_two_concurrent_writes_of_one_grant` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_20d077ee_notify_payload_pins_the_revoked_at_format` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_22b26d27_operator_and_agent_write_grants` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_7a27cadf_payload_builders` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_a6b59772_identical_returned_other_refused_expired_replaced` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[-10-expires_at_in_past]` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[604801-expires_at_too_far]` (task 2.2): passed
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[None-expires_at_required]` (task 2.2): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_31cf8071_revoke_names_what_it_revoked` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_52a42138_the_lists_and_the_single_grant_show_the_new_fields` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_b2b19611_invalid_and_conflicting_requests` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_c4e8685f_grantor_filter_and_unchanged_bodies` (task 3.1): passed
- `tests.unit.admin_api.test_permissions_expiry::test_C_c997909a_a_grant_with_an_expiry` (task 3.1): passed

## Guard events

- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
