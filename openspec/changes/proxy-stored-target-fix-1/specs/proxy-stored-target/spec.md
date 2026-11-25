# Spec Delta

## Purpose
How the egress proxy chooses where a request goes (only the target stored with the credential), how stored targets of older credentials are filled in, and how every proxied response is cleaned of credential echoes before it reaches the caller.

## ADDED Requirements

### Requirement: task 4.1: live-stack acceptance tests not updated — finding F-3e53e4bd
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: task 4.1: live-stack acceptance tests not updated
- **WHEN** the live-stack acceptance tests test_e2e_smoke.py (step 10), test_golden_path.py, test_data_plane_smoke.py and test_classical_key.py read the credential back from the mock backend's received_key
- **THEN** each of them asserts that received_key equals "[REDACTED]" rather than the registered secret, with a comment explaining that the proxy redacts exactly the value it injected, and no acceptance test still asserts received_key equals the registered secret.
