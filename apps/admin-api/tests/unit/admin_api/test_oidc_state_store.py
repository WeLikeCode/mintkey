"""
Unit tests for OidcStateRepository using FakeOidcStateRepository.

Source: openspec/changes/kubernetes-readiness/specs/oidc-state-store/spec.md.
"""
from __future__ import annotations

import time

import pytest

from admin_api.auth.oidc_state import FakeOidcStateRepository


class TestOidcStateRepository:
    @pytest.mark.asyncio
    async def test_put_and_pop_returns_entry(self) -> None:
        store: dict = {}
        repo = FakeOidcStateRepository(store)
        await repo.put("s1", "cv1", "https://example.com/cb", 600)
        entry = await repo.pop("s1")
        assert entry is not None
        assert entry["code_verifier"] == "cv1"
        assert entry["redirect_uri"] == "https://example.com/cb"

    @pytest.mark.asyncio
    async def test_pop_expired_returns_none(self) -> None:
        store: dict = {}
        repo = FakeOidcStateRepository(store)
        await repo.put("s2", "cv2", "https://example.com/cb", -1)
        entry = await repo.pop("s2")
        assert entry is None

    @pytest.mark.asyncio
    async def test_pop_single_use(self) -> None:
        store: dict = {}
        repo = FakeOidcStateRepository(store)
        await repo.put("s3", "cv3", "https://example.com/cb", 600)
        first = await repo.pop("s3")
        second = await repo.pop("s3")
        assert first is not None
        assert second is None

    @pytest.mark.asyncio
    async def test_fresh_instance_reads(self) -> None:
        store: dict = {}
        repo_a = FakeOidcStateRepository(store)
        await repo_a.put("s4", "cv4", "https://example.com/cb", 600)
        repo_b = FakeOidcStateRepository(store)
        entry = await repo_b.pop("s4")
        assert entry is not None
        assert entry["code_verifier"] == "cv4"
