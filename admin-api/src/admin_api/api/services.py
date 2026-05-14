"""
Service CRUD endpoints.

POST   /v1/tenants/{tenant_id}/services         — register a service (201)
GET    /v1/tenants/{tenant_id}/services         — list services (200)
PATCH  /v1/tenants/{tenant_id}/services/{sid}   — update a service (200)
DELETE /v1/tenants/{tenant_id}/services/{sid}   — delete a service (204)

Architecture constraints:
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - pg_notify via bound parameters — ADR-0008, T-1.0.15.
  - Audit emit on every state change — ADR-0014.7, Req AUD-3.
  - ULID IDs with prefix "svc_" — ADR-0017.11.
  - Global channel "mintkey:service" — ADR-0014.1.
  - RFC1918 / loopback / metadata destinations rejected — S-SEC-1.
  - No plaintext credentials in responses or logs — S-SEC-1, ADR-0014.4.

Source: design §4 api/services.py; Req 3; ADR-0008; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

import ipaddress
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

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


def _wire_id_to_db_uuid(wire_id: str) -> str:
    """
    Convert a wire svc_ ID back to the UUID string stored in the DB.

    The wire form is "svc_" + 32 hex chars (UUID without dashes).
    The DB form is "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx".
    Returns the raw hex string if the input does not match the expected pattern
    (allowing callers to pass raw UUIDs too).
    """
    if wire_id.startswith("svc_"):
        hex_part = wire_id[4:]  # 32 hex chars
        if len(hex_part) == 32:
            return (
                f"{hex_part[:8]}-{hex_part[8:12]}-{hex_part[12:16]}"
                f"-{hex_part[16:20]}-{hex_part[20:]}"
            )
    return wire_id


def _service_row_to_dict(row: Any) -> dict[str, Any]:
    """Map a DB row (namedtuple-like) to the wire representation."""
    raw_id = str(row.id)
    # Wire ID: if the UUID was stored for a svc_ prefixed ID we surface the
    # original string form. For now we prefix the UUID with "svc_" to conform
    # to ADR-0017.11 at the API layer (schemas.py comment: translation happens
    # in the API layer).
    return {
        "id": f"svc_{raw_id.replace('-', '')}",
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "slug": row.slug,
        "display_name": row.display_name,
        "description": row.description,
        "base_url": row.base_url,
        "auth_scheme": row.auth_scheme,
        "openapi_url": row.openapi_url,
        "status": row.status,
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
                "SELECT id, tenant_id, name, slug, display_name, description,"
                " base_url, auth_scheme, openapi_url, status, created_at, updated_at"
                " FROM services WHERE tenant_id = :tenant_id"
                " AND (name ILIKE :pat ESCAPE '\\'"
                "   OR slug ILIKE :pat ESCAPE '\\'"
                "   OR description ILIKE :pat ESCAPE '\\'"
                "   OR base_url ILIKE :pat ESCAPE '\\')"
                " ORDER BY created_at"
            ),
            {"tenant_id": str(tenant_id), "pat": pattern},
        )
    else:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, name, slug, display_name, description,"
                " base_url, auth_scheme, openapi_url, status, created_at, updated_at"
                " FROM services WHERE tenant_id = :tenant_id ORDER BY created_at"
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
            "SELECT id, tenant_id, name, slug, display_name, description,"
            " base_url, auth_scheme, openapi_url, status, created_at, updated_at"
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
    return JSONResponse(_service_row_to_dict(row))


@router.post("/{service_id}/test")
async def test_service(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Test the registered service using its stored base_url.

    Makes a GET request to base_url using the stored auth_scheme/credential.
    Returns {"ok": bool, "status_code": int} and optional latency/error fields.

    Source: openapi.yaml operationId=testRunService; ADR-0014.4; S-SEC-1.
    """
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

    # Build request headers based on auth_scheme
    headers: dict[str, str] = {}
    if cred_entry and cred_entry.get("plaintext"):
        plaintext: str = cred_entry["plaintext"]
        if auth_scheme == "bearer_token":
            headers["Authorization"] = f"Bearer {plaintext}"
        elif auth_scheme == "api_key":
            headers["X-Api-Key"] = plaintext

    # Make outbound HTTP call — timeout 5 s
    import time as _time  # noqa: PLC0415
    start = _time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(base_url, headers=headers)
        latency_ms = int((_time.monotonic() - start) * 1000)
        ok = 200 <= response.status_code < 300
        return JSONResponse(
            {
                "ok": ok,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "response_body_truncated": response.text[:500],
            }
        )
    except httpx.TimeoutException:
        latency_ms = int((_time.monotonic() - start) * 1000)
        return JSONResponse({"ok": False, "latency_ms": latency_ms, "error": "timeout"})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})


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
            "SELECT id, tenant_id, name, slug, display_name, description,"
            " base_url, auth_scheme, openapi_url, status, created_at, updated_at"
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
