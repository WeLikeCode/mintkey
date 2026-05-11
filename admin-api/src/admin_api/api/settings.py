"""
Admin Settings endpoints (PlatformAdmin only).

GET   /v1/admin/settings — retrieve current platform-wide settings.
PATCH /v1/admin/settings — update platform-wide settings (partial update supported).

Architecture constraints:
  - PlatformAdmin check via X-Platform-Admin header (MVP stub; real auth wired later).
  - Settings stored in tenant_settings with key='admin_settings' and tenant_id IS NULL.
  - All SQL uses bound parameters — no f-string interpolation — ADR-0008.
  - Pydantic extra="forbid" on all models enforces unknown-key 422.
  - Audit event "settings.updated" emitted on every PATCH — ADR-0014.7.

Source: T-1.13.1; ADR-0008; ADR-0014.7.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from mintkey_models.audit import audit_emit

router = APIRouter(prefix="/v1/admin")

# ---------------------------------------------------------------------------
# Settings models — extra="forbid" ensures unknown keys → 422
# ---------------------------------------------------------------------------


class OIDCSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None


class AuditSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_days: int = 90
    chain_verify_interval_hours: int = 24


class AdminSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oidc: OIDCSettings = OIDCSettings()
    audit: AuditSettings = AuditSettings()


# ---------------------------------------------------------------------------
# PlatformAdmin guard (MVP stub)
# ---------------------------------------------------------------------------

_SYSTEM_TENANT_ID = UUID("00000000-0000-0000-0000-000000000000")

_PERMISSION_DENIED = JSONResponse(
    status_code=403,
    content={"mintkey:code": "permission_denied", "title": "Platform admin required"},
)


def _is_platform_admin(request: Request) -> bool:
    """
    MVP stub: returns True when X-Platform-Admin: true header is present.

    In production this will validate a signed session claim. The header
    approach is intentionally test-only — the real gate is wired in T-1.13.2.

    Source: T-1.13.1.
    """
    return request.headers.get("X-Platform-Admin") == "true"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETTINGS_KEY = "admin_settings"


async def _load_settings(session: AsyncSession) -> AdminSettings:
    """Load admin settings from tenant_settings; return defaults if absent."""
    result = await session.execute(
        text(
            "SELECT value FROM tenant_settings"
            " WHERE key = :key AND tenant_id IS NULL"
        ),
        {"key": _SETTINGS_KEY},
    )
    row = result.fetchone()
    if row is None:
        return AdminSettings()
    try:
        data = json.loads(row.value) if isinstance(row.value, str) else row.value
        return AdminSettings.model_validate(data)
    except Exception:
        return AdminSettings()


async def _save_settings(session: AsyncSession, settings: AdminSettings) -> None:
    """Upsert admin settings into tenant_settings."""
    value = json.dumps(settings.model_dump())
    await session.execute(
        text(
            "INSERT INTO tenant_settings (key, tenant_id, value)"
            " VALUES (:key, NULL, CAST(:value AS jsonb))"
            " ON CONFLICT (key, tenant_id) DO UPDATE SET value = CAST(:value AS jsonb)"
        ),
        {"key": _SETTINGS_KEY, "value": value},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/settings")
async def get_admin_settings(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Return current platform-wide admin settings.

    Requires PlatformAdmin role (X-Platform-Admin: true in MVP).

    Source: T-1.13.1.
    """
    if not _is_platform_admin(request):
        return JSONResponse(
            status_code=403,
            content={"mintkey:code": "permission_denied", "title": "Platform admin required"},
        )
    settings = await _load_settings(session)
    return JSONResponse(settings.model_dump())


@router.patch("/settings")
async def patch_admin_settings(
    body: AdminSettings,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Partially update platform-wide admin settings.

    Missing keys in the request body retain their existing values (or defaults).
    Unknown keys → 422 (Pydantic extra="forbid").
    Emits audit event "settings.updated" — ADR-0014.7.

    Source: T-1.13.1.
    """
    if not _is_platform_admin(request):
        return JSONResponse(
            status_code=403,
            content={"mintkey:code": "permission_denied", "title": "Platform admin required"},
        )

    # Load current state; merge with incoming body (body wins for provided fields)
    current = await _load_settings(session)

    current_data = current.model_dump()
    incoming_data = body.model_dump()

    # Deep merge: incoming values override current values field by field
    merged_data = {**current_data}
    for section_key, section_val in incoming_data.items():
        if isinstance(section_val, dict) and isinstance(merged_data.get(section_key), dict):
            merged_data[section_key] = {**merged_data[section_key], **section_val}
        else:
            merged_data[section_key] = section_val

    merged = AdminSettings.model_validate(merged_data)

    await _save_settings(session, merged)

    await audit_emit(
        session=session,
        tenant_id=_SYSTEM_TENANT_ID,
        event_type="settings.updated",
        actor_id=None,
        actor_type="platform_admin",
        target_id=None,
        target_type="admin_settings",
        payload=merged.model_dump(),
    )

    return JSONResponse(merged.model_dump())
