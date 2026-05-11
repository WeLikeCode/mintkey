"""
SQLAlchemy 2.x async Mapped types — mirror of the Liquibase schema.

IMPORTANT: These declarations mirror Liquibase changelogs. They are NOT
the source of truth for the schema. Never add a column here without first
adding it in a Liquibase changeset. The CI mirror-diff (T-1.11.5) enforces
this invariant per ADR-0015.

Sources:
  001-tenants.yaml, 002-operators.yaml, 003-agents.yaml, 004-services.yaml,
  005-credentials.yaml, 006-permission-grants.yaml, 007-audit-events.yaml,
  008-platform-tables.yaml
  ADR-0012 (SQLAlchemy 2.x async Mapped types)
  ADR-0015 (Liquibase is source of truth)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 001-tenants.yaml
# ---------------------------------------------------------------------------


class Tenant(Base):
    """Mirror of the tenants table. Source: 001-tenants.yaml."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    isolation_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="row")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# 002-operators.yaml
# ---------------------------------------------------------------------------


class Operator(Base):
    """Mirror of the operators table. Source: 002-operators.yaml."""

    __tablename__ = "operators"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(256))
    internal_password_hash: Mapped[Optional[str]] = mapped_column(Text)
    oidc_sub: Mapped[Optional[str]] = mapped_column(Text)
    oidc_provider: Mapped[Optional[str]] = mapped_column(Text)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OperatorTenantMembership(Base):
    """Mirror of the operator_tenant_memberships table. Source: 002-operators.yaml."""

    __tablename__ = "operator_tenant_memberships"

    operator_id: Mapped[UUID] = mapped_column(
        ForeignKey("operators.id"), nullable=False, primary_key=True
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Session(Base):
    """Mirror of the sessions table. Source: 002-operators.yaml."""

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    operator_id: Mapped[UUID] = mapped_column(ForeignKey("operators.id"), nullable=False)
    oidc_refresh_token_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# 003-agents.yaml
# ---------------------------------------------------------------------------


class Agent(Base):
    """Mirror of the agents table. Source: 003-agents.yaml."""

    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    mcp_endpoint: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    rate_limit_rps: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# 004-services.yaml
# ---------------------------------------------------------------------------


class Service(Base):
    """Mirror of the services table. Source: 004-services.yaml."""

    __tablename__ = "services"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_scheme: Mapped[str] = mapped_column(String(64), nullable=False)
    openapi_url: Mapped[Optional[str]] = mapped_column(Text)
    openapi_etag: Mapped[Optional[str]] = mapped_column(Text)
    allow_internal_urls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# 005-credentials.yaml
# ---------------------------------------------------------------------------


class Credential(Base):
    """Mirror of the credentials table. Source: 005-credentials.yaml."""

    __tablename__ = "credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id"), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    auth_scheme: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 006-permission-grants.yaml
# ---------------------------------------------------------------------------


class PermissionGrant(Base):
    """Mirror of the permission_grants table. Source: 006-permission-grants.yaml."""

    __tablename__ = "permission_grants"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)
    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(nullable=False)


# ---------------------------------------------------------------------------
# 007-audit-events.yaml
# ---------------------------------------------------------------------------


class AuditEvent(Base):
    """Mirror of the audit_events table. Source: 007-audit-events.yaml."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[Optional[UUID]] = mapped_column()
    actor_type: Mapped[Optional[str]] = mapped_column(String(64))
    target_id: Mapped[Optional[UUID]] = mapped_column()
    target_type: Mapped[Optional[str]] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    request_id: Mapped[Optional[UUID]] = mapped_column()
    trace_id: Mapped[Optional[str]] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# 008-platform-tables.yaml
# ---------------------------------------------------------------------------


class TenantSetting(Base):
    """Mirror of the tenant_settings table. Source: 008-platform-tables.yaml."""

    __tablename__ = "tenant_settings"

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, primary_key=True
    )
    key: Mapped[str] = mapped_column(String(256), nullable=False, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(nullable=False)


class AdminRequestJti(Base):
    """
    Mirror of the admin_request_jti table (replay-protection denylist).
    Source: 008-platform-tables.yaml.
    """

    __tablename__ = "admin_request_jti"

    jti: Mapped[UUID] = mapped_column(primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ServiceIdentity(Base):
    """
    Mirror of the service_identities table (inter-service bootstrap tokens).
    Source: 008-platform-tables.yaml.
    """

    __tablename__ = "service_identities"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    hashed_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditChainState(Base):
    """
    Mirror of the audit_chain_state table (per-tenant hash-chain head pointer).
    Source: 008-platform-tables.yaml; ADR-0014.7 (mandatory audit hash chain).
    """

    __tablename__ = "audit_chain_state"

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, primary_key=True
    )
    head_event_id: Mapped[Optional[UUID]] = mapped_column()
    head_hash: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_verified_event_id: Mapped[Optional[UUID]] = mapped_column()
