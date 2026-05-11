"""
Pydantic v2 read-models (Out schemas) for Mintkey wire surfaces.

These mirror the Liquibase schema (via SQLAlchemy Mapped types in db.py)
and are consumed by admin-api and mcp-server response serialization.

Source: T-1.0.9; design §1; ADR-0012; ADR-0015.
All IDs are UUID at the Python layer (wire uses ULID-prefixed strings per
ADR-0017.11 — that translation happens in the API layer, not here).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TenantOut(BaseModel):
    """Read model for the tenants table. Source: 001-tenants.yaml."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    display_name: str
    isolation_mode: str
    status: str
    created_at: datetime


class OperatorOut(BaseModel):
    """Read model for the operators table. Source: 002-operators.yaml."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    email: str
    display_name: str | None
    is_platform_admin: bool
    status: str
    created_at: datetime


class ServiceOut(BaseModel):
    """Read model for the services table. Source: 004-services.yaml."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    auth_scheme: str
    status: str
    created_at: datetime


class AgentOut(BaseModel):
    """Read model for the agents table. Source: 003-agents.yaml."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    status: str
    api_key_fingerprint: str | None
    created_at: datetime


class PermissionGrantOut(BaseModel):
    """Read model for the permission_grants table. Source: 006-permission-grants.yaml."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    agent_id: UUID
    service_id: UUID
    action: str
    constraints: dict[str, Any]
    created_at: datetime


class AuditEventOut(BaseModel):
    """Read model for the audit_events table. Source: 007-audit-events.yaml."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    event_type: str
    actor_id: UUID | None
    actor_type: str | None
    target_id: UUID | None
    target_type: str | None
    payload: dict[str, Any]
    at: datetime
