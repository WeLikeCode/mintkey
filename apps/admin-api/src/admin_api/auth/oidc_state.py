"""
OIDC PKCE login state persistence.

Source: openspec/changes/kubernetes-readiness/specs/oidc-state-store/spec.md.
"""
from __future__ import annotations

import time
from typing import Any, TypedDict


class OidcStateEntry(TypedDict):
    code_verifier: str
    redirect_uri: str


class OidcStateRepository:
    """Persists OIDC PKCE login state with TTL in the oidc_login_state table."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def put(
        self,
        state: str,
        code_verifier: str,
        redirect_uri: str,
        ttl_seconds: int,
    ) -> None:
        from sqlalchemy import text

        await self._session.execute(
            text(
                "INSERT INTO oidc_login_state(state, code_verifier, redirect_uri, expires_at) "
                "VALUES (:state, :code_verifier, :redirect_uri, now() + make_interval(secs => :ttl)) "
                "ON CONFLICT (state) DO NOTHING"
            ),
            {
                "state": state,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "ttl": ttl_seconds,
            },
        )

    async def pop(self, state: str) -> OidcStateEntry | None:
        from sqlalchemy import text

        result = await self._session.execute(
            text(
                "DELETE FROM oidc_login_state WHERE state = :state AND expires_at > now() "
                "RETURNING code_verifier, redirect_uri"
            ),
            {"state": state},
        )
        row = result.fetchone()
        if row is None:
            return None
        return {"code_verifier": row[0], "redirect_uri": row[1]}


class FakeOidcStateRepository:
    """In-memory OidcStateRepository for testing."""

    def __init__(self, store: dict[str, tuple[str, str, float]]) -> None:
        self._store = store

    async def put(
        self,
        state: str,
        code_verifier: str,
        redirect_uri: str,
        ttl_seconds: int,
    ) -> None:
        self._store[state] = (code_verifier, redirect_uri, time.time() + ttl_seconds)

    async def pop(self, state: str) -> OidcStateEntry | None:
        entry = self._store.pop(state, None)
        if entry is None:
            return None
        code_verifier, redirect_uri, expires_at = entry
        if time.time() > expires_at:
            return None
        return {"code_verifier": code_verifier, "redirect_uri": redirect_uri}
