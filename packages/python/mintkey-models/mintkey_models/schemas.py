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
from typing import Any, List, Optional
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


# ---------------------------------------------------------------------------
# 012-service-api-keys.yaml — ADR-0018; long-lived-api-keys task 1.3
# ---------------------------------------------------------------------------


class ServiceApiKeyCreate(BaseModel):
    """
    Request body for POST /v1/tenants/{tid}/agents/{aid}/api-keys.
    Source: design §4.1; Req 1.1, 8.1.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    allowed_actions: List[str]
    expires_at: Optional[datetime] = None
    constraints: Optional[dict[str, Any]] = None  # validated as closed Constraints at the API layer

    @field_validator("allowed_actions")
    @classmethod
    def actions_non_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("allowed_actions must be non-empty (mirrors CHECK constraint)")
        return v


class ServiceApiKey(BaseModel):
    """
    List / show element for a service API key — no plaintext (Req 1.2, 10.1).
    Source: design §4.1; Req 8.2, 8.3.
    """

    model_config = ConfigDict(from_attributes=True)

    api_key_id: str           # svckey_<ULID> wire form (ADR-0017.11)
    key_fingerprint: str      # hex(sha256(plaintext)[:8]) — safe in audit/logs
    service_id: UUID
    allowed_actions: List[str]
    constraints: Optional[dict[str, Any]]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    created_by: UUID
    status: str               # "active" | "expired" | "revoked"


class ServiceApiKeyCreated(ServiceApiKey):
    """
    201 response body — extends ServiceApiKey with plaintext shown ONCE.
    Source: design §4.2; Req 1.1, 1.2.
    The plaintext is NOT stored; this model is only used for the one-time 201 response.
    """

    plaintext_key: str  # mk_svckey_<…> — never stored; show-once at creation/rotation


# ---------------------------------------------------------------------------
# 028-budget-counters.yaml — P-011; agent-budgets T-BUD-2.1
# ---------------------------------------------------------------------------


class BudgetCounterOut(BaseModel):
    """Read model for the budget_counters table. Source: 028-budget-counters.yaml."""

    model_config = ConfigDict(from_attributes=True)

    permission_id: UUID
    period_start: datetime
    period_end: datetime
    ceiling: int
    used: int
    tenant_id: UUID


class BudgetStatus(BaseModel):
    """
    Response model for GET /budget — matches OpenAPI BudgetStatus schema.
    Source: T-BUD-1.4; design §5.
    """

    ceiling: int
    period: str
    used: int
    remaining: int
    period_start: datetime
    period_end: datetime
    alert_thresholds: List[int]


class BudgetConfig(BaseModel):
    """
    Input/constraints model for the budget configuration on permission grants.
    Source: FR-1; design §2; T-BUD-1.2.
    """

    model_config = ConfigDict(extra="forbid")

    ceiling: int = Field(ge=1)
    period: Literal["hourly", "daily", "weekly", "monthly"]
    alert_thresholds: List[int] = Field(default=[50, 80, 100])

    @field_validator("alert_thresholds")
    @classmethod
    def thresholds_valid(cls, v: List[int]) -> List[int]:
        for t in v:
            if t < 1 or t > 100:
                raise ValueError("Each alert_threshold must be between 1 and 100")
        return sorted(set(v))
