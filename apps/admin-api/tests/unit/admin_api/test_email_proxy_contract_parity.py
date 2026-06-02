"""
test_email_proxy_contract_parity.py

Contract-parity guard for the email-proxy feature (ADR-0024, C-1).

Asserts that ALL contract files stay in lockstep on the email-proxy surface:

1. vault.proto AuthScheme enum has values 14 (EMAIL_PASSWORD), 15 (EMAIL_OAUTH2),
   16 (EMAIL_APP_PASSWORD).
2. openapi.yaml AuthScheme named enum contains email_password, email_oauth2,
   email_app_password.
3. openapi.yaml has all three email-related path prefixes:
   - /v1/email-proxy/messages
   - /v1/email-proxy/mailboxes
   - /v1/internal/oauth2/{provider}/refresh
4. audit-event.schema.json contains all 14 email.* event type values in the
   discriminator mapping.
5. mcp/tools.yaml lists all 9 mintkey_*_email tools.
6. change-event.schema.json contains the 3 email.service.* change events in
   the discriminator mapping.
7. mcp/tools.yaml auth_scheme enum includes email_password, email_oauth2,
   email_app_password.

Run with:
  cd apps/admin-api
  unset MINTKEY_AUDIT_HMAC_KEY
  .venv/bin/python -m pytest tests/unit/admin_api/test_email_proxy_contract_parity.py -v
"""

import json
import re
from pathlib import Path

import yaml
import pytest

# ---------------------------------------------------------------------------
# Paths — resolved relative to this file so the test is portable.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[5]
PROTO_PATH = REPO_ROOT / "docs/architecture/contracts/vault-adapter/vault.proto"
OPENAPI_PATH = REPO_ROOT / "docs/architecture/contracts/rest/openapi.yaml"
AUDIT_SCHEMA_PATH = REPO_ROOT / "docs/architecture/contracts/events/audit-event.schema.json"
CHANGE_SCHEMA_PATH = REPO_ROOT / "docs/architecture/contracts/events/change-event.schema.json"
MCP_TOOLS_PATH = REPO_ROOT / "docs/architecture/contracts/mcp/tools.yaml"

# ---------------------------------------------------------------------------
# Expected contract values
# ---------------------------------------------------------------------------

EXPECTED_EMAIL_PROTO_VALUES = {
    "email_password": 14,
    "email_oauth2": 15,
    "email_app_password": 16,
}

EXPECTED_EMAIL_OPENAPI_SCHEMES = {
    "email_password",
    "email_oauth2",
    "email_app_password",
}

EXPECTED_EMAIL_PROXY_PATHS = {
    "/v1/email-proxy/messages",
    "/v1/email-proxy/mailboxes",
    "/v1/internal/oauth2/{provider}/refresh",
}

EXPECTED_AUDIT_EVENT_TYPES = {
    "email.service.registered",
    "email.service.updated",
    "email.service.deleted",
    "email.oauth2.authorize_initiated",
    "email.oauth2.authorized",
    "email.oauth2.refreshed",
    "email.oauth2.expired",
    "email.mailboxes.listed",
    "email.messages.listed",
    "email.message.read",
    "email.message.flags_updated",
    "email.message.deleted",
    "email.message.moved",
    "email.message.sent",
    # Added in feat/email-credentials-and-ui-fixes (ADR-0024)
    "email.credential.set",
    "email.credential.deleted",
}

EXPECTED_CHANGE_EVENT_TYPES = {
    "email.service.registered",
    "email.service.updated",
    "email.service.deleted",
}

EXPECTED_MCP_TOOLS = {
    "mintkey_list_mailboxes",
    "mintkey_list_emails",
    "mintkey_read_email",
    "mintkey_send_email",
    "mintkey_search_emails",
    "mintkey_delete_email",
    "mintkey_move_email",
    "mintkey_mark_email",
    "mintkey_download_attachment",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def proto_text() -> str:
    assert PROTO_PATH.exists(), f"vault.proto not found at {PROTO_PATH}"
    return PROTO_PATH.read_text()


@pytest.fixture(scope="module")
def openapi_doc() -> dict:
    assert OPENAPI_PATH.exists(), f"openapi.yaml not found at {OPENAPI_PATH}"
    return yaml.safe_load(OPENAPI_PATH.read_text())


@pytest.fixture(scope="module")
def audit_schema() -> dict:
    assert AUDIT_SCHEMA_PATH.exists(), f"audit-event.schema.json not found at {AUDIT_SCHEMA_PATH}"
    return json.loads(AUDIT_SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def change_schema() -> dict:
    assert CHANGE_SCHEMA_PATH.exists(), f"change-event.schema.json not found at {CHANGE_SCHEMA_PATH}"
    return json.loads(CHANGE_SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def mcp_tools_doc() -> dict:
    assert MCP_TOOLS_PATH.exists(), f"tools.yaml not found at {MCP_TOOLS_PATH}"
    return yaml.safe_load(MCP_TOOLS_PATH.read_text())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_proto_authscheme(proto_text: str) -> dict[str, int]:
    """Return {name_lower: numeric_value} for all AUTH_SCHEME_* entries (skipping UNSPECIFIED=0)."""
    pattern = re.compile(r"AUTH_SCHEME_([A-Z0-9_]+)\s*=\s*(\d+)\s*;")
    result: dict[str, int] = {}
    for match in pattern.finditer(proto_text):
        name, numeric = match.group(1).lower(), int(match.group(2))
        if numeric == 0:
            continue
        result[name] = numeric
    return result


def _get_openapi_named_authscheme_enum(openapi_doc: dict) -> list[str]:
    """Return the AuthScheme enum list from components.schemas.AuthScheme.enum."""
    try:
        return list(openapi_doc["components"]["schemas"]["AuthScheme"]["enum"])
    except KeyError as exc:
        raise AssertionError(
            f"Could not locate components.schemas.AuthScheme.enum in {OPENAPI_PATH}: {exc}"
        ) from exc


def _get_mcp_tools_names(mcp_doc: dict) -> set[str]:
    """Return the set of tool names from the tools list."""
    tools = mcp_doc.get("tools", [])
    return {t["name"] for t in tools if isinstance(t, dict) and "name" in t}


def _get_mcp_authscheme_enum(mcp_doc: dict) -> list[str]:
    """Return auth_scheme enum from $defs.auth_scheme.enum in tools.yaml."""
    try:
        return list(mcp_doc["$defs"]["auth_scheme"]["enum"])
    except KeyError as exc:
        raise AssertionError(
            f"Could not locate $defs.auth_scheme.enum in {MCP_TOOLS_PATH}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Tests — vault.proto
# ---------------------------------------------------------------------------

class TestProtoEmailSchemes:
    def test_email_password_value_14(self, proto_text: str) -> None:
        """vault.proto must define AUTH_SCHEME_EMAIL_PASSWORD = 14."""
        schemes = _parse_proto_authscheme(proto_text)
        assert "email_password" in schemes, (
            "vault.proto is missing AUTH_SCHEME_EMAIL_PASSWORD\n"
            f"Found schemes: {sorted(schemes.keys())}"
        )
        assert schemes["email_password"] == 14, (
            f"AUTH_SCHEME_EMAIL_PASSWORD should be 14, got {schemes['email_password']}"
        )

    def test_email_oauth2_value_15(self, proto_text: str) -> None:
        """vault.proto must define AUTH_SCHEME_EMAIL_OAUTH2 = 15."""
        schemes = _parse_proto_authscheme(proto_text)
        assert "email_oauth2" in schemes, (
            "vault.proto is missing AUTH_SCHEME_EMAIL_OAUTH2"
        )
        assert schemes["email_oauth2"] == 15, (
            f"AUTH_SCHEME_EMAIL_OAUTH2 should be 15, got {schemes['email_oauth2']}"
        )

    def test_email_app_password_value_16(self, proto_text: str) -> None:
        """vault.proto must define AUTH_SCHEME_EMAIL_APP_PASSWORD = 16."""
        schemes = _parse_proto_authscheme(proto_text)
        assert "email_app_password" in schemes, (
            "vault.proto is missing AUTH_SCHEME_EMAIL_APP_PASSWORD"
        )
        assert schemes["email_app_password"] == 16, (
            f"AUTH_SCHEME_EMAIL_APP_PASSWORD should be 16, got {schemes['email_app_password']}"
        )


# ---------------------------------------------------------------------------
# Tests — openapi.yaml AuthScheme
# ---------------------------------------------------------------------------

class TestOpenAPIAuthScheme:
    def test_email_schemes_in_named_enum(self, openapi_doc: dict) -> None:
        """openapi.yaml AuthScheme named enum must contain all 3 email schemes."""
        values = set(_get_openapi_named_authscheme_enum(openapi_doc))
        missing = EXPECTED_EMAIL_OPENAPI_SCHEMES - values
        assert not missing, (
            f"openapi.yaml AuthScheme named enum is missing: {sorted(missing)}\n"
            f"Present: {sorted(values)}"
        )

    def test_email_schemes_in_inline_enum(self, openapi_doc: dict) -> None:
        """TransientServiceCandidate.auth_scheme inline enum must contain the 3 email schemes."""
        try:
            inline = set(
                openapi_doc["components"]["schemas"]["TransientServiceCandidate"]
                ["properties"]["auth_scheme"]["enum"]
            )
        except KeyError as exc:
            raise AssertionError(
                f"Could not find TransientServiceCandidate.auth_scheme inline enum: {exc}"
            ) from exc
        missing = EXPECTED_EMAIL_OPENAPI_SCHEMES - inline
        assert not missing, (
            f"TransientServiceCandidate auth_scheme inline enum missing: {sorted(missing)}"
        )

    def test_named_and_inline_enums_agree(self, openapi_doc: dict) -> None:
        """Named and inline AuthScheme enums must be identical (no 3-way drift)."""
        named = set(_get_openapi_named_authscheme_enum(openapi_doc))
        try:
            inline = set(
                openapi_doc["components"]["schemas"]["TransientServiceCandidate"]
                ["properties"]["auth_scheme"]["enum"]
            )
        except KeyError:
            pytest.skip("TransientServiceCandidate.auth_scheme not found — skip parity check")
        only_named = named - inline
        only_inline = inline - named
        assert not only_named and not only_inline, (
            f"AuthScheme drift between named and inline enums:\n"
            f"  Only in named : {sorted(only_named)}\n"
            f"  Only in inline: {sorted(only_inline)}"
        )


# ---------------------------------------------------------------------------
# Tests — openapi.yaml paths
# ---------------------------------------------------------------------------

class TestOpenAPIPaths:
    def test_email_proxy_messages_path_exists(self, openapi_doc: dict) -> None:
        """/v1/email-proxy/messages path must exist in openapi.yaml."""
        paths = openapi_doc.get("paths", {})
        assert "/v1/email-proxy/messages" in paths, (
            f"openapi.yaml is missing path /v1/email-proxy/messages\n"
            f"Email-proxy paths present: {sorted(p for p in paths if 'email' in p.lower())}"
        )

    def test_email_proxy_mailboxes_path_exists(self, openapi_doc: dict) -> None:
        """/v1/email-proxy/mailboxes path must exist in openapi.yaml."""
        paths = openapi_doc.get("paths", {})
        assert "/v1/email-proxy/mailboxes" in paths, (
            f"openapi.yaml is missing path /v1/email-proxy/mailboxes"
        )

    def test_internal_oauth2_refresh_path_exists(self, openapi_doc: dict) -> None:
        """/v1/internal/oauth2/{provider}/refresh path must exist in openapi.yaml."""
        paths = openapi_doc.get("paths", {})
        assert "/v1/internal/oauth2/{provider}/refresh" in paths, (
            f"openapi.yaml is missing path /v1/internal/oauth2/{{provider}}/refresh\n"
            f"Internal paths present: {sorted(p for p in paths if 'internal' in p.lower())}"
        )

    def test_all_expected_email_paths_present(self, openapi_doc: dict) -> None:
        """All 3 required email-proxy paths must be present."""
        paths = set(openapi_doc.get("paths", {}).keys())
        missing = EXPECTED_EMAIL_PROXY_PATHS - paths
        assert not missing, (
            f"openapi.yaml is missing email-proxy paths: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Tests — audit-event.schema.json
# ---------------------------------------------------------------------------

class TestAuditEventSchema:
    def test_all_email_event_types_in_discriminator(self, audit_schema: dict) -> None:
        """audit-event.schema.json discriminator.mapping must contain all expected email.* events."""
        mapping = audit_schema.get("discriminator", {}).get("mapping", {})
        present = set(mapping.keys())
        missing = EXPECTED_AUDIT_EVENT_TYPES - present
        assert not missing, (
            f"audit-event.schema.json is missing event types in discriminator.mapping:\n"
            f"  Missing: {sorted(missing)}\n"
            f"  Present email types: {sorted(k for k in present if k.startswith('email.'))}"
        )

    def test_all_email_event_defs_in_defs(self, audit_schema: dict) -> None:
        """$defs must contain sub-schemas for all expected email.* event types."""
        defs = set(audit_schema.get("$defs", {}).keys())
        # Each event_type "email.x.y" maps to def "ev_email_x_y"
        expected_defs = {
            "ev_" + t.replace(".", "_") for t in EXPECTED_AUDIT_EVENT_TYPES
        }
        missing = expected_defs - defs
        assert not missing, (
            f"audit-event.schema.json $defs is missing: {sorted(missing)}"
        )

    def test_email_service_target_type_present(self, audit_schema: dict) -> None:
        """target_type enum must include 'email_service'."""
        target_types = set(
            audit_schema.get("$defs", {}).get("target_type", {}).get("enum", [])
        )
        assert "email_service" in target_types, (
            f"audit-event.schema.json target_type enum missing 'email_service'.\n"
            f"Found: {sorted(target_types)}"
        )


# ---------------------------------------------------------------------------
# Tests — change-event.schema.json
# ---------------------------------------------------------------------------

class TestChangeEventSchema:
    def test_email_service_change_events_in_discriminator(self, change_schema: dict) -> None:
        """change-event.schema.json discriminator.mapping must contain the 3 email.service.* events."""
        mapping = change_schema.get("discriminator", {}).get("mapping", {})
        present = set(mapping.keys())
        missing = EXPECTED_CHANGE_EVENT_TYPES - present
        assert not missing, (
            f"change-event.schema.json is missing email change events in discriminator.mapping:\n"
            f"  Missing: {sorted(missing)}\n"
            f"  Present: {sorted(k for k in present if k.startswith('email.'))}"
        )

    def test_email_service_defs_present(self, change_schema: dict) -> None:
        """$defs must contain sub-schemas for the 3 email.service.* change events."""
        defs = set(change_schema.get("$defs", {}).keys())
        expected_defs = {
            "ev_" + t.replace(".", "_") for t in EXPECTED_CHANGE_EVENT_TYPES
        }
        missing = expected_defs - defs
        assert not missing, (
            f"change-event.schema.json $defs is missing: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Tests — mcp/tools.yaml
# ---------------------------------------------------------------------------

class TestMCPTools:
    def test_all_9_email_tools_present(self, mcp_tools_doc: dict) -> None:
        """tools.yaml must list all 9 mintkey_*email* tools."""
        present = _get_mcp_tools_names(mcp_tools_doc)
        missing = EXPECTED_MCP_TOOLS - present
        assert not missing, (
            f"mcp/tools.yaml is missing email tools:\n"
            f"  Missing: {sorted(missing)}\n"
            f"  Present email tools: {sorted(t for t in present if 'email' in t.lower() or 'mailbox' in t.lower())}"
        )

    def test_email_schemes_in_mcp_authscheme_enum(self, mcp_tools_doc: dict) -> None:
        """$defs.auth_scheme.enum in tools.yaml must contain the 3 email schemes."""
        enum_values = set(_get_mcp_authscheme_enum(mcp_tools_doc))
        missing = EXPECTED_EMAIL_OPENAPI_SCHEMES - enum_values
        assert not missing, (
            f"mcp/tools.yaml $defs.auth_scheme.enum missing: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Cross-file parity
# ---------------------------------------------------------------------------

class TestCrossFileParity:
    def test_proto_email_schemes_in_openapi(self, proto_text: str, openapi_doc: dict) -> None:
        """All email auth_schemes in vault.proto must also appear in openapi.yaml named enum."""
        proto_schemes = _parse_proto_authscheme(proto_text)
        email_proto = {k for k in proto_schemes if k.startswith("email_")}
        openapi_named = set(_get_openapi_named_authscheme_enum(openapi_doc))
        missing = email_proto - openapi_named
        assert not missing, (
            f"email schemes in vault.proto absent from openapi.yaml named AuthScheme enum: {sorted(missing)}"
        )

    def test_proto_email_schemes_in_mcp(self, proto_text: str, mcp_tools_doc: dict) -> None:
        """All email auth_schemes in vault.proto must also appear in mcp/tools.yaml."""
        proto_schemes = _parse_proto_authscheme(proto_text)
        email_proto = {k for k in proto_schemes if k.startswith("email_")}
        mcp_enum = set(_get_mcp_authscheme_enum(mcp_tools_doc))
        missing = email_proto - mcp_enum
        assert not missing, (
            f"email schemes in vault.proto absent from mcp/tools.yaml auth_scheme enum: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Security scheme reference resolution — catches Issue-1's class of bug
# ---------------------------------------------------------------------------

class TestOpenAPISecuritySchemesResolve:
    """Every security: reference in every operation must resolve in components.securitySchemes."""

    def _collect_operation_security_refs(self, openapi_doc: dict) -> dict[str, list[str]]:
        """
        Walk all paths → operations → security blocks.
        Returns {operationId-or-path+method: [scheme_name, ...]} for
        every operation that has a non-empty security block.
        """
        refs: dict[str, list[str]] = {}
        paths = openapi_doc.get("paths", {})
        http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method not in http_methods:
                    continue
                if not isinstance(operation, dict):
                    continue
                security_list = operation.get("security")
                if not security_list:
                    continue
                scheme_names = []
                for requirement in security_list:
                    if isinstance(requirement, dict):
                        scheme_names.extend(requirement.keys())
                if scheme_names:
                    op_id = operation.get("operationId", f"{method.upper()} {path}")
                    refs[op_id] = scheme_names
        return refs

    def test_all_security_scheme_references_resolve(self, openapi_doc: dict) -> None:
        """
        Every scheme name referenced in any operation's security: block must be
        defined in components.securitySchemes.

        This test catches the class of bug where a new security scheme name is
        used in a security: block but never added to components.securitySchemes
        (which fails OpenAPI 3 validators, Redocly, Spectral, swagger-cli,
        openapi-spec-validator, and SDK code-generators).
        """
        defined = set(
            openapi_doc.get("components", {}).get("securitySchemes", {}).keys()
        )
        assert defined, (
            "openapi.yaml has no components.securitySchemes — cannot validate references."
        )

        op_refs = self._collect_operation_security_refs(openapi_doc)
        undefined_by_op: dict[str, list[str]] = {}
        for op_id, scheme_names in op_refs.items():
            missing = [s for s in scheme_names if s not in defined]
            if missing:
                undefined_by_op[op_id] = missing

        assert not undefined_by_op, (
            "openapi.yaml has operations referencing undefined security schemes.\n"
            f"Defined schemes: {sorted(defined)}\n"
            "Undefined references per operation:\n"
            + "\n".join(
                f"  {op}: {sorted(set(names))}"
                for op, names in sorted(undefined_by_op.items())
            )
        )
