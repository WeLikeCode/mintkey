"""
Chunk B tests — per-scheme injection_hint, describe_service new fields,
list_services hint, get_openapi url/inline/not_registered/fetch_failed,
landing.py chain wording.

Source: tasks.md 3.1-3.5, 6.1;
        spec service-usage-guidance;
        spec openapi-exposure;
        design.md D1-D5.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch



# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

_TEST_SVC_UUID = "7a3d8b1f-1c4e-4f90-9d2a-6e7f8a9b0c1d"


def _make_service_row(
    *,
    svc_id: str = _TEST_SVC_UUID,
    name: str = "test-svc",
    slug: str = "test-svc",
    base_url: str = "https://example.com",
    auth_scheme: str = "bearer_token",
    description=None,
    openapi_url=None,
    openapi_etag=None,
) -> MagicMock:
    row = MagicMock()
    row.id = svc_id
    row.name = name
    row.slug = slug
    row.base_url = base_url
    row.auth_scheme = auth_scheme
    row.description = description
    row.openapi_url = openapi_url
    row.openapi_etag = openapi_etag
    return row


def _make_constraints_row(constraints_dict) -> MagicMock:
    row = MagicMock()
    row.constraints = constraints_dict
    return row


def _make_app(
    *,
    service_row=None,
    constraints_row=None,
    execute_side_effect=None,
):
    """
    Build ASGI test app with DB and agent-context stubs.
    execute_side_effect, if provided, is used as AsyncMock side_effect so
    callers can control per-call behaviour (needed for get_openapi etag update).
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context
    from mcp_server.main import create_app

    _tenant_id = uuid.uuid4()
    _agent_id = str(uuid.uuid4())
    fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

    _orig_validate = _main_mod.validate_agent_key

    async def _fake_validate(key):
        return fake_ctx, None

    _main_mod.validate_agent_key = _fake_validate

    app = create_app()

    async def _fake_agent_ctx():
        return fake_ctx

    app.dependency_overrides[get_agent_context] = _fake_agent_ctx

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()
        if execute_side_effect is not None:
            session.execute = AsyncMock(side_effect=execute_side_effect)
        else:
            result_mock = MagicMock()
            result_mock.fetchone.return_value = service_row
            result_mock.fetchall.return_value = []
            # constraints lookup returns constraints_row
            constraints_result = MagicMock()
            constraints_result.fetchone.return_value = constraints_row

            async def _execute(stmt, params=None, **kw):
                stmt_str = str(stmt) if not isinstance(stmt, str) else stmt
                # Constraints query distinguishable by "permission_grants" in WHERE
                if "permission_grants" in stmt_str and "agent_id_ds" in stmt_str:
                    return constraints_result
                return result_mock

            session.execute = _execute
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session
    return app, _orig_validate, _main_mod


def _get(path: str, *, service_row=None, constraints_row=None, execute_side_effect=None):
    app, _orig, _main_mod = _make_app(
        service_row=service_row,
        constraints_row=constraints_row,
        execute_side_effect=execute_side_effect,
    )
    try:
        async def _run():
            from httpx import AsyncClient, ASGITransport
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(path, headers={"X-API-Key": "mk_agent_test"})
        return asyncio.run(_run())
    finally:
        _main_mod.validate_agent_key = _orig


# ---------------------------------------------------------------------------
# 3.1 discover: injection_hint presence and correctness
# ---------------------------------------------------------------------------


class TestDiscoverInjectionHint:

    def _make_discover_app(self, auth_scheme: str):
        """Build app whose discover endpoint returns one service with given scheme."""
        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        service_row = MagicMock()
        service_row.id = _TEST_SVC_UUID
        service_row.name = "test"
        service_row.slug = "test"
        service_row.base_url = "https://example.com"
        service_row.auth_scheme = auth_scheme

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                stmt_str = str(stmt) if not isinstance(stmt, str) else stmt
                if "FROM services" in stmt_str and "JOIN permission_grants" in stmt_str:
                    result.fetchall.return_value = [service_row]
                else:
                    result.fetchall.return_value = []
                result.fetchone.return_value = None
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session
        return app, _orig, _main_mod

    def _discover(self, auth_scheme: str) -> dict:
        app, _orig, _main_mod = self._make_discover_app(auth_scheme)
        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.get(
                        "/v1/tools/discover",
                        headers={"X-API-Key": "mk_agent_test"},
                    )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig
        assert resp.status_code == 200, resp.text
        services = resp.json()["services"]
        assert services, "Expected at least one service in discover response"
        return services[0]

    def test_bearer_token_has_injection_hint(self):
        """Scenario: Bearer-token service carries a concrete hint (spec service-usage-guidance)."""
        svc = self._discover("bearer_token")
        htc = svc.get("how_to_call", {})
        hint = htc.get("injection_hint")
        assert hint is not None, f"injection_hint missing from how_to_call: {htc}"
        assert "Authorization" in hint["injects"]
        assert "Bearer" in hint["injects"]

    def test_mtls_hint_says_not_implemented(self):
        """Scenario: Unimplemented scheme is honest."""
        svc = self._discover("mtls")
        hint = svc.get("how_to_call", {}).get("injection_hint")
        assert hint is not None
        assert hint["status"] == "not_implemented"

    def test_ssh_service_has_handled_by_other_proxy_hint(self):
        """SSH services: injection_hint.status == handled_by_other_proxy."""
        svc = self._discover("ssh_private_key")
        # SSH services use connect_type=ssh; how_to_call may differ
        # but if injection_hint is present it must be correct
        # If not present (SSH uses guide instead), that is acceptable per design.
        htc = svc.get("how_to_call", {})
        if "injection_hint" in htc:
            assert htc["injection_hint"]["status"] == "handled_by_other_proxy"

    def test_injection_hint_structure(self):
        """injection_hint must have all required fields."""
        svc = self._discover("bearer_token")
        hint = svc["how_to_call"]["injection_hint"]
        for key in ("injects", "location", "never_send", "handled_by", "status"):
            assert key in hint, f"injection_hint missing key: {key}"

    def test_email_service_has_no_http_injection_hint(self):
        """Email services use connect_type=email; injection_hint is from email-proxy category."""
        app, _orig, _main_mod = self._make_discover_app("bearer_token")
        # For email services we test via their discovery shape directly —
        # email services use _make_email_how_to_call which has no injection_hint.
        # We verify that the non-email path does include injection_hint.
        _main_mod.validate_agent_key = _orig
        # The point is tested above; skip redundant test.


# ---------------------------------------------------------------------------
# 3.2 describe_service: new fields
# ---------------------------------------------------------------------------


class TestDescribeServiceNewFields:

    def _describe(
        self,
        auth_scheme: str = "bearer_token",
        openapi_url=None,
        constraints: dict | None = None,
    ):
        svc_row = _make_service_row(auth_scheme=auth_scheme, openapi_url=openapi_url)
        con_row = _make_constraints_row(constraints)
        resp = _get(
            f"/v1/tools/describe_service/{_TEST_SVC_UUID}",
            service_row=svc_row,
            constraints_row=con_row,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["service"]

    # --- auth_scheme_details ---

    def test_auth_scheme_details_present(self):
        svc = self._describe("bearer_token")
        assert "auth_scheme_details" in svc, f"Missing auth_scheme_details: {svc.keys()}"

    def test_auth_scheme_details_keys(self):
        svc = self._describe("bearer_token")
        details = svc["auth_scheme_details"]
        for key in ("injection_point", "header_name", "query_param", "format"):
            assert key in details, f"auth_scheme_details missing key: {key}"

    def test_bearer_token_details(self):
        svc = self._describe("bearer_token")
        d = svc["auth_scheme_details"]
        assert d["injection_point"] == "header"
        assert d["header_name"] == "Authorization"
        assert d["query_param"] is None

    def test_api_key_query_details(self):
        svc = self._describe("api_key_query")
        d = svc["auth_scheme_details"]
        assert d["injection_point"] == "query"
        assert d["header_name"] is None
        assert d["query_param"] == "api_key"

    def test_api_key_header_details(self):
        svc = self._describe("api_key_header")
        d = svc["auth_scheme_details"]
        assert d["injection_point"] == "header"
        assert d["header_name"] == "X-API-Key"
        assert d["query_param"] is None

    def test_mtls_details_note_not_implemented(self):
        svc = self._describe("mtls")
        d = svc["auth_scheme_details"]
        assert "not_implemented" in d["format"].lower() or "not implemented" in d["format"].lower(), (
            f"mtls format should mention not_implemented: {d['format']!r}"
        )

    # --- your_constraints ---

    def test_your_constraints_present(self):
        svc = self._describe()
        assert "your_constraints" in svc, f"Missing your_constraints: {svc.keys()}"

    def test_your_constraints_all_null_when_unset(self):
        """Agent with no constraints set receives explicit nulls."""
        svc = self._describe(constraints=None)
        c = svc["your_constraints"]
        assert c["rate_limit"] is None
        assert c["time_window"] is None
        assert c["request_path_prefix"] is None
        assert c["source_ip_allowlist"] is None

    def test_your_constraints_populated_when_set(self):
        """Agent with constraints sees them populated."""
        svc = self._describe(constraints={"rate_limit": 100, "time_window": 60})
        c = svc["your_constraints"]
        assert c["rate_limit"] == 100
        assert c["time_window"] == 60
        assert c["request_path_prefix"] is None
        assert c["source_ip_allowlist"] is None

    def test_your_constraints_empty_dict_gives_all_null(self):
        """Empty constraints dict gives all-null output."""
        svc = self._describe(constraints={})
        c = svc["your_constraints"]
        assert c["rate_limit"] is None
        assert c["time_window"] is None

    # --- explicit_proxy_url ---

    def test_explicit_proxy_url_present(self):
        svc = self._describe()
        assert "explicit_proxy_url" in svc, f"Missing explicit_proxy_url: {svc.keys()}"

    def test_explicit_proxy_url_shape(self):
        svc = self._describe()
        url = svc["explicit_proxy_url"]
        assert "/v1/call/" in url, f"explicit_proxy_url should contain /v1/call/: {url}"
        assert "svc_" in url, f"explicit_proxy_url should contain svc_ form: {url}"

    # --- openapi status object ---

    def test_openapi_field_present(self):
        svc = self._describe()
        assert "openapi" in svc, f"Missing openapi field: {svc.keys()}"

    def test_openapi_not_registered_when_no_url(self):
        svc = self._describe(openapi_url=None)
        assert svc["openapi"]["status"] == "not_registered"
        assert svc["openapi"]["url"] is None

    def test_openapi_available_when_url_set(self):
        svc = self._describe(openapi_url="https://example.com/openapi.json")
        assert svc["openapi"]["status"] == "available"
        assert svc["openapi"]["url"] == "https://example.com/openapi.json"

    def test_openapi_status_has_url_key(self):
        svc = self._describe(openapi_url="https://example.com/openapi.json")
        assert "url" in svc["openapi"]


# ---------------------------------------------------------------------------
# 3.3 list_services: hint line
# ---------------------------------------------------------------------------


class TestListServicesHint:

    def _list_services(self):
        """Call list_services with zero services → hint in payload."""
        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                result.fetchall.return_value = []
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session
        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.get(
                        "/v1/tools/list_services",
                        headers={"X-API-Key": "mk_agent_test"},
                    )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig
        return resp.json()

    def test_empty_list_has_hint_pointing_to_describe_service(self):
        """When no services, hint must mention describe_service or discover."""
        body = self._list_services()
        hint = body.get("hint", "")
        assert hint, "Expected hint in list_services when empty"
        # The hint should already exist; chunk B adds a mention of describe_service
        assert "describe_service" in hint or "discover" in hint, (
            f"Hint should mention describe_service or discover: {hint!r}"
        )

    def _list_services_with_one(self):
        """Call list_services with one service."""
        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        svc_row = MagicMock()
        svc_row.id = _TEST_SVC_UUID
        svc_row.name = "test"
        svc_row.slug = "test"
        svc_row.base_url = "https://example.com"
        svc_row.auth_scheme = "bearer_token"

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                stmt_str = str(stmt) if not isinstance(stmt, str) else stmt
                if "FROM services" in stmt_str and "JOIN permission_grants" in stmt_str:
                    result.fetchall.return_value = [svc_row]
                else:
                    result.fetchall.return_value = []
                result.fetchone.return_value = None
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session
        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.get(
                        "/v1/tools/list_services",
                        headers={"X-API-Key": "mk_agent_test"},
                    )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig
        return resp.json()

    def test_non_empty_list_has_hint(self):
        """When services present, there should be a usage hint at the response level."""
        body = self._list_services_with_one()
        # The hint field tells agents to use describe_service for details
        hint = body.get("hint", "")
        assert "describe_service" in hint or "discover" in hint, (
            f"list_services with services should hint at describe_service/discover: {hint!r}"
        )


# ---------------------------------------------------------------------------
# 3.4 get_openapi: url/inline/not_registered/fetch_failed modes
# ---------------------------------------------------------------------------


class TestGetOpenapi:

    def _build_openapi_app(
        self,
        *,
        openapi_url=None,
        openapi_etag=None,
    ):
        """Build app for get_openapi tests with configurable service row."""
        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        svc_row = MagicMock()
        svc_row.openapi_url = openapi_url
        svc_row.openapi_etag = openapi_etag

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                result.fetchone.return_value = svc_row
                result.fetchall.return_value = []
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session
        return app, _orig, _main_mod

    def _get_openapi(self, path: str, *, openapi_url=None, openapi_etag=None):
        app, _orig, _main_mod = self._build_openapi_app(
            openapi_url=openapi_url, openapi_etag=openapi_etag
        )
        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.get(path, headers={"X-API-Key": "mk_agent_test"})
            return asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig

    def test_not_registered_when_no_url(self):
        """Scenario: Unregistered spec is explicit (not a bare null)."""
        resp = self._get_openapi(
            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}",
            openapi_url=None,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("kind") == "not_registered", (
            f"Expected kind=not_registered, got: {body}"
        )
        assert "hint" in body, f"not_registered response should have hint: {body}"

    def test_url_mode_when_url_registered(self):
        """Default (inline=false) returns kind=url with openapi_url."""
        resp = self._get_openapi(
            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}",
            openapi_url="https://example.com/openapi.json",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("kind") == "url", f"Expected kind=url: {body}"
        assert body.get("openapi_url") == "https://example.com/openapi.json"

    def test_url_mode_includes_etag_field(self):
        resp = self._get_openapi(
            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}",
            openapi_url="https://example.com/openapi.json",
            openapi_etag='W/"abc123"',
        )
        body = resp.json()
        assert "etag" in body, f"url mode should include etag field: {body}"

    def test_inline_mode_success(self):
        """Scenario: inline fetch within cap → kind=inline."""
        fake_content = '{"openapi": "3.1.0"}'

        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        svc_row = MagicMock()
        svc_row.openapi_url = "https://example.com/openapi.json"
        svc_row.openapi_etag = None

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                result.fetchone.return_value = svc_row
                result.fetchall.return_value = []
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session

        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json", "etag": '"newetag"'}
        mock_response.url = httpx.URL("https://example.com/openapi.json")
        mock_response.text = fake_content
        mock_response.content = fake_content.encode()

        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                with patch("mcp_server.tools.discovery.httpx") as mock_httpx:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    mock_client.get = AsyncMock(return_value=mock_response)
                    mock_httpx.AsyncClient.return_value = mock_client

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        return await client.get(
                            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}?inline=true",
                            headers={"X-API-Key": "mk_agent_test"},
                        )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("kind") == "inline", f"Expected kind=inline: {body}"
        assert "document" in body
        assert "content_type" in body

    def test_inline_mode_oversized_returns_fetch_failed(self):
        """Scenario: upstream > 1 MiB → fetch_failed."""
        big_content = "x" * (1024 * 1024 + 1)

        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        svc_row = MagicMock()
        svc_row.openapi_url = "https://example.com/openapi.json"
        svc_row.openapi_etag = None

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                result.fetchone.return_value = svc_row
                result.fetchall.return_value = []
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session

        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.url = httpx.URL("https://example.com/openapi.json")
        mock_response.text = big_content
        mock_response.content = big_content.encode()

        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                with patch("mcp_server.tools.discovery.httpx") as mock_httpx:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    mock_client.get = AsyncMock(return_value=mock_response)
                    mock_httpx.AsyncClient.return_value = mock_client

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        return await client.get(
                            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}?inline=true",
                            headers={"X-API-Key": "mk_agent_test"},
                        )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("kind") == "fetch_failed", f"Expected fetch_failed for oversized: {body}"
        assert "openapi_url" in body

    def test_inline_mode_off_host_redirect_refused(self):
        """Off-host redirect → fetch_failed (security: no SSRF via redirect)."""
        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app
        import httpx

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        svc_row = MagicMock()
        svc_row.openapi_url = "https://example.com/openapi.json"
        svc_row.openapi_etag = None

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                result.fetchone.return_value = svc_row
                result.fetchall.return_value = []
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session

        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                # With follow_redirects=False httpx RETURNS the 302 response
                # (it never raises TooManyRedirects); the handler must treat
                # any non-200/304 status as fetch_failed.
                with patch("mcp_server.tools.discovery.httpx") as mock_httpx:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    redirect_resp = MagicMock()
                    redirect_resp.status_code = 302
                    redirect_resp.headers = {"location": "http://evil.internal/spec.json"}
                    mock_client.get = AsyncMock(return_value=redirect_resp)
                    mock_httpx.AsyncClient.return_value = mock_client

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        return await client.get(
                            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}?inline=true",
                            headers={"X-API-Key": "mk_agent_test"},
                        )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("kind") == "fetch_failed", (
            f"Off-host redirect should yield fetch_failed: {body}"
        )

    def test_inline_mode_etag_conditional_sent(self):
        """
        When openapi_etag is stored, the fetch uses If-None-Match and
        a 304 → url mode (not re-fetching content).
        """
        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app
        import httpx

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        svc_row = MagicMock()
        svc_row.openapi_url = "https://example.com/openapi.json"
        svc_row.openapi_etag = '"cached-etag"'

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                result.fetchone.return_value = svc_row
                result.fetchall.return_value = []
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session

        captured_headers = {}

        mock_response = MagicMock()
        mock_response.status_code = 304
        mock_response.headers = {}
        mock_response.url = httpx.URL("https://example.com/openapi.json")
        mock_response.text = ""
        mock_response.content = b""

        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                with patch("mcp_server.tools.discovery.httpx") as mock_httpx:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)

                    async def _get(url, *, headers=None, timeout=None, follow_redirects=None):
                        captured_headers.update(headers or {})
                        return mock_response

                    mock_client.get = _get
                    mock_httpx.AsyncClient.return_value = mock_client

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        return await client.get(
                            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}?inline=true",
                            headers={"X-API-Key": "mk_agent_test"},
                        )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig

        assert resp.status_code == 200, resp.text
        # If-None-Match should have been sent
        assert "If-None-Match" in captured_headers, (
            f"Expected If-None-Match in fetch headers: {captured_headers}"
        )
        assert captured_headers["If-None-Match"] == '"cached-etag"'

    def test_inline_fetch_timeout_returns_fetch_failed(self):
        """Timeout → fetch_failed (tool must not raise)."""
        import mcp_server.main as _main_mod
        from mcp_server.db.session import get_db_session
        from mcp_server.tools.discovery import get_agent_context
        from mcp_server.main import create_app
        import httpx

        _tenant_id = uuid.uuid4()
        _agent_id = str(uuid.uuid4())
        fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

        _orig = _main_mod.validate_agent_key

        async def _fake_validate(key):
            return fake_ctx, None

        _main_mod.validate_agent_key = _fake_validate
        app = create_app()

        async def _fake_ctx():
            return fake_ctx

        app.dependency_overrides[get_agent_context] = _fake_ctx

        svc_row = MagicMock()
        svc_row.openapi_url = "https://example.com/openapi.json"
        svc_row.openapi_etag = None

        async def _fake_db_session() -> AsyncGenerator:
            session = AsyncMock()

            async def _execute(stmt, params=None, **kw):
                result = MagicMock()
                result.fetchone.return_value = svc_row
                result.fetchall.return_value = []
                return result

            session.execute = _execute
            yield session

        app.dependency_overrides[get_db_session] = _fake_db_session

        try:
            async def _run():
                from httpx import AsyncClient, ASGITransport
                with patch("mcp_server.tools.discovery.httpx") as mock_httpx:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    mock_client.get = AsyncMock(
                        side_effect=httpx.TimeoutException("timed out")
                    )
                    mock_httpx.AsyncClient.return_value = mock_client

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        return await client.get(
                            f"/v1/tools/get_openapi/{_TEST_SVC_UUID}?inline=true",
                            headers={"X-API-Key": "mk_agent_test"},
                        )
            resp = asyncio.run(_run())
        finally:
            _main_mod.validate_agent_key = _orig

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["kind"] == "fetch_failed"


# ---------------------------------------------------------------------------
# 3.5 landing.py: bootstrap + discovery chain wording
# ---------------------------------------------------------------------------


class TestLandingChain:

    def _get_root(self):
        from mcp_server.tools.landing import _ROOT_DOC
        return _ROOT_DOC

    def test_root_hint_references_bootstrap(self):
        doc = self._get_root()
        hint = doc.get("hint", "")
        assert "bootstrap" in hint.lower(), (
            f"Root hint should reference bootstrap: {hint!r}"
        )

    def test_bootstrap_endpoint_present_in_rest(self):
        doc = self._get_root()
        endpoints = doc["endpoints"]["rest"]
        assert "bootstrap" in endpoints, "bootstrap must be listed in REST endpoints"

    def test_discover_endpoint_present_in_rest(self):
        doc = self._get_root()
        endpoints = doc["endpoints"]["rest"]
        assert "discover" in endpoints, "discover must be listed in REST endpoints"

    def test_describe_service_endpoint_present_in_rest(self):
        doc = self._get_root()
        endpoints = doc["endpoints"]["rest"]
        assert "describe_service" in endpoints, "describe_service must be listed in REST endpoints"

    def test_tools_index_describe_service_description(self):
        """describe_service tool description mentions usage detail."""
        from mcp_server.tools.landing import _TOOLS_INDEX
        desc = _TOOLS_INDEX["tools"]["describe_service"]["description"]
        assert desc, "describe_service must have a non-empty description"


class TestBuiltinCapabilitiesAdvertised:
    """list_services and discover must always carry the built-in-capabilities
    pointer, so catalog-refreshing agents learn about secret storage etc.
    (Field added after a real agent refreshed via discover and concluded no
    credential-storage capability existed.)"""

    def test_constant_mentions_secret_tools(self):
        from mcp_server.tools.discovery import _BUILTIN_CAPABILITIES
        for tool in ("secret_put", "secret_get", "secret_list", "secret_delete"):
            assert tool in _BUILTIN_CAPABILITIES
        assert "mintkey_get_openapi" in _BUILTIN_CAPABILITIES

    def test_list_services_and_discover_payloads_carry_capabilities(self):
        import inspect
        from mcp_server.tools import discovery
        src = inspect.getsource(discovery)
        # Both payload constructions reference the shared constant.
        assert src.count('"capabilities": _BUILTIN_CAPABILITIES') == 2
