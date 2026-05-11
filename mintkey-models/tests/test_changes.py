"""
Tests for changes.py — LISTEN/NOTIFY wrapper.

TDD: written before implementation per T-1.0.9 (session 2) test-first discipline.
Source: T-1.0.9; design §1; ADR-0014.1 (global channels, per-tenant filter in wrapper).

Requirements verified:
- Tenant scope is required (not empty) to prevent accidental cross-tenant listeners.
- "*" is accepted for platform-admin / all-tenants use.
- Specific tenant list is accepted.
"""
from __future__ import annotations


class TestChangesClientRequiresTenantScope:
    """Empty tenant_scope raises ValueError — ADR-0014.1 guard."""

    def test_changes_client_requires_tenant_scope(self) -> None:
        from mintkey_models.changes import ChangesClient

        try:
            ChangesClient(dsn="postgresql://localhost/test", tenant_scope="")
            assert False, "Expected ValueError not raised"
        except ValueError as exc:
            assert "tenant_scope is required" in str(exc), (
                f"Expected 'tenant_scope is required' in error, got: {exc}"
            )


class TestChangesClientAcceptsAllTenants:
    """tenant_scope='*' (AllTenants) must construct without error — ADR-0014.1."""

    def test_changes_client_accepts_all_tenants(self) -> None:
        from mintkey_models.changes import ChangesClient

        # Must not raise
        client = ChangesClient(dsn="postgresql://localhost/test", tenant_scope="*")
        assert client is not None


class TestChangesClientAcceptsSpecificTenants:
    """List of tenant-id strings must construct without error — ADR-0014.1."""

    def test_changes_client_accepts_specific_tenants(self) -> None:
        from mintkey_models.changes import ChangesClient

        tenant_ids = [
            "tenant_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "tenant_01ARZ3NDEKTSV4RRFFQ69G5FAW",
        ]
        # Must not raise
        client = ChangesClient(dsn="postgresql://localhost/test", tenant_scope=tenant_ids)
        assert client is not None
