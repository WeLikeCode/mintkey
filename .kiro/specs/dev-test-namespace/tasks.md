# Implementation Plan: Dev-Test Namespace

## Overview

Implement a parallel, isolated Mintkey development/testing environment using Docker Compose's multi-file override mechanism. The test namespace (`mintkey-test`) runs simultaneously alongside the primary instance on the same machine, sharing built images but isolating ports (+100 offset), volumes, networks, and data. Includes CI validation, Makefile lifecycle targets, documentation, and test-targeting support.

## Tasks

- [x] 1. Create core infrastructure files
  - [x] 1.1 Create `docker-compose.test.yml` override file
    - Remap all 16 host-exposed ports by +100 (container ports unchanged)
    - Pin 10 locally-built services with `image: mintkey-<service>` directives
    - Add `name: mintkey-test` to the file header for self-documentation
    - Add container port comments for non-obvious mappings (cAdvisor 8080→8188, Grafana 3000→3103)
    - Do NOT include `ports: []` for seed-job (unnecessary override)
    - Bind kong admin to `127.0.0.1:8101:8001` (localhost-only, matching primary)
    - _Requirements: 2.1, 2.2, 2.3, 6.1, 6.2, 9.1_

  - [x] 1.2 Create `.env.test` environment file
    - Define all 7 `MINTKEY_*_PUBLIC_URL` variables with offset port values
    - Add header comment explaining purpose and loading mechanism
    - _Requirements: 7.2, 8.1, 8.2_

  - [x] 1.3 Update `.gitignore` to explicitly track `.env.test`
    - Add a comment noting `.env.test` is intentionally committed (no secrets)
    - Ensure `.env.test` is NOT matched by existing `.env` ignore patterns
    - _Requirements: 9.3_

- [x] 2. Implement Makefile targets
  - [x] 2.1 Add a `COMPOSE_TEST` variable to reduce command repetition
    - Define `COMPOSE_TEST := docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test --project-name mintkey-test`
    - Use this variable in all test namespace targets
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 2.2 Add `dev-test` target
    - Start the test namespace in detached mode using `$(COMPOSE_TEST) up -d`
    - Print access URLs (admin-api :8180, admin-ui :8181, Keycloak :8543, Grafana :3103)
    - Print bootstrap admin password from `mintkey-test_bootstrap_secrets` volume
    - _Requirements: 5.1, 5.4, 5.5, 5.6_

  - [x] 2.3 Add `dev-test-down` target
    - Stop and remove test namespace containers without removing volumes
    - Use `$(COMPOSE_TEST) down`
    - _Requirements: 5.2_

  - [x] 2.4 Add `dev-test-logs` target
    - Tail logs in follow mode from all test namespace containers
    - Use `$(COMPOSE_TEST) logs -f`
    - _Requirements: 5.3_

  - [x] 2.5 Add `dev-test-reset` target for full volume teardown
    - Use `$(COMPOSE_TEST) down --volumes`
    - Print warning that all test namespace data will be destroyed
    - _Requirements: 3.1 (adversarial review: MAJOR fix)_

  - [x] 2.6 Add `smoke-test-ns` target for running smoke tests against test namespace
    - Set env vars pointing to offset ports (admin-api :8180, admin-ui :8181, etc.)
    - Run existing smoke/integration test suite against test namespace endpoints
    - Verify test namespace is running before executing
    - _Requirements: 10.1, 10.2, 10.3, 10.4 (adversarial review: CRITICAL fix)_

  - [x] 2.7 Update Makefile `help` target with new dev-test targets
    - Add entries for `dev-test`, `dev-test-down`, `dev-test-logs`, `dev-test-reset`, `smoke-test-ns`
    - _Requirements: 12.1_

- [x] 3. Checkpoint — Validate compose config merges correctly
  - Ensure `docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test config` succeeds without errors, ask the user if questions arise.

- [x] 4. Create CI validation script for port-drift detection
  - [x] 4.1 Create `tools/validate-test-override.py` script
    - Parse both `docker-compose.yml` and `docker-compose.test.yml` as YAML
    - Assert every port-mapped service in primary has a corresponding override entry
    - Verify each test port equals primary port + 100
    - Verify `.env.test` contains all 7 required `MINTKEY_*_PUBLIC_URL` variables with correct offset values
    - Verify all 10 locally-built services have `image:` pins in the override
    - Exit non-zero with descriptive error on any drift
    - _Requirements: 2.1, 2.2, 6.2 (adversarial review: CRITICAL fix)_

  - [x] 4.2 Write unit tests for the validation script
    - Test detection of missing port override
    - Test detection of incorrect port arithmetic
    - Test detection of missing image pin
    - Test detection of missing env var
    - _Requirements: 2.1, 2.2_

- [x] 5. Create documentation
  - [x] 5.1 Create `docs/DEV-TEST.md`
    - Explain the dev-test namespace concept (parallel namespace via Docker Compose override)
    - Document the port offset rule (primary + 100)
    - Include complete port mapping table (16 services × primary port / test port / container port columns)
    - Document usage instructions referencing Makefile targets
    - Document that test namespace works standalone (primary doesn't need to be running)
    - Document memory requirements (~8 GB for dual stacks, 12 GB recommended)
    - Document shell env var precedence risk in troubleshooting section
    - Document why `MINTKEY_KEYCLOAK_INTERNAL_URL` doesn't need overriding (Docker per-network DNS)
    - Include troubleshooting: port conflicts, verifying primary unaffected, env var precedence
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5 (adversarial review: MAJOR fixes)_

  - [x] 5.2 Update `PORTS.md` with test namespace ports
    - Add a "Test Namespace" section or column showing offset ports
    - Reference `docs/DEV-TEST.md` for full documentation
    - _Requirements: 12.2 (adversarial review: MINOR fix)_

- [x] 6. Checkpoint — Ensure all files are syntactically valid
  - Run `docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test config > /dev/null` and `python3 tools/validate-test-override.py`. Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integration wiring and final validation
  - [x] 7.1 Add validation script to CI workflow
    - Add a step in `.github/workflows/ci.yml` that runs `python3 tools/validate-test-override.py`
    - Ensure it runs on PRs that touch `docker-compose*.yml`, `.env.test`, or the validation script itself
    - _Requirements: 2.1, 9.1 (adversarial review: CRITICAL fix)_

  - [x] 7.2 Write integration test for namespace isolation
    - Verify merged compose config is valid YAML
    - Verify no port overlap between primary and test namespace
    - Verify all 7 named volumes get `mintkey-test_` prefix in merged config
    - Verify network is `mintkey-test_mintkey` in merged config
    - _Requirements: 1.1, 1.3, 3.1, 4.1_

- [x] 8. Final checkpoint — Ensure all tests pass
  - Run `python3 tools/validate-test-override.py` and verify CI config is valid. Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- No property-based tests — this feature is infrastructure configuration (YAML, Makefile, shell) with no pure functions or business logic suitable for PBT
- The CI validation script (task 4.1) is the primary automated correctness check — it detects port-drift when services are added to the primary compose file
- The `smoke-test-ns` target (task 2.6) enables running existing test suites against the offset ports without duplicating test code

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": 3, "tasks": ["4.1", "5.1", "5.2"] },
    { "id": 4, "tasks": ["4.2", "7.1", "7.2"] }
  ]
}
```
