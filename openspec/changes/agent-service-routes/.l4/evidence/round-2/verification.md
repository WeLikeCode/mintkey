# Verification: openspec:agent-service-routes: FAIL (round 2)

traceability: not checked (an earlier step failed)

- Base: `128a5a77e2907c2a6a03faffcb462d2c4528e5ae`
- Head: `8de70c9f53571a49d697cd4f4398ec951ee8497f`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.4 | base staging@128a5a77e2 contained; Feedback FB-001 (behaviour): Unknown agent keys on the agent routes cannot slow the MCP server's key checks; Feedback FB-002 (behaviour): The target check of an agent-supplied URL is bounded in time and holds no database connection; Feedback FB-003 (behaviour): ser... |
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

- [major, feedback] Feedback FB-001 (behaviour): Unknown agent keys on the agent routes cannot slow the MCP server's key checks: Today every Bearer mk_agent_* string, of any length, reaches a full Argon2id verify through the same module-level semaphore (4 slots) that /v1/internal/validate-agent-key uses, so a burst on /v1/agent/ queues the MCP server's key checks behind it.
- [major, feedback] Feedback FB-002 (behaviour): The target check of an agent-supplied URL is bounded in time and holds no database connecti...: Today the check runs after set_tenant_context (create) or after the FOR UPDATE (update), so a slow resolver holds a pooled connection, and resolve_host has no timeout.
- [major, feedback] Feedback FB-003 (behaviour): service.credential.set matches its schema: The event is emitted with target_type credential while the definition this unit adds requires service.
- [major, feedback] Feedback FB-004 (behaviour): Invalid field values answer 422, never 500 or a silent 200: Today an over-long display_name reaches the database and raises a DataError (500), and {"description": null} answers 200 with no change.

## Fix unit

Fix unit 1 is created for these tasks:
- F-f9d5c71b Feedback FB-001 (behaviour): Unknown agent keys on the agent routes cannot slow the MCP server's...
- F-c16d7dab Feedback FB-002 (behaviour): The target check of an agent-supplied URL is bounded in time and hol...
- F-5af045b0 Feedback FB-003 (behaviour): service.credential.set matches its schema
- F-aa8d250f Feedback FB-004 (behaviour): Invalid field values answer 422, never 500 or a silent 200

## New tests (red then green, `task.red_ok` in the ledger)

- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[array]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[extra_key]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[unreadable_json]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[carriage_return]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[empty]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[line_feed]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[nul]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[too_long]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_failing_vault_answers_502_before_metadata` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_other_owner_answers_403_without_a_write` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_08831467_unsupported_scheme_answers_422_without_a_vault_call` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_header]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_query]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_bad_characters]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_connection]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_content_length]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_host]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_missing]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_transfer_encoding]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_valid]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_x_mintkey]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_x_mintkey_lower]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[query_missing]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[query_valid]` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_4b7e8c8f_bearer_credential_is_written_and_never_echoed` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_credential::test_C_6d26cd39_row_is_locked_before_the_vault_write` (task 4.1): not in the report
- `tests.unit.admin_api.test_agent_publishing_service::test_C_404b5f68_require_owned_service_returns_owned_and_refuses_others` (task 1.1): not in the report
- `tests.unit.admin_api.test_agent_publishing_service::test_C_7d79dfe4_service_view_has_twelve_keys_and_nullable_timestamps` (task 1.1): not in the report
- `tests.unit.admin_api.test_agent_publishing_service::test_C_b64100a4_parse_service_ref_decodes_ids_and_passes_slugs` (task 1.1): not in the report
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_25c5b05b_consumer_is_refused_on_each_route` (task 6.1): not in the report
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_48021709_agent_route_table_and_snapshot` (task 6.1): not in the report
- `tests.unit.admin_api.test_agent_routes_isolation::test_C_96185b5c_cookieless_post_reaches_agent_authentication` (task 6.1): not in the report
- `tests.unit.admin_api.test_agent_service_error_bodies::test_C_00b5d763_every_refusal_has_one_exact_body` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_returns_returning_row_and_writes_event` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_a7c250ac_create_uses_the_name_as_display_name` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[bad_name]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[extra_owner]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[extra_status]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[http_url]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[oauth2_client_credentials]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[private_url]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[ssh_private_key]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_b190eac4_refused_body_has_one_error_body_and_no_insert[svc_name]` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_returns_the_callers_services` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_c4f8c198_list_without_owned_services_is_empty` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_existing_slug_conflicts_without_an_insert` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_create::test_C_c7dc1fce_integrity_error_conflicts` (task 2.1): not in the report
- `tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[empty]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[name_key]` (task 3.1): not in the report
- `tests.unit.admin_api.test_agent_services_update::test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement[none]` (task 3.1): not in the report

## Guard events

- guard.violation: apps/admin-api/src/admin_api/services/agent_publishing.py
- guard.violation: apps/admin-api/src/admin_api/services/agent_publishing.py
- guard.violation: apps/admin-api/src/admin_api/api/agent.py
- guard.violation: apps/admin-api/src/admin_api/api/agent.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.violation: apps/admin-api/src/admin_api/api/agent_services.py
- guard.test_tamper: tests/acceptance/openapi_snapshot.json
