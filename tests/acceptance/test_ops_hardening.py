"""
WS-7b acceptance test — memory monitoring + ops hardening.

Non-integration structural assertions run always; the integration gate is
MINTKEY_INTEGRATION_TEST=true (requires a running docker-compose stack).

Sources: PLAN.md WS-7b; ADR-0017.6; ADR-0018; ADR-0019.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

_ROOT = Path(__file__).parent.parent.parent


# ===========================================================================
# Alerting rules
# ===========================================================================


def test_alert_rules_file_exists() -> None:
    """alert_rules.yml must exist at the repo root."""
    path = _ROOT / "alert_rules.yml"
    assert path.exists(), f"Missing: {path}"


def test_alert_rules_yaml_valid() -> None:
    """alert_rules.yml must be valid YAML."""
    path = _ROOT / "alert_rules.yml"
    content = yaml.safe_load(path.read_text())
    assert "groups" in content, "alert_rules.yml must have a 'groups' key"


def test_required_alert_rules_present() -> None:
    """All 8 required alerting rules must be defined."""
    path = _ROOT / "alert_rules.yml"
    src = path.read_text()
    required = [
        "AuditChainTampered",
        "JwksEndpointDown",
        "VaultAdapterGrpcErrors",
        "ChangeChannelSubscriberLag",
        "DiskSpaceLow",
        "BootstrapSecretsMissing",
        "OtelCollectorDroppingSpans",
        "OperatorLoginFailureSpike",
    ]
    missing = [r for r in required if r not in src]
    assert not missing, f"Missing alerting rules: {missing}"


def test_mintkey_container_mem_high_alert_exists() -> None:
    """MintkeyContainerMemHigh alert must exist and use cAdvisor metrics."""
    path = _ROOT / "alert_rules.yml"
    src = path.read_text()
    assert "MintkeyContainerMemHigh" in src, "MintkeyContainerMemHigh alert missing"
    assert "container_memory_working_set_bytes" in src, "cAdvisor metric missing in alert"
    assert "container_spec_memory_limit_bytes" in src, "cAdvisor limit metric missing in alert"


# ===========================================================================
# Prometheus config
# ===========================================================================


def test_prometheus_loads_alert_rules() -> None:
    """prometheus.yml must reference the alert_rules.yml file."""
    prom = _ROOT / "prometheus.yml"
    src = prom.read_text()
    assert "alert_rules.yml" in src, "prometheus.yml must reference alert_rules.yml"
    assert "rule_files" in src, "prometheus.yml must have a rule_files section"


def test_prometheus_scrapes_cadvisor() -> None:
    """prometheus.yml must scrape cAdvisor for container memory metrics."""
    prom = _ROOT / "prometheus.yml"
    src = prom.read_text()
    assert "cadvisor" in src, "prometheus.yml missing cadvisor scrape target"


# ===========================================================================
# cAdvisor in compose
# ===========================================================================


def test_cadvisor_in_compose() -> None:
    """docker-compose.yml must include a cadvisor service."""
    compose = _ROOT / "docker-compose.yml"
    src = compose.read_text()
    assert "cadvisor" in src, "docker-compose.yml missing cAdvisor service"
    assert "container_memory" in src or "gcr.io/cadvisor" in src, (
        "cAdvisor image not referenced in docker-compose.yml"
    )


# ===========================================================================
# Grafana memory dashboard
# ===========================================================================


def test_grafana_memory_dashboard_exists() -> None:
    """A Grafana memory dashboard with cAdvisor panels must be provisioned."""
    dashboard_dir = _ROOT / "grafana" / "provisioning" / "dashboards"
    dashboards = list(dashboard_dir.glob("*.json"))
    contents = [d.read_text() for d in dashboards]
    has_memory = any(
        "container_memory_working_set_bytes" in c for c in contents
    )
    assert has_memory, "No Grafana dashboard contains container_memory_working_set_bytes"


# ===========================================================================
# Threat model updated
# ===========================================================================


def test_threat_model_has_adminjs_entry() -> None:
    """Threat model must document AdminJS private-key compromise (ADR-0019)."""
    tm = _ROOT / "docs" / "architecture" / "01-architecture" / "05-threat-model.md"
    assert tm.exists(), f"Missing: {tm}"
    src = tm.read_text()
    assert "AdminJS" in src and "private" in src.lower(), (
        "Threat model missing AdminJS private-key entry"
    )
    assert "ADR" in src and "0019" in src, "Threat model missing ADR-0019 reference"


def test_threat_model_has_classical_api_key_entry() -> None:
    """Threat model must document leaked classical API key (ADR-0018)."""
    tm = _ROOT / "docs" / "architecture" / "01-architecture" / "05-threat-model.md"
    src = tm.read_text()
    assert "mk_svckey" in src or "classical" in src.lower(), (
        "Threat model missing classical API key entry"
    )
    assert "ADR" in src and "0018" in src, "Threat model missing ADR-0018 reference"


# ===========================================================================
# Kiro spec updated (ADR-0019 model)
# ===========================================================================


def test_kiro_design_no_adminjs_sql_readonly() -> None:
    """Kiro design.md must not describe @adminjs/sql in read-only mode (ADR-0019 supersedes)."""
    design = _ROOT / ".kiro" / "specs" / "mintkey-mvp" / "design.md"
    assert design.exists(), f"Missing: {design}"
    src = design.read_text()
    assert "@adminjs/sql` adapter is used in **read-only mode**" not in src, (
        "Kiro design.md still references @adminjs/sql read-only (contradicts ADR-0019)"
    )


def test_kiro_design_no_connect_pg_simple_in_language_line() -> None:
    """Kiro design.md language line must not list connect-pg-simple (AdminJS has no DB connection)."""
    design = _ROOT / ".kiro" / "specs" / "mintkey-mvp" / "design.md"
    src = design.read_text()
    # The language line should not claim connect-pg-simple is part of the stack
    import re
    lang_line_match = re.search(r"\*\*Language:\*\*.*", src)
    if lang_line_match:
        lang_line = lang_line_match.group(0)
        assert "connect-pg-simple" not in lang_line or "no" in lang_line.lower(), (
            "Kiro design.md language line still claims connect-pg-simple without ADR-0019 caveat"
        )


# ===========================================================================
# Integration test (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_cadvisor_returns_metrics() -> None:
    """cAdvisor /metrics must return container_memory_working_set_bytes."""
    import httpx

    r = httpx.get("http://localhost:8088/metrics", timeout=10)
    assert r.status_code == 200
    assert "container_memory_working_set_bytes" in r.text


@INTEGRATION
def test_prometheus_alert_rules_loaded() -> None:
    """Prometheus must have loaded all required alert rules."""
    import httpx

    prom = os.getenv("MINTKEY_PROMETHEUS_URL", "http://localhost:9090")
    r = httpx.get(f"{prom}/api/v1/rules", timeout=10)
    assert r.status_code == 200
    rules_text = r.text
    for rule in ["MintkeyContainerMemHigh", "AuditChainTampered", "JwksEndpointDown"]:
        assert rule in rules_text, f"Prometheus rule not loaded: {rule}"
