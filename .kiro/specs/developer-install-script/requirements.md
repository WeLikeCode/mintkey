# Requirements Document

## Introduction

A shell-based developer install script that automates the full "clone to running stack" workflow for Mintkey. The script targets developers and self-hosters deploying from source on a VM or VPS. It clones the repository, validates prerequisites, builds all containers locally, runs seeding (Keycloak realm, bootstrap admin, DB migrations), and starts the full solution via Docker Compose. This is the "from source" developer variant — not the future production installer that pulls pre-built images from ghcr.io.

## Glossary

- **Install_Script**: The shell script (`install.sh`) that orchestrates the full developer setup workflow from clone through running stack.
- **Host_Machine**: The Linux VM, VPS, or macOS workstation where the developer runs the Install_Script.
- **Seed_Job**: The one-shot Docker container (`seed-job` service) that bootstraps the default tenant, platform admin, Keycloak realm, and cryptographic keypairs.
- **Prerequisite_Check**: The validation phase that confirms Docker, Docker Compose, and Git are installed and meet minimum version requirements.
- **Configuration_Prompt**: An interactive prompt that collects deployment-specific inputs from the user (domain, admin credentials, tenant info).
- **Stack**: The full set of 15 long-running services plus 2 one-shot jobs defined in `docker-compose.yml`.

## Requirements

### Requirement 1: Repository Cloning

**User Story:** As a developer, I want the script to clone the Mintkey repository from GitHub, so that I have the full source code ready for a local build.

#### Acceptance Criteria

1. WHEN the Install_Script is invoked and no `.git` directory exists within the target directory, THE Install_Script SHALL clone the Mintkey repository from `https://github.com/WeLikeCode/mintkey.git` into the current working directory within 120 seconds.
2. WHEN the Install_Script is invoked and a `.git` directory already exists within the target directory, THE Install_Script SHALL skip the clone step and proceed with the existing source.
3. IF the clone operation fails due to network error or invalid URL, THEN THE Install_Script SHALL display an error message indicating the failure reason and exit with a non-zero status code.
4. IF `git` is not installed or not found on the system PATH, THEN THE Install_Script SHALL display an error message indicating that git is required and exit with a non-zero status code.

### Requirement 2: Prerequisite Validation

**User Story:** As a developer, I want the script to verify that Docker, Docker Compose, and Git are installed, so that I know my environment is ready before the build begins.

#### Acceptance Criteria

1. THE Install_Script SHALL verify that `docker` is available on the PATH and that the major version reported by `docker --version` is 24 or higher.
2. THE Install_Script SHALL verify that `docker compose` (v2 plugin syntax) is available by invoking `docker compose version` and confirming it exits with status 0.
3. THE Install_Script SHALL verify that `git` is available on the PATH by invoking `git --version` and confirming it exits with status 0.
4. THE Install_Script SHALL verify that the Docker daemon is running by executing `docker info` with a timeout of 10 seconds and confirming it exits with status 0.
5. IF any prerequisite check fails, THEN THE Install_Script SHALL check all remaining prerequisites before exiting, display each failing tool's name, the required condition (e.g., "Docker >= 24", "Docker daemon running"), and a platform-appropriate suggested install or fix command, then exit with status code 1.
6. IF `docker info` does not complete within 10 seconds, THEN THE Install_Script SHALL treat the Docker daemon as unavailable and report it as a failed prerequisite.

### Requirement 3: Interactive Configuration

**User Story:** As a self-hoster, I want the script to ask me for deployment-specific configuration (domain, admin credentials, tenant info), so that the stack is configured for my environment without manual file editing.

#### Acceptance Criteria

1. WHEN the Install_Script reaches the configuration phase, THE Configuration_Prompt SHALL ask the user for the public-facing domain or IP address used to construct service URLs (MCP, proxy, admin-api, admin-ui, Keycloak, Grafana, Jaeger) for the stack.
2. WHEN the Install_Script reaches the configuration phase, THE Configuration_Prompt SHALL ask the user for the initial platform admin email address and accept only values matching a valid email format (local-part@domain with at least one dot in the domain).
3. WHEN the Install_Script reaches the configuration phase, THE Configuration_Prompt SHALL ask the user for the initial tenant name (defaulting to `t_default` if left blank) and accept only lowercase alphanumeric characters and underscores, between 3 and 64 characters, prefixed with `t_`.
4. THE Install_Script SHALL write collected configuration values into a `.env` file in the repository root, using `.env.example` as the template, generating random 32-byte hex tokens for any `REPLACE_WITH_*` placeholder values.
5. IF the user provides a value that fails validation for any prompt, THEN THE Configuration_Prompt SHALL display an error message indicating the validation rule violated and re-prompt the user for the same field, up to a maximum of 3 consecutive invalid attempts before aborting with a non-zero exit code.
6. WHEN the user provides no value for an optional prompt, THE Install_Script SHALL use the documented default value from `.env.example`.
7. WHEN the Install_Script is invoked with a `--non-interactive` flag, THE Install_Script SHALL use default values for all optional prompts and require that all required values (domain/IP, admin email) are supplied via environment variables or command-line arguments, aborting with a non-zero exit code and an error message listing missing values if any required value is absent.
8. IF a `.env` file already exists in the repository root, THEN THE Install_Script SHALL prompt the user for confirmation before overwriting, defaulting to abort if no confirmation is given within 30 seconds.

### Requirement 4: Container Build from Source

**User Story:** As a developer, I want the script to build all Docker images locally from source, so that I can run the full stack without depending on a container registry.

#### Acceptance Criteria

1. WHEN prerequisites pass and configuration is complete, THE Install_Script SHALL execute `docker compose build` to build all images defined in `docker-compose.yml` from local source.
2. IF a container build fails, THEN THE Install_Script SHALL display the failing service name and the last 50 lines of the build error output, then exit with a non-zero status code.
3. THE Install_Script SHALL set `DOCKER_BUILDKIT=1` before invoking the build command to enable the Docker BuildKit backend.
4. IF the Docker BuildKit backend is not available (Docker version < 18.09), THEN THE Install_Script SHALL display an error message indicating that BuildKit is required and the minimum Docker version, then exit with a non-zero status code.
5. WHEN the build completes without error, THE Install_Script SHALL verify that every service defined with a `build:` context in `docker-compose.yml` has a corresponding local image by running `docker compose images` and confirming a non-empty image ID exists for each built service.

### Requirement 5: Database Migration

**User Story:** As a developer, I want the script to run Liquibase migrations automatically, so that the database schema is ready without manual intervention.

#### Acceptance Criteria

1. WHEN the Stack is starting, THE Install_Script SHALL ensure the Liquibase one-shot job (`liquibase` service) runs to completion before services that depend on the schema start.
2. IF the Liquibase migration fails (exits with non-zero status), THEN THE Install_Script SHALL display the last 50 lines of the Liquibase container logs and exit with a non-zero status code.
3. WHEN the Install_Script is re-run against an already-migrated database, THE Liquibase service SHALL detect no pending changesets and complete successfully with exit code 0 (idempotent).

### Requirement 6: Seeding (Keycloak Realm, Bootstrap Admin, Keypairs)

**User Story:** As a developer, I want the script to run all seeding steps automatically, so that the stack is usable immediately after startup.

#### Acceptance Criteria

1. WHEN the database migration completes (Liquibase exits 0) and Keycloak responds HTTP 200 on its `/health/ready` endpoint, THE Install_Script SHALL ensure the Seed_Job runs to completion within 60 seconds.
2. THE Seed_Job SHALL create, in order: (a) the default tenant with slug `t_default` and `isolation_mode='row'`, (b) the platform admin operator with `role=Admin` and Argon2id-hashed random password, (c) the Keycloak `mintkey` realm with the `mintkey-admin` confidential OIDC client registration, (d) four service-identity boot secrets (`svcid_admin_api`, `svcid_mcp`, `svcid_broker`, `svcid_proxy`) hashed into `service_identities`, (e) an Ed25519 keypair for AdminJS (public key stored in Vault Adapter, private key written to `./data/bootstrap-secrets/admin_ui_private.pem` with mode `0400`), and (f) an Ed25519 keypair for the Credential Broker (private key stored in Vault Adapter, public key published via JWKS).
3. WHEN the Seed_Job completes, THE Seed_Job SHALL write all generated secrets (admin password, four service-identity tokens, AdminJS private key path) to `./data/bootstrap-secrets/` with file mode `0400`, and print the bootstrap admin password once to stdout.
4. WHEN the Install_Script is re-run against an already-seeded database, THE Seed_Job SHALL detect existing seed data via conflict-safe inserts (ON CONFLICT DO NOTHING or existence checks) and exit 0 without modifying existing records.
5. IF the Seed_Job fails (exits non-zero or exceeds the 60-second deadline), THEN THE Install_Script SHALL display the Seed_Job's combined stdout and stderr output and exit with a non-zero status code.

### Requirement 7: Stack Startup and Health Verification

**User Story:** As a developer, I want the script to start the full stack and confirm all services are healthy, so that I know the deployment succeeded.

#### Acceptance Criteria

1. WHEN builds and seeding are complete, THE Install_Script SHALL execute `docker compose up -d` to start all 15 long-running services (`postgres`, `keycloak`, `admin-api`, `admin-ui`, `mcp-server`, `broker`, `vault-adapter`, `kong`, `proxy-plugin`, `kong-syncer`, `demo-backend`, `otel-collector`, `jaeger`, `prometheus`, `grafana`).
2. IF the `docker compose up -d` command exits with a non-zero status, THEN THE Install_Script SHALL display the compose error output and exit with a non-zero status code without proceeding to health verification.
3. THE Install_Script SHALL poll Docker healthcheck status for all 15 services every 2 seconds, with a configurable timeout (environment variable `MINTKEY_HEALTH_TIMEOUT_SECONDS`) defaulting to 120 seconds.
4. IF any service fails to report Docker healthcheck status `healthy` within the timeout, THEN THE Install_Script SHALL display the names of all unhealthy services and the last 50 lines of each unhealthy service's container logs, then exit with a non-zero status code.
5. WHEN all services report Docker healthcheck status `healthy`, THE Install_Script SHALL display a summary table showing each service name and its URL (`Admin UI` at port 8081, `Admin API` at port 8080, `MCP Server` at port 8082, `Kong proxy` at port 8000, `Keycloak` at port 8443, `Grafana` at port 3003, `Jaeger` at port 16686) and the bootstrap admin password file path (`./data/bootstrap-secrets/admin_password`).

### Requirement 8: Idempotent Re-run

**User Story:** As a developer, I want to safely re-run the install script after a failure or configuration change, so that I can recover without starting from scratch.

#### Acceptance Criteria

1. WHEN the Install_Script is invoked against an existing clone with running containers, THE Install_Script SHALL stop existing containers via `docker compose down` (with a timeout of 30 seconds per container) before rebuilding.
2. WHEN the Install_Script is re-run, THE Install_Script SHALL preserve existing Docker volumes (database data, vault data, bootstrap secrets) unless the user passes a `--clean` flag.
3. WHEN the user passes a `--clean` flag, THE Install_Script SHALL prompt the user for confirmation before removing all Docker Compose project volumes (those prefixed with the Compose project name). IF the user confirms, THEN THE Install_Script SHALL remove the volumes and proceed with a fresh install. IF the user declines, THEN THE Install_Script SHALL exit with a non-zero status code.
4. WHEN the user passes both `--clean` and `--non-interactive` flags, THE Install_Script SHALL skip the confirmation prompt and proceed with volume removal immediately.
5. WHEN the Install_Script completes a re-run, THE Install_Script SHALL produce the same observable end state as a first-time run: all services report healthy via their Docker healthchecks within the configured timeout, `GET /v1/ready` on `admin-api` returns `200 OK`, and the summary table of service URLs is displayed.

### Requirement 9: Error Handling and User Feedback

**User Story:** As a developer, I want clear error messages and progress indicators, so that I can diagnose failures without reading Docker logs manually.

#### Acceptance Criteria

1. THE Install_Script SHALL display a progress indicator for each major phase (clone, prerequisites, configure, build, migrate, seed, start, verify) consisting of the phase name and a status marker (a spinner or ellipsis while in progress, a checkmark on success, an X on failure).
2. IF any phase fails, THEN THE Install_Script SHALL print to stderr the phase name, a human-readable error description, and a suggested remediation step, then exit with a non-zero status code.
3. THE Install_Script SHALL log all command stdout and stderr output to a timestamped log file in the repository root (`install-YYYYMMDD-HHMMSS.log`). IF the log file cannot be created due to permissions or disk space, THEN THE Install_Script SHALL print a warning to stderr and continue without file logging.
4. THE Install_Script SHALL use colored terminal output (green for success, red for errors, yellow for warnings) when stdout is connected to a TTY and the `NO_COLOR` environment variable is not set. WHEN stdout is not a TTY or `NO_COLOR` is set, THE Install_Script SHALL emit plain uncolored text.
5. THE Install_Script SHALL write all error and warning messages to stderr and all progress and success messages to stdout.

### Requirement 10: Platform Compatibility

**User Story:** As a developer, I want the script to work on common Linux distributions and macOS, so that I can use it regardless of my development machine.

#### Acceptance Criteria

1. THE Install_Script SHALL execute without syntax errors and exit with code `0` on Bash 4.0 or higher.
2. THE Install_Script SHALL complete all prerequisite checks and produce correct install suggestions on Ubuntu 22.04+, Debian 12+, macOS 13+ (with Docker Desktop or Colima), and Fedora 38+.
3. WHEN the Install_Script starts, THE Install_Script SHALL detect the host operating system and present prerequisite install commands using `apt-get` for Debian/Ubuntu, `dnf` for Fedora/RHEL, and `brew` for macOS.
4. WHEN the Install_Script detects a missing prerequisite (Docker, Docker Compose, or Git), THE Install_Script SHALL print the package name and the platform-appropriate install command to stdout, and exit with a non-zero exit code unless the user confirms to proceed.
5. IF the host operating system is not Ubuntu 22.04+, Debian 12+, Fedora 38+, or macOS 13+, THEN THE Install_Script SHALL print a warning message to stderr identifying the detected OS and stating it is untested, then prompt the user for confirmation before continuing execution.
6. THE Install_Script SHALL not use Bash features introduced after version 4.0 (e.g., `${var@Q}` quoting from 4.4, `wait -n` from 4.3) to ensure compatibility with the minimum supported version.
7. THE Install_Script SHALL not support Windows natively in this version. Windows support (via WSL2 or native PowerShell) is deferred to a future release and SHALL be documented as a known limitation in the script's `--help` output.
