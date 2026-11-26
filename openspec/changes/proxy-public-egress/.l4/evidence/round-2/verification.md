# Verification: openspec:proxy-public-egress: FAIL (round 2)

traceability: not checked (an earlier step failed)

- Base: `bc9151a1d442dd95296ea71d143770670dfc55e9`
- Head: `053a6f76ec891928749334d58a7650dbc7fce299`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.6 | base staging@bc9151a1d4 contained; Feedback FB-001 (refactor): Resolve the resolver and dialer defaults outside the dial closure; Feedback FB-002 (behaviour): Refuse IPv6 forms that carry an IPv4 address |
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

- [major, feedback] Feedback FB-001 (refactor): Resolve the resolver and dialer defaults outside the dial closure: PublicDialContext assigns the captured r and d inside the returned closure when they are nil. NewPublicTransport passes r = nil and shares one transport across requests, so concurrent first dials write the captured variable at the same time (a data race the race detector reports). Pick net.DefaultResolver and a zero Dialer once, before the closure is returned, and let the closure only read them. Behaviour is unchanged.
- [major, feedback] Feedback FB-002 (behaviour): Refuse IPv6 forms that carry an IPv4 address: These IPv6 forms embed an IPv4 address, and the guard classifies them by their IPv6 prefix only, so an embedded private IPv4 address is not refused; the current list does not include them. Add the three ranges to nonPublicRanges in apps/proxy-plugin/internal/egress/public.go; every other address keeps its classification.

## Fix unit

Fix unit 1 is created for these tasks:
- F-b58eac76 Feedback FB-001 (refactor): Resolve the resolver and dialer defaults outside the dial closure
- F-3d836ff5 Feedback FB-002 (behaviour): Refuse IPv6 forms that carry an IPv4 address

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestOtherScopesAreUnchanged_C_e16db2b8` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeIgnoresProxyEnvironmentChild` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeIgnoresProxyEnvironment_C_0770d694` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeNameWithoutAddress_C_bd037c93` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesLoopbackName_C_37681a78` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestPublicScopeRefusesNonPublicTargets_C_bd7857b1` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestScopeArrivesFromVault_C_b5f6f1f1` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/proxy-plugin/cmd/proxy-plugin::TestUnknownScopeIsTreatedAsPublic_C_ed224807` (task 4.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeEverySchemeResponse_C_a4ac0a47` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeEverySchemeResponse_C_a4ac0a47/C-a4ac0a47` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFailingLookupFailsPut_C_eac1baf3` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFailingLookupFailsPut_C_eac1baf3/C-eac1baf3` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073/C-43146073/concurrent` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073/C-43146073/nil_nil` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeFirstPutAndConcurrentPuts_C_43146073/C-43146073/no_rows_error` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRotationKeepsScope_C_b52d2f54` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRotationKeepsScope_C_b52d2f54/C-b52d2f54` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRoundTrip_C_cbe614ee` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeRoundTrip_C_cbe614ee/C-cbe614ee` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeUnusableValueRefused_C_48ff464c` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestEgressScopeUnusableValueRefused_C_48ff464c/C-48ff464c` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestEveryTargetURLFileHandlesEgressScope_C_1971e22f` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestEveryTargetURLFileHandlesEgressScope_C_1971e22f/C-1971e22f` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestHashicorpDocEgressScope_C_adac8186` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestHashicorpDocEgressScope_C_adac8186/C-adac8186` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestStoreNotFoundIsSqlErrNoRows_C_0704866f` (task 3.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/store::TestStoreNotFoundIsSqlErrNoRows_C_0704866f/C-0704866f` (task 3.1): not in the report
- `tests.unit.admin_api.test_credential_egress_scope_changelog::test_C_09049412_changelog_adds_the_egress_scope_column` (task 1.1): not in the report
- `tests.unit.admin_api.test_vault_client_put_egress_scope::test_C_9f390972_put_credential_sends_the_scope_metadata` (task 2.1): not in the report

## Guard events

- guard.violation: apps/admin-api/src/admin_api/services/vault_client.py
- guard.violation: apps/admin-api/src/admin_api/services/vault_client.py
- guard.violation: apps/admin-api/src/admin_api/services/vault_client.py
