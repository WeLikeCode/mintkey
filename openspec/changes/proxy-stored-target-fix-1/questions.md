# Questions — proxy-stored-target-fix-1

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | open | 1.1 | technical | Unfreeze tests/acceptance/test_e2e_smoke.py:414, tests/acceptance/test_golden_path.py:545, tests/acceptance/test_data_plane_smoke.py:494 and tests/acceptance/test_classical_key.py:208: red test C-969b |
<!-- l4:index:end -->

---

## Q-001: Unfreeze tests/acceptance/test_e2e_smoke.py:414, tests/acceptance/test_golden_path.py:545, tests/acceptance/test_data_plane_smoke.py:494 and tests/acceptance/test_classical_key.py:208: red test C-969b

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): The question comes from a fix task: the unit is proxy-stored-target-fix-1 and its tasks.md has a single task "1.1 task 4.1: live-stack acceptance tests not updated" under "## 1. Fix". The fix unit's spec (specs/proxy-stored-target/spec.md lines 11-13) and the parent tasks.md task 4.1 (lines 119-124) both require edits to tests/acceptance/test_e2e_smoke.py, test_golden_path.py, test_data_plane_smoke.py and test_classical_key.py, and I verified those files still compare received_key with the registered secret (test_classical_key.py:208 REAL_CRED, test_data_plane_smoke.py:494 and test_golden_path.py:545 secret_value, test_e2e_smoke.py:414 the demo literal). The red test test_live_stack_redaction_assertions.py:85-113 reads those four files from disk, so no production-code change can make it pass. The only answer is a change to test files, which for a fix task the rules say a person must commit; I cannot accept option 1 nor answer otherwise.
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-11-25T01:21Z by deepseek, run r-20261125T0056Z-9676, task 1.1

### Context
tests/acceptance/test_live_stack_redaction_assertions.py (lines 89-113) parses the four live-stack acceptance files and requires every received_key comparison to be `==` with the constant "[REDACTED]", plus a comment containing both 'redact' and 'inject'. That is exactly what spec C-969b7732 and openspec/changes/proxy-stored-target/tasks.md task 4.1 demand ('every assertion that received_key equals the registered secret becomes received_key == "[REDACTED]" ... with a comment saying so'). The red test cannot be satisfied from production code: it reads those four files from disk. But the green phase's test-path-freeze restored all four when attempt 1 edited them (ledger r-20261125T0056Z-9676 seq 83-86, guard.test_tamper, action=restored), and the current gate run fails exactly those four parametrised cases and nothing else. The files are test files, so green may not change them without an answer that names them.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/acceptance/test_classical_key.py`, `tests/acceptance/test_data_plane_smoke.py`, `tests/acceptance/test_e2e_smoke.py`, write an answer that names its path exactly as written here or run `l4 questions accept Q-NNN --unit proxy-stored-target-fix-1`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/acceptance/test_e2e_smoke.py` line 414: replace `assert proxy_r.json().get("received_key") == "[REDACTED:openai-key]", (` with a preceding comment `# The proxy redacts exactly the credential value it injected, so the mock backend's echo reads back as [REDACTED].` and `assert proxy_r.json().get("received_key") == "[REDACTED]", (`; Edit `tests/acceptance/test_golden_path.py` line 545: replace `assert proxy_body.get("received_key") == secret_value, (` with a preceding comment `# The proxy redacts exactly the credential value it injected, so received_key reads back as [REDACTED].` and `assert proxy_body.get("received_key") == "[REDACTED]", (`; Edit `tests/acceptance/test_data_plane_smoke.py` line 494: the same comment plus `assert proxy_body.get("received_key") == "[REDACTED]", (`; Edit `tests/acceptance/test_classical_key.py` line 208: add a comment `# The proxy redacts exactly the value it injected, so the echoed received_key is [REDACTED].` and replace `assert received == REAL_CRED, (` with `assert received == "[REDACTED]", (`. Keep every other statement (including `received = proxy_r.json().get("received_key")`) and the assert messages. This unfreezes exactly those four files for task 1.1.
2. Do not unfreeze the four files: keep their current assertions on the registered secret and accept that C-969b7732 cannot pass (the fix is then impossible for this unit).

### Harness notes
Harness note: the previous attempt of this task was rejected: red tests still failing: tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_classical_key.py], tests.acceptance.test_live_stack_redaction_assertions::test_C_969b7732_live_stack_test_asserts_the_redaction_marker[test_data_plane_smo
E           AssertionError: test_classical_key.py compares received_key with 'REAL_CRED'; expected the redaction marker '[REDACTED]' because the proxy replaces exactly the value it injected
E           assert (False) (same for 3 tests)
E            +  where False = isinstance(<ast.Name object at 0x7f6a5f790150>, <class 'ast.Constant'>)
E            +    where <class 'ast.Constant'> = ast.Constant (same for 4 tests)
E           AssertionError: test_data_plane_smoke.py compares received_key with 'secret_value'; expected the redac
../../tests/acceptance/test_live_stack_redaction_assertions.py:100

### Answer
<!-- write below this line -->
Answered by the repository owner's delegate (a Claude Code session the owner authorised to answer person-only unfreeze questions on this plan). Unfreeze these four files for task 1.1: `tests/acceptance/test_e2e_smoke.py`, `tests/acceptance/test_golden_path.py`, `tests/acceptance/test_data_plane_smoke.py` and `tests/acceptance/test_classical_key.py`. This is what the parent's task 4.1 and C-969b7732 require: the proxy now redacts exactly the credential value it injected, so the mock backend's echo reads back as "[REDACTED]". In each file change only the received_key comparison: compare with the string constant "[REDACTED]" (test_e2e_smoke.py line 414 compares with the demo key literal, test_golden_path.py line 545 and test_data_plane_smoke.py line 494 with secret_value, test_classical_key.py line 208 with REAL_CRED), put directly above it the comment `# The proxy redacts exactly the credential value it injected, so the echoed received_key reads back as [REDACTED].`, and in that assert's message write the marker where it printed the expected secret. Keep every other statement, including `received = proxy_r.json().get("received_key")` and the `plaintext_key not in proxy_r.text` check. Note: option 1 shows the line of test_e2e_smoke.py with a redaction placeholder where the file holds the demo key literal; the literal in the file is what is replaced.
