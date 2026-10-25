# Verification: openspec:agent-auth-unavailable: FAIL (round 2)

traceability: not checked (an earlier step failed)

- Base: `2bdc6c769afac3dfb9e6dc983171072caa633985`
- Head: `0ba515796fad3f7e6ceeef89d398acbe3409ead1`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.5 | base staging@2bdc6c769a contained; Feedback FB-001 (behaviour): to_mib accepts 512mi, 1gi and non-ASCII digits |
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

- [major, feedback] Feedback FB-001 (behaviour): to_mib accepts 512mi, 1gi and non-ASCII digits: Review by Claude as the owner's delegate. The requirement "admin-api's memory limit fits its verify concurrency" says to_mib converts an integer followed by m, M or Mi (MiB) or g, G or Gi (times 1024) and that any other string SHALL raise ValueError whose message contains the string. The pattern (\d+)([mMgG]i?) also accepts a lowercase unit with i (512mi gives 512, 1gi gives 1024), and \d matches non-ASCII digits (５１２m gives 512). Accept exactly the six units (for example (\d+)(Mi|Gi|m|M|g|G) compiled with re.ASCII, still with fullmatch) and change nothing else: the other functions, their mess...

## Fix unit

Fix unit 1 is created for these tasks:
- F-fede8b82 Feedback FB-001 (behaviour): to_mib accepts 512mi, 1gi and non-ASCII digits

## New tests (red then green, `task.red_ok` in the ledger)

- `apps.mcp-server.tests.test_rest_auth_unavailable::test_C_0bbc396d_list_services_unjudged_key_gets_503_without_using_session` (task 1.1): not in the report
- `apps.mcp-server.tests.test_rest_auth_unavailable::test_C_9a964586_request_token_unjudged_x_api_key_gets_same_503` (task 1.1): not in the report
- `tests.acceptance.test_admin_api_verify_capacity::test_C_06752b13_capacity_problem_reports_a_definition_below_the_rule` (task 3.1): not in the report
- `tests.acceptance.test_admin_api_verify_capacity::test_C_434fcc7f_to_mib_converts_memory_units_and_refuses_others` (task 3.1): not in the report
- `tests.acceptance.test_admin_api_verify_capacity::test_C_cbd20f5c_three_definitions_fit_the_rule` (task 3.1): not in the report
- `tests.acceptance.test_admin_api_verify_capacity::test_C_e54cc104_compose_concurrency_refuses_a_non_integer_value` (task 3.1): not in the report
- `tests.acceptance.test_admin_api_verify_capacity::test_C_f6faf63f_capacity_problem_ignores_a_definition_without_a_limit` (task 3.1): not in the report
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_51ef8acf_verify_mismatch_is_still_401` (task 2.1): not in the report
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_55531051_cancelled_verify_propagates` (task 2.1): not in the report
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_60c778ab_invalid_stored_hash_is_still_401` (task 2.1): not in the report
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_b6439852_unexpected_verify_error_answers_503` (task 2.1): not in the report
- `tests.unit.admin_api.test_validate_agent_key_errors::test_C_f73110db_unknown_key_stays_401_when_dummy_verify_raises` (task 2.1): not in the report

## Guard events

- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/00d37eca0cff8298bcc57d724ad4af38514d52ab
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/03f4ea02fbde4bdd9a3d248f0c644929d25e8f96
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0519dacc6346555d3ac10973817fad5743cbda6e
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0b63898109098817c3aec161e0ce39accb0908cd
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0bc66cadaf685114a450ccf9f65b2269cc3c8a0c
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0c804442f1592ea36742d8ce7b6e10607d253806
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/0e2a10bd85fa356fd102af8c6b21a89fb9d5e3cb
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/10ac3c915769b98d8219bc559a3f685dffbbdec2
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/11b0f908d80b9191f302979390ee23d23a91da0d
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/13bec1f0671b2d9ee1e5db791511c12434e025d6
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1489eb63746552f5d20fec487cf605f8d2f4db4f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/16534ea5694cf7df163d6a3567cab60b29255607
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/17414745e5049ce2971ccfe864032ec701103776
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1af6f3e81150e1d36969925c83c201dc7b5d11e5
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1b1251adb00aca450ddcb56631ece60a1ffbef97
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cbe65c3ad8c619476df40b26415f02b840f5f86
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/1cfabd3da28cee3867d48daae62928dead50da8f
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/2081cc36619dcd637237b2a6bc287200d38a2fa9
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/232e222d62794c94d897ee9f68a6cc680da7b63a
- guard.violation: apps/admin-ui/node_modules/.vitest-cache/262b4524a46ca714f04b997c38b37a5efeb8bb6d
- guard.violation: infra/compose/docker-compose.ghcr.yml
- guard.violation: infra/compose/docker-compose.yml
