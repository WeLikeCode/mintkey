# Verification: openspec:agent-principal-and-egress: FAIL (round 3)

traceability: not checked (an earlier step failed)

- Base: `0c676fec3046d36705bfcfb5f6cb6ec193ef2f5d`
- Head: `ac32349b0cd7ed4f0d570e49d7a4ecf8415ea5c0`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.7 | base staging@0c676fec30 contained; Feedback FB-001 (behaviour): Refuse the IPv6 forms that carry an IPv4 address; Feedback FB-002 (behaviour): A malformed agent-supplied URL is refused, never an error; Feedback FB-003 (behaviour): The deny list matches names however they are written |
| 1 | integrity | not_run | 0.0 | an earlier step failed |
| 2 | build | not_run | 0.0 | an earlier step failed |
| 3 | tests | not_run | 0.0 | an earlier step failed |
| 4 | traceability | not_run | 0.0 | an earlier step failed |
| 4a | audit sampling | not_run | 0.0 | an earlier step failed |
| 5 | ui test generation | not_run | 0.0 | an earlier step failed |
| 6 | quality | not_run | 0.0 | an earlier step failed |
| 8 | s1 judge | not_run | 0.0 | an earlier step failed |
| 9 | judge | not_run | 0.0 | an earlier step failed |
| 10 | aggregation | ok | 0.0 | FAIL |

## Criteria

None judged.

## Findings

- [major, feedback] Feedback FB-001 (behaviour): Refuse the IPv6 forms that carry an IPv4 address: address_is_public relies on ip.is_global, which treats 64:ff9b::/96 as global (Python 3.13), while the proxy's guard refuses it; the two checks should refuse the same ranges.
- [major, feedback] Feedback FB-002 (behaviour): A malformed agent-supplied URL is refused, never an error: Today a.example..com or a 64-character label raises UnicodeEncodeError from getaddrinfo (a 500), tabs and newlines are silently removed by urlsplit so the validated host differs from the stored URL, and 127.1 or 0x7f.1 reach the resolver.
- [major, feedback] Feedback FB-003 (behaviour): The deny list matches names however they are written: Only one trailing dot is removed from the host, entries are not normalised the same way, *.localhost is not in the built-in list, and an unusable entry silently protects nothing.

## Fix unit

Fix unit 2 is created for these tasks:
- F-479e3869 Feedback FB-001 (behaviour): Refuse the IPv6 forms that carry an IPv4 address
- F-a34b91c1 Feedback FB-002 (behaviour): A malformed agent-supplied URL is refused, never an error
- F-93283de1 Feedback FB-003 (behaviour): The deny list matches names however they are written

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

## Guard events

- guard.test_tamper: tests/unit/admin_api/test_agent_role_refusal.py
