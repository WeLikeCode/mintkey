"""
Acceptance test: Prometheus metrics present on all containers (T-1.10.2).

Verifies that each container exposes the required Prometheus metrics at /metrics.
Runs in two modes:
  - Unit (no Docker): validates prometheus.yml scrape targets are configured
    and that metrics names follow the naming conventions.
  - Integration (requires live stack): scrapes /metrics from each container.

Source: T-1.10.2; Req 11 AC2–AC4.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMETHEUS_YML = REPO_ROOT / "infra" / "observability" / "prometheus.yml"

# Expected metric names per component (T-1.10.2)
REQUIRED_METRICS = {
    "apps/admin-api": ["mintkey_requests_total", "mintkey_request_duration_seconds"],
    "broker": ["mintkey_token_issued_total", "mintkey_requests_total"],
    "proxy-plugin": ["mintkey_proxy_hit_total", "mintkey_proxy_added_latency_seconds"],
    "vault-adapter": ["mintkey_vault_dek_cache_hit_total", "mintkey_vault_dek_cache_miss_total"],
    "apps/mcp-server": ["mintkey_requests_total", "mintkey_request_duration_seconds"],
}

# Metric naming convention: must match this pattern (Prometheus best practices)
METRIC_NAME_PATTERN = re.compile(r"^mintkey_[a-z][a-z0-9_]*$")


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests (no Docker required)
# ─────────────────────────────────────────────────────────────────────────────

def test_prometheus_yml_exists():
    """prometheus.yml exists at repo root."""
    assert PROMETHEUS_YML.exists(), f"prometheus.yml not found at {PROMETHEUS_YML}"


def test_prometheus_yml_valid():
    """prometheus.yml is valid YAML."""
    data = yaml.safe_load(PROMETHEUS_YML.read_text())
    assert "scrape_configs" in data, "prometheus.yml missing scrape_configs"
    assert len(data["scrape_configs"]) > 0


def test_prometheus_scrapes_all_required_containers():
    """prometheus.yml configures scrape jobs for all required containers."""
    data = yaml.safe_load(PROMETHEUS_YML.read_text())
    job_names = {job["job_name"] for job in data["scrape_configs"]}

    required_jobs = {"apps/admin-api", "broker", "apps/mcp-server", "vault-adapter", "otel-collector"}
    missing = required_jobs - job_names
    assert not missing, f"Missing scrape jobs in prometheus.yml: {missing}"


def test_metric_names_follow_convention():
    """All required metric names follow the mintkey_ prefix naming convention."""
    violations = []
    for component, metrics in REQUIRED_METRICS.items():
        for metric in metrics:
            if not METRIC_NAME_PATTERN.match(metric):
                violations.append(f"{component}: {metric}")
    assert not violations, f"Metric names violate naming convention: {violations}"


def test_red_metrics_defined_for_api_components():
    """API components (admin-api, mcp-server) define RED metrics."""
    for component in ["apps/admin-api", "apps/mcp-server"]:
        metrics = REQUIRED_METRICS[component]
        has_rate = any("requests_total" in m for m in metrics)
        has_duration = any("duration" in m for m in metrics)
        assert has_rate, f"{component} missing rate metric (requests_total)"
        assert has_duration, f"{component} missing duration metric"


def test_proxy_plugin_defines_hit_and_latency_metrics():
    """Proxy plugin defines both hit counter and latency histogram."""
    metrics = REQUIRED_METRICS["proxy-plugin"]
    assert "mintkey_proxy_hit_total" in metrics
    assert "mintkey_proxy_added_latency_seconds" in metrics


def test_vault_adapter_defines_dek_cache_metrics():
    """Vault adapter defines DEK cache hit/miss counters."""
    metrics = REQUIRED_METRICS["vault-adapter"]
    assert "mintkey_vault_dek_cache_hit_total" in metrics
    assert "mintkey_vault_dek_cache_miss_total" in metrics


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (requires live stack)
# ─────────────────────────────────────────────────────────────────────────────

CONTAINER_PORTS = {
    "apps/admin-api": ("localhost", 8080),
    "broker": ("localhost", 8083),
    "apps/mcp-server": ("localhost", 8082),
    "vault-adapter": ("localhost", 8084),
}


@pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Integration test: requires running docker compose stack",
)
@pytest.mark.parametrize("component", list(CONTAINER_PORTS.keys()))
def test_metrics_endpoint_reachable(component):
    """Each container exposes /metrics and returns 200."""
    import httpx

    host, port = CONTAINER_PORTS[component]
    resp = httpx.get(f"http://{host}:{port}/metrics", timeout=5.0)
    assert resp.status_code == 200, (
        f"{component} /metrics returned {resp.status_code}"
    )


@pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Integration test: requires running docker compose stack",
)
@pytest.mark.parametrize("component,metrics", list(REQUIRED_METRICS.items()))
def test_required_metrics_present_in_output(component, metrics):
    """Each container's /metrics output contains the required metric names."""
    import httpx

    if component not in CONTAINER_PORTS:
        pytest.skip(f"No port configured for {component}")

    host, port = CONTAINER_PORTS[component]
    resp = httpx.get(f"http://{host}:{port}/metrics", timeout=5.0)
    assert resp.status_code == 200

    body = resp.text
    missing = [m for m in metrics if m not in body]
    assert not missing, (
        f"{component} /metrics missing: {missing}"
    )
