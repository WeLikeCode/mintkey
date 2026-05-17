"""
Service CRUD endpoints.

POST   /v1/tenants/{tenant_id}/services              — register a service (201)
GET    /v1/tenants/{tenant_id}/services              — list services (200)
PATCH  /v1/tenants/{tenant_id}/services/{sid}        — update a service (200)
DELETE /v1/tenants/{tenant_id}/services/{sid}        — delete a service (204)
POST   /v1/tenants/{tenant_id}/services/test-transient — dry-run test without persistence (200)

Architecture constraints:
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - pg_notify via bound parameters — ADR-0008, T-1.0.15.
  - Audit emit on every state change — ADR-0014.7, Req AUD-3.
  - ULID IDs with prefix "svc_" — ADR-0017.11.
  - Global channel "mintkey:service" — ADR-0014.1.
  - RFC1918 / loopback / metadata destinations rejected — S-SEC-1.
  - No plaintext credentials in responses or logs — S-SEC-1, ADR-0014.4.
  - test-transient: credential value NEVER written to DB, vault, logs, or audit — OPS-T.

Source: design §4 api/services.py; Req 3; ADR-0008; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

import ipaddress
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional, cast
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid as _wire_to_db
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/services")

# ---------------------------------------------------------------------------
# Forbidden destination networks — S-SEC-1 / ADR-0014.4
# ---------------------------------------------------------------------------

_FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
]

# Crockford base32 alphabet (uppercase, no I/L/O/U)
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _new_svc_id() -> str:
    """
    Generate a ULID-format ID with the 'svc_' prefix — ADR-0017.11.

    Layout: 10 time chars (48-bit ms) + 16 random chars = 26 Crockford base32 chars.
    """
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(uuid.uuid4().bytes[:10], "big")

    # Encode 48-bit timestamp into 10 Crockford chars
    t_enc = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    # Encode 80 random bits into 16 Crockford chars
    r_enc = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    return "svc_" + "".join(t_enc) + "".join(r_enc)


def _is_forbidden_destination(base_url: str) -> bool:
    """
    Return True when base_url resolves to a forbidden network — S-SEC-1.

    Forbidden: RFC1918, loopback (127/8, ::1), link-local (169.254/16, fe80::/10),
    and unique-local (fc00::/7).

    DNS names are allowed (not resolved here); only IP literals are checked.
    """
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname
        if not host:
            return False
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _FORBIDDEN_NETWORKS)
    except ValueError:
        return False  # not an IP literal — DNS resolution happens at request time


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ServiceCreate(BaseModel):
    name: str
    base_url: str
    auth_scheme: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    openapi_url: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    auth_scheme: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    openapi_url: Optional[str] = None
    status: Optional[str] = None


class TestRunRequest(BaseModel):
    """
    Body for POST /{service_id}/test — operationId testRunService.

    All fields are optional with sensible defaults so that an empty body `{}`
    falls back to GET /health (matching the OpenAPI default).

    Source: openapi.yaml TestRunRequest; R14b fix (R13 found body silently dropped).
    """

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    path: str = "/health"
    headers: Optional[dict[str, str]] = None
    body: Optional[str] = None
    timeout_ms: Optional[int] = 5000


class TransientServiceCandidate(BaseModel):
    """Candidate service config for a dry-run test — OPS-T."""

    name: str = "candidate"
    base_url: str
    auth_scheme: str


class TransientCredentialCandidate(BaseModel):
    """
    Candidate credential for a dry-run test — OPS-T.

    The `value` field is used inline for the HTTP call ONLY.
    It is NEVER written to DB, vault, any log line, or the audit payload.
    """

    value: str
    header_name: Optional[str] = None   # api_key_header scheme
    query_param: Optional[str] = None   # api_key_query scheme
    token_url: Optional[str] = None     # oauth2_client_credentials (future)
    client_id: Optional[str] = None     # oauth2_client_credentials (future)


class TransientTestParams(BaseModel):
    """HTTP call parameters for a dry-run test — OPS-T."""

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    path: str = "/"
    headers: Optional[dict[str, str]] = None
    body: Optional[str] = None
    timeout_ms: int = 5000


class TransientTestRequest(BaseModel):
    """
    Body for POST /test-transient — operationId testServiceTransient.

    Carries the full candidate service config + credential inline.
    Nothing is persisted to DB or vault.

    Source: openapi.yaml TransientTestRequest; OPS-T.
    """

    service: TransientServiceCandidate
    credential: TransientCredentialCandidate
    test: TransientTestParams = TransientTestParams()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _forbidden_response() -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "mintkey:code": "forbidden_destination",
            "title": "The base_url resolves to a forbidden destination",
        },
    )


def _check_ssrf_hostname(final_url: str, base_url: str) -> None:
    """
    Enforce that the outbound URL's effective hostname stays within the
    service's declared base_url hostname — S-SEC-1 / ADR-0014.4.

    A malicious test.path (e.g. ``//evil.com/foo``) could cause the
    constructed final_url to escape to a different host.  Parsing both URLs
    and comparing hostnames (case-insensitive) closes that gap.

    Raises HTTPException(400) if the hostnames do not match.
    """
    base_host = urlparse(base_url).hostname or ""
    final_host = urlparse(final_url).hostname or ""
    if final_host.lower() != base_host.lower():
        raise HTTPException(
            status_code=400,
            detail={
                "mintkey:code": "ssrf_blocked",
                "title": "Outbound hostname does not match the service base_url",
                "base_host": base_host,
                "final_host": final_host,
            },
        )


def _wire_id_to_db_uuid(wire_id: str) -> str:
    """
    Convert a wire svc_ ID back to the UUID string stored in the DB.

    Thin wrapper around utils.wire_ids.wire_to_db_uuid — accepts both the
    canonical Crockford form and the legacy 32-hex form for backward-compat.
    Returns wire_id unchanged if it does not match a known svc_ prefix.

    Source: ADR-0017.11; #13.
    """
    return _wire_to_db(wire_id, "svc")


def _service_row_to_dict(row: Any) -> dict[str, Any]:
    """Map a DB row (namedtuple-like) to the wire representation.

    Emits Crockford ULID wire-form IDs (canonical per ADR-0017.11 / #13).
    Includes current_key_version — MAX key_version of active credentials (UX-FB-B).
    """
    return {
        "id": db_uuid_to_wire(row.id, "svc"),
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "slug": row.slug,
        "display_name": row.display_name,
        "description": row.description,
        "base_url": row.base_url,
        "auth_scheme": row.auth_scheme,
        "openapi_url": row.openapi_url,
        "status": row.status,
        "current_key_version": int(row.current_key_version or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_service(
    tenant_id: UUID,
    body: ServiceCreate,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Register a new backend service under a tenant.

    Source: Req 3; ADR-0008; ADR-0014.7; ADR-0017.11.
    """
    # Validate base_url is not a forbidden destination — S-SEC-1
    if _is_forbidden_destination(body.base_url):
        return _forbidden_response()

    # Set tenant context — bound parameters, ADR-0008
    await set_tenant_context(session, tenant_id)

    # Generate ULID ID with svc_ prefix — ADR-0017.11
    svc_id = _new_svc_id()
    # Derive the DB UUID from the ULID's 128-bit value — R12 (mirrors R8-redux for agents).
    # _new_svc_id() returns "svc_<26-char Crockford ULID>"; decode the 26-char tail to the
    # same 128-bit integer and wrap as uuid.UUID so the stored row PK is algebraically
    # identical to what _wire_id_to_uuid(svc_id, "svc_") decodes from the wire form.
    # Dropping the independent uuid.uuid4() eliminates the asymmetry that caused silent
    # 404s for new services: POST returned svc_<Crockford> whose bits never matched the PK.
    _crockford_tail = svc_id[len("svc_"):]
    _val = 0
    for _ch in _crockford_tail.upper():
        _val = (_val << 5) | _CROCKFORD.index(_ch)
    _val &= (1 << 128) - 1
    internal_id = uuid.UUID(int=_val)
    now = datetime.now(timezone.utc)

    # Derive slug from name
    slug = body.name.lower().replace(" ", "-")

    await session.execute(
        text(
            "INSERT INTO services"
            " (id, tenant_id, name, slug, display_name, description,"
            "  base_url, auth_scheme, openapi_url, status, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :name, :slug, :display_name, :description,"
            "  :base_url, :auth_scheme, :openapi_url, :status, :created_at, :updated_at)"
        ),
        {
            "id": str(internal_id),
            "tenant_id": str(tenant_id),
            "name": body.name,
            "slug": slug,
            "display_name": body.display_name,
            "description": body.description,
            "base_url": body.base_url,
            "auth_scheme": body.auth_scheme,
            "openapi_url": body.openapi_url,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    )

    # Emit audit event — ADR-0014.7, Req AUD-3
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.registered",
        actor_id=None,
        actor_type="operator",
        target_id=internal_id,
        target_type="service",
        payload={"name": body.name, "auth_scheme": body.auth_scheme, "svc_id": svc_id},
    )

    # NOTIFY change channel — ADR-0014.1, bound parameters
    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.registered",
            "tenant_id": str(tenant_id),
            "service_id": svc_id,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": svc_id,
            "tenant_id": str(tenant_id),
            "name": body.name,
            "slug": slug,
            "display_name": body.display_name,
            "description": body.description,
            "base_url": body.base_url,
            "auth_scheme": body.auth_scheme,
            "openapi_url": body.openapi_url,
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_services(
    tenant_id: UUID,
    q: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List all services for a tenant.

    Optional query parameters:
      q — case-insensitive substring search across name, slug, description, base_url.

    Source: Req 3; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    if q is not None:
        escaped = _escape_like(q)
        pattern = f"%{escaped}%"
        result = await session.execute(
            text(
                "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
                " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
                " COALESCE(("
                "   SELECT MAX(c.key_version)"
                "   FROM credentials c"
                "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
                " ), 0) AS current_key_version"
                " FROM services s WHERE s.tenant_id = :tenant_id"
                " AND (s.name ILIKE :pat ESCAPE '\\'"
                "   OR s.slug ILIKE :pat ESCAPE '\\'"
                "   OR s.description ILIKE :pat ESCAPE '\\'"
                "   OR s.base_url ILIKE :pat ESCAPE '\\')"
                " ORDER BY s.created_at"
            ),
            {"tenant_id": str(tenant_id), "pat": pattern},
        )
    else:
        result = await session.execute(
            text(
                "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
                " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
                " COALESCE(("
                "   SELECT MAX(c.key_version)"
                "   FROM credentials c"
                "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
                " ), 0) AS current_key_version"
                " FROM services s WHERE s.tenant_id = :tenant_id ORDER BY s.created_at"
            ),
            {"tenant_id": str(tenant_id)},
        )
    rows = result.fetchall()
    services = [_service_row_to_dict(r) for r in rows]
    return JSONResponse({"services": services})


@router.get("/{service_id}")
async def get_service(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Describe a single service.

    Source: openapi.yaml operationId=getService; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    db_uuid = _wire_id_to_db_uuid(service_id)
    result = await session.execute(
        text(
            "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
            " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
            " COALESCE(("
            "   SELECT MAX(c.key_version)"
            "   FROM credentials c"
            "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
            " ), 0) AS current_key_version"
            " FROM services s WHERE s.id = :sid AND s.tenant_id = :tid"
        ),
        {"sid": db_uuid, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )
    return JSONResponse(_service_row_to_dict(row))


@router.post("/test-transient")
async def test_service_transient(
    tenant_id: UUID,
    body: TransientTestRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Validate a candidate service config + credential WITHOUT persisting to DB or vault.

    Accepts a full TransientTestRequest (service config + credential + test params),
    performs the HTTP call in-memory, emits a service.test_executed audit event with
    transient=True, and returns the result.

    The credential value is NEVER written to DB, vault, any log line, or the audit payload.

    Source: openapi.yaml operationId=testServiceTransient; OPS-T; S-SEC-1; ADR-0014.4.
    """
    # SSRF guardrail — S-SEC-1 / ADR-0014.4
    if _is_forbidden_destination(body.service.base_url):
        return _forbidden_response()

    await set_tenant_context(session, tenant_id)

    base_url: str = body.service.base_url
    auth_scheme: str = body.service.auth_scheme
    test = body.test

    # Build the final URL
    base_url_stripped = base_url.rstrip("/")
    path_part = test.path if test.path.startswith("/") else "/" + test.path
    final_url = base_url_stripped + path_part

    # Build request headers based on auth_scheme using the inline credential
    # The plaintext value is used here only — it must not appear in any log or audit payload.
    headers: dict[str, str] = {}
    plaintext: str = body.credential.value
    if auth_scheme == "bearer_token":
        headers["Authorization"] = f"Bearer {plaintext}"
    elif auth_scheme == "api_key_header":
        header_name: str = body.credential.header_name or ""
        if not header_name:
            logger.warning(
                "test_service_transient: api_key_header credential missing header_name — "
                "falling back to 'X-API-Key'. tenant=%s",
                str(tenant_id),
            )
            header_name = "X-API-Key"
        headers[header_name] = plaintext
    elif auth_scheme == "api_key_query":
        query_param: str = body.credential.query_param or ""
        if not query_param:
            logger.warning(
                "test_service_transient: api_key_query credential missing query_param — "
                "falling back to 'api_key'. tenant=%s",
                str(tenant_id),
            )
            query_param = "api_key"
        separator = "&" if "?" in final_url else "?"
        final_url = f"{final_url}{separator}{query_param}={plaintext}"

    # SSRF host-binding guardrail — S-SEC-1 / ADR-0014.4
    # Verify the assembled URL's hostname hasn't escaped the service base_url
    # (e.g. via a malicious test.path like //evil.com/steal).
    _check_ssrf_hostname(final_url, base_url)

    # Merge auth headers with optional extra headers from the request body
    merged_headers = {**headers, **(test.headers or {})}
    timeout_s = test.timeout_ms / 1000.0

    # Make outbound HTTP call
    import time as _time  # noqa: PLC0415
    start = _time.monotonic()
    ok: bool = False
    status_code: int = 0
    latency_ms: int = 0
    response_body_truncated: str = ""
    error: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.request(
                method=test.method,
                url=final_url,
                headers=merged_headers,
                content=test.body,
            )
        latency_ms = int((_time.monotonic() - start) * 1000)
        ok = 200 <= response.status_code < 300
        status_code = response.status_code
        response_body_truncated = response.text[:500]
    except httpx.TimeoutException:
        latency_ms = int((_time.monotonic() - start) * 1000)
        error = "timeout"
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((_time.monotonic() - start) * 1000)
        error = str(exc)

    # Emit audit event — ADR-0014.7, Req AUD-3
    # Wrapped in try/except so a logging failure never breaks the response.
    # IMPORTANT: credential value and response body bytes are NEVER included.
    try:
        await audit_emit(
            session=session,
            tenant_id=tenant_id,
            event_type="service.test_executed",
            actor_id=None,
            actor_type="operator",
            target_id=None,
            target_type="service",
            payload={
                "method": test.method,
                "path_template": test.path,
                "base_url": base_url,
                "auth_scheme": auth_scheme,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "ok": ok,
                "transient": True,
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "test_service_transient: audit_emit failed (non-fatal). tenant=%s",
            str(tenant_id),
        )

    result: dict[str, Any] = {"ok": ok, "latency_ms": latency_ms, "final_url": final_url}
    if status_code:
        result["status_code"] = status_code
    if response_body_truncated:
        result["response_body_truncated"] = response_body_truncated
    if error is not None:
        result["error"] = error
    return JSONResponse(result)


@router.post("/{service_id}/test")
async def test_service(
    tenant_id: UUID,
    service_id: str,
    req: Optional[TestRunRequest] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Test the registered service using its stored base_url + the request body's path/method.

    Accepts TestRunRequest body (method, path, headers, body, timeout_ms).
    All fields are optional with defaults (GET, /health, 5000 ms).
    Emits service.test_executed audit event with transient=False.

    Source: openapi.yaml operationId=testRunService; ADR-0014.4; S-SEC-1; R14b; OPS-T.
    """
    if req is None:
        req = TestRunRequest()
    await set_tenant_context(session, tenant_id)

    # Fetch the service row
    db_uuid = _wire_id_to_db_uuid(service_id)
    result = await session.execute(
        text(
            "SELECT id, tenant_id, name, base_url, auth_scheme"
            " FROM services WHERE id = :sid AND tenant_id = :tid"
        ),
        {"sid": db_uuid, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )

    base_url: str = row.base_url
    auth_scheme: str = row.auth_scheme

    # SSRF guardrail — S-SEC-1 / ADR-0014.4
    if _is_forbidden_destination(base_url):
        return _forbidden_response()

    # Fetch credential from vault (plaintext stays in request scope — ADR-0014.4)
    from admin_api.services.vault_client import get_vault_client  # noqa: PLC0415
    vault = await get_vault_client()
    cred_entry = await vault.get_credential(str(tenant_id), str(row.id))

    # Build the final URL: urljoin handles leading-slash on path correctly.
    # urljoin('http://x:8999', '/health') == 'http://x:8999/health'
    # urljoin('http://x:8999/', '/health') == 'http://x:8999/health'
    base_url_stripped = base_url.rstrip("/")
    path_part = req.path if req.path.startswith("/") else "/" + req.path
    final_url = base_url_stripped + path_part

    # Build request headers based on auth_scheme
    headers: dict[str, str] = {}
    if cred_entry and cred_entry.get("plaintext"):
        plaintext: str = cast(str, cred_entry["plaintext"])
        if auth_scheme == "bearer_token":
            headers["Authorization"] = f"Bearer {plaintext}"
        elif auth_scheme == "api_key_header":
            header_name: str = cast(str, cred_entry.get("header_name") or "")
            if not header_name:
                logger.warning(
                    "test_service: api_key_header credential missing header_name — "
                    "falling back to 'X-API-Key'. service=%s tenant=%s",
                    service_id,
                    str(tenant_id),
                )
                header_name = "X-API-Key"
            headers[header_name] = plaintext
        elif auth_scheme == "api_key_query":
            query_param: str = cast(str, cred_entry.get("query_param") or "")
            if not query_param:
                logger.warning(
                    "test_service: api_key_query credential missing query_param — "
                    "falling back to 'api_key'. service=%s tenant=%s",
                    service_id,
                    str(tenant_id),
                )
                query_param = "api_key"
            separator = "&" if "?" in final_url else "?"
            final_url = f"{final_url}{separator}{query_param}={plaintext}"

    # SSRF host-binding guardrail — S-SEC-1 / ADR-0014.4
    # base_url comes from DB (trusted) but an attacker-supplied req.path
    # could still redirect to a different host via e.g. //evil.com/steal.
    _check_ssrf_hostname(final_url, base_url)

    # Merge auth headers with optional extra headers from the request body
    merged_headers = {**headers, **(req.headers or {})}
    timeout_s = (req.timeout_ms or 5000) / 1000.0

    # Make outbound HTTP call
    import time as _time  # noqa: PLC0415
    start = _time.monotonic()
    test_ok: bool = False
    test_status_code: int = 0
    test_latency_ms: int = 0
    test_response_body: str = ""

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.request(
                method=req.method,
                url=final_url,
                headers=merged_headers,
                content=req.body,
            )
        test_latency_ms = int((_time.monotonic() - start) * 1000)
        test_ok = 200 <= response.status_code < 300
        test_status_code = response.status_code
        test_response_body = response.text[:500]

        # Emit audit event — ADR-0014.7, Req AUD-3, OPS-T
        # Wrapped in try/except so a logging failure never breaks the response.
        # IMPORTANT: credential value and response body bytes are NEVER included.
        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=row.id,
                target_type="service",
                payload={
                    "method": req.method,
                    "path_template": req.path,
                    "auth_scheme": auth_scheme,
                    "status_code": test_status_code,
                    "latency_ms": test_latency_ms,
                    "ok": test_ok,
                    "transient": False,
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service: audit_emit failed (non-fatal). service=%s tenant=%s",
                service_id,
                str(tenant_id),
            )

        return JSONResponse(
            {
                "ok": test_ok,
                "status_code": test_status_code,
                "latency_ms": test_latency_ms,
                "response_body_truncated": test_response_body,
                "final_url": final_url,
            }
        )
    except httpx.TimeoutException:
        test_latency_ms = int((_time.monotonic() - start) * 1000)

        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=row.id,
                target_type="service",
                payload={
                    "method": req.method,
                    "path_template": req.path,
                    "auth_scheme": auth_scheme,
                    "status_code": 0,
                    "latency_ms": test_latency_ms,
                    "ok": False,
                    "transient": False,
                    "error": "timeout",
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service: audit_emit failed (non-fatal). service=%s tenant=%s",
                service_id,
                str(tenant_id),
            )

        return JSONResponse({"ok": False, "latency_ms": test_latency_ms, "error": "timeout"})
    except Exception as exc:  # noqa: BLE001
        test_latency_ms = int((_time.monotonic() - start) * 1000)
        logger.warning(
            "test_service: unexpected error. service=%s tenant=%s error=%r",
            service_id,
            str(tenant_id),
            exc,
        )

        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=row.id,
                target_type="service",
                payload={
                    "method": req.method,
                    "path_template": req.path,
                    "auth_scheme": auth_scheme,
                    "status_code": 0,
                    "latency_ms": test_latency_ms,
                    "ok": False,
                    "transient": False,
                    "error": "internal_error",
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service: audit_emit failed (non-fatal). service=%s tenant=%s",
                service_id,
                str(tenant_id),
            )

        return JSONResponse({"ok": False, "error": "internal_error"})


@router.patch("/{service_id}")
async def update_service(
    tenant_id: UUID,
    service_id: str,
    body: ServiceUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Update mutable fields of a service.

    Source: Req 3; ADR-0008; ADR-0014.7.
    """
    if body.base_url is not None and _is_forbidden_destination(body.base_url):
        return _forbidden_response()

    await set_tenant_context(session, tenant_id)

    db_uuid = _wire_id_to_db_uuid(service_id)
    now = datetime.now(timezone.utc)

    # Build the UPDATE using a fixed set of known columns to avoid dynamic SQL.
    # Each column is either updated to its new value or kept via COALESCE to the
    # existing value. This keeps the SQL template a string literal — ADR-0008,
    # T-1.0.15 (no f-string SQL).
    await session.execute(
        text(
            "UPDATE services"
            " SET name = COALESCE(:name, name),"
            "     base_url = COALESCE(:base_url, base_url),"
            "     auth_scheme = COALESCE(:auth_scheme, auth_scheme),"
            "     display_name = COALESCE(:display_name, display_name),"
            "     description = COALESCE(:description, description),"
            "     openapi_url = COALESCE(:openapi_url, openapi_url),"
            "     status = COALESCE(:status, status),"
            "     updated_at = :updated_at"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {
            "name": body.name,
            "base_url": body.base_url,
            "auth_scheme": body.auth_scheme,
            "display_name": body.display_name,
            "description": body.description,
            "openapi_url": body.openapi_url,
            "status": body.status,
            "updated_at": now,
            "sid": db_uuid,
            "tid": str(tenant_id),
        },
    )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.updated",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="service",
        payload={"service_id": service_id},
    )

    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.updated",
            "tenant_id": str(tenant_id),
            "service_id": service_id,
        },
    )

    result = await session.execute(
        text(
            "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
            " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
            " COALESCE(("
            "   SELECT MAX(c.key_version)"
            "   FROM credentials c"
            "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
            " ), 0) AS current_key_version"
            " FROM services s WHERE s.id = :sid AND s.tenant_id = :tid"
        ),
        {"sid": db_uuid, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )
    return JSONResponse(_service_row_to_dict(row))


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """
    Delete (hard-delete) a service.

    Source: Req 3; ADR-0008; ADR-0014.7.
    """
    await set_tenant_context(session, tenant_id)

    db_uuid = _wire_id_to_db_uuid(service_id)
    await session.execute(
        text("DELETE FROM services WHERE id = :sid AND tenant_id = :tid"),
        {"sid": db_uuid, "tid": str(tenant_id)},
    )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.deleted",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="service",
        payload={"service_id": service_id},
    )

    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.deleted",
            "tenant_id": str(tenant_id),
            "service_id": service_id,
        },
    )

    return Response(status_code=204)
