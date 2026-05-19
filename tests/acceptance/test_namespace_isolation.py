"""
Namespace isolation integration test (Task 7.2).

Validates that the merged Docker Compose configuration for the test namespace
provides proper isolation from the primary namespace:
  - Merged config is valid YAML
  - No port overlap between primary and test namespace
  - All 7 named volumes get `mintkey-test_` prefix
  - Network is `mintkey-test_mintkey`

This test does NOT require Docker containers to be running — it only uses
`docker compose config` which is a dry-run merge that validates and outputs
the resolved configuration.

Validates: Requirements 1.1, 1.3, 3.1, 4.1
Sources: design.md §Isolation Boundaries, docker-compose.test.yml
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The 7 named volumes defined in docker-compose.yml
EXPECTED_VOLUMES = [
    "postgres_data",
    "vault_data",
    "vault_kek",
    "bootstrap_secrets",
    "grafana_data",
    "broker_wal",
    "proxy_wal",
]


def _has_docker_compose() -> bool:
    """Check if docker compose CLI is available."""
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


requires_docker_compose = pytest.mark.skipif(
    not _has_docker_compose(),
    reason="docker compose CLI not available",
)


def _get_compose_config(test_namespace: bool) -> dict:
    """
    Run `docker compose config` and return the parsed YAML.

    Args:
        test_namespace: If True, use the test override and .env.test.
                        If False, use the primary config only.
    """
    if test_namespace:
        cmd = [
            "docker", "compose",
            "-f", "docker-compose.yml",
            "-f", "docker-compose.test.yml",
            "--env-file", ".env.test",
            "config",
        ]
    else:
        cmd = ["docker", "compose", "config"]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(
            f"docker compose config failed (exit {result.returncode}):\n"
            f"{result.stderr}"
        )
    return yaml.safe_load(result.stdout)


def _extract_host_ports(config: dict) -> set[int]:
    """Extract all host port numbers from a compose config."""
    ports: set[int] = set()
    services = config.get("services", {})
    for _svc_name, svc_def in services.items():
        for port_entry in svc_def.get("ports", []):
            if isinstance(port_entry, dict):
                # Compose config outputs structured port mappings
                published = port_entry.get("published")
                if published is not None:
                    try:
                        ports.add(int(published))
                    except (ValueError, TypeError):
                        pass
            elif isinstance(port_entry, str):
                # Format: "host:container" or "ip:host:container"
                parts = port_entry.split(":")
                if len(parts) == 2:
                    try:
                        ports.add(int(parts[0]))
                    except ValueError:
                        pass
                elif len(parts) == 3:
                    try:
                        ports.add(int(parts[1]))
                    except ValueError:
                        pass
    return ports


@requires_docker_compose
class TestNamespaceIsolation:
    """Integration tests for dev-test namespace isolation properties."""

    @pytest.fixture(scope="class")
    def test_config(self) -> dict:
        """Merged test namespace compose config."""
        return _get_compose_config(test_namespace=True)

    @pytest.fixture(scope="class")
    def primary_config(self) -> dict:
        """Primary namespace compose config."""
        return _get_compose_config(test_namespace=False)

    def test_merged_config_is_valid_yaml(self, test_config: dict):
        """
        The merged compose config must be valid YAML and contain
        expected top-level keys.

        Validates: Requirement 1.1
        """
        assert isinstance(test_config, dict), "Config should parse as a dict"
        assert "services" in test_config, "Config must have 'services' key"
        assert "volumes" in test_config, "Config must have 'volumes' key"
        assert "networks" in test_config, "Config must have 'networks' key"

    def test_no_port_overlap(self, primary_config: dict, test_config: dict):
        """
        No host port number should appear in both the primary and test
        namespace configurations.

        Validates: Requirement 2.3 (no shared port numbers)
        """
        primary_ports = _extract_host_ports(primary_config)
        test_ports = _extract_host_ports(test_config)

        overlap = primary_ports & test_ports
        assert not overlap, (
            f"Port overlap detected between primary and test namespace: "
            f"{sorted(overlap)}"
        )

    def test_volumes_prefixed_with_mintkey_test(self, test_config: dict):
        """
        All 7 named volumes in the test config must be prefixed with
        `mintkey-test_` (auto-prefixed by Docker Compose project name).

        Validates: Requirement 3.1
        """
        volumes = test_config.get("volumes", {})

        # Docker Compose config outputs volume keys as their short name
        # (e.g. "postgres_data") with the full prefixed name in the "name"
        # field (e.g. "mintkey-test_postgres_data").
        resolved_volume_names: set[str] = set()
        for vol_key, vol_def in volumes.items():
            if isinstance(vol_def, dict) and "name" in vol_def:
                resolved_volume_names.add(vol_def["name"])
            else:
                resolved_volume_names.add(vol_key)

        for vol in EXPECTED_VOLUMES:
            expected_name = f"mintkey-test_{vol}"
            assert expected_name in resolved_volume_names, (
                f"Expected volume '{expected_name}' not found in test config. "
                f"Resolved volume names: {sorted(resolved_volume_names)}"
            )

    def test_network_is_mintkey_test_mintkey(self, test_config: dict):
        """
        The network name in the test config must be `mintkey-test_mintkey`.

        Validates: Requirement 4.1
        """
        networks = test_config.get("networks", {})
        # Docker Compose config output uses the full qualified network name
        # as the key when a project name is set via `name:` directive.
        # The network could appear as "mintkey-test_mintkey" directly,
        # or as "mintkey" with a name field set to "mintkey-test_mintkey".
        found = False
        for net_key, net_def in networks.items():
            # Check if the key itself is the full name
            if net_key == "mintkey-test_mintkey":
                found = True
                break
            # Check if the network definition has a name field
            if isinstance(net_def, dict) and net_def.get("name") == "mintkey-test_mintkey":
                found = True
                break
            # Also check the key pattern: when project name is "mintkey-test"
            # and network is "mintkey", compose config may output "mintkey"
            # with the external name being "mintkey-test_mintkey"
            if net_key == "mintkey" and isinstance(net_def, dict):
                name = net_def.get("name", "")
                if "mintkey-test" in name:
                    found = True
                    break

        assert found, (
            f"Expected network 'mintkey-test_mintkey' not found in test config. "
            f"Available networks: {networks}"
        )
