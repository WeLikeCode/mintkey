# Kiro Project Template — task runner
# All targets delegate to scripts in tools/ or bootstrap/.
# Run `make help` to see available targets.

REPO_ROOT := $(shell pwd)
TOOLS     := $(REPO_ROOT)/tools

.PHONY: help deps bootstrap doctor audit-steering vibe-check spec-trace contract-lint template-diff template-pull

help:
	@echo "Available targets:"
	@echo "  deps                   Check & install required dependencies (python3, uv, jq, git, csvkit)"
	@echo "  bootstrap              Run the project-setup wizard (invoke via Kiro: /project-setup)"
	@echo "  doctor                 Verify local environment health"
	@echo "  audit-steering         Audit steering files (word counts, modes, stale files)"
	@echo "  audit-steering JSON=1  Same, machine-readable JSON output"
	@echo "  vibe-check             Pre-PR spec-reference scan on staged files"
	@echo "  spec-trace             Generate ADR/contract traceability matrix → .spec-trace/matrix.md"
	@echo "  contract-lint          Lint OpenAPI / AsyncAPI / JSON Schema contracts"
	@echo "  template-diff          Show uncommitted changes to template-owned paths"
	@echo "  template-pull VERSION= 3-way merge a new template version (requires 'template' remote)"

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
