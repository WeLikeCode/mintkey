# Mintkey + Kiro Project Template — task runner
# Run `make help` to see all targets.

REPO_ROOT := $(shell pwd)
TOOLS     := $(REPO_ROOT)/tools
PYTHON    := python3
UV        := uv
PYTEST    := $(UV) run pytest
GO        := go

# Test namespace (parallel isolated environment on offset ports)
COMPOSE_TEST := docker compose -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.test.yml --env-file .env.test --project-name mintkey-test

# ─────────────────────────────────────────────────────────────────────────────
# Mintkey development targets
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help admin-password dev dev-test dev-test-down dev-test-reset dev-test-logs smoke-test-ns \
        test test-unit test-arch test-integration test-acceptance \
        test\:e2e test\:e2e\:headed test\:e2e\:ci \
        smoke test-golden test-data-plane test-data-plane-smoke test-data-plane-resilience \
        lint lint-python lint-go lint-ts lint-contracts \
        deps bootstrap doctor audit-steering vibe-check spec-trace contract-lint \
        template-diff template-pull \
        demo demo-mock \
        create-operator

help:
	@echo ""
	@echo "Mintkey dev targets:"
	@echo "  dev                    Start all services with docker compose"
	@echo "  dev-test               Start the test namespace (parallel isolated environment)"
	@echo "  dev-test-down          Stop the test namespace (preserves volumes)"
	@echo "  dev-test-logs          Tail test namespace logs"
	@echo "  dev-test-reset         Stop test namespace and destroy all its volumes"
	@echo "  smoke-test-ns          Run smoke tests against the test namespace"
	@echo "  test                   Run all tests (unit + arch + acceptance)"
	@echo "  test-unit              Run unit tests only (Python + Go; no Docker)"
	@echo "  test-arch              Run architecture tests only (no Docker)"
	@echo "  test-acceptance        Run acceptance tests (no Docker required for most)"
	@echo "  test-integration       Run integration tests (requires Docker + MINTKEY_INTEGRATION_TEST=true)"
	@echo "  test:e2e               Run Playwright E2E UI tests (requires running Docker stack)"
	@echo "  test:e2e:headed        Run Playwright E2E tests in headed mode (for debugging)"
	@echo "  test:e2e:ci            Run Playwright E2E tests in CI mode (Chromium only, retries)"
	@echo "  smoke                  Run E2E smoke test against running stack"
	@echo "  test-golden            Run WS-8 cross-stack golden-path E2E test (requires running stack)"
	@echo "  test-data-plane        Run WS-4 data-plane smoke + resilience tests (requires running stack)"
	@echo "  test-data-plane-smoke  Run WS-4 per-service smoke tests only"
	@echo "  test-data-plane-resilience  Run WS-4 resilience/failure-injection tests only"
	@echo "  lint                   Run all linters (Python + Go + TypeScript + contracts)"
	@echo "  lint-python            Run ruff + mypy --strict on Python code"
	@echo "  lint-go                Run golangci-lint on Go code"
	@echo "  lint-ts                Run eslint on admin-ui TypeScript"
	@echo "  lint-contracts         Validate OpenAPI + JSON Schema + MCP tools YAML"
	@echo "  create-operator        Provision or repair a Mintkey operator (Keycloak + DB)"
	@echo "                         Usage: make create-operator EMAIL=foo@mintkey.internal NAME='Foo Bar' PASSWORD=s3cr3t"
	@echo "                                make create-operator EMAIL=foo@mintkey.internal NAME='Foo Bar' PASSWORD=s3cr3t TENANT_ID=<uuid>"
	@echo "                                make create-operator EMAIL=foo@mintkey.internal NAME='Foo Bar' PASSWORD=s3cr3t DRY_RUN=1"
	@echo "                                make create-operator EMAIL=foo@mintkey.internal NAME='Foo Bar' PASSWORD=s3cr3t RESET_PASSWORD=1"
	@echo ""
	@echo "Kiro template targets:"
	@echo "  deps                   Check & install required dependencies"
	@echo "  bootstrap              Run the project-setup wizard"
	@echo "  doctor                 Verify local environment health"
	@echo "  audit-steering         Audit steering files"
	@echo "  vibe-check             Pre-PR spec-reference scan on staged files"
	@echo "  spec-trace             Generate ADR/contract traceability matrix"
	@echo "  contract-lint          Lint OpenAPI / AsyncAPI / JSON Schema contracts"
	@echo "  template-diff          Show uncommitted changes to template-owned paths"
	@echo "  template-pull VERSION= 3-way merge a new template version"
	@echo ""

# ── Development ──────────────────────────────────────────────────────────────

dev:
	docker compose up -d
	@echo "Stack started. Admin UI: http://localhost:8081"
	@echo "Bootstrap password: $$($(MAKE) -s admin-password 2>/dev/null || echo 'not yet seeded')"

## admin-password: Decrypt and print the current Fernet-encrypted
##                 admin_password from data/bootstrap-secrets/. KEK reads
##                 from $$MINTKEY_BOOTSTRAP_KEK (env or .env), falling back
##                 to the compose default. This is the operator-facing
##                 helper to find the bootstrap admin SSO password.
admin-password:
	@python3 -c "from cryptography.fernet import Fernet; import os; \
		kek = os.environ.get('MINTKEY_BOOTSTRAP_KEK') or 'TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas='; \
		print(Fernet(kek.encode()).decrypt(open('data/bootstrap-secrets/admin_password','rb').read()).decode())"

## create-operator: Idempotently provision (or repair) a Mintkey operator.
##   Runs create_operator.py inside the seed-job container on the compose network.
##   Required: EMAIL=<email> NAME=<display name> PASSWORD=<password>
##   Optional: TENANT_ID=<uuid>  NO_PLATFORM_ADMIN=1  DRY_RUN=1
##             RESET_PASSWORD=1  (force-rotate KC password even for existing users)
##   Examples:
##     make create-operator EMAIL=ops@mintkey.internal NAME="Ops User" PASSWORD=s3cr3t
##     make create-operator EMAIL=ops@mintkey.internal NAME="Ops User" PASSWORD=s3cr3t DRY_RUN=1
##     make create-operator EMAIL=adminus@mintkey.internal NAME=Adminus PASSWORD=s3cr3t \
##         TENANT_ID=ce79c39d-33de-4689-b827-2e926cb5f2c7
##     make create-operator EMAIL=ops@mintkey.internal NAME="Ops User" PASSWORD=s3cr3t RESET_PASSWORD=1
EMAIL        ?=
NAME         ?=
PASSWORD     ?=
TENANT_ID    ?=
NO_PLATFORM_ADMIN ?=
DRY_RUN      ?=
RESET_PASSWORD ?=

create-operator:
	@test -n "$(EMAIL)"    || (echo "ERROR: EMAIL is required. Usage: make create-operator EMAIL=foo@mintkey.internal NAME='Foo Bar' PASSWORD=<password>" && exit 1)
	@test -n "$(NAME)"     || (echo "ERROR: NAME is required. Usage: make create-operator EMAIL=foo@mintkey.internal NAME='Foo Bar' PASSWORD=<password>" && exit 1)
	@test -n "$(PASSWORD)" || (echo "ERROR: PASSWORD is required. Usage: make create-operator EMAIL=foo@mintkey.internal NAME='Foo Bar' PASSWORD=<password>" && exit 1)
	docker compose --env-file .env -f infra/compose/docker-compose.yml run --rm --no-deps \
		-e PGHOST=postgres \
		-e PGPORT=5432 \
		-e PGDATABASE=mintkey \
		-e PGUSER=mintkey_migrate \
		-e PGPASSWORD=changeme \
		-e KEYCLOAK_ADMIN=admin \
		-e KEYCLOAK_ADMIN_PASSWORD=changeme \
		-e MINTKEY_KEYCLOAK_INTERNAL_URL=http://keycloak:8443 \
		-v "$(REPO_ROOT)/apps/seed-job/create_operator.py:/app/create_operator.py:ro" \
		seed-job python /app/create_operator.py \
			--email "$(EMAIL)" \
			--display-name "$(NAME)" \
			--password "$(PASSWORD)" \
			$(if $(TENANT_ID),--tenant-id "$(TENANT_ID)",) \
			$(if $(NO_PLATFORM_ADMIN),--no-platform-admin,--platform-admin) \
			$(if $(DRY_RUN),--dry-run,) \
			$(if $(RESET_PASSWORD),--reset-password,)

dev-test-logs:
	$(COMPOSE_TEST) logs -f

dev-test:
	$(COMPOSE_TEST) up -d
	@echo ""
	@echo "Test namespace started."
	@echo "  admin-api:  http://localhost:8180"
	@echo "  admin-ui:   http://localhost:8181"
	@echo "  Keycloak:   http://localhost:8543"
	@echo "  Grafana:    http://localhost:3103"
	@echo ""
	@echo "Bootstrap password: $$(docker run --rm \
		-v mintkey-test_bootstrap_secrets:/secrets alpine \
		cat /secrets/admin_password 2>/dev/null || echo 'not yet seeded')"

dev-test-down:
	$(COMPOSE_TEST) down

dev-test-reset:
	@echo "WARNING: This will destroy ALL test namespace data (volumes)."
	$(COMPOSE_TEST) down --volumes

smoke-test-ns:
	@$(COMPOSE_TEST) ps --format '{{.State}}' | grep -q running || \
		(echo "Error: test namespace is not running. Run 'make dev-test' first." && exit 1)
	MINTKEY_INTEGRATION_TEST=true \
	MINTKEY_API_URL=http://localhost:8180 \
	MINTKEY_MCP_URL=http://localhost:8182 \
	MINTKEY_KONG_URL=http://localhost:8100 \
	$(PYTHON) -m pytest tests/acceptance/test_e2e_smoke.py -v -s

# ── Testing ───────────────────────────────────────────────────────────────────

test: test-unit test-arch test-acceptance
	@echo "All tests passed."

test-unit:
	@echo "── Python unit tests ──"
	cd apps/admin-api && $(UV) run pytest $(REPO_ROOT)/tests/unit/admin_api/ -v
	@echo "── mintkey-models unit tests ──"
	cd packages/python/mintkey-models && $(UV) run pytest tests/ -v
	@echo "── Go unit tests ──"
	$(GO) test ./... -v -short 2>&1 | tail -20

test-arch:
	@echo "── Architecture tests ──"
	cd apps/admin-api && $(UV) run pytest \
		$(REPO_ROOT)/tests/acceptance/test_no_sql_injection.py \
		$(REPO_ROOT)/tests/acceptance/test_audit_coverage.py \
		$(REPO_ROOT)/tests/acceptance/test_audit_append_only.py \
		$(REPO_ROOT)/tests/acceptance/test_sqlalchemy_mirror.py \
		$(REPO_ROOT)/tests/acceptance/test_platform_admin_rls.py \
		-v

test-acceptance:
	@echo "── Acceptance tests ──"
	cd apps/admin-api && $(UV) run pytest $(REPO_ROOT)/tests/acceptance/ -v \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_brokered_call.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_rotation_propagation.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_revocation_timing.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_token_issuance_perf.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_proxy_latency.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_avail.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_e2e_smoke.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_e2e_trace.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_mermaid_renders.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_metrics.py \
		--ignore=$(REPO_ROOT)/tests/acceptance/test_grafana.py

test-integration:
	@echo "── Integration tests (requires Docker) ──"
	MINTKEY_INTEGRATION_TEST=true cd apps/admin-api && $(UV) run pytest \
		$(REPO_ROOT)/tests/acceptance/test_brokered_call.py \
		$(REPO_ROOT)/tests/acceptance/test_rotation_propagation.py \
		$(REPO_ROOT)/tests/acceptance/test_revocation_timing.py \
		$(REPO_ROOT)/tests/acceptance/test_token_issuance_perf.py \
		$(REPO_ROOT)/tests/acceptance/test_proxy_latency.py \
		$(REPO_ROOT)/tests/acceptance/test_avail.py \
		-v

smoke:
	@echo "── E2E smoke test ──"
	@if ! docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'; then \
		echo "ERROR: docker compose stack not running. Run 'make dev' first."; exit 1; \
	fi
	MINTKEY_INTEGRATION_TEST=true $(PYTHON) -m pytest tests/acceptance/test_e2e_smoke.py -v -s

test-golden:
	@echo "── WS-8 cross-stack golden-path E2E test ──"
	@if ! docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'; then \
		echo "ERROR: docker compose stack not running. Run 'make dev' first."; exit 1; \
	fi
	MINTKEY_INTEGRATION_TEST=true $(PYTHON) -m pytest tests/acceptance/test_golden_path.py -v -s

test-data-plane-smoke:
	@echo "── WS-4 data-plane smoke tests ──"
	@if ! docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'; then \
		echo "ERROR: docker compose stack not running. Run 'make dev' first."; exit 1; \
	fi
	MINTKEY_INTEGRATION_TEST=true $(PYTHON) -m pytest tests/acceptance/test_data_plane_smoke.py -v

test-data-plane-resilience:
	@echo "── WS-4 data-plane resilience tests ──"
	@if ! docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'; then \
		echo "ERROR: docker compose stack not running. Run 'make dev' first."; exit 1; \
	fi
	MINTKEY_INTEGRATION_TEST=true $(PYTHON) -m pytest tests/acceptance/test_data_plane_resilience.py -v

test-data-plane: test-data-plane-smoke test-data-plane-resilience
	@echo "── WS-4 data-plane tests complete ──"

# ── Playwright E2E UI tests ──────────────────────────────────────────────────

# NOTE: colons in target names are escaped (`\:`) for GNU Make 3.81
# compatibility (macOS default). Without the escape, make fails with
# "*** target pattern contains no '%'. Stop." before any target can run.
# This pre-existed the monorepo restructure but blocked `make help`,
# `make admin-password`, and similar discovery commands until escaped.

test\:e2e-setup:
	@bash $(TOOLS)/e2e-setup-env.sh

test\:e2e: ## Run Playwright E2E UI tests (headless, all browsers)
	@test -f apps/admin-ui/e2e/.env.local || (echo "ERROR: run 'make test\:e2e-setup' first" && exit 1)
	cd apps/admin-ui && npx playwright test --config e2e/playwright.config.ts --reporter=list,html

test\:e2e\:headed: ## Run Playwright E2E UI tests in headed mode (debug)
	@test -f apps/admin-ui/e2e/.env.local || (echo "ERROR: run 'make test\:e2e-setup' first" && exit 1)
	cd apps/admin-ui && npx playwright test --config e2e/playwright.config.ts --headed --reporter=list,html

test\:e2e\:ci: ## Run Playwright E2E UI tests in CI mode (Chromium only, retries)
	@test -f apps/admin-ui/e2e/.env.local || (echo "ERROR: run 'make test\:e2e-setup' first" && exit 1)
	cd apps/admin-ui && CI=true npx playwright test --config e2e/playwright.config.ts --reporter=junit,html

# ── Linting ───────────────────────────────────────────────────────────────────

lint: lint-python lint-go lint-contracts
	@echo "All linters passed."

lint-python:
	@echo "── Python: ruff ──"
	# Blocking linters: || true masks removed (OSS-3 remediation) so Python lint
	# failures now exit non-zero and are visible to contributors.
	cd apps/admin-api && $(UV) run ruff check src/
	cd apps/mcp-server && $(UV) run ruff check src/
	cd packages/python/mintkey-models && $(UV) run ruff check mintkey_models/
	@echo "── Python: mypy ──"
	cd apps/admin-api && $(UV) run mypy --strict src/admin_api/
	cd packages/python/mintkey-models && $(UV) run mypy --strict mintkey_models/

lint-go:
	@echo "── Go: vet ──"
	$(GO) vet ./...
	@echo "── Go: staticcheck (if installed) ──"
	@which staticcheck >/dev/null 2>&1 && staticcheck ./... || echo "  (staticcheck not installed; skipping)"

lint-ts:
	@echo "── TypeScript: eslint ──"
	@if [ -d apps/admin-ui/node_modules ]; then \
		cd apps/admin-ui && pnpm eslint src/ --max-warnings=0; \
	else \
		echo "  (admin-ui not installed; run 'cd apps/admin-ui && pnpm install')"; \
	fi

lint-contracts:
	@echo "── OpenAPI spec ──"
	$(PYTHON) -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')))" \
		&& echo "  OpenAPI: OK" || echo "  OpenAPI: FAILED"
	@echo "── JSON Schemas ──"
	$(PYTHON) -c "import json; from jsonschema import Draft202012Validator as V; \
		[V.check_schema(json.load(open(p))) for p in [ \
		'docs/architecture/contracts/events/audit-event.schema.json', \
		'docs/architecture/contracts/events/change-event.schema.json']]" \
		&& echo "  JSON Schema: OK" || echo "  JSON Schema: FAILED"
	@echo "── MCP tools YAML ──"
	$(PYTHON) -c "import yaml; yaml.safe_load(open('docs/architecture/contracts/mcp/tools.yaml'))" \
		&& echo "  MCP YAML: OK" || echo "  MCP YAML: FAILED"

deps:
	@bash $(TOOLS)/deps.sh

bootstrap:
	@echo "The bootstrap wizard runs as a Kiro skill."
	@echo "Open Kiro and say: 'set up this project' or invoke /project-setup"
	@echo ""
	@echo "If you prefer the shell wizard: ./bootstrap/setup-wizard.sh"

doctor:
	@bash $(TOOLS)/doctor.sh

audit-steering:
	@bash $(TOOLS)/kiro-steering-audit.sh $(if $(JSON),--json,)

vibe-check:
	@bash $(TOOLS)/vibe-check.sh

spec-trace:
	@bash $(TOOLS)/spec-trace.sh

contract-lint:
	@bash $(TOOLS)/contract-lint.sh

template-diff:
	@bash $(TOOLS)/template-diff.sh diff

template-pull:
	@bash $(TOOLS)/template-diff.sh pull $(VERSION)

# ─────────────────────────────────────────────────────────────────────────────
# Demo targets (Builder B-1 experience)
# Requirements: 11.*, 12.*
# WARNING: Neither target destroys volumes. Back up first with
#   bash scripts/dev-backup.sh --write
# before any docker compose down -v operation.
# ─────────────────────────────────────────────────────────────────────────────

## demo: Start the full Mintkey stack and print admin URL + bootstrap password.
##       Polls all three health endpoints (180 s timeout). Idempotent — safe to
##       run when the stack is already up.
demo:
	@docker info >/dev/null 2>&1 || { echo "ERROR: Docker is not running. Start Docker Desktop (or the Docker daemon) and try again."; exit 1; }
	@echo "Starting Mintkey stack..."
	docker compose up -d
	@echo "Waiting for health checks (admin-api :8080, admin-ui :8081, mcp-server :8082) — 180 s timeout..."
	@elapsed=0; \
	while [ $$elapsed -lt 180 ]; do \
		api_ok=0; ui_ok=0; mcp_ok=0; \
		curl -sf http://localhost:8080/v1/health >/dev/null 2>&1 && api_ok=1; \
		curl -sf http://localhost:8081/health    >/dev/null 2>&1 && ui_ok=1; \
		curl -sf http://localhost:8082/v1/health >/dev/null 2>&1 && mcp_ok=1; \
		if [ $$api_ok -eq 1 ] && [ $$ui_ok -eq 1 ] && [ $$mcp_ok -eq 1 ]; then \
			break; \
		fi; \
		sleep 5; elapsed=$$((elapsed + 5)); \
		printf "."; \
	done; \
	if [ $$elapsed -ge 180 ]; then \
		echo ""; \
		echo "ERROR: Timed out after 180 s waiting for services to become healthy."; \
		echo "       Run 'docker compose ps' to check container status."; \
		echo "       Run 'docker compose logs <service>' for diagnostics."; \
		exit 1; \
	fi
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║  ✓ Mintkey stack is up.                                              ║"
	@echo "║                                                                      ║"
	@echo "║  Open the admin UI:    http://localhost:8081                         ║"
	@echo "║  Bootstrap password:   make admin-password                           ║"
	@echo "║                        (Fernet-decrypts data/bootstrap-secrets/      ║"
	@echo "║                         admin_password via MINTKEY_BOOTSTRAP_KEK)    ║"
	@echo "║                                                                      ║"
	@echo "║  Next steps:                                                         ║"
	@echo "║    make demo-mock   — run a PAT-free mock-backend demo               ║"
	@echo "║    bash scripts/dev-backup.sh --write   — back up state before reset ║"
	@echo "║    docs/guides/agent-never-sees-secret.md   — security walkthrough   ║"
	@echo "╚══════════════════════════════════════════════════════════════════════╝"

## demo-mock: Auto-start the stack (if not running) then execute the PAT-free
##            mock-backend demo flow end-to-end (scripts/demo-mock-flow.sh).
demo-mock:
	@docker info >/dev/null 2>&1 || { echo "ERROR: Docker is not running. Start Docker Desktop (or the Docker daemon) and try again."; exit 1; }
	@running=$$(docker compose ps --status running --quiet 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$running" -lt 10 ]; then \
		echo "Stack not fully running ($$running/10+ expected containers up). Starting..."; \
		$(MAKE) demo; \
	else \
		echo "Stack already running ($$running containers up). Skipping start."; \
	fi
	@echo ""
	@echo "Running PAT-free mock-backend demo flow..."
	@echo "See: docs/guides/10min-mock-demo.md"
	@echo ""
	bash scripts/demo-mock-flow.sh || { echo ""; echo "ERROR: Mock demo failed. Review the output above for the failing step."; exit 1; }
