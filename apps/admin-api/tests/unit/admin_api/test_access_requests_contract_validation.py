"""
test_access_requests_contract_validation.py

Add-only contract-validation guard for the agent-access-requests feature
(spec .kiro/specs/agent-access-requests, task 1.5).

This is a NEW test file. It modifies no existing test. It scopes every
assertion to the feature's additions (Req 13.1, 13.3, 13.5, 13.6) so that
PRE-EXISTING contract issues do not cause it to fail:

  - openapi.yaml carries pre-existing Redocly warnings (7 `nullable: true`
    occurrences in unrelated schemas) and 2 pre-existing duplicate enum
    members (`permission_denied`, `service_not_found`) in
    `x-mintkey-error-codes.values`. This file does NOT run Redocly and does
    NOT assert enum uniqueness — it only asserts the structural validity of
    each document and the presence of the 7 feature error codes in BOTH
    closed enums.

What it checks (mirrors the CI `lint-contracts` job + adds the cross-enum gate):

  1. `openapi_spec_validator.validate` accepts
     docs/architecture/contracts/rest/openapi.yaml (structural OAS 3.1).
  2. `Draft202012Validator.check_schema` accepts
     docs/architecture/contracts/events/audit-event.schema.json.
  3. docs/architecture/contracts/mcp/tools.yaml parses as YAML.
  4. Every one of the 7 feature error codes is a member of BOTH:
       - `x-mintkey-error-codes.values` in openapi.yaml, AND
       - `$defs.error_code.enum` in tools.yaml
     (Req 13.3, ADR-0017.10).

Run with:
  cd apps/admin-api
  uv run pytest tests/unit/admin_api/test_access_requests_contract_validation.py -v
"""

import json
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths — resolved relative to this file so the test is portable.
# apps/admin-api/tests/unit/admin_api/<file>.py -> parents[5] == repo root.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[5]
OPENAPI_PATH = REPO_ROOT / "docs/architecture/contracts/rest/openapi.yaml"
AUDIT_SCHEMA_PATH = REPO_ROOT / "docs/architecture/contracts/events/audit-event.schema.json"
MCP_TOOLS_PATH = REPO_ROOT / "docs/architecture/contracts/mcp/tools.yaml"

# ---------------------------------------------------------------------------
# The 7 error codes introduced by the agent-access-requests feature (task 1.4).
# Each MUST be a member of both closed enums (Req 13.3).
# ---------------------------------------------------------------------------
FEATURE_ERROR_CODES = frozenset(
    {
        "request_not_found",
        "request_not_pending",
        "already_granted",
        "request_already_pending",
        "secret_field_not_allowed",
        "missing_secret_material",
        "reason_required",
    }
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def openapi_doc() -> dict:
    assert OPENAPI_PATH.exists(), f"openapi.yaml not found at {OPENAPI_PATH}"
    return yaml.safe_load(OPENAPI_PATH.read_text())


@pytest.fixture(scope="module")
def audit_schema() -> dict:
    assert AUDIT_SCHEMA_PATH.exists(), f"audit-event.schema.json not found at {AUDIT_SCHEMA_PATH}"
    return json.loads(AUDIT_SCHEMA_PATH.read_text())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openapi_error_codes(openapi_doc: dict) -> list[str]:
    """Return the raw `x-mintkey-error-codes.values` list from openapi.yaml.

    Returned as a list (NOT a set) so callers can reason about presence
    without being sensitive to the pre-existing duplicate members.
    """
    try:
        return list(openapi_doc["x-mintkey-error-codes"]["values"])
    except (KeyError, TypeError) as exc:
        raise AssertionError(
            f"Could not locate x-mintkey-error-codes.values in {OPENAPI_PATH}: {exc}"
        ) from exc


def _mcp_error_code_enum(mcp_doc: dict) -> list[str]:
    """Return the `$defs.error_code.enum` list from tools.yaml."""
    try:
        return list(mcp_doc["$defs"]["error_code"]["enum"])
    except (KeyError, TypeError) as exc:
        raise AssertionError(
            f"Could not locate $defs.error_code.enum in {MCP_TOOLS_PATH}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# 1-3. Structural validity of the three touched contract documents.
# ---------------------------------------------------------------------------

class TestContractStructuralValidity:
    def test_openapi_is_structurally_valid(self, openapi_doc: dict) -> None:
        """openapi.yaml must pass openapi_spec_validator (structural OAS 3.1)."""
        from openapi_spec_validator import validate as validate_openapi

        # Raises OpenAPIValidationError on structural problems; a clean return
        # (or None) means the document is structurally valid.
        validate_openapi(openapi_doc)

    def test_audit_event_schema_is_valid(self, audit_schema: dict) -> None:
        """audit-event.schema.json must be a valid Draft 2020-12 JSON Schema."""
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(audit_schema)

    def test_mcp_tools_yaml_parses(self) -> None:
        """tools.yaml must parse as a YAML mapping (mirrors the CI YAML lint)."""
        assert MCP_TOOLS_PATH.exists(), f"tools.yaml not found at {MCP_TOOLS_PATH}"
        doc = yaml.safe_load(MCP_TOOLS_PATH.read_text())
        assert isinstance(doc, dict), "tools.yaml did not parse to a mapping"


# ---------------------------------------------------------------------------
# 4. Cross-enum presence: every feature code in BOTH closed enums (Req 13.3).
#    Scoped to the 7 feature codes only — pre-existing duplicate members
#    (permission_denied, service_not_found) are irrelevant to these assertions.
# ---------------------------------------------------------------------------

class TestFeatureErrorCodeCrossEnum:
    def test_all_feature_codes_in_openapi_enum(self, openapi_doc: dict) -> None:
        """All 7 feature codes appear in openapi.yaml x-mintkey-error-codes.values."""
        present = set(_openapi_error_codes(openapi_doc))
        missing = FEATURE_ERROR_CODES - present
        assert not missing, (
            "openapi.yaml x-mintkey-error-codes.values is missing feature error codes:\n"
            f"  Missing: {sorted(missing)}\n"
            f"  Present feature codes: {sorted(FEATURE_ERROR_CODES & present)}"
        )

    def test_all_feature_codes_in_mcp_enum(self, openapi_doc: dict) -> None:
        """All 7 feature codes appear in tools.yaml $defs.error_code.enum."""
        mcp_doc = yaml.safe_load(MCP_TOOLS_PATH.read_text())
        present = set(_mcp_error_code_enum(mcp_doc))
        missing = FEATURE_ERROR_CODES - present
        assert not missing, (
            "tools.yaml $defs.error_code.enum is missing feature error codes:\n"
            f"  Missing: {sorted(missing)}\n"
            f"  Present feature codes: {sorted(FEATURE_ERROR_CODES & present)}"
        )

    def test_every_feature_code_is_in_both_enums(self, openapi_doc: dict) -> None:
        """The authoritative cross-enum gate: each of the 7 codes is a member of
        BOTH closed enums, so no feature code is returnable from one surface
        without being declared on the other (Req 13.3, ADR-0017.10)."""
        mcp_doc = yaml.safe_load(MCP_TOOLS_PATH.read_text())
        openapi_present = set(_openapi_error_codes(openapi_doc))
        mcp_present = set(_mcp_error_code_enum(mcp_doc))

        offenders = {
            code: {
                "in_openapi": code in openapi_present,
                "in_tools": code in mcp_present,
            }
            for code in sorted(FEATURE_ERROR_CODES)
            if not (code in openapi_present and code in mcp_present)
        }
        assert not offenders, (
            "Every feature error code must appear in BOTH the openapi.yaml "
            "`mintkey:code` enum (x-mintkey-error-codes.values) AND the "
            "tools.yaml `error_code` enum.\n"
            f"  Codes not in both: {offenders}"
        )
