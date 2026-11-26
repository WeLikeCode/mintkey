# Questions — proxy-stored-target

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
| Q-001 | answered | none | verdict | Finding F-3e53e4bd: task 4.1: live-stack acceptance tests not updated |
| Q-002 | open | none | verdict | Hold H-5ce5dda0: skipped: existing tests in `tests/acceptance/test_classical_key.py` were also skipped in a base report, and the file ... |
| Q-003 | open | none | verdict | Hold H-430ee622: skipped: existing tests in `tests/acceptance/test_data_plane_smoke.py` were also skipped in a base report, and the fi... |
| Q-004 | open | none | verdict | Hold H-46baa229: skipped: existing tests in `tests/acceptance/test_golden_path.py` were also skipped in a base report, and the file ad... |
<!-- l4:index:end -->

---

## Q-001: Finding F-3e53e4bd: task 4.1: live-stack acceptance tests not updated

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier

### Context
The judge raised a major finding in round 1, and no deterministic check confirms it.

Title: task 4.1: live-stack acceptance tests not updated
Detail: Task 4.1 requires test_e2e_smoke.py, test_golden_path.py, test_data_plane_smoke.py and test_classical_key.py to assert received_key == "[REDACTED]". The diff shows no change to any tests/acceptance file, though the implementer's note claims they were updated.

Answer `accept` to waive the finding, or `reject` and say why: a rejected finding is fixed by a fix unit, and your reason comes first in it.
This finding cites no criterion: end the reason with one sentence WHEN <the situation> THEN <the behaviour you expect>, with WHEN and THEN in capitals, or no fix can be made from the reject.

### Options
1. accept
2. reject: <reason>, then WHEN ... THEN ... to set the check

### Answer
<!-- write below this line -->
reject The finding is correct. Task 4.1 of tasks.md requires that in test_e2e_smoke.py, test_golden_path.py, test_data_plane_smoke.py and test_classical_key.py every assertion that received_key equals the registered secret becomes an assertion that it equals the redaction marker, with a comment saying why. None of the four files was changed: test_data_plane_smoke.py and test_golden_path.py still assert received_key equals secret_value, test_e2e_smoke.py still asserts it equals the demo secret literal, test_classical_key.py still asserts it equals REAL_CRED, and no file under tests/acceptance contains the text [REDACTED]. Since main.go now builds every flow through newUpstreamProxy, which calls scrubber.ScrubWith with the injected credential, the proxy replaces the echoed value and these live-stack tests would fail against the compose stack as written. WHEN the live-stack acceptance tests test_e2e_smoke.py (step 10), test_golden_path.py, test_data_plane_smoke.py and test_classical_key.py read the credential back from the mock backend's received_key THEN each of them asserts that received_key equals "[REDACTED]" rather than the registered secret, with a comment explaining that the proxy redacts exactly the value it injected, and no acceptance test still asserts received_key equals the registered secret.

---

## Q-002: Hold H-5ce5dda0: skipped: existing tests in `tests/acceptance/test_classical_key.py` were also skipped in a base report, and the file ...

- **Status:** open
- **Escalated by:** the delegate: a skipped-test hold is a person's decision
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 4, verifier

### Context
After round 4 the verifier cannot decide on its own: skipped: existing tests in `tests/acceptance/test_classical_key.py` were also skipped in a base report, and the file adds or changes no skip the harness reads (1 tests)

The skipped tests (1):
- tests.acceptance.test_classical_key::test_classical_key_full_flow

What was compared: these tests were also skipped in a base report (step 1 base run), the file adds or changes no skip construct the harness reads (decorators, marks and skip calls in the file) and nothing inside the file that decides whether an unchanged skip skips (a flag, a condition, a helper, a fixture or an import it reads), the unit changed the file only in places that cannot change why a test skips (comment and blank lines, the body of a test beyond what skips it, a whole new import of a name the file did not use), and no support, runner, setup or dependency file changed. What is not told apart: production code the unit changed, a module the file imports that the unit did not change (an added import is allowed only from the standard library), run-time or import-time state that another test sets (its body, decorator or default values), a changed sibling test module the file imports, and dynamic forms and plugins that read test names (`exec`, `getattr`, `importlib`, `globals()`, a plugin such as test dependencies): the tests were skipped at the base too, but the reason may have changed. Often the cause is an environment the gate does not have (a stack, a service). `accept` means you ran them where they can run, or know they pass there; it holds for this content of the file only. `reject: <reason>` ends the round, because a fix unit cannot change test files: no fix unit is made and the unit is escalated with skipped_tests_rejected; then change the file in your own commit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
---

## Q-003: Hold H-430ee622: skipped: existing tests in `tests/acceptance/test_data_plane_smoke.py` were also skipped in a base report, and the fi...

- **Status:** open
- **Escalated by:** the delegate: a skipped-test hold is a person's decision
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 4, verifier

### Context
After round 4 the verifier cannot decide on its own: skipped: existing tests in `tests/acceptance/test_data_plane_smoke.py` were also skipped in a base report, and the file adds or changes no skip the harness reads (4 tests)

The skipped tests (4):
- tests.acceptance.test_data_plane_smoke::test_broker_smoke
- tests.acceptance.test_data_plane_smoke::test_kong_smoke
- tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke
- tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke

What was compared: these tests were also skipped in a base report (step 1 base run), the file adds or changes no skip construct the harness reads (decorators, marks and skip calls in the file) and nothing inside the file that decides whether an unchanged skip skips (a flag, a condition, a helper, a fixture or an import it reads), the unit changed the file only in places that cannot change why a test skips (comment and blank lines, the body of a test beyond what skips it, a whole new import of a name the file did not use), and no support, runner, setup or dependency file changed. What is not told apart: production code the unit changed, a module the file imports that the unit did not change (an added import is allowed only from the standard library), run-time or import-time state that another test sets (its body, decorator or default values), a changed sibling test module the file imports, and dynamic forms and plugins that read test names (`exec`, `getattr`, `importlib`, `globals()`, a plugin such as test dependencies): the tests were skipped at the base too, but the reason may have changed. Often the cause is an environment the gate does not have (a stack, a service). `accept` means you ran them where they can run, or know they pass there; it holds for this content of the file only. `reject: <reason>` ends the round, because a fix unit cannot change test files: no fix unit is made and the unit is escalated with skipped_tests_rejected; then change the file in your own commit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
---

## Q-004: Hold H-46baa229: skipped: existing tests in `tests/acceptance/test_golden_path.py` were also skipped in a base report, and the file ad...

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 4, verifier

### Context
After round 4 the verifier cannot decide on its own: skipped: existing tests in `tests/acceptance/test_golden_path.py` were also skipped in a base report, and the file adds or changes no skip the harness reads (3 tests)

The skipped tests (3):
- tests.acceptance.test_golden_path::test_ws10_list_versions_end_to_end
- tests.acceptance.test_golden_path::test_ws8_golden_path_agent_to_upstream
- tests.acceptance.test_golden_path::test_ws9_vault_grpc_end_to_end

What was compared: these tests were also skipped in a base report (step 1 base run), the file adds or changes no skip construct the harness reads (decorators, marks and skip calls in the file) and nothing inside the file that decides whether an unchanged skip skips (a flag, a condition, a helper, a fixture or an import it reads), the unit changed the file only in places that cannot change why a test skips (comment and blank lines, the body of a test beyond what skips it, a whole new import of a name the file did not use), and no support, runner, setup or dependency file changed. What is not told apart: production code the unit changed, a module the file imports that the unit did not change (an added import is allowed only from the standard library), run-time or import-time state that another test sets (its body, decorator or default values), a changed sibling test module the file imports, and dynamic forms and plugins that read test names (`exec`, `getattr`, `importlib`, `globals()`, a plugin such as test dependencies): the tests were skipped at the base too, but the reason may have changed. Often the cause is an environment the gate does not have (a stack, a service). `accept` means you ran them where they can run, or know they pass there; it holds for this content of the file only. `reject: <reason>` ends the round, because a fix unit cannot change test files: no fix unit is made and the unit is escalated with skipped_tests_rejected; then change the file in your own commit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
