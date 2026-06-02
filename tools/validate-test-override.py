#!/usr/bin/env python3
"""Validate docker-compose.test.yml stays in sync with docker-compose.yml.

Checks:
  1. Every port-mapped service in primary has a corresponding override entry
     with host port = primary host port + 100.
  2. .env.test contains all 7 required MINTKEY_*_PUBLIC_URL variables with
     correct offset values.
  3. All 12 locally-built services have image: pins in the override.

Exits non-zero with descriptive errors on any drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORT_OFFSET = 100

REPO_ROOT = Path(__file__).resolve().parent.parent

PRIMARY_COMPOSE = REPO_ROOT / "infra" / "compose" / "docker-compose.yml"
TEST_COMPOSE = REPO_ROOT / "infra" / "compose" / "docker-compose.test.yml"
ENV_TEST = REPO_ROOT / ".env.test"

# The 11 locally-built services that must have image: pins in the override.
LOCALLY_BUILT_SERVICES = frozenset(
    [
        "seed-job",
        "vault-adapter",
        "admin-api",
        "admin-ui",
        "mcp-server",
        "broker",
        "kong-syncer",
        "proxy-plugin",
        "mock-backend",
        "jaeger-auth",
        "ssh-proxy",
        "email-proxy",
    ]
)

# Required MINTKEY_*_PUBLIC_URL variables and their expected values.
REQUIRED_ENV_VARS: dict[str, str] = {
    "MINTKEY_KEYCLOAK_PUBLIC_URL": "http://localhost:8543",
    "MINTKEY_ADMIN_API_PUBLIC_URL": "http://localhost:8180",
    "MINTKEY_ADMIN_UI_PUBLIC_URL": "http://localhost:8181",
    "MINTKEY_MCP_PUBLIC_URL": "http://localhost:8182",
    "MINTKEY_PROXY_PUBLIC_URL": "http://localhost:8100",
    "MINTKEY_GRAFANA_PUBLIC_URL": "http://localhost:3103",
    "MINTKEY_JAEGER_PUBLIC_URL": "http://localhost:16786",
}


# ---------------------------------------------------------------------------
# YAML loading with !override tag support
# ---------------------------------------------------------------------------


def _override_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> list:
    """Handle the !override YAML tag used in docker-compose.test.yml."""
    return loader.construct_sequence(node)


# Register the constructor for SafeLoader
yaml.add_constructor("!override", _override_constructor, Loader=yaml.SafeLoader)


# ---------------------------------------------------------------------------
# Port parsing
# ---------------------------------------------------------------------------


def _resolve_compose_var(s: str) -> str:
    """Resolve compose-style ${VAR:-default} or ${VAR-default} to their default value.

    Docker Compose allows variable substitution syntax in port mappings.  The
    validator runs without a loaded .env, so we substitute the default portion
    (e.g. ``${MINTKEY_SSH_PROXY_PORT:-2222}`` → ``2222``).  Variables without
    a default resolve to ``"0"`` as a safe sentinel (they would fail at runtime
    anyway).
    """
    return re.sub(r"\$\{[A-Z_][A-Z0-9_]*:?-?([^}]*)\}", lambda m: m.group(1) or "0", s)


def parse_port_mapping(port_str: str) -> tuple[str | None, int, int]:
    """Parse a Docker Compose port string into (bind_addr, host_port, container_port).

    Supported formats:
      - "8080:8080"
      - "127.0.0.1:8001:8001"
      - "8080:8080/tcp"  (protocol suffix stripped)
      - "${VAR:-default}:8080"  (compose variable substitution resolved to default)
    """
    # Resolve ${VAR:-default} substitutions before any other parsing
    port_str = _resolve_compose_var(port_str)
    # Strip protocol suffix if present
    port_str = re.sub(r"/(tcp|udp|sctp)$", "", port_str.strip())

    parts = port_str.split(":")
    if len(parts) == 3:
        bind_addr = parts[0]
        host_port = int(parts[1])
        container_port = int(parts[2])
    elif len(parts) == 2:
        bind_addr = None
        host_port = int(parts[0])
        container_port = int(parts[1])
    else:
        raise ValueError(f"Unrecognized port format: {port_str!r}")

    return bind_addr, host_port, container_port


def get_service_ports(services: dict) -> dict[str, list[tuple[str | None, int, int]]]:
    """Extract port mappings for all services that have ports defined.

    Returns: {service_name: [(bind_addr, host_port, container_port), ...]}
    """
    result: dict[str, list[tuple[str | None, int, int]]] = {}
    for svc_name, svc_config in services.items():
        if not svc_config:
            continue
        ports = svc_config.get("ports")
        if not ports:
            continue
        parsed = []
        for p in ports:
            parsed.append(parse_port_mapping(str(p)))
        if parsed:
            result[svc_name] = parsed
    return result


# ---------------------------------------------------------------------------
# .env.test parsing
# ---------------------------------------------------------------------------


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict, ignoring comments and blank lines."""
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------


def validate_port_offsets(
    primary_ports: dict[str, list[tuple[str | None, int, int]]],
    test_ports: dict[str, list[tuple[str | None, int, int]]],
) -> list[str]:
    """Check that every port-mapped service in primary has a test override with +100 offset."""
    errors: list[str] = []

    for svc_name, primary_mappings in primary_ports.items():
        if svc_name not in test_ports:
            errors.append(
                f"Service '{svc_name}' has ports in primary but no port override in test compose"
            )
            continue

        test_mappings = test_ports[svc_name]

        # Build lookup: container_port -> (bind_addr, host_port) for test
        test_by_container: dict[int, tuple[str | None, int]] = {}
        for bind_addr, host_port, container_port in test_mappings:
            test_by_container[container_port] = (bind_addr, host_port)

        for bind_addr, host_port, container_port in primary_mappings:
            expected_test_port = host_port + PORT_OFFSET

            if container_port not in test_by_container:
                errors.append(
                    f"Service '{svc_name}': primary port {host_port}:{container_port} "
                    f"has no corresponding test override for container port {container_port}"
                )
                continue

            _, actual_test_port = test_by_container[container_port]
            if actual_test_port != expected_test_port:
                errors.append(
                    f"Service '{svc_name}': expected test host port {expected_test_port} "
                    f"(primary {host_port} + {PORT_OFFSET}) but got {actual_test_port} "
                    f"for container port {container_port}"
                )

    return errors


def validate_env_vars() -> list[str]:
    """Check .env.test has all 7 required MINTKEY_*_PUBLIC_URL vars with correct values."""
    errors: list[str] = []

    if not ENV_TEST.exists():
        errors.append(f".env.test not found at {ENV_TEST}")
        return errors

    env = parse_env_file(ENV_TEST)

    for var_name, expected_value in REQUIRED_ENV_VARS.items():
        if var_name not in env:
            errors.append(f".env.test missing required variable: {var_name}")
        elif env[var_name] != expected_value:
            errors.append(
                f".env.test variable {var_name}: expected '{expected_value}' "
                f"but got '{env[var_name]}'"
            )

    return errors


def validate_image_pins(test_services: dict) -> list[str]:
    """Check all 12 locally-built services have image: directives in the override."""
    errors: list[str] = []

    for svc_name in sorted(LOCALLY_BUILT_SERVICES):
        if svc_name not in test_services:
            errors.append(
                f"Locally-built service '{svc_name}' missing from test override"
            )
            continue

        svc_config = test_services[svc_name]
        if not svc_config or "image" not in svc_config:
            errors.append(
                f"Locally-built service '{svc_name}' missing 'image:' pin in test override"
            )

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    errors: list[str] = []

    # Load compose files
    if not PRIMARY_COMPOSE.exists():
        errors.append(f"Primary compose file not found: {PRIMARY_COMPOSE}")
        _print_errors(errors)
        return 1

    if not TEST_COMPOSE.exists():
        errors.append(f"Test compose file not found: {TEST_COMPOSE}")
        _print_errors(errors)
        return 1

    primary_data = yaml.safe_load(PRIMARY_COMPOSE.read_text())
    test_data = yaml.safe_load(TEST_COMPOSE.read_text())

    primary_services = primary_data.get("services", {})
    test_services = test_data.get("services", {})

    # 1. Validate port offsets
    primary_ports = get_service_ports(primary_services)
    test_ports = get_service_ports(test_services)
    errors.extend(validate_port_offsets(primary_ports, test_ports))

    # 2. Validate .env.test variables
    errors.extend(validate_env_vars())

    # 3. Validate image pins
    errors.extend(validate_image_pins(test_services))

    if errors:
        _print_errors(errors)
        return 1

    print("✓ All validation checks passed.")
    return 0


def _print_errors(errors: list[str]) -> None:
    print(f"✗ Validation failed with {len(errors)} error(s):\n", file=sys.stderr)
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err}", file=sys.stderr)
    print(file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
