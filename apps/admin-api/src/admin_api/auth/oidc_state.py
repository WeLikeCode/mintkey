"""
Shared PKCE login-state store for the OIDC login flow (ADR-0009; ADR-0016.2).

Replaces the old process-local in-memory `_state_store` dict that used to
live in admin_api.auth.oidc. That dict broke OIDC login once admin-api ran
at replicas > 1: /login and /callback can land on different pods, so a
state written on one pod was invisible to a pop() on another, producing a
spurious "state_mismatch" 401.

OidcStateRepository persists state in public.oidc_login_state (see
db/changelog/029-oidc-login-state.yaml) so any replica can read what any
other replica wrote. Rows are single-use (DELETE ... RETURNING on pop) and
short-lived (expires_at, opportunistically GC'd on each put()).

FakeOidcStateRepository provides the exact same async interface backed by
a shared in-memory dict, for hermetic unit tests (the unit CI lane has no
Postgres). Two FakeOidcStateRepository instances constructed over the same
dict simulate two replicas sharing one store.

Source: ADR-0009; ADR-0016.2; Req 2 AC6; db/changelog/023-oauth2-state.yaml
(closest analog: short-lived single-use CSRF-nonce store with the same
opportunistic-GC-on-insert pattern).
"""
from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class OidcStateRepository:
    """Postgres-backed PKCE login-state store shared across admin-api replicas."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def put(
        self,
        state: str,
        code_verifier: str,
        redirect_uri: str,
        ttl_seconds: int,
    ) -> None:
        """Persist PKCE state, first opportunistically GC'ing expired rows.

        Mirrors 023-oauth2-state's "opportunistic GC on each INSERT" pattern,
        keeping abandoned-login rows (browser closed mid-flow, etc.) from
        accumulating without a background job.
        """
        await self._db.execute(text("DELETE FROM oidc_login_state WHERE expires_at < now()"))
        await self._db.execute(
            text(
                "INSERT INTO oidc_login_state"
                " (state, code_verifier, redirect_uri, expires_at)"
                " VALUES (:state, :code_verifier, :redirect_uri,"
                " now() + make_interval(secs => :ttl))"
                " ON CONFLICT (state) DO NOTHING"
            ),
            {
                "state": state,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "ttl": ttl_seconds,
            },
        )

    async def pop(self, state: str) -> dict[str, str] | None:
        """Atomically consume (single-use) and TTL-guard a state row.

        Returns None if the state is unknown OR expired — the caller
        (oidc_token_exchange) treats either case identically as an invalid
        state (ValueError("state_mismatch") -> 401), never a 500.
        """
        result = await self._db.execute(
            text(
                "DELETE FROM oidc_login_state"
                " WHERE state = :state AND expires_at > now()"
                " RETURNING code_verifier, redirect_uri"
            ),
            {"state": state},
        )
        row = result.fetchone()
        if row is None:
            return None
        return {"code_verifier": row[0], "redirect_uri": row[1]}


class FakeOidcStateRepository:
    """In-memory stand-in for OidcStateRepository, used by hermetic unit tests.

    Construct multiple instances over the SAME backing dict to simulate
    multiple admin-api replicas sharing one PKCE state store:

        shared: dict[str, tuple[str, str, float]] = {}
        repo_pod_a = FakeOidcStateRepository(shared)
        repo_pod_b = FakeOidcStateRepository(shared)
        await repo_pod_a.put(...)
        await repo_pod_b.pop(...)  # succeeds — this is the cross-replica fix
    """

    def __init__(self, store: dict[str, tuple[str, str, float]]) -> None:
        self._store = store

    async def put(
        self,
        state: str,
        code_verifier: str,
        redirect_uri: str,
        ttl_seconds: int,
    ) -> None:
        now = time.time()
        expired = [k for k, (_, _, exp) in self._store.items() if exp <= now]
        for k in expired:
            self._store.pop(k, None)

        if state in self._store:
            return
        self._store[state] = (code_verifier, redirect_uri, now + ttl_seconds)

    async def pop(self, state: str) -> dict[str, str] | None:
        entry = self._store.get(state)
        if entry is None:
            return None
        code_verifier, redirect_uri, expires_at = entry
        del self._store[state]
        if expires_at <= time.time():
            return None
        return {"code_verifier": code_verifier, "redirect_uri": redirect_uri}
