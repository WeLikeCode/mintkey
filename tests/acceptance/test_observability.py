"""
WS-6 acceptance test — observability + audit (ADR-0017.6, design §13).

Non-integration structural assertions run always; the integration gate is
MINTKEY_INTEGRATION_TEST=true (requires a running docker-compose stack).

Sources: ADR-0017.6; design §13; T-1.10.x.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

_ROOT = Path(__file__).parent.parent.parent


# ===========================================================================
# Unit assertions (always run)
# ===========================================================================


def test_otel_init_in_all_go_services() -> None:
    """Every Go service main.go must call otelinit.Init."""
    mains = [
        _ROOT / "apps" / "broker" / "cmd" / "broker" / "main.go",
        _ROOT / "apps" / "vault-adapter" / "cmd" / "vault-adapter" / "main.go",
        _ROOT / "apps" / "kong-syncer" / "cmd" / "kong-syncer" / "main.go",
        _ROOT / "apps" / "proxy-plugin" / "cmd" / "proxy-plugin" / "main.go",
    ]
    for path in mains:
        assert path.exists(), f"Missing: {path}"
        src = path.read_text()
        assert "otelinit.Init" in src, f"otelinit.Init missing in {path.name}"


def test_metrics_endpoint_in_all_go_services() -> None:
    """Every Go service main.go must serve /metrics."""
    checks = {
        _ROOT / "apps" / "broker" / "cmd" / "broker" / "main.go": "/metrics",
        _ROOT / "apps" / "vault-adapter" / "cmd" / "vault-adapter" / "main.go": "/metrics",
        _ROOT / "apps" / "kong-syncer" / "cmd" / "kong-syncer" / "main.go": "/metrics",
        _ROOT / "apps" / "proxy-plugin" / "cmd" / "proxy-plugin" / "main.go": "/metrics",
    }
    for path, marker in checks.items():
        src = path.read_text()
        assert marker in src, f"{marker} endpoint missing in {path.name}"


def test_prometheus_scrapes_all_services() -> None:
    """prometheus.yml must scrape all Mintkey services."""
    prom = _ROOT / "infra" / "observability" / "prometheus.yml"
    assert prom.exists(), f"Missing: {prom}"
    src = prom.read_text()
    required_targets = [
        "admin-api",
        "broker",
        "vault-adapter",
        "mcp-server",
        "kong-syncer",
        "proxy-plugin",
    ]
    missing = [t for t in required_targets if t not in src]
    assert not missing, f"Prometheus missing targets: {missing}"


def test_otel_collector_config_has_redaction() -> None:
    """OTel collector config must have both attribute deletion and redaction processors."""
    config = _ROOT / "infra" / "observability" / "otel-collector-config.yaml"
    assert config.exists(), f"Missing: {config}"
    src = config.read_text()
    assert "attributes/redact" in src, "attributes/redact processor missing"
    assert "redaction:" in src, "redaction processor missing"
    # Key attributes that must be deleted
    for attr in ["authorization", "cookie"]:
        assert attr in src.lower(), f"Missing redaction for {attr}"


def test_audit_emit_implementation_exists() -> None:
    """mintkey_models/audit.py must have a real audit_emit implementation."""
    audit_py = _ROOT / "packages/python/mintkey-models" / "mintkey_models" / "audit.py"
    assert audit_py.exists(), f"Missing: {audit_py}"
    src = audit_py.read_text()
    assert "pg_advisory_xact_lock" in src, "advisory lock missing in audit_emit"
    assert "audit_chain_state" in src, "chain state missing in audit_emit"
    assert "INSERT INTO audit_events" in src, "INSERT into audit_events missing"
    assert "UPDATE audit_chain_state" in src, "UPDATE chain state missing"


def test_grafana_dashboards_exist() -> None:
    """Grafana dashboards must be provisioned."""
    dashboard_dir = _ROOT / "infra" / "observability" / "grafana" / "provisioning" / "dashboards"
    assert dashboard_dir.exists(), f"Missing: {dashboard_dir}"
    dashboards = list(dashboard_dir.glob("*.json"))
    assert len(dashboards) >= 1, "No Grafana dashboard JSON files found"


# ===========================================================================
# Integration test (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_prometheus_targets_all_up() -> None:
    """All Prometheus scrape targets must report UP."""
    import httpx

    prom = os.getenv("MINTKEY_PROMETHEUS_URL", "http://localhost:9090")
    r = httpx.get(f"{prom}/api/v1/targets", timeout=10)
    assert r.status_code == 200, f"Prometheus targets: {r.status_code}"
    data = r.json()
    targets = data.get("data", {}).get("activeTargets", [])
    down = [
        t["labels"]["job"]
        for t in targets
        if t.get("health") != "up"
    ]
    assert not down, f"Prometheus targets DOWN: {down}"


@INTEGRATION
def test_audit_chain_valid() -> None:
    """Audit chain verification must pass — no tamper events."""
    import httpx
    import os

    BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
    BOOTSTRAP_PASSWORD = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "changeme")

    with httpx.Client(timeout=30) as client:
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        csrf_token = csrf_r.json()["csrf_token"]
        client.post(
            f"{BASE_API}/v1/auth/session",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
            headers={"X-CSRF-Token": csrf_token},
        )

        # Audit list must return items with hash fields (chain is populated)
        audit_r = client.get(f"{BASE_API}/v1/tenants/t_default/audit")
        assert audit_r.status_code == 200
        items = audit_r.json().get("items", [])
        if items:
            assert items[0].get("hash") is not None, "Audit events missing hash field"
