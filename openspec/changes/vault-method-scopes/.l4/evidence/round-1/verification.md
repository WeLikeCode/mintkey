# Verification: openspec:vault-method-scopes: FAIL (round 1)

traceability: not checked (an earlier step failed)

- Base: `cd7f5e7cb59b4187ea03e78b0511d4983a2252e3`
- Head: `0bb2ae8ba49aba0450294e0f4d0f6b7f4c627355`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base staging@cd7f5e7cb5 contained |
| 1 | integrity | failed | 582.1 | a pre-existing test fails on the unit's code; scope: 12 changed file(s) |
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
| pre-existing tests | skipped | no Python test file changed; 2 other test file(s) are checked by the run of pre-existing tests |
| red-green freeze | ok | 1 task(s): red and green compared |
| test path freeze | ok | 1 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: apps/vault-adapter/internal/server/grpc.go, apps/vault-adapter/internal/server/grpc_agent_secrets.go, apps/vault-adapter/internal/server/grpc_ssh.go, apps/vault-adapter/internal/server/grpc_ssh_test.go, apps/vault-adapter/internal/server/grpc_test.... |
| tdd history | ok | 2 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | failed | 2654 of 2656 base tests pass on the unit's code with its 4 test and support files at the base (base: base worktree) |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/vault-adapter/internal/server/grpc.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_agent_secrets.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_ssh.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_ssh_test.go` |  | relevant | named in the spec |
| `apps/vault-adapter/internal/server/grpc_test.go` |  | relevant | named in the spec |
| `apps/vault-adapter/internal/server/identities.go` | vault-adapter | relevant | named in the spec |
| `apps/vault-adapter/internal/server/identity_scopes_test.go` |  | relevant | new test file |
| `apps/vault-adapter/internal/server/method_scopes_test.go` |  | relevant | new test file |
| `openspec/changes/vault-method-scopes/.l4/ledger/r-20261026T0311Z-4b41.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/.l4/ledger/r-20261026T0313Z-8028.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/vault-method-scopes/tasks.md` |  | none | exempt: harness, spec or documentation path |

### Changed functions

Diff coverage not run.

### Tests

Tests-ran check not run.

## Criteria

None judged.

## Findings

- [blocker, deterministic] a pre-existing test fails on the unit's code: github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestGRPCValidateServiceIdentity_MissingToken (Failed), github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestSSHVault_GetAgentByFingerprint_MissingToken (Failed)

## Fix unit

Fix unit 1 is created for these tasks:
- F-2813828d a pre-existing test fails on the unit's code

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestBootIdentities_LeastPrivilegeScopes_C_5ecd45eb` (task 2.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestBuiltServer_OnlyHealthWatchStreams_C_6484c16c` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestListVersions_RequiresIdentity_C_2d4f1ec1` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_CoversEveryServedMethod_C_8bf69f2c` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_NotWrittenByRegistration_C_56f4739c` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestMethodTable_ScopePerMethod_C_8c1bdc49` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestProxyIdentity_CannotPutCredential_AdminCan_C_b2d83dba` (task 2.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestSSHProxyIdentity_StoresHostKeyButCannotPutCredential_C_35dca710` (task 2.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_FullIdentityServedEverywhere_C_70816534` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_HealthMethodsNeedNoIdentity_C_ac51d472_C_377bc9e7` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_NoIdentityRefusedOnEveryListedMethod_C_c547eb9c` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_ReadOnlyIdentityCannotWrite_C_78d436a5` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_UnlistedMethodRefused_C_377bc9e7` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestScopeInterceptor_WrongTokenRefusedOnEveryListedMethod_C_e4e95bdb` (task 1.1): not in the report
- `github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestValidateServiceIdentity_RequiresIdentityButNoScope_C_08b38088` (task 1.1): not in the report
