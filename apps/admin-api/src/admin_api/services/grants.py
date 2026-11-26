"""The one write path that creates and removes permission grants.

Every caller that grants or revokes access goes through this module: the
operator API now, the agent grant tools and access-request approvals later.
The SQL lives here; the caller keeps the audit event and the change-channel
NOTIFY.

Sources:
  - ``openspec/changes/grant-expiry/spec.md`` — One write path creates and
    removes grants
  - ``openspec/changes/grant-expiry/design.md`` — D6, D7, D7b, D8
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Grantor:
    """Who gave a grant: an operator or an agent, by DB uuid text."""

    type: str
    id: str | None


@dataclass(frozen=True)
class GrantRecord:
    """A permission grant as the service sees it (ids as DB uuid text)."""

    id: str
    wire_id: str
    agent_id: str
    service_id: str
    action: str
    constraints: dict[str, Any]
    expires_at: datetime | None
    grantor_type: str
    grantor_id: str | None
    created_at: datetime | None
    created: bool


class GrantConflict(Exception):
    """A live grant has different constraints or another expiry."""


async def write_grant(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: str,
    service_id: str,
    action: str,
    constraints: dict[str, Any],
    expires_at: datetime | None,
    grantor: Grantor,
    now: datetime | None = None,
) -> GrantRecord:
    raise NotImplementedError


async def delete_grant(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    grant_id: str,
    agent_id: str | None = None,
) -> GrantRecord | None:
    raise NotImplementedError


def grant_granted_audit_payload(record: GrantRecord) -> dict[str, Any]:
    raise NotImplementedError


def grant_revoked_audit_payload(
    record: GrantRecord, revoked_by: Grantor
) -> dict[str, Any]:
    raise NotImplementedError


def grant_revoked_notify_payload(
    tenant_id: UUID, record: GrantRecord, revoked_at: datetime
) -> dict[str, Any]:
    raise NotImplementedError


def grant_wire_fields(record_or_row: Any, now: datetime) -> dict[str, Any]:
    raise NotImplementedError
