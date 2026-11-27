# Verification: openspec:agent-principal-and-egress: FAIL (round 1)

traceability: not checked (an earlier step failed)

- Base: `0c676fec3046d36705bfcfb5f6cb6ec193ef2f5d`
- Head: `d8c6688c8beb1cb2bfaeeed63d6cc58d61d0ce93`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base merged: staging@0c676fec30 as d8c6688c8b (1 commit) |
| 1 | integrity | failed | 0.4 | an inline suppression was not declared; scope: 12 changed file(s) |
| 2 | build | not_run | 0.0 | an earlier step failed |
| 3 | tests | not_run | 0.0 | an earlier step failed |
| 4 | traceability | not_run | 0.0 | an earlier step failed |
| 4a | audit sampling | not_run | 0.0 | an earlier step failed |
| 5 | ui test generation | not_run | 0.0 | an earlier step failed |
| 6 | quality | not_run | 0.0 | an earlier step failed |
| 8 | s1 judge | not_run | 0.0 | an earlier step failed |
| 9 | judge | not_run | 0.0 | an earlier step failed |
| 10 | aggregation | ok | 0.0 | FAIL |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 5 test file(s) compared with the base |
| red-green freeze | ok | 5 task(s): red and green compared |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | failed | 8 new suppression(s), 5 declared |
| tdd history | ok | 5 task(s); red tests passing at head: step 3 |
| python encoding | ok | 8 Python file(s) added or changed, each read, none declares another encoding |
| pre-existing tests still pass | skipped | step 1 already failed |

Declared suppressions:
- tests/unit/admin_api/test_agent_principal.py:39 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:40 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:41 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:46 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)
- tests/unit/admin_api/test_agent_principal.py:47 # noqa: E402 (declared: The test inserts the repository source directories into sys.path before importing project modules.)

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/internal.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/auth/agent_principal.py` | admin-api | relevant | named in the spec |
| `docs/architecture/contracts/events/audit-event.schema.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/ledger/r-20261127T1106Z-019e.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/.l4/ledger/r-20261127T1336Z-73e4.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/agent-principal-and-egress/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/python/mintkey-models/mintkey_models/egress.py` | python | relevant | named in the spec |
| `packages/python/mintkey-models/tests/test_egress.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_key_check.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_principal.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_agent_role_refusal.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_audit_schema_agent_denied.py` |  | relevant | new test file |

### Changed functions

Diff coverage not run.

### Tests

Tests-ran check not run.

## Criteria

None judged.

## Findings

- [major, deterministic] an inline suppression was not declared: tests/unit/admin_api/test_agent_role_refusal.py:32 # noqa: E402, tests/unit/admin_api/test_agent_role_refusal.py:33 # noqa: E402, tests/unit/admin_api/test_agent_role_refusal.py:38 # noqa: E402. Remove each comment by fixing what it hides; declare one only if it cannot be removed

## Fix unit

Fix unit 1 is created for these tasks:
- F-6eb0cc43 an inline suppression was not declared

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_accepted_urls` (task 1.1): not in the report
- `packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_address_is_public` (task 1.1): not in the report
- `packages.python.mintkey-models.tests.test_egress::test_C_3a64dd27_names_that_resolve_badly` (task 1.1): not in the report
- `packages.python.mintkey-models.tests.test_egress::test_C_90151371_refused_urls` (task 1.1): not in the report
- `packages.python.mintkey-models.tests.test_egress::test_C_97e80bfe_deny_names_reader` (task 1.1): not in the report
- `tests.unit.admin_api.test_agent_key_check::test_C_083b1a5a_C_9a0d1912_validate_agent_key_issues_no_statement_itself` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_expired_key_returns_the_expired_401` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_unknown_key_returns_the_invalid_key_401` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_valid_key_returns_the_row_and_none` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_key_check::test_C_9a0d1912_verify_failure_returns_the_503` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_3c508836_publisher_key_yields_the_principal` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[expired_key_401]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[unknown_key_401]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_handler_answers_the_same_http_response[verify_unavailable_503]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_rejected_key_raises_agent_api_error[expired_key_401]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_rejected_key_raises_agent_api_error[unknown_key_401]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5861b2ec_rejected_key_raises_agent_api_error[verify_unavailable_503]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[basic_auth]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[bearer_not_an_agent_key]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[cookie_only]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[no_header]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_5b21f986_no_usable_credential_is_401_without_a_session[x_api_key_only]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_70750b4d_key_check_failure_is_503_and_closes_the_session` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_70750b4d_session_factory_failure_is_503` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_principal::test_C_acbb978c_route_session_never_sees_the_platform_view` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_role_refusal::test_C_882edc8c_consumer_is_refused_and_the_denial_is_recorded` (task 3.2): not in the report
- `tests.unit.admin_api.test_agent_role_refusal::test_C_882edc8c_publisher_passes_and_records_nothing` (task 3.2): not in the report
- `tests.unit.admin_api.test_agent_role_refusal::test_C_aa34abc8_audit_failure_still_answers_403_and_logs` (task 3.2): not in the report
- `tests.unit.admin_api.test_agent_role_refusal::test_C_aa34abc8_session_failure_still_answers_403_and_logs` (task 3.2): not in the report
- `tests.unit.admin_api.test_audit_schema_agent_denied::test_C_c66906b5_definition_states_event_and_payload` (task 4.1): not in the report
- `tests.unit.admin_api.test_audit_schema_agent_denied::test_C_c66906b5_mapping_one_of_and_envelope_actor` (task 4.1): not in the report
