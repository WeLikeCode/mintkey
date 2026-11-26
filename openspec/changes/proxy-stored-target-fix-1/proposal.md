# Proposal: fix 1 for proxy-stored-target

## Why
The verifier found problems in `proxy-stored-target` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-3e53e4bd (major): task 4.1: live-stack acceptance tests not updated: Decided by delegate in Q-001: The finding is correct. Task 4.1 of tasks.md requires that in test_e2e_smoke.py, test_golden_path.py, test_data_plane_smoke.py and test_classical_key.py every assertion that received_key equals the registered secret becomes an assertion that it equals the redaction marker, with a comment saying why. None of the four files was changed: test_data_plane_smoke.py and test_golden_path.py still assert received_key equals secret_value, test_e2e_smoke.py still asserts it equals the demo secret literal, test_classical_key.py still asserts it equals REAL_CRED, and no file under tests/acceptance contains the text (REDACTED). Since main.go now builds every flow through newUpstreamProxy, which calls scrubber.ScrubWith with the injected credential, the proxy replaces the echoed value and these live-stack tests would fail against the compose stack as written. WHEN the live-stack acceptance tests test_e2e_smoke.py (step 10), test_golden_path.py, test_data_plane_smoke.py and test_classical_key.py read the credential back from the mock backend's received_key THEN each of them asserts that received_key equals "(REDACTED)" rather than the registered secret, with a comment explaining that the proxy redacts exactly the value it injected, and no acceptance test still asserts received_key equals the registered secret.. Task 4.1 requires test_e2e_smoke.py, test_golden_path.py, test_data_plane_smo...

## Impact
The code and the tests of `proxy-stored-target`.
