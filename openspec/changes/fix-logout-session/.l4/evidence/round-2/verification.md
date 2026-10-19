# Verification: openspec:fix-logout-session: PASS (round 2)

traceability: 32/32 criteria covered by a discriminating test

- Base: `e5d0c8dd4d0a35afea1d13ccaf52ed869cc9e3a2`
- Head: `716d48bcb332b6b96594bb737ad4fa8d172a69d7`
- Implementer profiles: deepseek, glm
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `4eb99c979123e2b7f31d40db0a5ac25a69b4507bc8d555e748c4f92bfd784227`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared)
- Cost: $0.9230

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.8 | base staging@e5d0c8dd4d contained |
| 1 | integrity | ok | 0.4 | 7 sub-checks; scope: 43 changed file(s) |
| 2 | build | ok | 12.0 |  |
| 3 | tests | ok | 113.1 |  |
| 4 | traceability | ok | 0.3 | 32/32 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: coverage.py is not importable in the project environment |
| 8 | s1 judge | ok | 4.1 | 32/32 criteria judged by jev |
| 9 | judge | ok | 25.3 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261019T1615Z-2b83/027-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261019T1615Z-2b83/028-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261019T1615Z-2b83/029-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261019T1615Z-2b83/030-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261019T1615Z-2b83/031-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261019T1615Z-2b83/032-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261019T1615Z-2b83/033-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261019T1615Z-2b83/034-lint.log |
| lint | pass | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261019T1615Z-2b83/035-lint.log |
| typecheck | pass | `uv run --frozen --directory apps/admin-api mypy --strict src/admin_api/` | .l4-out/gates/r-20261019T1615Z-2b83/036-typecheck.log |
| typecheck | pass | `uv run --frozen --directory packages/python/mintkey-models mypy --strict mintkey_models/` | .l4-out/gates/r-20261019T1615Z-2b83/037-typecheck.log |
| typecheck | pass | `pnpm --dir apps/admin-ui exec tsc --noEmit` | .l4-out/gates/r-20261019T1615Z-2b83/038-typecheck.log |
| test | pass | `sh .l4/gates/test.sh` | .l4-out/gates/r-20261019T1615Z-2b83/039-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 5 test file(s) compared with the base |
| red-green freeze | ok | 9 task(s): red and green compared |
| test path freeze | ok | 10 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | not checked: python only; changed files outside it: apps/admin-ui/e2e/tests/21-logout-replay.spec.ts, apps/admin-ui/e2e/tests/21-logout-session.spec.ts, apps/admin-ui/src/components/app/LoggedIn.tsx, apps/admin-ui/src/components/index.ts, apps/admin-ui/src/index.ts (+6 more) |
| tdd history | ok | 9 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-25c3e029 | operator-logout › Logout deletes the server-side session › The old cookie is refused after logout inside the cache window | covered | tests.unit.admin_api.test_logout_session::test_old_cookie_refused_after_logout_inside_cache_window (passed, red_assertion) | - | 0.95 |
| C-33f55440 | operator-logout › Logout deletes the server-side session › Logout clears both cookies | covered | tests.unit.admin_api.test_logout_session::test_logout_clears_both_cookies (passed, red_assertion) | - | 0.89 |
| C-6f9d4126 | operator-logout › Logout deletes the server-side session › Logout without a session cookie | covered | tests.unit.admin_api.test_logout_session::test_logout_without_session_cookie_does_not_delete_or_evict (passed, red_assertion) | - | 0.93 |
| C-8f0418a0 | operator-logout › Logout deletes the server-side session › Logout twice with the same cookie | covered | tests.unit.admin_api.test_logout_session::test_logout_twice_with_same_cookie (passed, red_assertion) | - | 0.91 |
| C-d633f116 | operator-logout › Logout deletes the server-side session › Concurrent logouts with the same cookie | covered | tests.unit.admin_api.test_logout_session::test_concurrent_logouts_with_same_cookie (passed, red_assertion) | - | 0.93 |
| C-7c224daa | operator-logout › Logout deletes the server-side session › A cookie that is not a UUID | covered | tests.unit.admin_api.test_logout_session::test_logout_with_non_uuid_cookie_clears_both_cookies (passed, red_assertion) | - | 0.92 |
| C-a965c3a1 | operator-logout › Logout deletes the server-side session › Logout of an expired session | covered | tests.unit.admin_api.test_logout_session::test_logout_of_expired_session_deletes_by_token (passed, red_assertion) | - | 0.93 |
| C-efb11918 | operator-logout › A failed session delete is reported › The session store raises | covered | tests.unit.admin_api.test_logout_store_failure::test_delete_session_failure_answers_503_and_still_evicts (passed, red_assertion) | - | 0.93 |
| C-22d8b961 | operator-logout › A failed session delete is reported › The contract lists the outcomes | covered | tests.unit.admin_api.test_logout_store_failure::test_openapi_logout_lists_204_and_503 (passed, red_assertion) | - | 0.88 |
| C-c5131b3d | operator-logout › delete_session removes a session row › A session row is deleted | covered | tests.unit.admin_api.test_delete_session::test_delete_session_deletes_row_and_returns_true (passed, zero_value) | - | 0.91 |
| C-279c765d | operator-logout › delete_session removes a session row › No row to delete | covered | tests.unit.admin_api.test_delete_session::test_delete_session_returns_false_when_no_row (passed, zero_value) | - | 0.95 |
| C-52ed0cc6 | operator-logout › delete_session removes a session row › A token that is not a UUID | covered | tests.unit.admin_api.test_delete_session::test_delete_session_non_uuid_opens_no_database (passed, zero_value); tests.unit.admin_api.test_delete_session::test_delete_session_returns_false_when_no_row (passed, zero_value) | - | 0.94 |
| C-7700945c | operator-logout › The whoami cache forgets a logged-out token › Eviction removes only that token | covered | tests.unit.admin_api.test_whoami_eviction::test_evicting_cached_token_removes_only_it (passed, zero_value) | - | 0.93 |
| C-fe62049f | operator-logout › The whoami cache forgets a logged-out token › Evicting a token that is not cached | covered | tests.unit.admin_api.test_whoami_eviction::test_evicting_uncached_token_keeps_other_entries (passed, zero_value); tests.unit.admin_api.test_whoami_eviction::test_lookup_in_flight_during_logout_is_not_cached (passed, zero_value) | - | 0.94 |
| C-4bb6f563 | operator-logout › The whoami cache forgets a logged-out token › A lookup in flight during logout is not cached | covered | tests.unit.admin_api.test_whoami_eviction::test_lookup_in_flight_during_logout_is_not_cached (passed, zero_value) | - | 0.91 |
| C-a6ef632a | operator-logout › admin-ui logout ends the AdminJS session › A full logout | covered | tests/test_logout_session.test.ts::createLogoutHandler — C-a6ef632a a full logout > C-a6ef632a: calls admin-api, destroys the AdminJS session, clears all three cookies and redirects (passed, red_assertion) | - | 0.90 |
| C-5dc3374d | operator-logout › admin-ui logout ends the AdminJS session › admin-api is unreachable or refuses | covered | tests/test_logout_session.test.ts::createLogoutHandler — C-5dc3374d admin-api is unreachable or refuses > C-5dc3374d: destroys the AdminJS session and clears the cookies when admin-api answers 503 (passed, red_assertion); tests/test_logout_session.test.ts::createLogoutHandler — C-5dc3374d admin-api ... | - | 0.95 |
| C-a4f02538 | operator-logout › admin-ui logout ends the AdminJS session › The session store fails to destroy | covered | tests/test_logout_session.test.ts::createLogoutHandler — C-a4f02538 the session store fails to destroy > C-a4f02538: still clears the three cookies and redirects when destroy reports an error (passed, red_assertion) | - | 0.95 |
| C-3cb4c380 | operator-logout › admin-ui logout ends the AdminJS session › A request with no session object | covered | tests/test_logout_session.test.ts::createLogoutHandler — C-3cb4c380 a request with no session object > C-3cb4c380: calls no admin-api, clears only the operator cookies and redirects (passed, red_assertion) | - | 0.93 |
| C-e0bc4928 | operator-logout › admin-ui logout ends the AdminJS session › Two concurrent logouts | covered | tests/test_logout_session.test.ts::createLogoutHandler — C-e0bc4928 two concurrent logouts > C-e0bc4928: both redirect, both clear adminjs.sid and the store ends empty (passed, red_assertion) | - | 0.95 |
| C-f475d740 | operator-logout › admin-ui logout is a CSRF-protected POST › A missing token is refused | covered | tests/test_logout_guard.test.ts::logoutGuard — C-f475d740 missing token > C-f475d740: refuses a request without the _csrf field (passed, red_assertion); tests/test_logout_guard.test.ts::logoutGuard — C-f475d740 missing token > C-f475d740: refuses a request without the csrf_token cookie (passed, red_... | - | 0.86 |
| C-de8201d5 | operator-logout › admin-ui logout is a CSRF-protected POST › A wrong token is refused | covered | tests/test_logout_guard.test.ts::logoutGuard — C-de8201d5 wrong token > C-de8201d5: refuses a token of another length (passed, red_assertion); tests/test_logout_guard.test.ts::logoutGuard — C-de8201d5 wrong token > C-de8201d5: refuses a token of the same length that differs (passed, red_assertion); ... | - | 0.91 |
| C-e629437b | operator-logout › admin-ui logout is a CSRF-protected POST › Nothing to log out | covered | tests/test_logout_guard.test.ts::logoutGuard — C-e629437b nothing to log out > C-e629437b: redirects to login when the session has no adminUser and there is no cookie (passed, red_assertion); tests/test_logout_guard.test.ts::logoutGuard — C-e629437b nothing to log out > C-e629437b: redirects to logi... | - | 0.90 |
| C-4749db35 | operator-logout › admin-ui logout is a CSRF-protected POST › GET renders a confirmation form | covered | tests/test_logout_router.test.ts::GET /admin/logout — C-4749db35 renders a confirmation form > C-4749db35: renders an escaped _csrf form without side effects (passed, red_assertion) | - | 0.91 |
| C-12db9b82 | operator-logout › admin-ui logout is a CSRF-protected POST › GET without a CSRF cookie | covered | tests/test_logout_router.test.ts::GET /admin/logout — C-12db9b82 without a CSRF cookie > C-12db9b82: renders the same form with an empty _csrf value and changes nothing (passed, red_assertion) | - | 0.93 |
| C-f7e06575 | operator-logout › admin-ui logout is a CSRF-protected POST › GET without a session | covered | tests/test_logout_router.test.ts::GET /admin/logout — C-f7e06575 without a session > C-f7e06575: redirects to /admin/login when there is no session (passed, red_assertion) | - | 0.85 |
| C-6d2b5e54 | operator-logout › The admin UI logs out through a POST form › The top bar renders the form | covered | tests/LoggedIn.render.test.tsx::LoggedIn override — C-6d2b5e54 top bar form > C-6d2b5e54: shows the email and a POST form with hidden _csrf and logout button, without a logout link (passed, red_assertion) | - | 0.95 |
| C-d34b4cb5 | operator-logout › The admin UI logs out through a POST form › Submit sends the current CSRF cookie | covered | tests/LoggedIn.render.test.tsx::LoggedIn override — C-d34b4cb5 current CSRF cookie on submit > C-d34b4cb5: submit replaces the rendered _csrf with the current csrf_token cookie (passed, red_assertion) | - | 0.94 |
| C-5f6816da | operator-logout › The admin UI logs out through a POST form › A session without a CSRF token | covered | tests/LoggedIn.render.test.tsx::LoggedIn override — C-5f6816da no CSRF token > C-5f6816da: renders and submits an empty _csrf when session and cookie have no token (passed, red_assertion) | - | 0.93 |
| C-7ab935e2 | operator-logout › The admin UI logs out through a POST form › The override is registered | covered | tests/test_logout_wiring.test.ts::components/index.ts — C-7ab935e2 LoggedIn override registration > C-7ab935e2: registers the LoggedIn override with ./app/LoggedIn (passed, red_assertion) | - | 0.89 |
| C-6a1cff5f | operator-logout › The admin UI logs out through a POST form › The router serves both methods behind the limiter | covered | tests/test_logout_router.test.ts::createLogoutRouter — C-6a1cff5f serves both methods behind the limiter > C-6a1cff5f: the limiter runs for GET and both POSTs, and each answer is right (passed, red_assertion) | - | 0.96 |
| C-234b2839 | operator-logout › The admin UI logs out through a POST form › The server mounts the routes | covered | tests/test_logout_wiring.test.ts::src/index.ts — C-234b2839 mounts the logout router > C-234b2839: mounts createLogoutRouter before requireSession and keeps no GET logout handler (passed, red_assertion) | - | 0.94 |

## Evidence

### Needs attention

- diff coverage not measured: coverage.py is not importable in the project environment

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/auth.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/auth/sessions.py` | admin-api | relevant | named in the spec |
| `apps/admin-ui/e2e/tests/21-logout-replay.spec.ts` |  | relevant | new test file |
| `apps/admin-ui/e2e/tests/21-logout-session.spec.ts` |  | relevant | named in the spec |
| `apps/admin-ui/src/components/app/LoggedIn.tsx` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/src/components/index.ts` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/src/index.ts` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/src/routes/logout.ts` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/tests/LoggedIn.render.test.tsx` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_guard.test.ts` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_router.test.ts` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_session.test.ts` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_wiring.test.ts` |  | relevant | new test file |
| `docs/architecture/contracts/rest/openapi.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1246Z-38f3.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1247Z-1460.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1248Z-cdea.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1250Z-2273.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1251Z-db38.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1253Z-94f0.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1255Z-b911.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1301Z-6147.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1303Z-8159.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1304Z-1c90.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1305Z-6c11.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1307Z-e8b3.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1313Z-104d.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1615Z-2b83.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/verification.md` |  | none | exempt: harness, spec or documentation path |
| `tests/unit/admin_api/conftest.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_delete_session.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_logout_session.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_logout_store_failure.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_whoami_eviction.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: coverage.py is not importable in the project environment

### Tests

2735 of 2789 passed, 0 failed, 0 errored, 54 skipped.
43 of 43 new tests passed.
Skipped in files the unit did not touch: `apps.mcp-server.tests.test_bootstrap::test_integration_bootstrap_unauthenticated`, `apps.mcp-server.tests.test_bootstrap::test_integration_discover_without_auth_is_401`, `apps.mcp-server.tests.test_describe_service::test_integration_describe_service_returns_new_fields`, `apps.mcp-server.tests.test_request_token::test_integration_slug_resolves_to_permission_not_found`, `apps.mcp-server.tests.test_request_token::test_integration_unknown_slug_returns_404_error_shape`, `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionTimerTrigger`, `github.com/mintkey/mintkey/services/broker/internal/api/resolve::TestConstantTimeTiming`, `tests.acceptance.test_admin_ui_boot::test_login_page_returns_200`, `tests.acceptance.test_admin_ui_boot::test_login_with_bootstrap_credentials`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/agents/actions/list]`, `tests.acceptance.test_admin_ui_boot::test_resource_list_returns_200_with_data[/admin/api/resources/services/actions/list]`, `tests.acceptance.test_agent_wire_id_handling::test_get_agent_and_permissions_wire_id_end_to_end`, `tests.acceptance.test_agent_wire_id_handling::test_post_returned_id_round_trips`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_get_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_grant_permission_wire_svc_no_constraints`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_list_api_keys_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_revoke_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_carry_forward::test_rotate_api_key_wire_agent_id`, `tests.acceptance.test_api_keys_and_permissions_chain::test_create_api_key_with_wire_form_agent_id_a1`, `tests.acceptance.test_api_keys_and_permissions_chain::test_end_to_end_chain`, `tests.acceptance.test_api_keys_and_permissions_chain::test_tenant_permissions_list_returns_grants_a2`, `tests.acceptance.test_async_audit_emission::test_aud_mismatch_rejected_event_emitted_in_strict_mode`, `tests.acceptance.test_async_audit_emission::test_hash_chain_validates_after_async_appends`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_actor_id_non_null`, `tests.acceptance.test_async_audit_emission::test_proxy_hit_event_appears_after_proxy_call`, `tests.acceptance.test_async_audit_emission::test_token_issued_event_appears_after_jwt_issue`, `tests.acceptance.test_budget_config_propagation::test_e2e_config_update_propagation`, `tests.acceptance.test_budget_enforcement::test_e2e_budget_ceiling_5_calls_then_429`, `tests.acceptance.test_budget_manual_reset::test_e2e_manual_reset_allows_next_call`, `tests.acceptance.test_budget_period_rollover::test_e2e_period_rollover_new_counter_created`, `tests.acceptance.test_classical_key::test_classical_key_full_flow`, `tests.acceptance.test_data_plane_resilience::test_expired_jwt_rejected_by_proxy`, `tests.acceptance.test_data_plane_resilience::test_revoked_agent_cannot_issue_jwt`, `tests.acceptance.test_data_plane_resilience::test_vault_down_returns_502_no_cred_leak`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_jwt_rejected`, `tests.acceptance.test_data_plane_resilience::test_wrong_scope_strict_mode_rejects_with_403`, `tests.acceptance.test_data_plane_smoke::test_broker_smoke`, `tests.acceptance.test_data_plane_smoke::test_kong_smoke`, `tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke`, `tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke`, `tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end`, `tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream`, `tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end`, `tests.acceptance.test_mcp_auth_chain::test_mcp_auth_chain_end_to_end`, `tests.acceptance.test_observability::test_audit_chain_valid`, `tests.acceptance.test_observability::test_prometheus_targets_all_up`, `tests.acceptance.test_ops_hardening::test_cadvisor_returns_metrics`, `tests.acceptance.test_ops_hardening::test_prometheus_alert_rules_loaded`, `tests.acceptance.test_services_uuid_derivation::test_create_api_key_with_svc_wire_form_post_r12`, `tests.acceptance.test_services_uuid_derivation::test_create_service_uuid_derivation_probe`, `tests.acceptance.test_test_service_body_parsing::test_test_service_default_body_no_5xx`, `tests.acceptance.test_test_service_body_parsing::test_test_service_path_with_leading_slash`, `tests.acceptance.test_test_service_body_parsing::test_test_service_unsupported_method_returns_422`, `tests.acceptance.test_test_service_body_parsing::test_test_service_with_health_path_returns_ok`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-25c3e029 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-33f55440 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6f9d4126 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8f0418a0 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d633f116 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7c224daa | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a965c3a1 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-efb11918 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-22d8b961 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c5131b3d | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-279c765d | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-52ed0cc6 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7700945c | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fe62049f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4bb6f563 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a6ef632a | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5dc3374d | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a4f02538 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3cb4c380 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e0bc4928 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f475d740 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-de8201d5 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e629437b | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4749db35 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-12db9b82 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f7e06575 | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6d2b5e54 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d34b4cb5 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5f6816da | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7ab935e2 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6a1cff5f | ok | 0.960 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-234b2839 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-25c3e029 | operator-logout › Logout deletes the server-side session › The old cookie is refused after logout inside the cache window | pass | pass | the judge passed it and a discriminating test passes |
| C-33f55440 | operator-logout › Logout deletes the server-side session › Logout clears both cookies | pass | pass | the judge passed it and a discriminating test passes |
| C-6f9d4126 | operator-logout › Logout deletes the server-side session › Logout without a session cookie | pass | pass | the judge passed it and a discriminating test passes |
| C-8f0418a0 | operator-logout › Logout deletes the server-side session › Logout twice with the same cookie | pass | pass | the judge passed it and a discriminating test passes |
| C-d633f116 | operator-logout › Logout deletes the server-side session › Concurrent logouts with the same cookie | pass | pass | the judge passed it and a discriminating test passes |
| C-7c224daa | operator-logout › Logout deletes the server-side session › A cookie that is not a UUID | pass | pass | the judge passed it and a discriminating test passes |
| C-a965c3a1 | operator-logout › Logout deletes the server-side session › Logout of an expired session | pass | pass | the judge passed it and a discriminating test passes |
| C-efb11918 | operator-logout › A failed session delete is reported › The session store raises | pass | pass | the judge passed it and a discriminating test passes |
| C-22d8b961 | operator-logout › A failed session delete is reported › The contract lists the outcomes | pass | pass | the judge passed it and a discriminating test passes |
| C-c5131b3d | operator-logout › delete_session removes a session row › A session row is deleted | pass | pass | the judge passed it and a discriminating test passes |
| C-279c765d | operator-logout › delete_session removes a session row › No row to delete | pass | pass | the judge passed it and a discriminating test passes |
| C-52ed0cc6 | operator-logout › delete_session removes a session row › A token that is not a UUID | pass | pass | the judge passed it and a discriminating test passes |
| C-7700945c | operator-logout › The whoami cache forgets a logged-out token › Eviction removes only that token | pass | pass | the judge passed it and a discriminating test passes |
| C-fe62049f | operator-logout › The whoami cache forgets a logged-out token › Evicting a token that is not cached | pass | pass | the judge passed it and a discriminating test passes |
| C-4bb6f563 | operator-logout › The whoami cache forgets a logged-out token › A lookup in flight during logout is not cached | pass | pass | the judge passed it and a discriminating test passes |
| C-a6ef632a | operator-logout › admin-ui logout ends the AdminJS session › A full logout | pass | pass | the judge passed it and a discriminating test passes |
| C-5dc3374d | operator-logout › admin-ui logout ends the AdminJS session › admin-api is unreachable or refuses | pass | pass | the judge passed it and a discriminating test passes |
| C-a4f02538 | operator-logout › admin-ui logout ends the AdminJS session › The session store fails to destroy | pass | pass | the judge passed it and a discriminating test passes |
| C-3cb4c380 | operator-logout › admin-ui logout ends the AdminJS session › A request with no session object | pass | pass | the judge passed it and a discriminating test passes |
| C-e0bc4928 | operator-logout › admin-ui logout ends the AdminJS session › Two concurrent logouts | pass | pass | the judge passed it and a discriminating test passes |
| C-f475d740 | operator-logout › admin-ui logout is a CSRF-protected POST › A missing token is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-de8201d5 | operator-logout › admin-ui logout is a CSRF-protected POST › A wrong token is refused | pass | pass | the judge passed it and a discriminating test passes |
| C-e629437b | operator-logout › admin-ui logout is a CSRF-protected POST › Nothing to log out | pass | pass | the judge passed it and a discriminating test passes |
| C-4749db35 | operator-logout › admin-ui logout is a CSRF-protected POST › GET renders a confirmation form | pass | pass | the judge passed it and a discriminating test passes |
| C-12db9b82 | operator-logout › admin-ui logout is a CSRF-protected POST › GET without a CSRF cookie | pass | pass | the judge passed it and a discriminating test passes |
| C-f7e06575 | operator-logout › admin-ui logout is a CSRF-protected POST › GET without a session | pass | pass | the judge passed it and a discriminating test passes |
| C-6d2b5e54 | operator-logout › The admin UI logs out through a POST form › The top bar renders the form | pass | pass | the judge passed it and a discriminating test passes |
| C-d34b4cb5 | operator-logout › The admin UI logs out through a POST form › Submit sends the current CSRF cookie | pass | pass | the judge passed it and a discriminating test passes |
| C-5f6816da | operator-logout › The admin UI logs out through a POST form › A session without a CSRF token | pass | pass | the judge passed it and a discriminating test passes |
| C-7ab935e2 | operator-logout › The admin UI logs out through a POST form › The override is registered | pass | pass | the judge passed it and a discriminating test passes |
| C-6a1cff5f | operator-logout › The admin UI logs out through a POST form › The router serves both methods behind the limiter | pass | pass | the judge passed it and a discriminating test passes |
| C-234b2839 | operator-logout › The admin UI logs out through a POST form › The server mounts the routes | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Stray trailing blank line in auth.py: The diff adds an extra blank line at end of auth.py.
- [minor, judge] Logout when delete_session returns False still evicts (spec gap) (criterion C-8f0418a0): Behaviour for a valid cookie whose row is already gone is not pinned: code still evicts cache and answers 204.

## New tests (red then green, `task.red_ok` in the ledger)

- `tests.unit.admin_api.test_delete_session::test_delete_session_deletes_row_and_returns_true` (task 1.1): passed
- `tests.unit.admin_api.test_delete_session::test_delete_session_non_uuid_opens_no_database` (task 1.1): passed
- `tests.unit.admin_api.test_delete_session::test_delete_session_returns_false_when_no_row` (task 1.1): passed
- `tests.unit.admin_api.test_logout_session::test_concurrent_logouts_with_same_cookie` (task 3.1): passed
- `tests.unit.admin_api.test_logout_session::test_logout_clears_both_cookies` (task 3.1): passed
- `tests.unit.admin_api.test_logout_session::test_logout_of_expired_session_deletes_by_token` (task 3.1): passed
- `tests.unit.admin_api.test_logout_session::test_logout_twice_with_same_cookie` (task 3.1): passed
- `tests.unit.admin_api.test_logout_session::test_logout_with_non_uuid_cookie_clears_both_cookies` (task 3.1): passed
- `tests.unit.admin_api.test_logout_session::test_logout_without_session_cookie_does_not_delete_or_evict` (task 3.1): passed
- `tests.unit.admin_api.test_logout_session::test_old_cookie_refused_after_logout_inside_cache_window` (task 3.1): passed
- `tests.unit.admin_api.test_logout_store_failure::test_delete_session_failure_answers_503_and_still_evicts` (task 3.2): passed
- `tests.unit.admin_api.test_logout_store_failure::test_openapi_logout_lists_204_and_503` (task 3.2): passed
- `tests.unit.admin_api.test_whoami_eviction::test_evicting_cached_token_removes_only_it` (task 2.1): passed
- `tests.unit.admin_api.test_whoami_eviction::test_evicting_uncached_token_keeps_other_entries` (task 2.1): passed
- `tests.unit.admin_api.test_whoami_eviction::test_lookup_in_flight_during_logout_is_not_cached` (task 2.1): passed
- `tests/LoggedIn.render.test.tsx::LoggedIn override — C-5f6816da no CSRF token > C-5f6816da: renders and submits an empty _csrf when session and cookie have no token` (task 5.1): passed
- `tests/LoggedIn.render.test.tsx::LoggedIn override — C-6d2b5e54 top bar form > C-6d2b5e54: shows the email and a POST form with hidden _csrf and logout button, without a logout link` (task 5.1): passed
- `tests/LoggedIn.render.test.tsx::LoggedIn override — C-d34b4cb5 current CSRF cookie on submit > C-d34b4cb5: submit replaces the rendered _csrf with the current csrf_token cookie` (task 5.1): passed
- `tests/test_logout_guard.test.ts::logoutGuard — C-de8201d5 wrong token > C-de8201d5: refuses a token of another length` (task 4.1): passed
- `tests/test_logout_guard.test.ts::logoutGuard — C-de8201d5 wrong token > C-de8201d5: refuses a token of the same length that differs` (task 4.1): passed
- `tests/test_logout_guard.test.ts::logoutGuard — C-e629437b nothing to log out > C-e629437b: redirects to login when the session has no adminUser and there is no cookie` (task 4.1): passed
- `tests/test_logout_guard.test.ts::logoutGuard — C-e629437b nothing to log out > C-e629437b: redirects to login when there is no session object and no cookie` (task 4.1): passed
- `tests/test_logout_guard.test.ts::logoutGuard — C-f475d740 missing token > C-f475d740: refuses a request without the _csrf field` (task 4.1): passed
- `tests/test_logout_guard.test.ts::logoutGuard — C-f475d740 missing token > C-f475d740: refuses a request without the csrf_token cookie` (task 4.1): passed
- `tests/test_logout_guard.test.ts::logoutGuard — valid token > calls next() once when _csrf equals the csrf_token cookie` (task 4.1): passed
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: does not percent-decode the value` (task 4.1): passed
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: keeps every '=' after the first one in the value` (task 4.1): passed
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: returns the first occurrence of a repeated name` (task 4.1): passed
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: trims surrounding spaces from the value` (task 4.1): passed
- `tests/test_logout_guard.test.ts::readCookie > C-f475d740: matches the exact cookie name (xcsrf_token is not csrf_token)` (task 4.1): passed
- `tests/test_logout_guard.test.ts::readCookie > C-f475d740: returns undefined for a missing header, missing name or empty value` (task 4.1): passed
- `tests/test_logout_router.test.ts::GET /admin/logout — C-12db9b82 without a CSRF cookie > C-12db9b82: renders the same form with an empty _csrf value and changes nothing` (task 4.3): passed
- `tests/test_logout_router.test.ts::GET /admin/logout — C-4749db35 renders a confirmation form > C-4749db35: renders an escaped _csrf form without side effects` (task 4.3): passed
- `tests/test_logout_router.test.ts::GET /admin/logout — C-f7e06575 without a session > C-f7e06575: redirects to /admin/login when there is no session` (task 4.3): passed
- `tests/test_logout_router.test.ts::createLogoutRouter — C-6a1cff5f serves both methods behind the limiter > C-6a1cff5f: the limiter runs for GET and both POSTs, and each answer is right` (task 4.3): passed
- `tests/test_logout_session.test.ts::createLogoutHandler — C-3cb4c380 a request with no session object > C-3cb4c380: calls no admin-api, clears only the operator cookies and redirects` (task 4.2): passed
- `tests/test_logout_session.test.ts::createLogoutHandler — C-5dc3374d admin-api is unreachable or refuses > C-5dc3374d: destroys the AdminJS session and clears the cookies when admin-api answers 503` (task 4.2): passed
- `tests/test_logout_session.test.ts::createLogoutHandler — C-5dc3374d admin-api is unreachable or refuses > C-5dc3374d: destroys the AdminJS session and clears the cookies when fetch rejects` (task 4.2): passed
- `tests/test_logout_session.test.ts::createLogoutHandler — C-a4f02538 the session store fails to destroy > C-a4f02538: still clears the three cookies and redirects when destroy reports an error` (task 4.2): passed
- `tests/test_logout_session.test.ts::createLogoutHandler — C-a6ef632a a full logout > C-a6ef632a: calls admin-api, destroys the AdminJS session, clears all three cookies and redirects` (task 4.2): passed
- `tests/test_logout_session.test.ts::createLogoutHandler — C-e0bc4928 two concurrent logouts > C-e0bc4928: both redirect, both clear adminjs.sid and the store ends empty` (task 4.2): passed
- `tests/test_logout_wiring.test.ts::components/index.ts — C-7ab935e2 LoggedIn override registration > C-7ab935e2: registers the LoggedIn override with ./app/LoggedIn` (task 5.1): passed
- `tests/test_logout_wiring.test.ts::src/index.ts — C-234b2839 mounts the logout router > C-234b2839: mounts createLogoutRouter before requireSession and keeps no GET logout handler` (task 5.2): passed

## Guard events

- guard.violation: apps/admin-api/.hypothesis/.gitignore
- guard.violation: apps/admin-api/.hypothesis/constants/005cb2d0b75b9414
- guard.violation: apps/admin-api/.hypothesis/constants/036533ff311156f8
- guard.violation: apps/admin-api/.hypothesis/constants/0442a4f9ff664719
- guard.violation: apps/admin-api/.hypothesis/constants/04b7d9b483ff416a
- guard.violation: apps/admin-api/.hypothesis/constants/04e20610335c1efd
- guard.violation: apps/admin-api/.hypothesis/constants/04ed1b57880398d1
- guard.violation: apps/admin-api/.hypothesis/constants/0d3a9017498e3f12
- guard.violation: apps/admin-api/.hypothesis/constants/14ef6ba5c8afc3e7
- guard.violation: apps/admin-api/.hypothesis/constants/19c615b0a90adb19
- guard.violation: apps/admin-api/.hypothesis/constants/1b881106c94d3162
- guard.violation: apps/admin-api/.hypothesis/constants/1b8d833b1bb06b3c
- guard.violation: apps/admin-api/.hypothesis/constants/1d6aa44528bb5e5b
- guard.violation: apps/admin-api/.hypothesis/constants/2ba4c0b09b43d140
- guard.violation: apps/admin-api/.hypothesis/constants/334e2cd35334a535
- guard.violation: apps/admin-api/.hypothesis/constants/33a8e71f1cf846ad
- guard.violation: apps/admin-api/.hypothesis/constants/3407634a43eb80e3
- guard.violation: apps/admin-api/.hypothesis/constants/3f1fcc632dadb1fb
- guard.violation: apps/admin-api/.hypothesis/constants/41e441930e6c3f19
- guard.violation: apps/admin-api/.hypothesis/constants/430558def4d4d762
- guard.violation: apps/admin-api/.hypothesis/constants/45b43bc4cd7408d6
- guard.violation: apps/admin-api/.hypothesis/constants/45e7300cb0b8c359
- guard.violation: apps/admin-api/.hypothesis/constants/477c89f2694a04a7
- guard.violation: apps/admin-api/.hypothesis/constants/47ecc356f6e12ff0
- guard.violation: apps/admin-api/.hypothesis/constants/4848be6476209b5a
- guard.violation: apps/admin-api/.hypothesis/constants/4ad84b7fa02c7c08
- guard.violation: apps/admin-api/.hypothesis/constants/59db66ad4bbd29cb
- guard.violation: apps/admin-api/.hypothesis/constants/675eaafa7040a6ef
- guard.violation: apps/admin-api/.hypothesis/constants/67b0a8ccf18bf5d2
- guard.violation: apps/admin-api/.hypothesis/constants/68c2001795193bfb
- guard.violation: apps/admin-api/.hypothesis/constants/6e823fefe683e026
- guard.violation: apps/admin-api/.hypothesis/constants/6fb98dde3112dfad
- guard.violation: apps/admin-api/.hypothesis/constants/783b996bd7418477
- guard.violation: apps/admin-api/.hypothesis/constants/7920a2051ef23688
- guard.violation: apps/admin-api/.hypothesis/constants/7e64b0f62de0d79e
- guard.violation: apps/admin-api/.hypothesis/constants/82db23fd656472a4
- guard.violation: apps/admin-api/.hypothesis/constants/894a586d5f2ed4bf
- guard.violation: apps/admin-api/.hypothesis/constants/8993f21eb5fba8fd
- guard.violation: apps/admin-api/.hypothesis/constants/8d8ee59068d4113f
- guard.violation: apps/admin-api/.hypothesis/constants/91b1032f0cb7da5b
- guard.violation: apps/admin-api/.hypothesis/constants/972dd3a4af379804
- guard.violation: apps/admin-api/.hypothesis/constants/9845bd703d94aabc
- guard.violation: apps/admin-api/.hypothesis/constants/a39392c1d25db545
- guard.violation: apps/admin-api/.hypothesis/constants/a4a4bfc444a036a6
- guard.violation: apps/admin-api/.hypothesis/constants/a939faedc6eb633e
- guard.violation: apps/admin-api/.hypothesis/constants/b06d435bdec50977
- guard.violation: apps/admin-api/.hypothesis/constants/b68093d4142c13cf
- guard.violation: apps/admin-api/.hypothesis/constants/bcea3d9f0ea3aad2
- guard.violation: apps/admin-api/.hypothesis/constants/c50e4315a75123bc
- guard.violation: apps/admin-api/.hypothesis/constants/c59c3c3d0ab38a43
- guard.violation: apps/admin-api/.hypothesis/constants/c5e393b944f93e17
- guard.violation: apps/admin-api/.hypothesis/constants/c854cc07e76b8294
- guard.violation: apps/admin-api/.hypothesis/constants/cc354972bffdf65c
- guard.violation: apps/admin-api/.hypothesis/constants/cf52bfc4d6d4552d
- guard.violation: apps/admin-api/.hypothesis/constants/d03f30b52f4b5e99
- guard.violation: apps/admin-api/.hypothesis/constants/d07acab8241772bc
- guard.violation: apps/admin-api/.hypothesis/constants/d51cb5d1491a2e75
- guard.violation: apps/admin-api/.hypothesis/constants/da39a3ee5e6b4b0d
- guard.violation: apps/admin-api/.hypothesis/constants/e155377647d3a41f
- guard.violation: apps/admin-api/.hypothesis/constants/e22ce368906cab3e
- guard.violation: apps/admin-api/.hypothesis/constants/ef119a92d73a4038
- guard.violation: apps/admin-api/.hypothesis/constants/ef9d4f4ea0f23d80
- guard.violation: apps/admin-api/.hypothesis/constants/f1b88638987c5dc7
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/charmap.json.gz
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/codec-v2-utf-8.json.gz
- guard.violation: apps/admin-api/.hypothesis/constants/005cb2d0b75b9414
- guard.violation: apps/admin-api/.hypothesis/constants/036533ff311156f8
- guard.violation: apps/admin-api/.hypothesis/constants/0442a4f9ff664719
- guard.violation: apps/admin-api/.hypothesis/constants/04b7d9b483ff416a
- guard.violation: apps/admin-api/.hypothesis/constants/04e20610335c1efd
- guard.violation: apps/admin-api/.hypothesis/constants/04ed1b57880398d1
- guard.violation: apps/admin-api/.hypothesis/constants/0d3a9017498e3f12
- guard.violation: apps/admin-api/.hypothesis/constants/14ef6ba5c8afc3e7
- guard.violation: apps/admin-api/.hypothesis/constants/19c615b0a90adb19
- guard.violation: apps/admin-api/.hypothesis/constants/1b881106c94d3162
- guard.violation: apps/admin-api/.hypothesis/constants/1b8d833b1bb06b3c
- guard.violation: apps/admin-api/.hypothesis/constants/1d6aa44528bb5e5b
- guard.violation: apps/admin-api/.hypothesis/constants/2ba4c0b09b43d140
- guard.violation: apps/admin-api/.hypothesis/constants/334e2cd35334a535
- guard.violation: apps/admin-api/.hypothesis/constants/3407634a43eb80e3
- guard.violation: apps/admin-api/.hypothesis/constants/3f1fcc632dadb1fb
- guard.violation: apps/admin-api/.hypothesis/constants/41e441930e6c3f19
- guard.violation: apps/admin-api/.hypothesis/constants/430558def4d4d762
- guard.violation: apps/admin-api/.hypothesis/constants/45b43bc4cd7408d6
- guard.violation: apps/admin-api/.hypothesis/constants/45e7300cb0b8c359
- guard.violation: apps/admin-api/.hypothesis/constants/477c89f2694a04a7
- guard.violation: apps/admin-api/.hypothesis/constants/47ecc356f6e12ff0
- guard.violation: apps/admin-api/.hypothesis/constants/4848be6476209b5a
- guard.violation: apps/admin-api/.hypothesis/constants/4ad84b7fa02c7c08
- guard.violation: apps/admin-api/.hypothesis/constants/59db66ad4bbd29cb
- guard.violation: apps/admin-api/.hypothesis/constants/675eaafa7040a6ef
- guard.violation: apps/admin-api/.hypothesis/constants/67b0a8ccf18bf5d2
- guard.violation: apps/admin-api/.hypothesis/constants/68c2001795193bfb
- guard.violation: apps/admin-api/.hypothesis/constants/6e823fefe683e026
- guard.violation: apps/admin-api/.hypothesis/constants/6fb98dde3112dfad
- guard.violation: apps/admin-api/.hypothesis/constants/7920a2051ef23688
- guard.violation: apps/admin-api/.hypothesis/constants/7e64b0f62de0d79e
- guard.violation: apps/admin-api/.hypothesis/constants/82db23fd656472a4
- guard.violation: apps/admin-api/.hypothesis/constants/894a586d5f2ed4bf
- guard.violation: apps/admin-api/.hypothesis/constants/8993f21eb5fba8fd
- guard.violation: apps/admin-api/.hypothesis/constants/8d8ee59068d4113f
- guard.violation: apps/admin-api/.hypothesis/constants/91b1032f0cb7da5b
- guard.violation: apps/admin-api/.hypothesis/constants/972dd3a4af379804
- guard.violation: apps/admin-api/.hypothesis/constants/9845bd703d94aabc
- guard.violation: apps/admin-api/.hypothesis/constants/9bff7cb592d55a76
- guard.violation: apps/admin-api/.hypothesis/constants/a39392c1d25db545
- guard.violation: apps/admin-api/.hypothesis/constants/a4a4bfc444a036a6
- guard.violation: apps/admin-api/.hypothesis/constants/a939faedc6eb633e
- guard.violation: apps/admin-api/.hypothesis/constants/b06d435bdec50977
- guard.violation: apps/admin-api/.hypothesis/constants/b68093d4142c13cf
- guard.violation: apps/admin-api/.hypothesis/constants/bcea3d9f0ea3aad2
- guard.violation: apps/admin-api/.hypothesis/constants/c50e4315a75123bc
- guard.violation: apps/admin-api/.hypothesis/constants/c59c3c3d0ab38a43
- guard.violation: apps/admin-api/.hypothesis/constants/c5e393b944f93e17
- guard.violation: apps/admin-api/.hypothesis/constants/c854cc07e76b8294
- guard.violation: apps/admin-api/.hypothesis/constants/cc354972bffdf65c
- guard.violation: apps/admin-api/.hypothesis/constants/cf52bfc4d6d4552d
- guard.violation: apps/admin-api/.hypothesis/constants/d03f30b52f4b5e99
- guard.violation: apps/admin-api/.hypothesis/constants/d07acab8241772bc
- guard.violation: apps/admin-api/.hypothesis/constants/d51cb5d1491a2e75
- guard.violation: apps/admin-api/.hypothesis/constants/da39a3ee5e6b4b0d
- guard.violation: apps/admin-api/.hypothesis/constants/e155377647d3a41f
- guard.violation: apps/admin-api/.hypothesis/constants/e22ce368906cab3e
- guard.violation: apps/admin-api/.hypothesis/constants/ef119a92d73a4038
- guard.violation: apps/admin-api/.hypothesis/constants/ef9d4f4ea0f23d80
- guard.violation: apps/admin-api/.hypothesis/constants/f1b88638987c5dc7
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/charmap.json.gz
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/codec-v2-utf-8.json.gz
- guard.violation: apps/admin-ui/src/routes/logout.ts
- guard.violation: apps/admin-ui/src/routes/logout.ts
- guard.violation: apps/admin-ui/src/components/app/LoggedIn.tsx
