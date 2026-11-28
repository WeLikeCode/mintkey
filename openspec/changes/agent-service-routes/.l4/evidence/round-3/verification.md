# Verification: openspec:agent-service-routes: FAIL (round 3)

traceability: 25/25 criteria covered by a discriminating test

- Base: `128a5a77e2907c2a6a03faffcb462d2c4528e5ae`
- Head: `d543ce5abe2671f8c7a3af8cc8c7246ff17f8093`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 3 call(s), judged in 2 parts and 1 follow-up, prompt sha256 `c88895b5b385418e418cad3c7bf5a45710d5b304499fbd9d01445bbb627fd38e`
  - part 1: 11 file(s), 112685 characters, profile claude-judge, reply valid
  - part 2: 15 file(s), 103464 characters, profile claude-judge, reply valid
  - follow-up 1: C-48021709, C-96185b5c, C-25c5b05b, C-3f78eec5; files of parts 1 and 2: 8 file(s), 60150 characters, profile claude-judge, reply valid
- Judge replies of claude-judge (this unit, all rounds): valid 5, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $2.9916

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.6 | base staging@128a5a77e2 contained |
| 1 | integrity | ok | 172.3 | 11 sub-checks; scope: 42 changed file(s), 1 held |
| 2 | build | ok | 90.6 |  |
| 3 | tests | ok | 135.4 |  |
| 4 | traceability | ok | 0.2 | 25/25 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 1.0 | 20/25 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 70.9 | 3 call(s) |
| 10 | aggregation | ok | 0.0 | FAIL |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261128T0035Z-135b/058-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261128T0035Z-135b/059-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261128T0035Z-135b/060-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261128T0035Z-135b/061-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261128T0035Z-135b/062-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261128T0035Z-135b/063-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261128T0035Z-135b/064-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261128T0035Z-135b/065-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261128T0035Z-135b/066-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261128T0035Z-135b/067-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261128T0035Z-135b/068-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261128T0035Z-135b/069-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261128T0035Z-135b/070-test.log |

## Files by part

- part 1: openspec/changes/agent-service-routes-fix-1/.openspec.yaml (316 characters)
- part 1: apps/admin-api/src/admin_api/api/agent.py (908 characters)
- part 1: apps/admin-api/src/admin_api/auth/agent_key_guard.py (2600 characters)
- part 1: tests/unit/admin_api/test_agent_key_guard.py (11823 characters)
- part 1: apps/admin-api/src/admin_api/auth/agent_principal.py (3308 characters)
- part 1: tests/unit/admin_api/test_agent_publishing_service.py (9867 characters)
- part 1: tests/unit/admin_api/test_agent_routes_isolation.py (13492 characters)
- part 1: apps/admin-api/src/admin_api/services/agent_publishing.py (5874 characters)
- part 1: apps/admin-api/src/admin_api/api/agent_services.py (26262 characters)
- part 1: tests/unit/admin_api/test_agent_credential.py (25389 characters)
- part 1: tests/unit/admin_api/test_agent_credential_audit_event.py (12846 characters)
- part 2: tests/unit/admin_api/test_agent_service_error_bodies.py (10795 characters)
- part 2: tests/unit/admin_api/test_agent_service_field_validation.py (10962 characters)
- part 2: tests/unit/admin_api/test_agent_services_create.py (20097 characters)
- part 2: tests/unit/admin_api/test_agent_services_update.py (23639 characters)
- part 2: tests/unit/admin_api/test_agent_target_check_bounded.py (12414 characters)
- part 2: docs/architecture/contracts/events/audit-event.schema.json (3738 characters)
- part 2: tests/unit/admin_api/test_audit_schema_agent_services.py (5449 characters)
- part 2: packages/python/mintkey-models/mintkey_models/egress.py (1243 characters)
- part 2: apps/admin-api/src/admin_api/api/internal.py (2350 characters)
- part 2: apps/admin-api/src/admin_api/main.py (2087 characters)
- part 2: tests/acceptance/openapi_snapshot.json (436 characters)
- part 2: openspec/changes/agent-service-routes-fix-1/proposal.md (1980 characters)
- part 2: openspec/changes/agent-service-routes-fix-1/specs/agent-service-credential/spec.md (3129 characters)
- part 2: openspec/changes/agent-service-routes-fix-1/tasks.md (784 characters)
- part 2: openspec/changes/agent-service-routes/tasks.md (4361 characters)

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 11 test file(s) compared with the base; 1 other test file(s) are checked by the run of pre-existing tests |
| red-green freeze | ok | 10 task(s): red and green compared |
| test path freeze | ok | 10 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 6 new suppression(s), 6 declared |
| tdd history | ok | 10 task(s); red tests passing at head: step 3 |
| python encoding | ok | 19 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | ok | 3009 of 3009 base tests pass on the unit's code with its 11 test and support files at the base (base: evidence) |

Declared suppressions:
- tests/unit/admin_api/test_agent_key_guard.py:35 # noqa: E402 (declared: admin_api is imported after the sys.path setup this test file shares with the other admin-api unit tests.)
- tests/unit/admin_api/test_agent_key_guard.py:36 # noqa: E402 (declared: admin_api is imported after the sys.path setup this test file shares with the other admin-api unit tests.)
- tests/unit/admin_api/test_agent_key_guard.py:37 # noqa: E402 (declared: admin_api is imported after the sys.path setup this test file shares with the other admin-api unit tests.)
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
| C-6d26cd39 | agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write | covered | tests.unit.admin_api.test_agent_credential::test_C_6d26cd39_row_is_locked_before_the_vault_write (passed, zero_value) | - | 0.81 |
| C-e79dc506 | agent-service-credential › The new events are in the audit contract › the contract lists them | covered | tests.unit.admin_api.test_audit_schema_agent_services::test_C_e79dc506_credential_cleared_definition (passed, red_assertion); tests.unit.admin_api.test_audit_schema_agent_services::test_C_e79dc506_credential_events_mapped_and_in_one_of (passed, red_assertion); tests.unit.admin_api.test_audit_schema_... | - | 0.92 |
| C-48021709 | agent-service-routes › The agent routes are separate from the operator routes › the route table | covered | tests.unit.admin_api.test_agent_routes_isolation::test_C_48021709_agent_route_table_and_snapshot (passed, red_assertion) | - | 0.89 |
| C-96185b5c | agent-service-routes › The agent routes are separate from the operator routes › a cookie-less POST reaches authentication | covered | tests.unit.admin_api.test_agent_routes_isolation::test_C_96185b5c_cookieless_post_reaches_agent_authentication (passed, red_assertion) | - | 0.95 |
| C-25c5b05b | agent-service-routes › The agent routes are separate from the operator routes › a consumer key is refused | covered | tests.unit.admin_api.test_agent_routes_isolation::test_C_25c5b05b_consumer_is_refused_on_each_route (passed, red_assertion) | - | 0.94 |
| C-00b5d763 | agent-service-routes › Every error of the service routes has one body › one body shape | covered | tests.unit.admin_api.test_agent_service_error_bodies::test_C_00b5d763_every_refusal_has_one_exact_body (passed, zero_value) | - | 0.94 |
| C-b64100a4 | agent-service-routes › The owned service lookup is one function › references | covered | tests.unit.admin_api.test_agent_publishing_service::test_C_b64100a4_parse_service_ref_decodes_ids_and_passes_slugs (passed, zero_value) | - | 0.93 |
| C-404b5f68 | agent-service-routes › The owned service lookup is one function › ownership | covered | tests.unit.admin_api.test_agent_publishing_service::test_C_404b5f68_require_owned_service_returns_owned_and_refuses_others (passed, zero_value) | - | 0.95 |
| C-7d79dfe4 | agent-service-routes › The owned service lookup is one function › the view | covered | tests.unit.admin_api.test_agent_publishing_service::test_C_7d79dfe4_service_view_has_twelve_keys_and_nullable_timestamps (passed, zero_value) | - | 0.90 |
| C-a7c250ac | agent-service-routes › A publisher creates a service › a service is created | covered | tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_returns_returning_row_and_writes_event (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_uses_the_name_as_display_name (passed, zero_value) | - | 0.83 |
| C-b190eac4 | agent-service-routes › A publisher creates a service › refused bodies | covered | tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[bad_name] (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[extra_owner] (passed, zero_value); tests.unit.... | - | - |
| C-c7dc1fce | agent-service-routes › A publisher creates a service › a taken slug | covered | tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_existing_slug_conflicts_without_an_insert (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_integrity_error_conflicts (passed, zero_value) | - | 0.94 |
| C-c4f8c198 | agent-service-routes › A publisher lists its own services › the list is the caller's | covered | tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_returns_the_callers_services (passed, zero_value); tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_without_owned_services_is_empty (passed, zero_value) | - | 0.92 |
| C-d225b1e7 | agent-service-routes › A publisher updates only its own services › a metadata edit keeps the credential, a changed target clears it | covered | tests.unit.admin_api.test_agent_services_update::test_C_d225b1e7_auth_scheme_change_clears_the_credential (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_d225b1e7_base_url_change_clears_the_credential (passed, zero_value); tests.unit.admin_api.test_agent_services_update... | - | 0.95 |
| C-ce4c7660 | agent-service-routes › A publisher updates only its own services › a changed target without a credential, nothing changed, refused | covered | tests.unit.admin_api.test_agent_services_update::test_C_ce4c7660_changed_target_without_credential_deletes_without_event (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_ce4c7660_refused_target_writes_nothing (passed, zero_value); tests.unit.admin_api.test_agent_services... | - | 0.94 |
| C-f996158c | agent-service-routes › A publisher updates only its own services › not the owner | covered | tests.unit.admin_api.test_agent_services_update::test_C_f996158c_not_owned_patch_is_refused_without_update[no_owner] (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_f996158c_not_owned_patch_is_refused_without_update[other_agent] (passed, zero_value); tests.unit.admin_ap... | - | 0.94 |
| C-9092a793 | agent-service-routes › A publisher updates only its own services › refused bodies | covered | tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[empty] (passed, zero_value); tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[name_key] (passed, zero_value);... | - | 0.91 |
| C-ec735b1d | agent-service-routes › A publisher updates only its own services › the row is locked first | covered | tests.unit.admin_api.test_agent_services_update::test_C_ec735b1d_row_is_locked_before_every_update_and_delete (passed, zero_value) | - | 0.86 |
| C-c2386573 | agent-service-credential › Unknown agent keys on the agent routes cannot slow the MCP server's key checks — feedback FB-001 › Unknown agent keys on the agent routes cannot slow the MCP server's key checks | covered | tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_agent_keys_do_not_wait_on_internal_capacity (passed, zero_value); tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_full_agent_capacity_answers_503_at_once (passed, zero_value); tests.unit.admin_api.test_agent_key_guard::test_C_c238... | - | - |
| C-3f78eec5 | agent-service-credential › The target check of an agent-supplied URL is bounded in time and holds no database connection — feedback FB-002 › The target check of an agent-supplied URL is bounded in time and holds no database connection | covered | tests.unit.admin_api.test_agent_target_check_bounded::test_C_3f78eec5_create_slow_target_is_bounded_without_a_connection[base_url] (passed, red_assertion); tests.unit.admin_api.test_agent_target_check_bounded::test_C_3f78eec5_create_slow_target_is_bounded_without_a_connection[openapi_url] (passed, r... | - | 0.92 |
| C-50c7880c | agent-service-credential › service.credential.set matches its schema — feedback FB-003 › service.credential.set matches its schema | covered | tests.unit.admin_api.test_agent_credential_audit_event::test_C_50c7880c_credential_set_event_targets_the_service_and_validates (passed, red_assertion) | - | 0.92 |
| C-2a3254e4 | agent-service-credential › Invalid field values answer 422, never 500 or a silent 200 — feedback FB-004 › Invalid field values answer 422, never 500 or a silent 200 | covered | tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_create_refuses_bad_display_name_without_insert[257_chars] (passed, red_assertion); tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_create_refuses_bad_display_name_without_insert[empty] (passed, red_as... | - | - |

## Evidence

### Needs attention

- out of scope: `packages/python/mintkey-models/mintkey_models/egress.py` (module `python`)
- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.serena/memories/harness/lessons.md` |  | none | exempt: harness, spec or documentation path |
| `apps/admin-api/src/admin_api/api/agent.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/agent_services.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/api/internal.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/auth/agent_key_guard.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/auth/agent_principal.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/main.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/services/agent_publishing.py` | admin-api | relevant | named in the spec |
| `docs/architecture/contracts/events/audit-event.schema.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes-fix-1/specs/agent-service-credential/spec.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261127T1729Z-559f.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261127T2004Z-3d36.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261127T2226Z-441e.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261127T2304Z-99a7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/.l4/ledger/r-20261128T0035Z-135b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/feedback.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-service-routes/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/python/mintkey-models/mintkey_models/egress.py` | python | out_of_scope | module `python` is not named in the spec |
| `tests/acceptance/openapi_snapshot.json` |  | relevant | named in the spec |
| `tests/unit/admin_api/test_agent_credential.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_credential_audit_event.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_key_guard.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_publishing_service.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_routes_isolation.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_service_error_bodies.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_service_field_validation.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_services_create.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_services_update.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_target_check_bounded.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_audit_schema_agent_services.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

3101 of 3155 passed, 0 failed, 0 errored, 54 skipped.
91 of 91 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-4b7e8c8f | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3be566fb | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-08831467 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-6d26cd39 | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e79dc506 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-48021709 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-96185b5c | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-25c5b05b | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-00b5d763 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b64100a4 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-404b5f68 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7d79dfe4 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a7c250ac | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b190eac4 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-c7dc1fce | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c4f8c198 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d225b1e7 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ce4c7660 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f996158c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9092a793 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ec735b1d | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c2386573 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-3f78eec5 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-50c7880c | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2a3254e4 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-4b7e8c8f | agent-service-credential › A credential is written, never read, and bound to its target › a bearer credential | pass | pass | the judge passed it and a discriminating test passes |
| C-3be566fb | agent-service-credential › A credential is written, never read, and bound to its target › header and query names | pass | pass | the judge passed it and a discriminating test passes |
| C-08831467 | agent-service-credential › A credential is written, never read, and bound to its target › bad values, other owners, a failing vault, an unsupported scheme | pass | pass | the judge passed it and a discriminating test passes |
| C-6d26cd39 | agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write | pass | pass | the judge passed it and a discriminating test passes |
| C-e79dc506 | agent-service-credential › The new events are in the audit contract › the contract lists them | pass | pass | the judge passed it and a discriminating test passes |
| C-48021709 | agent-service-routes › The agent routes are separate from the operator routes › the route table | pass | pass | the judge passed it and a discriminating test passes; its evidence was split over parts 1 and 2 of the diff: follow-up call 1 judged its 6 files of those parts together and answered pass |
| C-96185b5c | agent-service-routes › The agent routes are separate from the operator routes › a cookie-less POST reaches authentication | pass | pass | the judge passed it and a discriminating test passes; its evidence was split over parts 1 and 2 of the diff: follow-up call 1 judged its 5 files of those parts together and answered pass |
| C-25c5b05b | agent-service-routes › The agent routes are separate from the operator routes › a consumer key is refused | pass | pass | the judge passed it and a discriminating test passes; its evidence was split over parts 1 and 2 of the diff: follow-up call 1 judged its 5 files of those parts together and answered pass |
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
| C-c2386573 | agent-service-credential › Unknown agent keys on the agent routes cannot slow the MCP server's key checks — feedback FB-001 › Unknown agent keys on the agent routes cannot slow the MCP server's key checks | pass | pass | the judge passed it and a discriminating test passes |
| C-3f78eec5 | agent-service-credential › The target check of an agent-supplied URL is bounded in time and holds no database connection — feedback FB-002 › The target check of an agent-supplied URL is bounded in time and holds no database connection | pass | pass | the judge passed it and a discriminating test passes; its evidence was split over parts 1 and 2 of the diff: follow-up call 1 judged its 4 files of those parts together and answered pass |
| C-50c7880c | agent-service-credential › service.credential.set matches its schema — feedback FB-003 › service.credential.set matches its schema | pass | pass | the judge passed it and a discriminating test passes |
| C-2a3254e4 | agent-service-credential › Invalid field values answer 422, never 500 or a silent 200 — feedback FB-004 › Invalid field values answer 422, never 500 or a silent 200 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Collection route is a dispatcher on request.method (criterion C-48021709): _services_collection serves POST and GET as one APIRoute to satisfy a test's route-table collapse, so OpenAPI shows one operation function for both methods.
- [major, feedback] FB-002 not addressed: not in this part: the timeout is in egress.py (part 2); part 1 only shows the target check moved b...: Judged not addressed: not in this part: the timeout is in egress.py (part 2); part 1 only shows the target check moved before set_tenant_context in create and a commit before it in update Today the check runs after set_tenant_context (create) or after the FOR UPDATE (update), so a slow resolver holds a pooled connection, and resolve_host has no timeout.

## Fix unit

Fix unit 2 is created for these tasks:
- F-2a2ace30 FB-002 not addressed: not in this part: the timeout is in egress.py (part 2); part 1 only shows t...

## Feedback

- FB-001: judged addressed, pending a PASS round: agent_principal.py: require_agent_key_shape, capacity.locked() -> 503 mintkey:auth_unavailable; agent_key_guard.py own semaphore; agent.py router dependency
- FB-002: not addressed: not in this part: the timeout is in egress.py (part 2); part 1 only shows the target check moved before set_tenant_context in create and a commit before it in update
- FB-003: judged addressed, pending a PASS round: agent_services.py credential route: target_id=service.id, target_type="service"
- FB-004: judged addressed, pending a PASS round: agent_services.py: _check_display_name (1..256) and _refuse_null validators in AgentServiceCreate/AgentServiceUpdate

## Needs a human

- scope: `packages/python/mintkey-models/mintkey_models/egress.py` changes module `python`, which the spec does not name

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
- `tests.unit.admin_api.test_agent_credential_audit_event::test_C_50c7880c_credential_set_event_targets_the_service_and_validates` (task 1.3): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_agent_keys_do_not_wait_on_internal_capacity` (task 1.1): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_full_agent_capacity_answers_503_at_once` (task 1.1): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_wrong_shape_is_401_without_a_verify[bad_alphabet]` (task 1.1): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_wrong_shape_is_401_without_a_verify[empty]` (task 1.1): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_wrong_shape_is_401_without_a_verify[long]` (task 1.1): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_wrong_shape_is_401_without_a_verify[lowercase]` (task 1.1): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_wrong_shape_is_401_without_a_verify[no_prefix]` (task 1.1): passed
- `tests.unit.admin_api.test_agent_key_guard::test_C_c2386573_wrong_shape_is_401_without_a_verify[short]` (task 1.1): passed
- `tests.unit.admin_api.test_agent_publishing_service::test_C_404b5f68_require_owned_service_returns_owned_and_refuses_others` (task 1.1): passed
- `tests.unit.admin_api.test_agent_publishing_service::test_C_7d79dfe4_service_view_has_twelve_keys_and_nullable_timestamps` (task 1.1): passed
- `tests.unit.admin_api.test_agent_publishing_service::test_C_b64100a4_parse_service_ref_decodes_ids_and_passes_slugs` (task 1.1): passed
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_25c5b05b_consumer_is_refused_on_each_route` (task 6.1): passed
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_48021709_agent_route_table_and_snapshot` (task 6.1): passed
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_96185b5c_cookieless_post_reaches_agent_authentication` (task 6.1): passed
- `tests.unit.admin_api.test_agent_service_error_bodies::test_C_00b5d763_every_refusal_has_one_exact_body` (task 3.1): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_create_refuses_bad_display_name_without_insert[257_chars]` (task 1.4): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_create_refuses_bad_display_name_without_insert[empty]` (task 1.4): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_patch_refuses_a_null_field_without_update[auth_scheme]` (task 1.4): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_patch_refuses_a_null_field_without_update[base_url]` (task 1.4): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_patch_refuses_a_null_field_without_update[description]` (task 1.4): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_patch_refuses_a_null_field_without_update[display_name]` (task 1.4): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_patch_refuses_a_null_field_without_update[openapi_url]` (task 1.4): passed
- `tests.unit.admin_api.test_agent_service_field_validation::test_C_2a3254e4_patch_refuses_bad_display_name_without_update[257_chars]` (task 1.4): passed

## Guard events

- guard.violation: apps/admin-api/src/admin_api/services/agent_publishing.py
- guard.violation: apps/admin-api/src/admin_api/services/agent_publishing.py
- guard.violation: apps/admin-api/src/admin_api/api/agent.py
- guard.violation: apps/admin-api/src/admin_api/api/agent.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.test_tamper: tests/acceptance/openapi_snapshot.json
