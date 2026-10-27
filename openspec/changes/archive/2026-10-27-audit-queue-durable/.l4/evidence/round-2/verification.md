# Verification: openspec:audit-queue-durable: FAIL (round 2)

traceability: not checked (an earlier step failed)

- Base: `3e404e1d96e08c7459c1f8949d864a9f0485662c`
- Head: `7e27c920f2e4d60cf435d38c9931e04725115904`
- Implementer profiles: deepseek
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.9 | base staging@3e404e1d96 contained |
| 1 | integrity | failed | 488.8 | a pre-existing test fails on the unit's code; scope: 22 changed file(s) |
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
| pre-existing tests | skipped | no Python test file changed; 1 other test file(s) are checked by the run of pre-existing tests |
| red-green freeze | ok | 4 task(s): red and green compared |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | not checked: python only; changed files outside it: packages/go/auditq/backlog_test.go, packages/go/auditq/compact_test.go, packages/go/auditq/durable_test.go, packages/go/auditq/metrics.go, packages/go/auditq/queue.go (+2 more) |
| tdd history | ok | 4 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | failed | 2720 of 2721 base tests pass on the unit's code with its 5 test and support files at the base (base: evidence) |

## Test changes made by humans (allowed, L4-SEC-004)

- github.com/mintkey/mintkey/packages/go/auditq::TestDeadLetterMetrics fails with the base version of its files (changed by 50bf0daea8, 35dea71388)

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `openspec/changes/audit-queue-durable-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2007Z-6906.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2013Z-81cc.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2243Z-71a7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/.l4/ledger/r-20261026T2310Z-1139.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/audit-queue-durable/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/go/auditq/backlog_test.go` |  | relevant | new test file |
| `packages/go/auditq/compact_test.go` |  | relevant | named in the spec |
| `packages/go/auditq/durable_test.go` |  | relevant | new test file |
| `packages/go/auditq/metrics.go` | go | relevant | named in the spec |
| `packages/go/auditq/queue.go` | go | relevant | named in the spec |
| `packages/go/auditq/settings_test.go` |  | relevant | new test file |
| `packages/go/auditq/walformat_test.go` |  | relevant | new test file |

### Changed functions

Diff coverage not run.

### Tests

Tests-ran check not run.

## Criteria

None judged.

## Findings

- [blocker, deterministic] a pre-existing test fails on the unit's code: tests.acceptance.test_async_audit_emission::test_auditq_unit_tests_pass (AssertionError: auditq unit tests failed (exit 1):)

## Fix unit

Fix unit 2 is created for these tasks:
- F-2813828d a pre-existing test fails on the unit's code

## New tests (red then green, `task.red_ok` in the ledger)

- `github.com/mintkey/mintkey/packages/go/auditq::TestAppendAfterPartialLineStartsNewLine_C_306d3e39` (task 3.2): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestBacklogInExposition_C_93344fde` (task 1.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestCloseWhileSinkDownKeepsEvents_C_377ec4fd` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestCompactionBetweenReadAndTombstone_C_88d9b9f7` (task 3.2): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestConcurrencyIsBounded_C_d0d6b92f` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestCurrentFormatWALDrainsInPlace_C_c0a8fbe4` (task 3.2): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsDefaults_C_ea45dc31` (task 2.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsFromEnvironment_C_be765c63` (task 2.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestDrainSettingsInvalidValues_C_0b97502f` (task 2.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestRefusalStatuses_C_f33bec22` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestRefusedEventRecord_C_8c6da99a` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestRefusedEventsDoNotHoldUpOthers_C_2ea77966` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestReplayCountsPendingEvents_C_933c705a` (task 1.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestRetriesPastFiveFailures_C_339a52c5` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestRetryDelayDoublesUpToCap_C_e8b4f95d` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestSinkDownThenBack_C_ff7aad7b` (task 3.1): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestUnreadableLineDeadLettered_C_84b4a061` (task 3.2): not in the report
- `github.com/mintkey/mintkey/packages/go/auditq::TestUnwritableWALDeliversFromMemory_C_aa2619c2` (task 3.1): not in the report
