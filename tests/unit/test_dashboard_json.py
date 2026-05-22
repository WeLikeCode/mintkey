"""Unit tests validating the Grafana request-monitoring dashboard JSON structure.

Validates: Requirements 3.1, 5.1, 8.4
"""
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_PATH = REPO_ROOT / "infra" / "observability" / "grafana" / "provisioning" / "dashboards" / "request-monitoring.json"


@pytest.fixture()
def dashboard():
    """Load and parse the dashboard JSON."""
    assert DASHBOARD_PATH.exists(), f"Dashboard file not found at {DASHBOARD_PATH}"
    return json.loads(DASHBOARD_PATH.read_text())


def test_dashboard_uid(dashboard):
    """Assert dashboard uid is 'mintkey-request-monitoring'."""
    assert dashboard["uid"] == "mintkey-request-monitoring"


def test_template_variable_agent_exists(dashboard):
    """Assert template variable 'agent' exists with correct query."""
    variables = dashboard["templating"]["list"]
    agent_vars = [v for v in variables if v["name"] == "agent"]
    assert len(agent_vars) == 1, "Expected exactly one 'agent' template variable"
    agent = agent_vars[0]
    assert agent["query"] == "label_values(mintkey_proxy_calls_total, mintkey_actor_id)"


def test_template_variable_service_exists(dashboard):
    """Assert template variable 'service' exists with correct query."""
    variables = dashboard["templating"]["list"]
    service_vars = [v for v in variables if v["name"] == "service"]
    assert len(service_vars) == 1, "Expected exactly one 'service' template variable"
    service = service_vars[0]
    assert service["query"] == "label_values(mintkey_proxy_calls_total, mintkey_service_id)"


def test_all_panels_reference_prometheus_datasource(dashboard):
    """Assert all 4 panels reference datasource uid 'prometheus'."""
    panels = dashboard["panels"]
    assert len(panels) == 4, f"Expected 4 panels, got {len(panels)}"
    for panel in panels:
        ds = panel.get("datasource", {})
        assert ds.get("uid") == "prometheus", (
            f"Panel '{panel.get('title')}' does not reference datasource uid 'prometheus'"
        )


def test_all_panel_queries_reference_template_variables(dashboard):
    """Assert all panel queries reference both $agent and $service template variables."""
    panels = dashboard["panels"]
    for panel in panels:
        targets = panel.get("targets", [])
        assert len(targets) > 0, f"Panel '{panel.get('title')}' has no targets"
        for target in targets:
            expr = target.get("expr", "")
            assert "$agent" in expr, (
                f"Panel '{panel.get('title')}' query does not reference $agent: {expr}"
            )
            assert "$service" in expr, (
                f"Panel '{panel.get('title')}' query does not reference $service: {expr}"
            )


def test_outcome_panel_color_overrides(dashboard):
    """Assert outcome panel has color overrides for all 5 outcome values."""
    panels = dashboard["panels"]
    outcome_panels = [p for p in panels if p.get("title") == "Outcome Breakdown"]
    assert len(outcome_panels) == 1, "Expected exactly one 'Outcome Breakdown' panel"
    outcome_panel = outcome_panels[0]

    overrides = outcome_panel.get("fieldConfig", {}).get("overrides", [])
    expected_outcomes = {"success", "client_error", "server_error", "denied", "error"}

    override_names = set()
    for override in overrides:
        matcher = override.get("matcher", {})
        if matcher.get("id") == "byName":
            name = matcher.get("options")
            # Verify it has a color property
            props = override.get("properties", [])
            has_color = any(p.get("id") == "color" for p in props)
            if has_color:
                override_names.add(name)

    assert override_names == expected_outcomes, (
        f"Expected color overrides for {expected_outcomes}, got {override_names}"
    )
