# Mintkey + Kiro Project Template — task runner
# Run `make help` to see all targets.

REPO_ROOT := $(shell pwd)
TOOLS     := $(REPO_ROOT)/tools
PYTHON    := python3
UV        := uv
PYTEST    := $(UV) run pytest
GO        := go

# ─────────────────────────────────────────────────────────────────────────────
# Mintkey development targets
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help dev test test-unit test-arch test-integration test-acceptance \
        test:e2e test:e2e:headed test:e2e:ci \
        smoke test-golden test-data-plane test-data-plane-smoke test-data-plane-resilience \
        lint lint-python lint-go lint-ts lint-contracts \
        deps bootstrap doctor audit-steering vibe-check spec-trace contract-lint \
        template-diff template-pull

help:
	@echo ""
	@echo "Mintkey dev targets:"
	@echo "  dev                    Start all services with docker compose"
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
	@echo "Stack started. Admin UI: http://localhost:3000"
	@echo "Bootstrap password: $$(cat data/bootstrap-secrets/admin_password 2>/dev/null || echo 'not yet seeded')"

# ── Testing ───────────────────────────────────────────────────────────────────

test: test-unit test-arch test-acceptance
	@echo "All tests passed."

test-unit:
	@echo "── Python unit tests ──"
	cd admin-api && $(UV) run pytest $(REPO_ROOT)/tests/unit/admin_api/ -v
	@echo "── mintkey-models unit tests ──"
	cd mintkey-models && $(UV) run pytest tests/ -v
	@echo "── Go unit tests ──"
	$(GO) test ./... -v -short 2>&1 | tail -20

test-arch:
	@echo "── Architecture tests ──"
	cd admin-api && $(UV) run pytest \
		$(REPO_ROOT)/tests/acceptance/test_no_sql_injection.py \
		$(REPO_ROOT)/tests/acceptance/test_audit_coverage.py \
		$(REPO_ROOT)/tests/acceptance/test_audit_append_only.py \
		$(REPO_ROOT)/tests/acceptance/test_sqlalchemy_mirror.py \
		$(REPO_ROOT)/tests/acceptance/test_platform_admin_rls.py \
		-v

test-acceptance:
	@echo "── Acceptance tests ──"
	cd admin-api && $(UV) run pytest $(REPO_ROOT)/tests/acceptance/ -v \
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
	MINTKEY_INTEGRATION_TEST=true cd admin-api && $(UV) run pytest \
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

test:e2e-setup:
	@bash $(TOOLS)/e2e-setup-env.sh

test:e2e: ## Run Playwright E2E UI tests (headless, all browsers)
	@test -f admin-ui/e2e/.env.local || (echo "ERROR: run 'make test:e2e-setup' first" && exit 1)
	cd admin-ui && npx playwright test --config e2e/playwright.config.ts --reporter=list,html

test:e2e:headed: ## Run Playwright E2E UI tests in headed mode (debug)
	@test -f admin-ui/e2e/.env.local || (echo "ERROR: run 'make test:e2e-setup' first" && exit 1)
	cd admin-ui && npx playwright test --config e2e/playwright.config.ts --headed --reporter=list,html

test:e2e:ci: ## Run Playwright E2E UI tests in CI mode (Chromium only, retries)
	@test -f admin-ui/e2e/.env.local || (echo "ERROR: run 'make test:e2e-setup' first" && exit 1)
	cd admin-ui && CI=true npx playwright test --config e2e/playwright.config.ts --reporter=junit,html

# ── Linting ───────────────────────────────────────────────────────────────────

lint: lint-python lint-go lint-contracts
	@echo "All linters passed."

lint-python:
	@echo "── Python: ruff ──"
	# Blocking linters: || true masks removed (OSS-3 remediation) so Python lint
	# failures now exit non-zero and are visible to contributors.
	cd admin-api && $(UV) run ruff check src/
	cd mcp-server && $(UV) run ruff check src/
	cd mintkey-models && $(UV) run ruff check mintkey_models/
	@echo "── Python: mypy ──"
	cd admin-api && $(UV) run mypy --strict src/admin_api/
	cd mintkey-models && $(UV) run mypy --strict mintkey_models/

lint-go:
	@echo "── Go: vet ──"
	$(GO) vet ./...
	@echo "── Go: staticcheck (if installed) ──"
	@which staticcheck >/dev/null 2>&1 && staticcheck ./... || echo "  (staticcheck not installed; skipping)"

lint-ts:
	@echo "── TypeScript: eslint ──"
	@if [ -d admin-ui/node_modules ]; then \
		cd admin-ui && pnpm eslint src/ --max-warnings=0; \
	else \
		echo "  (admin-ui not installed; run 'cd admin-ui && pnpm install')"; \
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
