# Requirements Document

## Introduction

This feature delivers a parallel, isolated Mintkey development/testing environment ("dev-test namespace") that can run simultaneously alongside the primary Mintkey instance on the same machine. The goal is to allow developers to run tests, experiment, and develop without risking corruption of the primary ("live demo" or evaluation) environment's data, ports, or Docker resources.

## Glossary

- **Primary_Instance**: The default Mintkey Docker Compose stack started with `make dev`, using project name `mintkey`, default ports, and default named volumes.
- **Test_Namespace**: A parallel Mintkey Docker Compose stack using project name `mintkey-test`, offset host ports, and separate named volumes and Docker network.
- **Port_Offset**: A fixed integer (100) added to each Primary_Instance host port to derive the corresponding Test_Namespace host port.
- **Compose_Override**: A `docker-compose.test.yml` file that remaps host ports and adjusts environment variables for the Test_Namespace without modifying the primary `docker-compose.yml`.
- **Env_Test_File**: A `.env.test` file containing adjusted public URL environment variables pointing to the offset ports for the Test_Namespace.
- **Seed_Job**: The one-shot container that bootstraps the Keycloak realm, admin credentials, and OIDC redirect URIs during stack initialization.

## Requirements

### Requirement 1: Separate Docker Compose Project Name

**User Story:** As a developer, I want the test environment to use a distinct Docker Compose project name, so that its containers, networks, and volumes do not collide with the primary instance.

#### Acceptance Criteria

1. WHEN the Test_Namespace is started, THE Compose_Override SHALL use the project name `mintkey-test`.
2. WHILE both Primary_Instance and Test_Namespace are running, THE Test_Namespace SHALL have container names prefixed with `mintkey-test` that do not conflict with `mintkey`-prefixed containers.
3. THE Test_Namespace SHALL use Docker named volumes automatically prefixed with the `mintkey-test` project name, isolating all persistent data from the Primary_Instance.

### Requirement 2: Separate Port Range

**User Story:** As a developer, I want all Test_Namespace host ports to be offset by a consistent value from the primary ports, so that both environments can bind to the host simultaneously without conflicts.

#### Acceptance Criteria

1. THE Compose_Override SHALL remap every host-exposed port by adding a Port_Offset of 100 to the Primary_Instance host port, while container-internal ports remain unchanged.
2. WHEN the Test_Namespace is started, THE following port mappings SHALL apply:
   - Keycloak: 8543 (primary 8443 + 100)
   - admin-api: 8180 (primary 8080 + 100)
   - admin-ui: 8181 (primary 8081 + 100)
   - mcp-server: 8182 (primary 8082 + 100)
   - broker: 8183 (primary 8083 + 100)
   - vault-adapter gRPC: 8184 (primary 8084 + 100)
   - vault-adapter HTTP: 8187 (primary 8087 + 100)
   - kong-syncer: 8185 (primary 8085 + 100)
   - kong proxy: 8100 (primary 8000 + 100)
   - kong admin: 8101 (primary 8001 + 100)
   - proxy-plugin: 8186 (primary 8086 + 100)
   - mock-backend: 9099 (primary 8999 + 100)
   - otel-collector: 4417 (primary 4317 + 100)
   - jaeger-auth: 16786 (primary 16686 + 100)
   - grafana: 3103 (primary 3003 + 100)
   - cAdvisor: 8188 (primary 8088 + 100)
3. WHILE both environments are running, THE Test_Namespace host ports SHALL not share any port number with any Primary_Instance host port on the same host interface.
4. IF a Test_Namespace port cannot bind because it is already in use, THEN THE Compose_Override SHALL fail with an error message indicating which port is occupied and which service requires it.

### Requirement 3: Separate Named Volumes

**User Story:** As a developer, I want the test environment to use isolated Docker volumes, so that test data does not corrupt or interfere with primary instance data.

#### Acceptance Criteria

1. THE Test_Namespace SHALL use volumes prefixed with `mintkey-test_` (auto-prefixed by Docker Compose project name) for all seven named volumes: `postgres_data`, `vault_data`, `vault_kek`, `bootstrap_secrets`, `grafana_data`, `broker_wal`, and `proxy_wal`.
2. WHEN the Test_Namespace is torn down via `docker compose --project-name mintkey-test down --volumes`, THE Primary_Instance volumes (prefixed `mintkey_`) SHALL still exist and contain the same data as before the teardown (verified by `docker volume ls` listing all seven `mintkey_`-prefixed volumes and services starting cleanly against them without re-seeding).
3. WHEN the Primary_Instance is torn down via `docker compose --project-name mintkey down --volumes`, THE Test_Namespace volumes (prefixed `mintkey-test_`) SHALL still exist and contain the same data as before the teardown (verified by `docker volume ls` listing all seven `mintkey-test_`-prefixed volumes and services starting cleanly against them without re-seeding).
4. WHILE both environments are running simultaneously, WHEN one environment is torn down with volume removal, THE other environment's containers SHALL continue operating without interruption and its volumes SHALL remain intact.

### Requirement 4: Separate Docker Network

**User Story:** As a developer, I want the test environment to use its own Docker network, so that there is no cross-talk between the primary and test containers.

#### Acceptance Criteria

1. THE Test_Namespace SHALL create and use a Docker network named `mintkey-test_mintkey` (auto-prefixed by Docker Compose project name), separate from the Primary_Instance network `mintkey_mintkey`.
2. WHILE both environments are running, THE containers in the Test_Namespace SHALL have no TCP connectivity and no DNS resolution to containers in the Primary_Instance, and vice versa — enforced by each environment's containers being attached exclusively to their own project-scoped bridge network.
3. WHILE both environments are running, IF a `docker exec` command attempts to reach a Primary_Instance container IP or hostname from within a Test_Namespace container, THEN THE connection attempt SHALL fail (connection refused or timeout within 3 seconds) confirming network-level isolation.

### Requirement 5: Makefile Targets for Lifecycle Management

**User Story:** As a developer, I want simple Make targets to start, stop, and inspect the test namespace, so that switching between environments requires minimal effort.

#### Acceptance Criteria

1. THE Makefile SHALL provide a `dev-test` target that starts the Test_Namespace in detached mode by invoking `docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test --project-name mintkey-test up -d`.
2. THE Makefile SHALL provide a `dev-test-down` target that stops and removes the Test_Namespace containers without removing volumes, by invoking `docker compose --project-name mintkey-test down`. Volumes are preserved so that test data persists across restarts.
3. THE Makefile SHALL provide a `dev-test-logs` target that tails logs in follow mode from all Test_Namespace containers by invoking `docker compose --project-name mintkey-test logs -f`.
4. WHEN `make dev-test` is invoked, THE target SHALL print the following Test_Namespace access URLs to stdout after the stack starts:
   - admin-api: `http://localhost:8180`
   - admin-ui: `http://localhost:8181`
   - Keycloak: `http://localhost:8543`
   - Grafana: `http://localhost:3103`
5. WHEN `make dev-test` is invoked, THE target SHALL use `--project-name mintkey-test` to ensure namespace isolation from the Primary_Instance.
6. WHEN `make dev-test` is invoked, THE target SHALL print the bootstrap admin password from the Test_Namespace volume (or "not yet seeded" if the seed job has not run), matching the pattern used by the existing `dev` target.

### Requirement 6: Shared Docker Images

**User Story:** As a developer, I want both environments to share the same locally-built Docker images, so that I do not need to rebuild images when switching between namespaces.

#### Acceptance Criteria

1. THE Compose_Override SHALL not define any `build:` directives, so that Docker Compose inherits all build contexts from the primary `docker-compose.yml` unchanged.
2. THE Compose_Override SHALL set `image: mintkey-<service_name>` for each locally-built service (seed-job, vault-adapter, admin-api, admin-ui, mcp-server, broker, kong-syncer, proxy-plugin, mock-backend, jaeger-auth), pinning the image name to the Primary_Instance's project-prefixed tag so that Docker Compose does not generate a `mintkey-test`-prefixed image name and trigger a rebuild.
3. WHEN images have been built for the Primary_Instance (via `make dev` or `docker compose build`), THEN starting the Test_Namespace SHALL reuse those cached images without executing any build step, verifiable by the absence of "Building" output in `docker compose up` logs.
4. IF the Primary_Instance images have not been built when the Test_Namespace is started, THEN Docker Compose SHALL build the images using the primary `docker-compose.yml` build contexts and cache them under the Primary_Instance image names for subsequent reuse by either namespace.

### Requirement 7: Correct Keycloak Redirect URIs

**User Story:** As a developer, I want the test namespace's Keycloak realm to be configured with redirect URIs pointing to the offset ports, so that SSO login flows work correctly in the test environment.

#### Acceptance Criteria

1. WHEN the Test_Namespace Seed_Job runs, THE Seed_Job SHALL configure the Keycloak OIDC client redirect URIs using the Test_Namespace port values derived from the `MINTKEY_*_PUBLIC_URL` environment variables provided by the Env_Test_File: admin-api callback at port 8180, admin-ui callback at port 8181, Grafana OAuth callback at port 3103, and Jaeger OAuth callback at port 16786.
2. THE Env_Test_File SHALL set `MINTKEY_ADMIN_API_PUBLIC_URL=http://localhost:8180`, `MINTKEY_ADMIN_UI_PUBLIC_URL=http://localhost:8181`, `MINTKEY_GRAFANA_PUBLIC_URL=http://localhost:3103`, `MINTKEY_JAEGER_PUBLIC_URL=http://localhost:16786`, and `MINTKEY_KEYCLOAK_PUBLIC_URL=http://localhost:8543`.
3. WHEN an operator initiates a Keycloak login from the Test_Namespace admin-ui at port 8181, THE Keycloak authorization response SHALL redirect the operator back to the admin-ui OIDC callback endpoint at `http://localhost:8181` (matching the registered redirect URI), not to the Primary_Instance port 8081.
4. IF the Seed_Job attempts to configure Keycloak redirect URIs and the OIDC client does not exist in the Keycloak realm, THEN THE Seed_Job SHALL exit with a non-zero status code and log an error message indicating the missing client.

### Requirement 8: Correct Public URL Environment Variables

**User Story:** As a developer, I want all public-facing URL environment variables in the test namespace to point to the offset ports, so that cross-service links and OIDC flows resolve correctly.

#### Acceptance Criteria

1. THE Env_Test_File SHALL define the following variables with offset-port values:
   - `MINTKEY_KEYCLOAK_PUBLIC_URL=http://localhost:8543`
   - `MINTKEY_ADMIN_API_PUBLIC_URL=http://localhost:8180`
   - `MINTKEY_ADMIN_UI_PUBLIC_URL=http://localhost:8181`
   - `MINTKEY_MCP_PUBLIC_URL=http://localhost:8182`
   - `MINTKEY_PROXY_PUBLIC_URL=http://localhost:8100`
   - `MINTKEY_GRAFANA_PUBLIC_URL=http://localhost:3103`
   - `MINTKEY_JAEGER_PUBLIC_URL=http://localhost:16786`
2. WHEN the Test_Namespace is started, THE Compose_Override SHALL load the Env_Test_File via the Docker Compose `--env-file .env.test` flag so that all services inheriting from the primary `docker-compose.yml` receive the offset public URLs without per-service overrides.
3. WHEN an operator views the admin-ui dashboard in the Test_Namespace, THE admin-ui SHALL display `http://localhost:8182` as the MCP endpoint URL and `http://localhost:8100` as the proxy base URL in service detail views and the MCP connection instructions panel.
4. WHEN admin-api in the Test_Namespace constructs OIDC redirect URIs or callback URLs, THE URLs SHALL use `http://localhost:8180` as the base, matching the `MINTKEY_ADMIN_API_PUBLIC_URL` value from the Env_Test_File.

### Requirement 9: No Modification to Primary Compose File

**User Story:** As a developer, I want the test namespace to be implemented entirely via override files, so that the primary `docker-compose.yml` remains unchanged and unaffected.

#### Acceptance Criteria

1. THE Compose_Override SHALL be implemented as a separate `docker-compose.test.yml` file that layers on top of the primary `docker-compose.yml` using Docker Compose's multi-file mechanism (`-f docker-compose.yml -f docker-compose.test.yml`).
2. WHEN the Test_Namespace is started or stopped, THE primary `docker-compose.yml` SHALL remain byte-identical to its state before the Test_Namespace operation (verifiable via checksum comparison before and after).
3. THE Env_Test_File SHALL be a separate `.env.test` file that does not modify the primary `.env` or `.env.example`. THE `.env.test` file SHALL only be loaded when explicitly specified via `--env-file .env.test` and SHALL not be auto-loaded by Docker Compose when running the Primary_Instance with `make dev`.
4. WHEN the Primary_Instance is started without explicitly specifying the Compose_Override or Env_Test_File, THEN THE Primary_Instance SHALL behave identically regardless of whether `docker-compose.test.yml` and `.env.test` exist in the repository.

### Requirement 10: Full Functional Parity

**User Story:** As a developer, I want the test namespace to be fully functional (SSO, MCP, proxy, audit, observability), so that I can run the complete Mintkey stack for testing purposes.

#### Acceptance Criteria

1. WHEN the Test_Namespace is started, THE stack SHALL include all 15 long-running services and 2 one-shot jobs, identical to the Primary_Instance.
2. WHEN an agent connects to the Test_Namespace MCP server at port 8182, THE MCP server SHALL respond with service discovery results.
3. WHEN an operator accesses the Test_Namespace admin-ui at port 8181, THE SSO login flow through Keycloak at port 8543 SHALL complete successfully.
4. WHEN a proxied request is made through the Test_Namespace kong proxy at port 8100, THE request SHALL be routed through the proxy-plugin and reach the mock-backend.

### Requirement 11: macOS Compatibility

**User Story:** As a developer working on macOS, I want the test namespace to work on macOS with Docker Desktop, so that I can use it on my development machine.

#### Acceptance Criteria

1. WHEN the Test_Namespace is started on macOS with Docker Desktop version 4.x or later, THEN all 15 long-running services and 2 one-shot jobs SHALL reach a healthy state within 180 seconds, and the E2E smoke test SHALL pass with the same pass/fail outcome as on Linux.
2. THE Compose_Override SHALL use `host-gateway` for all `extra_hosts` entries so that containers can reach the Docker host IP, which Docker Desktop resolves natively on macOS without additional configuration.
3. IF a port conflict occurs on startup, THEN THE Docker Compose output SHALL include the host port number that failed to bind and the service name that attempted to bind it.
4. THE Compose_Override SHALL NOT require any macOS-specific file, environment variable, or manual step beyond having Docker Desktop installed and running.

### Requirement 12: Documentation

**User Story:** As a developer, I want clear documentation on how to use both environments simultaneously, so that I can quickly understand the setup and troubleshoot issues.

#### Acceptance Criteria

1. THE project SHALL include a markdown documentation file at a discoverable location (repository root or `docs/` directory) that explains the dev-test namespace concept, the port offset rule (Primary_Instance port + 100), the complete port mapping table for all 16 host-exposed services, and usage instructions referencing the Makefile targets (`dev-test`, `dev-test-down`, `dev-test-logs`).
2. THE documentation SHALL include a quick-reference table listing all 16 host-exposed services with columns for service name, Primary_Instance port, and Test_Namespace port (matching the port values defined in Requirement 2).
3. THE documentation SHALL describe how to run tests against the Test_Namespace by providing the exact commands to start the Test_Namespace (`make dev-test`), verify it is running (`make dev-test-logs`), and confirm service health, along with a statement that the Primary_Instance data and containers remain unaffected.
4. THE documentation SHALL explain how to tear down the Test_Namespace independently by providing the exact command (`make dev-test-down`) and describing that this removes Test_Namespace containers while preserving Primary_Instance containers and volumes.
5. THE documentation SHALL include a troubleshooting section that describes at minimum: how to identify port conflicts when both environments are running, and how to verify that the Primary_Instance is unaffected after Test_Namespace operations.
