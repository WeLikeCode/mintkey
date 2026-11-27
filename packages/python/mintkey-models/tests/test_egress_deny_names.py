"""
Tests for the agent egress policy's deny-list name matching.

Source: openspec/changes/agent-principal-and-egress-fix-2 (task 1.3; spec
agent-egress-policy, requirement "The deny list matches names however they are
written" — feedback FB-003).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import pytest

from mintkey_models import egress

Resolver = Callable[[str], Awaitable[list[str]]]

DENY_VAR = "MINTKEY_AGENT_EGRESS_DENY"

# Entries that can never match a host name: a bare wildcard, the wildcard with
# an empty suffix, a leading dot, and a wildcard-prefixed name without the dot.
UNUSABLE_ENTRIES = (
    "*",
    "*.",
    ".example.com",
    "*example.com",
)


def _resolver_for(addresses: list[str]) -> Resolver:
    async def fake(host: str) -> list[str]:
        return addresses

    return fake


def _refusal_reason(url: str) -> str:
    try:
        asyncio.run(egress.check_agent_target_url(url))
    except egress.TargetNotAllowed as exc:
        reason = getattr(exc, "reason", None)
        assert isinstance(reason, str), f"{url}: reason {reason!r} is not a string"
        return reason
    raise AssertionError(f"{url} was accepted")


# ---------------------------------------------------------------------------
# C-41b9e69f — the host's trailing dots do not change which entry it matches
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-41b9e69f")
def test_C_41b9e69f_host_trailing_dots_match_deny_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DENY_VAR, "corp.example.com")
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    for url in (
        "https://corp.example.com/",
        "https://corp.example.com./",
        "https://corp.example.com../",
        "https://corp.example.com.../",
    ):
        assert _refusal_reason(url) == "denied_name", url

    # A host with trailing dots that is not denied is still the same name.
    assert (
        asyncio.run(egress.check_agent_target_url("https://api.example.com../")) is None
    )


# ---------------------------------------------------------------------------
# C-41b9e69f — the deny entry's trailing dots do not change which host it denies
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-41b9e69f")
def test_C_41b9e69f_deny_entry_trailing_dots_match_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    for entry in ("corp.example.com.", "corp.example.com.."):
        monkeypatch.setenv(DENY_VAR, entry)
        assert _refusal_reason("https://corp.example.com/") == "denied_name", entry

    for entry in ("*.corp.example.net.", "*.corp.example.net.."):
        monkeypatch.setenv(DENY_VAR, entry)
        for url in (
            "https://a.corp.example.net/",
            "https://a.corp.example.net./",
            "https://a.corp.example.net../",
        ):
            assert _refusal_reason(url) == "denied_name", (entry, url)

    # The wildcard suffix still never matches the bare suffix itself.
    monkeypatch.setenv(DENY_VAR, "*.corp.example.net..")
    assert (
        asyncio.run(egress.check_agent_target_url("https://corp.example.net/")) is None
    )


# ---------------------------------------------------------------------------
# C-41b9e69f — localhost and every name under .localhost are refused
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-41b9e69f")
def test_C_41b9e69f_localhost_and_names_under_it_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DENY_VAR, raising=False)
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    for url in (
        "https://localhost/",
        "https://localhost./",
        "https://localhost../",
        "https://LOCALHOST/",
        "https://foo.localhost/",
        "https://foo.localhost./",
        "https://foo.localhost../",
        "https://a.b.localhost/",
    ):
        assert _refusal_reason(url) == "denied_name", url

    # A name that merely ends in the letters "localhost" is not under .localhost.
    assert (
        asyncio.run(egress.check_agent_target_url("https://notlocalhost.example.com/"))
        is None
    )


# ---------------------------------------------------------------------------
# C-41b9e69f — an entry that can never match is reported once as ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", UNUSABLE_ENTRIES)
@pytest.mark.l4("C-41b9e69f")
def test_C_41b9e69f_unusable_entry_is_logged_once_as_ignored(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    entry: str,
) -> None:
    monkeypatch.setenv(DENY_VAR, entry)
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))
    caplog.set_level(logging.DEBUG)

    # The unusable entry protects nothing, so an ordinary public name passes.
    assert (
        asyncio.run(egress.check_agent_target_url("https://api.example.com/")) is None
    )

    ignored_reports = [
        record for record in caplog.records if "ignor" in record.getMessage().lower()
    ]
    messages = [record.getMessage() for record in caplog.records]
    assert len(ignored_reports) == 1, messages
