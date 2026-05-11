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
