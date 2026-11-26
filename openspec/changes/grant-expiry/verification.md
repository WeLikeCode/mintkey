# Verification: openspec:grant-expiry: FAIL (round 3)

traceability: not checked (an earlier step failed)

- Base: `8e8999377566a6450daca896c6e64250dc0f4954`
- Head: `e4cb8898c6eec4c75447e4c8e1ba33858a047520`
- Implementer profiles: deepseek, glm
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.7 | base staging@8e89993775 contained; Feedback FB-001 (refactor): Restore the email grant queries of list_services and discover |
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

- [major, feedback] Feedback FB-001 (refactor): Restore the email grant queries of list_services and discover: Restore both email_permission_grants queries (list_services and discover) to their form on the base branch: JOIN email_permission_grants epg ON epg.email_service_id = es.id WHERE epg.agent_id = :agent_id AND es.deleted_at IS NULL, and drop the comment above each. The subquery that adds a null expires_at under the alias pg changes no result (email grants carry no expiry) and exists only for a test helper that matched the table name as a substring; that helper is fixed in the same push, so the tests read permission_grants as a whole word and pass with the base form. Behaviour is unchanged.

## Fix unit

Fix unit 2 is created for these tasks:
- F-3324c8f4 Feedback FB-001 (refactor): Restore the email grant queries of list_services and discover

## New tests (red then green, `task.red_ok` in the ledger)

- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_filters_expired_grants` (task 4.2): not in the report
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_describe_service_grant_reads_hide_expired_rows` (task 4.2): not in the report
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants` (task 4.2): not in the report
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_grant_reads_hide_expired_rows` (task 4.2): not in the report
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants` (task 4.2): not in the report
- `apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_grant_reads_hide_expired_rows` (task 4.2): not in the report
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_1494d103_expired_grant_is_denied` (task 4.1): not in the report
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_18424d96_grant_select_is_ordered` (task 4.1): not in the report
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_9398f128_C_b4dd4c2b_no_expiry_behaves_as_before` (task 4.1): not in the report
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_b4dd4c2b_lifetime_function` (task 4.1): not in the report
- `apps.mcp-server.tests.test_grant_expiry_tokens::test_C_f1c29313_broker_receives_shortened_lifetime` (task 4.1): not in the report
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_granted_payload_lists_expiry_and_grantor` (task 5.1): not in the report
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_revoked_payload_lists_grantor_and_revoker` (task 5.1): not in the report
- `tests.unit.admin_api.test_audit_schema_grants::test_C_29874427_token_denied_lists_grant_expired_reason` (task 5.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_migration::test_C_48b97ae8_changelog_adds_expiry_and_grantor_columns` (task 1.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_migration::test_C_efc458dc_core_table_has_columns_and_model_does_not` (task 1.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_readers::test_C_b5050c3c_other_readers_ignore_expired_grants` (task 4.3): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-5-604800]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[-604800]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[0-604800]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[3600-3600]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[604800-604800]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[99999999-7776000]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[None-604800]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_3dca655e_cap_reader[abc-604800]` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_a3ba81c6_expiry_boundary` (task 2.1): not in the report
- `tests.unit.admin_api.test_grant_expiry_rules::test_C_c0408375_operator_and_agent_rules` (task 2.1): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_099f4d96_delete_returns_record_or_nothing` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_1bd65fd0_two_concurrent_writes_of_one_grant` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_20d077ee_notify_payload_pins_the_revoked_at_format` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_22b26d27_operator_and_agent_write_grants` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_7a27cadf_payload_builders` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_a6b59772_identical_returned_other_refused_expired_replaced` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[-10-expires_at_in_past]` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[604801-expires_at_too_far]` (task 2.2): not in the report
- `tests.unit.admin_api.test_grants_service::test_C_bdb3718d_rule_violation_writes_nothing[None-expires_at_required]` (task 2.2): not in the report
- `tests.unit.admin_api.test_permissions_expiry::test_C_31cf8071_revoke_names_what_it_revoked` (task 3.1): not in the report
- `tests.unit.admin_api.test_permissions_expiry::test_C_52a42138_the_lists_and_the_single_grant_show_the_new_fields` (task 3.1): not in the report
- `tests.unit.admin_api.test_permissions_expiry::test_C_b2b19611_invalid_and_conflicting_requests` (task 3.1): not in the report
- `tests.unit.admin_api.test_permissions_expiry::test_C_c4e8685f_grantor_filter_and_unchanged_bodies` (task 3.1): not in the report
- `tests.unit.admin_api.test_permissions_expiry::test_C_c997909a_a_grant_with_an_expiry` (task 3.1): not in the report

## Guard events

- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
- guard.test_tamper: apps/mcp-server/tests/test_grant_expiry_discovery.py
