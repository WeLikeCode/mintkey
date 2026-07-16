"""
mintkey-models — shared Pydantic schemas and SQLAlchemy Mapped types.

Session 1: schemas.py, db.py, tenant_ctx.py
Source: T-1.0.9; design §1; ADR-0012; ADR-0015.
"""

from mintkey_models.db import (
    AdminRequestJti,
    Agent,
    AgentSecret,
    AgentSecretGrant,
    AuditChainState,
    AuditEvent,
    Base,
    BudgetCounter,
    Credential,
    Operator,
    OperatorTenantMembership,
    PermissionGrant,
    Service,
    ServiceApiKey as ServiceApiKeyModel,
    ServiceIdentity,
    Session,
    Tenant,
    TenantSetting,
)
from mintkey_models.schemas import (
    AgentOut,
    AuditEventOut,
    BudgetConfig,
    BudgetCounterOut,
    BudgetStatus,
    OperatorOut,
    PermissionGrantOut,
    ServiceApiKey,
    ServiceApiKeyCreate,
    ServiceApiKeyCreated,
    ServiceOut,
    TenantOut,
)

__all__ = [
    # SQLAlchemy models
    "AdminRequestJti",
    "Agent",
    "AgentSecret",
    "AgentSecretGrant",
    "AuditChainState",
    "AuditEvent",
    "Base",
    "BudgetCounter",
    "Credential",
    "Operator",
    "OperatorTenantMembership",
    "PermissionGrant",
    "Service",
    "ServiceApiKeyModel",
    "ServiceIdentity",
    "Session",
    "Tenant",
    "TenantSetting",
    # Pydantic schemas
    "AgentOut",
    "AuditEventOut",
    "BudgetConfig",
    "BudgetCounterOut",
    "BudgetStatus",
    "OperatorOut",
    "PermissionGrantOut",
    "ServiceApiKey",
    "ServiceApiKeyCreate",
    "ServiceApiKeyCreated",
    "ServiceOut",
    "TenantOut",
]
