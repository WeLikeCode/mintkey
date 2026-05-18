import logging

import pytest
from fastapi.testclient import TestClient

from mock_backend.rest.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_key_header_present():
    resp = client.get("/api-key-header", headers={"X-Api-Key": "test123"})
    assert resp.status_code == 200
    assert resp.json() == {"received_key": "test123"}


def test_api_key_header_missing():
    resp = client.get("/api-key-header")
    assert resp.status_code == 401


def test_api_key_query():
    resp = client.get("/api-key-query?api_key=test456")
    assert resp.status_code == 200
    assert resp.json() == {"received_key": "test456"}


def test_bearer():
    resp = client.get("/bearer", headers={"Authorization": "Bearer tok123"})
    assert resp.status_code == 200
    assert resp.json() == {"received_token": "tok123"}


def test_basic_auth():
    # dXNlcjpwYXNz == base64("user:pass")
    resp = client.get("/basic-auth", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert resp.status_code == 200
    assert resp.json() == {"received_user": "user"}


def test_oauth_protected():
    resp = client.get("/oauth-protected", headers={"Authorization": "Bearer oauthtok"})
    assert resp.status_code == 200
    assert resp.json() == {"received_token": "oauthtok"}


def test_echo():
    resp = client.post("/echo", json={"hello": "world"})
    assert resp.status_code == 200
    data = resp.json()
    assert "hello" in data["body"]


def test_5xx():
    resp = client.get("/5xx")
    assert resp.status_code == 500


def test_redirect_internal():
    resp = client.get("/redirect-internal", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/health"


def test_redirect_external():
    resp = client.get("/redirect-external", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://example.com/"


# ---------------------------------------------------------------------------
# Security: raw credential values must NOT appear in log output
# ---------------------------------------------------------------------------

def test_api_key_header_does_not_log_raw_key(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that x_api_key value is redacted in log output (not logged in full)."""
    raw_key = "canary-demo-api-key-supersensitive"
    with caplog.at_level(logging.INFO, logger="mock_backend.rest.main"):
        resp = client.get("/api-key-header", headers={"X-Api-Key": raw_key})
    assert resp.status_code == 200
    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_key not in log_output, (
        f"Raw API key leaked into log output: {log_output!r}"
    )
    # Redacted prefix should appear
    assert "cana…" in log_output


def test_api_key_query_does_not_log_raw_key(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that api_key query-string value is redacted in log output."""
    raw_key = "supersecret-query-api-key-12345"
    with caplog.at_level(logging.INFO, logger="mock_backend.rest.main"):
        resp = client.get(f"/api-key-query?api_key={raw_key}")
    assert resp.status_code == 200
    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_key not in log_output, (
        f"Raw API key (query) leaked into log output: {log_output!r}"
    )
    assert "supe…" in log_output


def test_bearer_does_not_log_raw_token(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that the Authorization header value is redacted in bearer endpoint logs."""
    raw_token = "Bearer mk_svckey_SUPERSENSITIVE12345"
    with caplog.at_level(logging.INFO, logger="mock_backend.rest.main"):
        resp = client.get("/bearer", headers={"Authorization": raw_token})
    assert resp.status_code == 200
    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_token not in log_output, (
        f"Raw Bearer token leaked into log output: {log_output!r}"
    )
    assert "mk_svckey_" not in log_output
    # The redacted prefix should be present
    assert "Bear…" in log_output


def test_basic_auth_does_not_log_raw_authorization(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that the Basic authorization header is redacted in log output."""
    # "user:pass" base64-encoded
    raw_auth = "Basic dXNlcjpwYXNz"
    with caplog.at_level(logging.INFO, logger="mock_backend.rest.main"):
        resp = client.get("/basic-auth", headers={"Authorization": raw_auth})
    assert resp.status_code == 200
    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_auth not in log_output, (
        f"Raw Basic auth header leaked into log output: {log_output!r}"
    )
    # _redact() takes the full header value ("Basic dXNl...") so first 4 chars are "Basi"
    assert "Basi…" in log_output


def test_oauth_protected_does_not_log_raw_token(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that the oauth-protected authorization header is redacted in logs."""
    raw_token = "Bearer oauthtok-supersensitive-value-99999"
    with caplog.at_level(logging.INFO, logger="mock_backend.rest.main"):
        resp = client.get("/oauth-protected", headers={"Authorization": raw_token})
    assert resp.status_code == 200
    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_token not in log_output, (
        f"Raw OAuth token leaked into log output: {log_output!r}"
    )
    assert "Bear…" in log_output


def test_health_does_not_log_raw_authorization(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that the health endpoint redacts the Authorization header in logs."""
    raw_token = "Bearer healthcheck-secret-token-12345"
    with caplog.at_level(logging.INFO, logger="mock_backend.rest.main"):
        resp = client.get("/health", headers={"Authorization": raw_token})
    assert resp.status_code == 200
    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_token not in log_output, (
        f"Raw authorization leaked in health log: {log_output!r}"
    )
    assert "Bear…" in log_output
