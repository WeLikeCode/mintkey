"""Unit tests validating OTel Collector config structure.

Validates Requirements 7.3 and 7.6:
- spanmetrics connector is defined and wired into both pipelines
- spanmetrics filters only mintkey.proxy.handle_request spans
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = REPO_ROOT / "infra" / "observability" / "otel-collector-config.yaml"


def _load_config() -> dict:
    """Load and parse the OTel Collector config YAML."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def test_spanmetrics_exists_under_connectors():
    """Assert spanmetrics is defined under the connectors key."""
    config = _load_config()
    assert "connectors" in config, "Missing top-level 'connectors' key"
    assert "spanmetrics" in config["connectors"], (
        "Missing 'spanmetrics' under connectors"
    )


def test_spanmetrics_in_traces_exporters():
    """Assert spanmetrics appears in service.pipelines.traces.exporters."""
    config = _load_config()
    traces_exporters = config["service"]["pipelines"]["traces"]["exporters"]
    assert "spanmetrics" in traces_exporters, (
        "spanmetrics not found in traces pipeline exporters"
    )


def test_spanmetrics_in_metrics_receivers():
    """Assert spanmetrics appears in service.pipelines.metrics.receivers."""
    config = _load_config()
    metrics_receivers = config["service"]["pipelines"]["metrics"]["receivers"]
    assert "spanmetrics" in metrics_receivers, (
        "spanmetrics not found in metrics pipeline receivers"
    )


def test_spanmetrics_include_span_names():
    """Assert include.span_names contains exactly ['mintkey.proxy.handle_request']."""
    config = _load_config()
    spanmetrics = config["connectors"]["spanmetrics"]
    include = spanmetrics["include"]
    assert include["span_names"] == ["mintkey.proxy.handle_request"], (
        f"Expected span_names=['mintkey.proxy.handle_request'], "
        f"got {include['span_names']}"
    )


def test_spanmetrics_namespace():
    """Assert connectors.spanmetrics.namespace is 'mintkey_proxy'."""
    config = _load_config()
    spanmetrics = config["connectors"]["spanmetrics"]
    assert spanmetrics["namespace"] == "mintkey_proxy", (
        f"Expected namespace='mintkey_proxy', got {spanmetrics['namespace']}"
    )
