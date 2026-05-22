"""
Acceptance test: Grafana dashboards are pre-provisioned (T-1.10.3).

Verifies:
  - All 4 required dashboard JSON files exist with expected titles.
  - Each dashboard has its expected panels.
  - Dashboard UIDs are stable.
  - Integration form queries the Grafana API (requires docker compose).

Source: T-1.10.3; Req 11 AC1–AC4.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS_DIR = REPO_ROOT / "infra" / "observability" / "grafana" / "provisioning" / "dashboards"

REQUIRED_DASHBOARDS = {
    "mintkey-overview": {
        "title": "mintkey-overview",
        "min_panels": 4,
        "expected_panel_titles": ["Request Rate", "Latency", "Token", "Proxy"],
    },
    "mintkey-per-service": {
        "title": "mintkey-per-service",
        "min_panels": 3,
        "expected_panel_titles": ["Proxy Hits", "Latency", "Token"],
    },
    "mintkey-credential-cache": {
        "title": "mintkey-credential-cache",
        "min_panels": 3,
        "expected_panel_titles": ["DEK Cache", "Lag", "Rotation"],
    },
    "mintkey-audit": {
        "title": "mintkey-audit",
        "min_panels": 3,
        "expected_panel_titles": ["Audit", "Chain", "PlatformAdmin"],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests (no Docker required)
# ─────────────────────────────────────────────────────────────────────────────

def test_dashboards_directory_exists():
    """grafana/provisioning/dashboards/ directory exists."""
    assert DASHBOARDS_DIR.is_dir(), f"Missing {DASHBOARDS_DIR}"


@pytest.mark.parametrize("uid", list(REQUIRED_DASHBOARDS.keys()))
def test_dashboard_file_exists(uid):
    """Each required dashboard JSON file exists."""
    path = DASHBOARDS_DIR / f"{uid}.json"
    assert path.exists(), f"Dashboard file missing: {path}"


@pytest.mark.parametrize("uid,spec", list(REQUIRED_DASHBOARDS.items()))
def test_dashboard_json_valid(uid, spec):
    """Each dashboard file is valid JSON with required fields."""
    path = DASHBOARDS_DIR / f"{uid}.json"
    data = json.loads(path.read_text())
    assert "title" in data, f"{uid}.json missing 'title'"
    assert "panels" in data, f"{uid}.json missing 'panels'"
    assert data["uid"] == uid, f"{uid}.json has wrong uid: {data.get('uid')}"


@pytest.mark.parametrize("uid,spec", list(REQUIRED_DASHBOARDS.items()))
def test_dashboard_has_minimum_panels(uid, spec):
    """Each dashboard has the minimum required number of panels."""
    path = DASHBOARDS_DIR / f"{uid}.json"
    data = json.loads(path.read_text())
    panel_count = len(data.get("panels", []))
    assert panel_count >= spec["min_panels"], (
        f"{uid}.json has {panel_count} panels, need ≥ {spec['min_panels']}"
    )


@pytest.mark.parametrize("uid,spec", list(REQUIRED_DASHBOARDS.items()))
def test_dashboard_panels_cover_expected_topics(uid, spec):
    """Each dashboard's panel titles collectively cover the expected topics."""
    path = DASHBOARDS_DIR / f"{uid}.json"
    data = json.loads(path.read_text())
    panel_titles = " ".join(p.get("title", "") for p in data.get("panels", []))

    missing_topics = [
        kw for kw in spec["expected_panel_titles"]
        if kw.lower() not in panel_titles.lower()
    ]
    assert not missing_topics, (
        f"{uid}.json panels don't cover topics: {missing_topics}. "
        f"Panel titles: {panel_titles}"
    )


def test_provider_yaml_exists():
    """grafana/provisioning/dashboards/provider.yaml exists."""
    path = DASHBOARDS_DIR / "provider.yaml"
    assert path.exists(), f"Missing {path}"


def test_datasource_yaml_exists():
    """grafana/provisioning/datasources/prometheus.yaml exists."""
    path = REPO_ROOT / "infra" / "observability" / "grafana" / "provisioning" / "datasources" / "prometheus.yaml"
    assert path.exists(), f"Missing {path}"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (requires live Grafana)
# ─────────────────────────────────────────────────────────────────────────────

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3001")
GRAFANA_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PASS = os.getenv("GRAFANA_ADMIN_PASS", "admin")


@pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Integration test: requires running Grafana instance",
)
def test_grafana_api_lists_all_dashboards():
    """Grafana API lists all 4 required dashboards."""
    import httpx

    resp = httpx.get(
        f"{GRAFANA_URL}/api/search",
        params={"type": "dash-db", "tag": "mintkey"},
        auth=(GRAFANA_USER, GRAFANA_PASS),
        timeout=5.0,
    )
    assert resp.status_code == 200

    uids = {d["uid"] for d in resp.json()}
    missing = set(REQUIRED_DASHBOARDS.keys()) - uids
    assert not missing, f"Grafana missing dashboards: {missing}"


@pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Integration test: requires running Grafana instance",
)
@pytest.mark.parametrize("uid", list(REQUIRED_DASHBOARDS.keys()))
def test_grafana_dashboard_loads(uid):
    """Each dashboard loads cleanly via the Grafana API."""
    import httpx

    resp = httpx.get(
        f"{GRAFANA_URL}/api/dashboards/uid/{uid}",
        auth=(GRAFANA_USER, GRAFANA_PASS),
        timeout=5.0,
    )
    assert resp.status_code == 200, f"Dashboard {uid} returned {resp.status_code}"
    data = resp.json()
    assert data["dashboard"]["uid"] == uid
