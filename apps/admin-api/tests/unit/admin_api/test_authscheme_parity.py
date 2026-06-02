"""
test_authscheme_parity.py

Regression guard: asserts that the AuthScheme enum in vault.proto and the
AuthScheme enum in openapi.yaml stay in lockstep.

Per proto comment (line ~83):
  "The two MUST stay in lockstep — adding a value here requires the same
   value in docs/contracts/rest/openapi.yaml."

Per ADR-0014: OpenAPI is the CANONICAL source; the union of both must appear
in ALL enum locations (named schema + inline at the service-candidate schema).

Run with:
  cd apps/admin-api
  .venv/bin/python -m pytest tests/unit/admin_api/test_authscheme_parity.py -v
"""

import re
from pathlib import Path

import yaml
import pytest


# ---------------------------------------------------------------------------
# Paths — resolved relative to this file so the test is portable.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[5]  # …/apps/admin-api/tests/unit/admin_api → repo root
PROTO_PATH = REPO_ROOT / "docs/architecture/contracts/vault-adapter/vault.proto"
OPENAPI_PATH = REPO_ROOT / "docs/architecture/contracts/rest/openapi.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_proto_authscheme(proto_text: str) -> set[str]:
    """
    Extract AuthScheme enum values from vault.proto.

    Matches lines like:
        AUTH_SCHEME_BEARER_TOKEN = 3;
    Skips AUTH_SCHEME_UNSPECIFIED = 0 (sentinel, not a real scheme).

    Returns lowercase names with the AUTH_SCHEME_ prefix stripped:
        {"bearer_token", "api_key_header", ...}
    """
    pattern = re.compile(r"AUTH_SCHEME_([A-Z0-9_]+)\s*=\s*(\d+)\s*;")
    values: set[str] = set()
    for match in pattern.finditer(proto_text):
        name, numeric = match.group(1), int(match.group(2))
        if numeric == 0:
            continue  # skip UNSPECIFIED sentinel
        values.add(name.lower())
    return values


def _parse_openapi_named_enum(openapi_doc: dict) -> set[str]:
    """
    Return the AuthScheme enum values from the named schema component:
        components.schemas.AuthScheme.enum
    """
    try:
        return set(openapi_doc["components"]["schemas"]["AuthScheme"]["enum"])
    except KeyError as exc:
        raise AssertionError(
            f"Could not locate components.schemas.AuthScheme.enum in {OPENAPI_PATH}: {exc}"
        ) from exc


def _parse_openapi_inline_enum(openapi_doc: dict) -> set[str]:
    """
    Return the AuthScheme enum values from the inline enum on the
    TransientServiceCandidate.auth_scheme property.

    Location: components.schemas.TransientServiceCandidate.properties.auth_scheme.enum
    """
    try:
        return set(
            openapi_doc["components"]["schemas"]["TransientServiceCandidate"]
            ["properties"]["auth_scheme"]["enum"]
        )
    except KeyError as exc:
        raise AssertionError(
            f"Could not locate TransientServiceCandidate.auth_scheme inline enum "
            f"in {OPENAPI_PATH}: {exc}"
        ) from exc


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAuthSchemeParity:
    def test_proto_values_present(self, proto_text: str) -> None:
        """Sanity: proto must define at least the well-known schemes."""
        values = _parse_proto_authscheme(proto_text)
        expected_subset = {
            "bearer_token", "api_key_header", "basic_auth",
            "ssh_private_key", "ssh_ca", "ssh_password",
            "mtls", "oauth2_password_grant",
        }
        missing = expected_subset - values
        assert not missing, (
            f"vault.proto AuthScheme is missing expected values: {sorted(missing)}\n"
            f"Found: {sorted(values)}"
        )

    def test_openapi_named_enum_matches_proto(
        self, proto_text: str, openapi_doc: dict
    ) -> None:
        """
        The named AuthScheme enum in OpenAPI must be a superset of (or equal to)
        the proto enum.  Per ADR-0014 the canonical direction is proto ⊆ openapi.
        """
        proto_values = _parse_proto_authscheme(proto_text)
        openapi_values = _parse_openapi_named_enum(openapi_doc)

        missing_in_openapi = proto_values - openapi_values
        assert not missing_in_openapi, (
            f"vault.proto has AuthScheme values absent from OpenAPI named schema:\n"
            f"  Missing: {sorted(missing_in_openapi)}\n"
            f"  proto   : {sorted(proto_values)}\n"
            f"  openapi : {sorted(openapi_values)}\n"
            f"Add the missing values to components.schemas.AuthScheme.enum in {OPENAPI_PATH}"
        )

    def test_openapi_inline_enum_matches_named(self, openapi_doc: dict) -> None:
        """
        The inline enum on TransientServiceCandidate.auth_scheme must equal the
        named AuthScheme enum — there must be no 3-way drift.
        """
        named = _parse_openapi_named_enum(openapi_doc)
        inline = _parse_openapi_inline_enum(openapi_doc)

        missing_in_inline = named - inline
        extra_in_inline = inline - named

        assert not missing_in_inline and not extra_in_inline, (
            f"AuthScheme inline enum (ServiceCandidateRequest) drifted from named schema:\n"
            f"  Missing in inline : {sorted(missing_in_inline)}\n"
            f"  Extra in inline   : {sorted(extra_in_inline)}\n"
            f"Keep both enums identical in {OPENAPI_PATH}"
        )

    def test_proto_and_openapi_named_are_equal(
        self, proto_text: str, openapi_doc: dict
    ) -> None:
        """
        Full equality check — no silent drift in either direction.
        """
        proto_values = _parse_proto_authscheme(proto_text)
        openapi_values = _parse_openapi_named_enum(openapi_doc)

        only_in_proto = proto_values - openapi_values
        only_in_openapi = openapi_values - proto_values

        assert not only_in_proto and not only_in_openapi, (
            f"AuthScheme enum mismatch between vault.proto and openapi.yaml:\n"
            f"  Only in proto  : {sorted(only_in_proto)}\n"
            f"  Only in openapi: {sorted(only_in_openapi)}\n"
            f"Reconcile to the union in both files."
        )
