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
