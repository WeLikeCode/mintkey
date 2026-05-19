"""Unit tests for tools/validate-test-override.py.

Tests the validation functions with fixture data (no Docker or actual compose
files required). Covers detection of:
  - Missing port override for a service
  - Incorrect port arithmetic (test port != primary + 100)
  - Missing image pin for a locally-built service
  - Missing env var in .env.test

Validates: Requirements 2.1, 2.2
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make the tools/ directory importable.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

# Import after path manipulation — the script is not a package.
validate_mod = importlib.import_module("validate-test-override")

validate_port_offsets = validate_mod.validate_port_offsets
validate_image_pins = validate_mod.validate_image_pins
validate_env_vars = validate_mod.validate_env_vars
parse_env_file = validate_mod.parse_env_file
REQUIRED_ENV_VARS = validate_mod.REQUIRED_ENV_VARS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def primary_ports():
    """Minimal primary port mappings for testing."""
    return {
        "admin-api": [(None, 8080, 8080)],
        "admin-ui": [(None, 8081, 8081)],
        "keycloak": [(None, 8443, 8443)],
        "kong": [(None, 8000, 8000), ("127.0.0.1", 8001, 8001)],
    }


@pytest.fixture()
def correct_test_ports():
    """Test port mappings with correct +100 offset."""
    return {
        "admin-api": [(None, 8180, 8080)],
        "admin-ui": [(None, 8181, 8081)],
        "keycloak": [(None, 8543, 8443)],
        "kong": [(None, 8100, 8000), ("127.0.0.1", 8101, 8001)],
    }


# ---------------------------------------------------------------------------
# Tests: validate_port_offsets — missing port override
# ---------------------------------------------------------------------------


class TestMissingPortOverride:
    """Test detection of missing port override for a service."""

    def test_detects_service_missing_from_test(self, primary_ports, correct_test_ports):
        """A service present in primary but absent from test triggers an error."""
        # Remove admin-ui from test ports
        del correct_test_ports["admin-ui"]

        errors = validate_port_offsets(primary_ports, correct_test_ports)

        assert len(errors) == 1
        assert "admin-ui" in errors[0]
        assert "no port override" in errors[0]

    def test_no_errors_when_all_services_present(self, primary_ports, correct_test_ports):
        """No errors when all primary services have test overrides."""
        errors = validate_port_offsets(primary_ports, correct_test_ports)
        assert errors == []

    def test_detects_multiple_missing_services(self, primary_ports, correct_test_ports):
        """Multiple missing services each produce an error."""
        del correct_test_ports["admin-ui"]
        del correct_test_ports["keycloak"]

        errors = validate_port_offsets(primary_ports, correct_test_ports)

        assert len(errors) == 2
        service_names = " ".join(errors)
        assert "admin-ui" in service_names
        assert "keycloak" in service_names


# ---------------------------------------------------------------------------
# Tests: validate_port_offsets — incorrect port arithmetic
# ---------------------------------------------------------------------------


class TestIncorrectPortArithmetic:
    """Test detection of incorrect port arithmetic (test port != primary + 100)."""

    def test_detects_wrong_offset(self, primary_ports, correct_test_ports):
        """A test port that is not primary + 100 triggers an error."""
        # Set admin-api test port to 8190 instead of 8180
        correct_test_ports["admin-api"] = [(None, 8190, 8080)]

        errors = validate_port_offsets(primary_ports, correct_test_ports)

        assert len(errors) == 1
        assert "admin-api" in errors[0]
        assert "8180" in errors[0]  # expected port
        assert "8190" in errors[0]  # actual port

    def test_detects_wrong_offset_multi_port_service(self, primary_ports, correct_test_ports):
        """Wrong offset on one port of a multi-port service triggers an error."""
        # Kong has two ports; make the admin port wrong
        correct_test_ports["kong"] = [(None, 8100, 8000), ("127.0.0.1", 8999, 8001)]

        errors = validate_port_offsets(primary_ports, correct_test_ports)

        assert len(errors) == 1
        assert "kong" in errors[0]
        assert "8101" in errors[0]  # expected
        assert "8999" in errors[0]  # actual

    def test_detects_missing_container_port_in_test(self, primary_ports):
        """A container port present in primary but missing from test triggers an error."""
        # Kong primary has two ports, test only has one
        test_ports = {
            "admin-api": [(None, 8180, 8080)],
            "admin-ui": [(None, 8181, 8081)],
            "keycloak": [(None, 8543, 8443)],
            "kong": [(None, 8100, 8000)],  # missing 8001 container port
        }

        errors = validate_port_offsets(primary_ports, test_ports)

        assert len(errors) == 1
        assert "kong" in errors[0]
        assert "container port 8001" in errors[0]


# ---------------------------------------------------------------------------
# Tests: validate_image_pins — missing image directive
# ---------------------------------------------------------------------------


class TestMissingImagePin:
    """Test detection of missing image pin for locally-built services."""

    def test_detects_service_missing_image_key(self):
        """A locally-built service without 'image:' in test override triggers an error."""
        test_services = {
            "seed-job": {"image": "mintkey-seed-job"},
            "vault-adapter": {"image": "mintkey-vault-adapter"},
            "admin-api": {"ports": ["8180:8080"]},  # missing image key
            "admin-ui": {"image": "mintkey-admin-ui"},
            "mcp-server": {"image": "mintkey-mcp-server"},
            "broker": {"image": "mintkey-broker"},
            "kong-syncer": {"image": "mintkey-kong-syncer"},
            "proxy-plugin": {"image": "mintkey-proxy-plugin"},
            "mock-backend": {"image": "mintkey-mock-backend"},
            "jaeger-auth": {"image": "mintkey-jaeger-auth"},
        }

        errors = validate_image_pins(test_services)

        assert len(errors) == 1
        assert "admin-api" in errors[0]
        assert "image" in errors[0].lower()

    def test_detects_service_missing_from_override(self):
        """A locally-built service entirely absent from test override triggers an error."""
        test_services = {
            "seed-job": {"image": "mintkey-seed-job"},
            "vault-adapter": {"image": "mintkey-vault-adapter"},
            "admin-api": {"image": "mintkey-admin-api"},
            "admin-ui": {"image": "mintkey-admin-ui"},
            "mcp-server": {"image": "mintkey-mcp-server"},
            "broker": {"image": "mintkey-broker"},
            "kong-syncer": {"image": "mintkey-kong-syncer"},
            "proxy-plugin": {"image": "mintkey-proxy-plugin"},
            "mock-backend": {"image": "mintkey-mock-backend"},
            # jaeger-auth missing entirely
        }

        errors = validate_image_pins(test_services)

        assert len(errors) == 1
        assert "jaeger-auth" in errors[0]

    def test_detects_empty_service_config(self):
        """A locally-built service with None/empty config triggers an error."""
        test_services = {
            "seed-job": {"image": "mintkey-seed-job"},
            "vault-adapter": {"image": "mintkey-vault-adapter"},
            "admin-api": {"image": "mintkey-admin-api"},
            "admin-ui": None,  # empty config
            "mcp-server": {"image": "mintkey-mcp-server"},
            "broker": {"image": "mintkey-broker"},
            "kong-syncer": {"image": "mintkey-kong-syncer"},
            "proxy-plugin": {"image": "mintkey-proxy-plugin"},
            "mock-backend": {"image": "mintkey-mock-backend"},
            "jaeger-auth": {"image": "mintkey-jaeger-auth"},
        }

        errors = validate_image_pins(test_services)

        assert len(errors) == 1
        assert "admin-ui" in errors[0]

    def test_no_errors_when_all_pinned(self):
        """No errors when all 10 locally-built services have image pins."""
        test_services = {
            "seed-job": {"image": "mintkey-seed-job"},
            "vault-adapter": {"image": "mintkey-vault-adapter"},
            "admin-api": {"image": "mintkey-admin-api"},
            "admin-ui": {"image": "mintkey-admin-ui"},
            "mcp-server": {"image": "mintkey-mcp-server"},
            "broker": {"image": "mintkey-broker"},
            "kong-syncer": {"image": "mintkey-kong-syncer"},
            "proxy-plugin": {"image": "mintkey-proxy-plugin"},
            "mock-backend": {"image": "mintkey-mock-backend"},
            "jaeger-auth": {"image": "mintkey-jaeger-auth"},
        }

        errors = validate_image_pins(test_services)

        assert errors == []


# ---------------------------------------------------------------------------
# Tests: validate_env_vars — missing env var
# ---------------------------------------------------------------------------


class TestMissingEnvVar:
    """Test detection of missing env var in .env.test."""

    def test_detects_missing_variable(self, tmp_path):
        """A missing MINTKEY_*_PUBLIC_URL variable triggers an error."""
        env_file = tmp_path / ".env.test"
        # Write all vars except MINTKEY_GRAFANA_PUBLIC_URL
        lines = []
        for var, val in REQUIRED_ENV_VARS.items():
            if var != "MINTKEY_GRAFANA_PUBLIC_URL":
                lines.append(f"{var}={val}")
        env_file.write_text("\n".join(lines) + "\n")

        with patch.object(validate_mod, "ENV_TEST", env_file):
            errors = validate_env_vars()

        assert len(errors) == 1
        assert "MINTKEY_GRAFANA_PUBLIC_URL" in errors[0]
        assert "missing" in errors[0].lower()

    def test_detects_incorrect_value(self, tmp_path):
        """An env var with wrong port value triggers an error."""
        env_file = tmp_path / ".env.test"
        lines = []
        for var, val in REQUIRED_ENV_VARS.items():
            if var == "MINTKEY_ADMIN_API_PUBLIC_URL":
                lines.append(f"{var}=http://localhost:9999")  # wrong port
            else:
                lines.append(f"{var}={val}")
        env_file.write_text("\n".join(lines) + "\n")

        with patch.object(validate_mod, "ENV_TEST", env_file):
            errors = validate_env_vars()

        assert len(errors) == 1
        assert "MINTKEY_ADMIN_API_PUBLIC_URL" in errors[0]
        assert "http://localhost:8180" in errors[0]  # expected
        assert "http://localhost:9999" in errors[0]  # actual

    def test_detects_missing_env_file(self, tmp_path):
        """A missing .env.test file triggers an error."""
        missing_file = tmp_path / "nonexistent" / ".env.test"

        with patch.object(validate_mod, "ENV_TEST", missing_file):
            errors = validate_env_vars()

        assert len(errors) == 1
        assert ".env.test not found" in errors[0]

    def test_no_errors_when_all_correct(self, tmp_path):
        """No errors when all 7 required variables are present with correct values."""
        env_file = tmp_path / ".env.test"
        lines = [f"{var}={val}" for var, val in REQUIRED_ENV_VARS.items()]
        env_file.write_text("\n".join(lines) + "\n")

        with patch.object(validate_mod, "ENV_TEST", env_file):
            errors = validate_env_vars()

        assert errors == []

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        """Comments and blank lines in .env.test are ignored."""
        env_file = tmp_path / ".env.test"
        lines = ["# This is a comment", ""]
        lines.extend(f"{var}={val}" for var, val in REQUIRED_ENV_VARS.items())
        lines.append("")
        lines.append("# trailing comment")
        env_file.write_text("\n".join(lines) + "\n")

        with patch.object(validate_mod, "ENV_TEST", env_file):
            errors = validate_env_vars()

        assert errors == []
