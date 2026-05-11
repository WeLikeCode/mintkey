"""
Tests for Pydantic schemas and SQLAlchemy Mapped types in mintkey-models.

TDD: written before implementation per T-1.0.9 Test-first discipline.
Source: T-1.0.9; design §1; ADR-0012; ADR-0015.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TestTenantSchema:
    def test_tenant_schema_validates(self) -> None:
        from mintkey_models.schemas import TenantOut

        data = {
            "id": uuid.uuid4(),
            "slug": "acme",
            "display_name": "Acme Corp",
            "isolation_mode": "row",
            "status": "active",
            "created_at": _utcnow(),
        }
        tenant = TenantOut(**data)
        assert tenant.slug == "acme"
        assert tenant.isolation_mode == "row"
        assert tenant.status == "active"

    def test_tenant_schema_from_attributes(self) -> None:
        """ConfigDict(from_attributes=True) must be set for SQLAlchemy row compat."""
        from mintkey_models.schemas import TenantOut

        class _FakeRow:
            id = uuid.uuid4()
            slug = "test-slug"
            display_name = "Test"
            isolation_mode = "row"
            status = "active"
            created_at = _utcnow()

        tenant = TenantOut.model_validate(_FakeRow())
        assert tenant.slug == "test-slug"


class TestServiceSchema:
    def test_service_schema_validates(self) -> None:
        from mintkey_models.schemas import ServiceOut

        data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "name": "My API",
            "slug": "my-api",
            "auth_scheme": "bearer_token",
            "status": "active",
            "created_at": _utcnow(),
        }
        svc = ServiceOut(**data)
        assert svc.slug == "my-api"
        assert svc.auth_scheme == "bearer_token"

    def test_service_schema_from_attributes(self) -> None:
        from mintkey_models.schemas import ServiceOut

        class _FakeRow:
            id = uuid.uuid4()
            tenant_id = uuid.uuid4()
            name = "Svc"
            slug = "svc"
            auth_scheme = "api_key"
            status = "active"
            created_at = _utcnow()

        svc = ServiceOut.model_validate(_FakeRow())
        assert svc.slug == "svc"


class TestAgentSchema:
    def test_agent_schema_validates(self) -> None:
        from mintkey_models.schemas import AgentOut

        data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "name": "my-agent",
            "status": "active",
            "api_key_fingerprint": "abcd1234",
            "created_at": _utcnow(),
        }
        agent = AgentOut(**data)
        assert agent.name == "my-agent"
        assert agent.api_key_fingerprint == "abcd1234"


class TestOperatorSchema:
    def test_operator_schema_validates(self) -> None:
        from mintkey_models.schemas import OperatorOut

        data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "email": "user@example.com",
            "display_name": "Alice",
            "is_platform_admin": False,
            "status": "active",
            "created_at": _utcnow(),
        }
        op = OperatorOut(**data)
        assert op.email == "user@example.com"
        assert op.is_platform_admin is False


class TestPermissionGrantSchema:
    def test_permission_grant_schema_validates(self) -> None:
        from mintkey_models.schemas import PermissionGrantOut

        data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "agent_id": uuid.uuid4(),
            "service_id": uuid.uuid4(),
            "action": "read",
            "constraints": {},
            "created_at": _utcnow(),
        }
        pg = PermissionGrantOut(**data)
        assert pg.action == "read"
        assert pg.constraints == {}


class TestAuditEventSchema:
    def test_audit_event_schema_validates(self) -> None:
        from mintkey_models.schemas import AuditEventOut

        data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "event_type": "service.created",
            "actor_id": uuid.uuid4(),
            "actor_type": "operator",
            "target_id": uuid.uuid4(),
            "target_type": "service",
            "payload": {"key": "value"},
            "at": _utcnow(),
        }
        ae = AuditEventOut(**data)
        assert ae.event_type == "service.created"
        assert ae.payload == {"key": "value"}

    def test_audit_event_nullable_fields(self) -> None:
        """actor_id, actor_type, target_id, target_type are all nullable."""
        from mintkey_models.schemas import AuditEventOut

        data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "event_type": "system.boot",
            "actor_id": None,
            "actor_type": None,
            "target_id": None,
            "target_type": None,
            "payload": {},
            "at": _utcnow(),
        }
        ae = AuditEventOut(**data)
        assert ae.actor_id is None


class TestDbTableNames:
    """
    Verify each SQLAlchemy Mapped class has the __tablename__ matching Liquibase.
    Source: ADR-0015 (SQLAlchemy mirrors Liquibase, never authoritative).
    """

    def test_db_table_names_match_liquibase(self) -> None:
        from mintkey_models.db import (
            AdminRequestJti,
            Agent,
            AuditChainState,
            AuditEvent,
            Credential,
            Operator,
            OperatorTenantMembership,
            PermissionGrant,
            Service,
            ServiceApiKey,
            ServiceIdentity,
            Session,
            Tenant,
            TenantSetting,
        )

        expected = {
            Tenant: "tenants",
            Operator: "operators",
            OperatorTenantMembership: "operator_tenant_memberships",
            Session: "sessions",
            Agent: "agents",
            Service: "services",
            Credential: "credentials",
            PermissionGrant: "permission_grants",
            AuditEvent: "audit_events",
            TenantSetting: "tenant_settings",
            AdminRequestJti: "admin_request_jti",
            ServiceIdentity: "service_identities",
            AuditChainState: "audit_chain_state",
            ServiceApiKey: "service_api_keys",  # task 1.3; Req 11.5
        }

        for cls, expected_name in expected.items():
            assert cls.__tablename__ == expected_name, (
                f"{cls.__name__}.__tablename__ should be '{expected_name}', "
                f"got '{cls.__tablename__}'"
            )


# ---------------------------------------------------------------------------
# Task 1.3 — ServiceApiKey ORM + Pydantic models  (Req 11.5; ADR-0018 §9)
# ---------------------------------------------------------------------------


class TestServiceApiKeySchema:
    def test_service_api_key_create_validates(self) -> None:
        """ServiceApiKeyCreate accepts valid request body; rejects extra keys."""
        from mintkey_models.schemas import ServiceApiKeyCreate

        body = ServiceApiKeyCreate(
            service_id=str(uuid.uuid4()),
            allowed_actions=["read:health"],
        )
        assert body.allowed_actions == ["read:health"]
        assert body.expires_at is None
        assert body.constraints is None

    def test_service_api_key_create_rejects_empty_actions(self) -> None:
        """allowed_actions must be non-empty (Req 7.2 — CHECK constraint mirror)."""
        import pytest
        from pydantic import ValidationError
        from mintkey_models.schemas import ServiceApiKeyCreate

        with pytest.raises(ValidationError):
            ServiceApiKeyCreate(service_id=str(uuid.uuid4()), allowed_actions=[])

    def test_service_api_key_out_no_plaintext(self) -> None:
        """ServiceApiKey (list/show) has no plaintext_key field (Req 1.2, 10.1)."""
        from mintkey_models.schemas import ServiceApiKey

        data = {
            "api_key_id": "svckey_01HXYZABC",
            "key_fingerprint": "a1b2c3d4e5f6a7b8",
            "service_id": uuid.uuid4(),
            "allowed_actions": ["read:health"],
            "constraints": None,
            "expires_at": None,
            "last_used_at": None,
            "created_at": _utcnow(),
            "created_by": uuid.uuid4(),
            "status": "active",
        }
        key = ServiceApiKey(**data)
        assert key.status == "active"
        assert not hasattr(key, "plaintext_key"), "ServiceApiKey must not expose plaintext"

    def test_service_api_key_created_has_plaintext(self) -> None:
        """ServiceApiKeyCreated (201) carries plaintext_key (shown once)."""
        from mintkey_models.schemas import ServiceApiKeyCreated

        data = {
            "api_key_id": "svckey_01HXYZABC",
            "key_fingerprint": "a1b2c3d4e5f6a7b8",
            "service_id": uuid.uuid4(),
            "allowed_actions": ["read:health"],
            "constraints": None,
            "expires_at": None,
            "last_used_at": None,
            "created_at": _utcnow(),
            "created_by": uuid.uuid4(),
            "status": "active",
            "plaintext_key": "mk_svckey_AAAABBBBCCCCDDDD",
        }
        created = ServiceApiKeyCreated(**data)
        assert created.plaintext_key == "mk_svckey_AAAABBBBCCCCDDDD"

    def test_service_api_key_orm_tablename(self) -> None:
        """ServiceApiKey ORM class maps to service_api_keys."""
        from mintkey_models.db import ServiceApiKey as SAK

        assert SAK.__tablename__ == "service_api_keys"
