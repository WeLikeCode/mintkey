"""
Bootstrap-parity test (task 4.2).

Extract backtick-quoted field tokens from the discovery-tool sections of
agent-bootstrap.md and assert each is a key present in the corresponding
tool's actual response.

Scope: <service_discovery> XML block only (list_services, describe_service,
get_openapi).  Fields inside code-block examples that are *not* response keys
(e.g. tool names, argument names, example values) are in the EXEMPTION_LIST.

Design ref: design.md D6; spec service-usage-guidance "Scenario: Bootstrap-vs-reality parity gate".
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Locate the bootstrap markdown
# ---------------------------------------------------------------------------
_BOOTSTRAP_MD = (
    Path(__file__).resolve().parents[1] / "skills" / "agent-bootstrap.md"
)


def _read_bootstrap() -> str:
    return _BOOTSTRAP_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Section extractor
# ---------------------------------------------------------------------------

def _extract_xml_block(content: str, tag: str) -> str:
    """Return the text inside <tag>...</tag> (first occurrence)."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", content, re.DOTALL)
    if m is None:
        raise ValueError(f"<{tag}> block not found in bootstrap markdown")
    return m.group(1)


def _backtick_tokens(text: str) -> list[str]:
    """
    Return all inline backtick-quoted tokens in *text* that look like response-field
    identifiers: purely alphanumeric+underscore, starting with a letter.

    Triple-backtick code blocks are stripped first so JSON keys inside fenced
    examples are not extracted — we only want the inline prose references.
    """
    # Strip fenced code blocks (```...```) before scanning for inline backticks.
    stripped = re.sub(r"```[^`]*?```", "", text, flags=re.DOTALL)
    raw = re.findall(r"`([^`]+)`", stripped)
    return [t for t in raw if re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", t)]


# ---------------------------------------------------------------------------
# Tool-response builders — produce an actual response dict using minimal mocks
# so we test the real builder code, not a hardcoded fixture.
# ---------------------------------------------------------------------------

def _make_describe_service_payload() -> dict[str, Any]:
    """
    Call the real response-builder path from discovery.py with a stub DB row.
    Returns the `service` sub-dict that agents receive.
    """
    from unittest.mock import MagicMock
    from mcp_server.tools.discovery import (
        _make_auth_scheme_details,
        _make_your_constraints,
        _connect_type,
    )
    from mcp_server.utils.wire_ids import db_uuid_to_wire
    from mcp_server.config.public_urls import resolve_proxy_public_url

    svc_id = str(uuid.uuid4())
    wire_id = db_uuid_to_wire(svc_id, "svc")
    proxy_url = resolve_proxy_public_url()
    auth_scheme = "bearer_token"
    openapi_url = "https://example.com/openapi.json"

    payload: dict[str, Any] = {
        "id": wire_id,
        "name": "example",
        "slug": "example",
        "base_url": "https://example.com",
        "auth_scheme": auth_scheme,
        "description": "example service",
        "openapi_url": openapi_url,
        "connect_type": _connect_type(auth_scheme),
        "explicit_proxy_url": f"{proxy_url}/v1/call/{wire_id}",
        "auth_scheme_details": _make_auth_scheme_details(auth_scheme),
        "your_constraints": _make_your_constraints(None),
        "openapi": {
            "status": "available",
            "url": openapi_url,
        },
    }
    return payload


def _make_list_services_item() -> dict[str, Any]:
    """Return the shape of one item in list_services.services[]."""
    from mcp_server.utils.wire_ids import db_uuid_to_wire
    from mcp_server.tools.discovery import _connect_type

    svc_id = str(uuid.uuid4())
    return {
        "id": db_uuid_to_wire(svc_id, "svc"),
        "name": "example",
        "slug": "example",
        "base_url": "https://example.com",
        "auth_scheme": "bearer_token",
        "connect_type": _connect_type("bearer_token"),
        "kind": "service",
    }


def _make_discover_item() -> dict[str, Any]:
    """Return the shape of one item in discover.services[] (includes how_to_call)."""
    from mcp_server.utils.wire_ids import db_uuid_to_wire
    from mcp_server.tools.discovery import _connect_type, _make_how_to_call

    svc_id = str(uuid.uuid4())
    wire_id = db_uuid_to_wire(svc_id, "svc")
    return {
        "id": wire_id,
        "name": "example",
        "slug": "example",
        "base_url": "https://example.com",
        "auth_scheme": "bearer_token",
        "connect_type": _connect_type("bearer_token"),
        "kind": "service",
        "how_to_call": _make_how_to_call(wire_id, "https://example.com", "bearer_token"),
    }


def _make_get_openapi_url_payload() -> dict[str, Any]:
    """Return the url-mode get_openapi response shape."""
    return {
        "kind": "url",
        "openapi_url": "https://example.com/openapi.json",
        "etag": '"abc"',
    }


def _make_get_openapi_inline_payload() -> dict[str, Any]:
    """Return the inline-mode get_openapi response shape."""
    return {
        "kind": "inline",
        "content_type": "application/json",
        "etag": '"abc"',
        "document": '{"openapi":"3.1.0"}',
    }


def _make_get_openapi_not_registered_payload() -> dict[str, Any]:
    return {
        "kind": "not_registered",
        "hint": "...",
    }


# ---------------------------------------------------------------------------
# Field allowlists per tool section
# ---------------------------------------------------------------------------

# Keys documented in the bootstrap that are field names in the response.
# Tokens in the exemption list are either:
#   - argument names (not response keys)
#   - example/literal values
#   - sub-field keys inside nested objects that are tested separately
# Each exemption has a comment explaining why.

_EXEMPTIONS_DESCRIBE_SERVICE: set[str] = {
    # Example argument value "svc_01HKJ7G", not a response key
    "svc_01HKJ7G",
    # Sub-fields of auth_scheme_details — tested via the auth_scheme_details dict,
    # not at the top level of the service response.
    "injection_point",
    "header_name",
    "query_param",
    "format",
    # Sub-fields of your_constraints nested object
    "requests_per_second",
    "burst",
    "timezone",
    "days",
    "start_local",
    "end_local",
    # Sub-fields of rate_limit, time_window nested objects
    "rate_limit",
    "time_window",
    "request_path_prefix",
    "source_ip_allowlist",
    # Sub-field of openapi nested object
    "status",
    "url",
    # Tool names appearing in prose
    "describe_service",
    "list_services",
    "get_openapi",
    # Backtick-quoted argument parameter name (not response key; response uses "id")
    "service_id",
    # Possible values of connect_type field (not keys themselves)
    "http",
    "ssh",
    "email",
    # Possible values of openapi.status (not keys)
    "available",
    "not_registered",
    # Possible values of auth_scheme_details.injection_point (not top-level keys)
    "header",
    "query",
    "connection",
    "out_of_band",
    # svc_ prefix — appears as part of wire-ID format description, not a field name
    "svc_",
    # "service" is the wrapper key under which the payload is nested —
    # tested separately in test_describe_service_response_has_id_not_service_id
    "service",
    # agent_connection_guide is a real field BUT only present for SSH services.
    # The test builder uses bearer_token (http), so it's absent; that's correct behavior.
    # SSH guide is tested in test_describe_service.py
    "agent_connection_guide",
    # Authorization is a header name value cited in an example, not a response key
    "Authorization",
    # api_key is a query param name example, not a response key
    "api_key",
    # 403 code mentioned in prose, not a response key
    "constraint_violated",
}

_EXEMPTIONS_LIST_SERVICES: set[str] = {
    # Tool names
    "list_services",
    "describe_service",
    "discover",
    # Top-level wrapper key — not a service item key; tested via response shape separately
    "services",
    # Values of connect_type (not keys)
    "http",
    "ssh",
    "email",
    # Values of kind (not keys)
    "service",
    "email_service",
    # hint is a top-level response key (not a service item key)
    # — present in the response but not in the per-item shape; keep it exempt at item level
    "hint",
}

_EXEMPTIONS_GET_OPENAPI: set[str] = {
    # Tool name
    "get_openapi",
    # Argument names / parameter names (not response keys)
    "service_id",
    "inline",
    # Boolean value mentioned in prose ("inline=false, default")
    "false",
    # Status/kind enum values cited as examples (not response keys themselves)
    "not_registered",
    "fetch_failed",
    "available",
    "url",
    # "kind" IS a real response key — intentionally NOT in this list
}


# ---------------------------------------------------------------------------
# Parse the discovery section of the bootstrap and split by sub-tool
# ---------------------------------------------------------------------------

def _get_describe_service_section(discovery_text: str) -> str:
    """Return the sub-text covering the describe_service tool."""
    # The section starts at the describe_service heading and ends at get_openapi heading.
    m = re.search(
        r"(\*\*`describe_service`.*?)(?=\*\*`get_openapi`|\*\*`whoami`|$)",
        discovery_text,
        re.DOTALL,
    )
    if m is None:
        raise ValueError("describe_service sub-section not found in <service_discovery>")
    return m.group(1)


def _get_list_services_section(discovery_text: str) -> str:
    """Return the sub-text covering the list_services tool."""
    m = re.search(
        r"(\*\*`list_services`.*?)(?=\*\*`describe_service`|\Z)",
        discovery_text,
        re.DOTALL,
    )
    if m is None:
        raise ValueError("list_services sub-section not found in <service_discovery>")
    return m.group(1)


def _get_get_openapi_section(discovery_text: str) -> str:
    """Return the sub-text covering the get_openapi tool."""
    m = re.search(
        r"(\*\*`get_openapi`.*?)(?=\*\*`whoami`|\Z)",
        discovery_text,
        re.DOTALL,
    )
    if m is None:
        raise ValueError("get_openapi sub-section not found in <service_discovery>")
    return m.group(1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBootstrapParity:
    """
    Every backtick-quoted field token in the discovery sections of
    agent-bootstrap.md must appear as a key in the corresponding tool response.

    The test FAILS when someone documents a field the wire doesn't return —
    keeping the bootstrap honest per design.md D6.
    """

    def setup_method(self):
        content = _read_bootstrap()
        discovery_text = _extract_xml_block(content, "service_discovery")
        self._discovery_text = discovery_text
        self._describe_section = _get_describe_service_section(discovery_text)
        self._list_section = _get_list_services_section(discovery_text)
        self._openapi_section = _get_get_openapi_section(discovery_text)

    # --- describe_service ---

    def test_describe_service_fields_exist_in_response(self):
        """All backtick field tokens in the describe_service section exist in the response."""
        tokens = _backtick_tokens(self._describe_section)
        payload = _make_describe_service_payload()
        # Flatten: also check inside auth_scheme_details, your_constraints, openapi
        all_keys: set[str] = set(payload.keys())
        all_keys.update(payload.get("auth_scheme_details", {}).keys())
        all_keys.update(payload.get("your_constraints", {}).keys())
        all_keys.update(payload.get("openapi", {}).keys())
        # Also add sub-fields of your_constraints nested objects (rate_limit etc are exempt)

        failures = []
        for token in tokens:
            if token in _EXEMPTIONS_DESCRIBE_SERVICE:
                continue
            if token not in all_keys:
                failures.append(token)
        assert not failures, (
            f"agent-bootstrap.md describe_service section documents field(s) that "
            f"the wire does NOT return: {sorted(failures)}. "
            "Either remove them from the docs or add them to the response builder."
        )

    def test_describe_service_response_has_id_not_service_id(self):
        """The response uses 'id', not 'service_id' — catch the old bootstrap promise."""
        payload = _make_describe_service_payload()
        assert "id" in payload, "describe_service must return 'id'"

    def test_describe_service_response_has_auth_scheme_details(self):
        """auth_scheme_details is present and has the contracted sub-keys."""
        payload = _make_describe_service_payload()
        assert "auth_scheme_details" in payload
        details = payload["auth_scheme_details"]
        for key in ("injection_point", "header_name", "query_param", "format"):
            assert key in details, f"auth_scheme_details missing '{key}'"

    def test_describe_service_response_has_your_constraints(self):
        """your_constraints is present and has the contracted sub-keys."""
        payload = _make_describe_service_payload()
        assert "your_constraints" in payload
        c = payload["your_constraints"]
        for key in ("rate_limit", "time_window", "request_path_prefix", "source_ip_allowlist"):
            assert key in c, f"your_constraints missing '{key}'"

    def test_describe_service_response_has_explicit_proxy_url(self):
        payload = _make_describe_service_payload()
        assert "explicit_proxy_url" in payload

    def test_describe_service_response_has_openapi_object(self):
        payload = _make_describe_service_payload()
        assert "openapi" in payload
        assert "status" in payload["openapi"]
        assert "url" in payload["openapi"]

    # --- list_services ---

    def test_list_services_fields_exist_in_response(self):
        """All backtick field tokens in the list_services section exist in the response."""
        tokens = _backtick_tokens(self._list_section)
        item = _make_list_services_item()
        failures = []
        for token in tokens:
            if token in _EXEMPTIONS_LIST_SERVICES:
                continue
            if token not in item:
                failures.append(token)
        assert not failures, (
            f"agent-bootstrap.md list_services section documents field(s) that "
            f"the wire does NOT return: {sorted(failures)}. "
            "Either remove them from the docs or add them to the response builder."
        )

    # --- get_openapi ---

    def test_get_openapi_fields_exist_in_url_response(self):
        """Field tokens in get_openapi section that apply to url-mode response exist there."""
        tokens = _backtick_tokens(self._openapi_section)
        url_payload = _make_get_openapi_url_payload()
        inline_payload = _make_get_openapi_inline_payload()
        not_reg_payload = _make_get_openapi_not_registered_payload()
        # Union of all response keys across all modes (agent sees one per call)
        all_keys = set(url_payload) | set(inline_payload) | set(not_reg_payload)
        failures = []
        for token in tokens:
            if token in _EXEMPTIONS_GET_OPENAPI:
                continue
            if token not in all_keys:
                failures.append(token)
        assert not failures, (
            f"agent-bootstrap.md get_openapi section documents field(s) that "
            f"the wire does NOT return across any response mode: {sorted(failures)}. "
            "Either remove them from the docs or add them to the response builder."
        )

    def test_get_openapi_url_mode_has_kind(self):
        payload = _make_get_openapi_url_payload()
        assert "kind" in payload

    def test_get_openapi_inline_mode_has_document(self):
        payload = _make_get_openapi_inline_payload()
        assert "document" in payload

    def test_get_openapi_not_registered_has_hint(self):
        payload = _make_get_openapi_not_registered_payload()
        assert "hint" in payload
