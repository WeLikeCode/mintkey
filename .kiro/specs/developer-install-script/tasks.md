# Implementation Plan: Developer Install Script

## Overview

A single Bash 4.0+ script (`install.sh`) at the repo root that automates the full "clone to running stack" workflow. Implementation follows the phase-based architecture: `parse_args` → `clone` → `prerequisites` → `configure` → `build` → `migrate` → `seed` → `start` → `verify` → `summary`. Testing uses bats-core for unit tests, hypothesis (Python) for property-based tests, and shellcheck for static analysis.

## Tasks

- [x] 1. Create script skeleton and utility functions
  - [x] 1.1 Create `install.sh` with shebang, Bash 4.0 version guard, `set -euo pipefail`, and `main()` entry point
    - Define the phase pipeline calling each phase function in order
    - Implement `parse_args()` for `--non-interactive`, `--clean`, `--help` flags
    - Implement signal trapping for SIGINT/SIGTERM with cleanup
    - _Requirements: 3.7, 8.1, 8.4, 10.1, 10.6_
  - [x] 1.2 Implement logging and output utility functions
    - `log()` — timestamped messages to log file + stdout/stderr
    - `die()` — error to stderr with remediation hint, exit non-zero
    - `detect_os()` — returns `ubuntu`, `debian`, `fedora`, or `macos`
    - `generate_token()` — produces 32-byte hex via `openssl rand -hex 32`
    - `prompt()` — reads user input with validation, retry (max 3), and timeout
    - Color support: green/red/yellow when TTY and `NO_COLOR` unset; plain otherwise
    - Create timestamped log file `install-YYYYMMDD-HHMMSS.log`; warn and continue if creation fails
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 10.3_

- [x] 2. Implement clone and prerequisite phases
  - [x] 2.1 Implement `phase_clone()`
    - Skip if `.git` directory exists in target directory
    - Clone from `https://github.com/WeLikeCode/mintkey.git` with 120-second timeout
    - Check git availability before attempting clone
    - Display error with failure reason on network/URL errors, exit non-zero
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 2.2 Implement `phase_prerequisites()`
    - Validate `docker` on PATH with major version ≥ 24
    - Validate `docker compose` v2 plugin syntax (exits 0)
    - Validate `git` on PATH (exits 0)
    - Validate Docker daemon running via `docker info` with 10-second timeout
    - Check ALL prerequisites before exiting (no short-circuit)
    - Display each failure with tool name, required condition, and platform-appropriate install command
    - Exit with status 1 if any check fails
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 10.3, 10.4_
  - [x] 2.3 Write property test for Docker version comparison (Property 5)
    - **Property 5: Docker version comparison correctness**
    - Generate version strings `Docker version X.Y.Z, build <hash>` with major 1–30; verify accept iff major ≥ 24
    - **Validates: Requirements 2.1**

- [x] 3. Implement configuration phase
  - [x] 3.1 Implement `phase_configure()` — interactive prompts
    - Prompt for public-facing domain/IP (non-empty, no whitespace, no trailing slash)
    - Prompt for admin email (matches `^[^@]+@[^@]+\.[^@]+$`)
    - Prompt for tenant name (matches `^t_[a-z0-9_]{1,61}$`, default `t_default`)
    - Retry up to 3 times on invalid input, then abort
    - _Requirements: 3.1, 3.2, 3.3, 3.5_
  - [x] 3.2 Implement `.env` file generation from `.env.example` template
    - Replace all `REPLACE_WITH_*` placeholders with `openssl rand -hex 32` output
    - Substitute domain-derived URLs for all 7 services (MCP, proxy, admin-api, admin-ui, Keycloak, Grafana, Jaeger)
    - Write admin email into appropriate variable
    - Use defaults from `.env.example` for optional prompts left blank
    - Prompt for confirmation before overwriting existing `.env` (30-second timeout, default abort)
    - _Requirements: 3.4, 3.6, 3.8_
  - [x] 3.3 Implement `--non-interactive` mode for configuration
    - Use default values for all optional prompts
    - Require `MINTKEY_DOMAIN` and `MINTKEY_ADMIN_EMAIL` from env vars or CLI args
    - Abort with error listing missing required values if any absent
    - _Requirements: 3.7_
  - [x] 3.4 Write property test for email validation (Property 1)
    - **Property 1: Email validation correctness**
    - Generate random strings (ASCII + unicode); verify accept/reject matches regex `^[^@]+@[^@]+\.[^@]+$`
    - **Validates: Requirements 3.2**
  - [x] 3.5 Write property test for tenant name validation (Property 2)
    - **Property 2: Tenant name validation correctness**
    - Generate random strings; verify accept/reject matches regex `^t_[a-z0-9_]{1,61}$`
    - **Validates: Requirements 3.3**
  - [x] 3.6 Write property test for domain/IP validation (Property 4)
    - **Property 4: Domain/IP validation correctness**
    - Generate random strings (with/without whitespace, trailing slashes); verify accept/reject matches rules
    - **Validates: Requirements 3.1**
  - [x] 3.7 Write property test for template substitution completeness (Property 3)
    - **Property 3: Template substitution completeness**
    - Generate `.env.example` templates with 1–10 `REPLACE_WITH_*` placeholders; verify output has zero placeholders and all tokens are 64 hex chars
    - **Validates: Requirements 3.4**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement build, migrate, and seed phases
  - [x] 5.1 Implement `phase_build()`
    - Set `DOCKER_BUILDKIT=1` before invoking build
    - Execute `docker compose build`
    - On failure: display failing service name and last 50 lines of build error, exit non-zero
    - Verify all built services have non-empty image IDs via `docker compose images`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 5.2 Implement `phase_migrate()` and `phase_seed()`
    - Migration: ensure Liquibase one-shot job runs to completion via Docker Compose dependency graph
    - On migration failure: display last 50 lines of Liquibase logs, exit non-zero
    - Seed: ensure seed-job runs after Liquibase exits 0 and Keycloak `/health/ready` returns 200
    - Seed timeout: 60 seconds
    - On seed failure: display seed-job stdout+stderr, exit non-zero
    - Both are idempotent on re-run (conflict-safe inserts)
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 6. Implement start, verify, and summary phases
  - [x] 6.1 Implement `phase_start()` with idempotent re-run support
    - Stop existing containers via `docker compose down` (30-second timeout) if running
    - Handle `--clean` flag: prompt for volume removal confirmation (skip prompt if `--non-interactive`)
    - Preserve Docker volumes unless `--clean` confirmed
    - Execute `docker compose up -d` for all 15 long-running services
    - On compose failure: display error output, exit non-zero
    - _Requirements: 7.1, 7.2, 8.1, 8.2, 8.3, 8.4_
  - [x] 6.2 Implement `phase_verify()` — health polling
    - Poll Docker healthcheck status for all 15 services every 2 seconds
    - Configurable timeout via `MINTKEY_HEALTH_TIMEOUT_SECONDS` (default 120)
    - On timeout: display unhealthy service names + last 50 lines of each unhealthy service's logs, exit non-zero
    - _Requirements: 7.3, 7.4, 8.5_
  - [x] 6.3 Implement `print_summary()` — service URL table
    - Display table with service name and URL: Admin UI :8081, Admin API :8080, MCP Server :8082, Kong proxy :8000, Keycloak :8443, Grafana :3003, Jaeger :16686
    - Display bootstrap admin password file path (`./data/bootstrap-secrets/admin_password`)
    - Construct URLs as `http://<domain>:<port>` using configured domain
    - _Requirements: 7.5_
  - [x] 6.4 Write property test for summary table URL construction (Property 6)
    - **Property 6: Summary table URL construction**
    - Generate valid domains/IPs; verify output contains all 7 service URLs with correct ports
    - **Validates: Requirements 3.1, 7.5**
  - [x] 6.5 Write property test for non-interactive missing value detection (Property 7)
    - **Property 7: Non-interactive missing value detection**
    - Generate random subsets of required env vars to unset; verify error lists exactly the missing ones
    - **Validates: Requirements 3.7**

- [x] 7. Implement `--help` output and platform compatibility
  - [x] 7.1 Implement `--help` flag output
    - Display usage, options, environment variables, and Windows limitation note
    - Match CLI interface defined in design document
    - _Requirements: 10.7_
  - [x] 7.2 Implement platform detection and install suggestions
    - Detect host OS via `/etc/os-release` and `uname`
    - Present `apt-get` for Debian/Ubuntu, `dnf` for Fedora/RHEL, `brew` for macOS
    - Warn on untested OS (not Ubuntu 22.04+, Debian 12+, Fedora 38+, macOS 13+) and prompt to continue
    - _Requirements: 10.2, 10.3, 10.4, 10.5_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Testing and static analysis
  - [x] 9.1 Set up bats-core test framework and write unit tests
    - Install bats-core test dependencies
    - Write unit tests for: `validate_email`, `validate_tenant_name`, `validate_domain`, `parse_docker_version`, `detect_os`, `generate_env_file`, `format_error`, `should_use_color`, `get_install_command`, `check_prerequisites` (aggregation)
    - _Requirements: 2.1, 3.1, 3.2, 3.3, 9.4, 10.2, 10.3_
  - [x] 9.2 Set up hypothesis PBT framework with Python wrapper for Bash functions
    - Create Python test file that invokes Bash validation functions via subprocess
    - Implement all 7 property-based tests (Properties 1–7) with minimum 100 iterations each
    - Tag format: `# Feature: developer-install-script, Property N: <property_text>`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7, 7.5_
  - [x] 9.3 Run shellcheck and Bash syntax validation
    - Run `shellcheck install.sh` and fix all warnings
    - Run `bash -n install.sh` on Bash 4.0 compatibility
    - Verify no Bash 4.1+ features used (no `${var@Q}`, `wait -n`, `mapfile -d`)
    - _Requirements: 10.1, 10.6_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests (bats-core) validate specific examples and edge cases
- Property tests use hypothesis (Python) invoking Bash functions via subprocess since Bash lacks a native PBT library
- The script must not use Bash features introduced after version 4.0

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "2.2", "3.1"] },
    { "id": 3, "tasks": ["2.3", "3.2", "3.3"] },
    { "id": 4, "tasks": ["3.4", "3.5", "3.6", "3.7"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2"] },
    { "id": 7, "tasks": ["6.1"] },
    { "id": 8, "tasks": ["6.2", "6.3"] },
    { "id": 9, "tasks": ["6.4", "6.5", "7.1", "7.2"] },
    { "id": 10, "tasks": ["9.1", "9.2", "9.3"] }
  ]
}
```
