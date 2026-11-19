"""Acceptance checks for the data-plane-only guide.

The page must name every setting the profile needs and must not leak a
credential value that the compose file supplies to the proxy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "guides" / "data-plane-only.md"
COMPOSE = ROOT / "infra" / "compose" / "docker-compose.yml"

REQUIRED_NAMES = [
    "broker",
    "proxy-plugin",
    "vault-adapter",
    "MINTKEY_VAULT_BACKEND=sqlite",
    "MINTKEY_VAULT_FILE_PATH",
    "admin-api",
    "Kong",
    "kong-syncer",
    "mcp-server",
    "Keycloak",
    "MINTKEY_VAULT_KEK_FILE",
    "MINTKEY_BROKER_SIGNING_KEY_FILE",
    "MINTKEY_VAULT_PROXY_IDENTITY_ID",
    "MINTKEY_VAULT_PROXY_TOKEN",
    "PutCredential",
    "MINTKEY_VAULT_ADMIN_IDENTITY_ID",
    "MINTKEY_VAULT_ADMIN_TOKEN",
    "BROKER_ADDR",
    "VAULT_GRPC_ADDR",
    "PLUGIN_PORT",
    "POST /v1/issue",
    "X-Mintkey-Service-Token",
    "MINTKEY_MCP_SERVICE_TOKEN",
    "ttl_seconds",
    "methods",
    "path_prefix",
    "/v1/call/",
    "svc_",
    "MINTKEY_ENV=production",
    "MINTKEY_AUD_ENFORCEMENT",
    "service not addressed",
    "MINTKEY_ADMIN_API_URL",
    "POST /v1/internal/audit/emit",
    "MINTKEY_BROKER_SERVICE_TOKEN",
    "MINTKEY_PROXY_SERVICE_TOKEN",
    "event_type",
    "DATABASE_URL",
    "NOTIFY",
    "mintkey:agent",
    "token.revoked",
    "agent.revoked",
]


def _proxy_plugin_environment() -> list[tuple[str, Any]]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    environment = data["services"]["proxy-plugin"]["environment"]
    if isinstance(environment, list):
        pairs: list[tuple[str, Any]] = []
        for item in environment:
            key, _, value = str(item).partition("=")
            pairs.append((key, value))
        return pairs
    return list(environment.items())


def _proxy_plugin_token_values() -> list[str]:
    values: list[str] = []
    for key, value in _proxy_plugin_environment():
        if not key.endswith("_TOKEN"):
            continue
        if not isinstance(value, str):
            continue
        if len(value) < 16 or "${" in value:
            continue
        values.append(value)
    return values


@pytest.mark.l4("C-f81bbc6f")
def test_data_plane_doc_names_every_setting() -> None:
    assert DOC.is_file(), f"missing file: {DOC}"
    text = DOC.read_text(encoding="utf-8")
    missing = [name for name in REQUIRED_NAMES if name not in text]
    assert not missing, (
        "docs/guides/data-plane-only.md does not name: " + ", ".join(missing)
    )


@pytest.mark.l4("C-f81bbc6f")
def test_data_plane_doc_has_no_mermaid_and_no_credential_values() -> None:
    assert DOC.is_file(), f"missing file: {DOC}"
    text = DOC.read_text(encoding="utf-8")
    assert "```mermaid" not in text, (
        "docs/guides/data-plane-only.md must not contain a mermaid fence"
    )
    token_values = _proxy_plugin_token_values()
    assert token_values, (
        "no proxy-plugin *_TOKEN value in infra/compose/docker-compose.yml is long "
        "enough and literal; the leak check would be vacuous"
    )
    leaked = [value for value in token_values if value in text]
    assert not leaked, (
        f"docs/guides/data-plane-only.md leaks {len(leaked)} proxy-plugin token "
        "value(s) from infra/compose/docker-compose.yml"
    )
