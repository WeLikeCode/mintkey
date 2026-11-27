"""
Tests for the agent egress policy's handling of malformed agent-supplied URLs.

Source: openspec/changes/agent-principal-and-egress-fix-2 (task 1.2; spec
agent-egress-policy, requirement "A malformed agent-supplied URL is refused,
never an error" — feedback FB-002).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from mintkey_models import egress

Resolver = Callable[[str], Awaitable[list[str]]]

DENY_VAR = "MINTKEY_AGENT_EGRESS_DENY"


def _resolver_for(addresses: list[str]) -> Resolver:
    async def fake(host: str) -> list[str]:
        return addresses

    return fake


def _assert_refused(url: str) -> str:
    """Assert *url* is refused, and that no other exception escapes."""
    try:
        asyncio.run(egress.check_agent_target_url(url))
    except egress.TargetNotAllowed as exc:
        reason = exc.reason
        assert isinstance(reason, str) and reason, f"{url}: reason {reason!r}"
        return reason
    except Exception as exc:
        raise AssertionError(
            f"{url} raised {type(exc).__name__} instead of refusing: {exc}"
        ) from exc
    raise AssertionError(f"{url} was accepted")


# ---------------------------------------------------------------------------
# C-879687b1 — empty labels and labels longer than 63 characters
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-879687b1")
def test_C_879687b1_bad_host_labels_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DENY_VAR, raising=False)
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    long_label = "a" * 64
    malformed = (
        "https://a.example..com/",
        "https://.example.com/",
        "https://example..com/",
        f"https://{long_label}.example.com/",
    )
    for url in malformed:
        _assert_refused(url)

    # A label of exactly 63 characters is valid, so the check still passes it.
    assert (
        asyncio.run(
            egress.check_agent_target_url(f"https://{'a' * 63}.example.com/")
        )
        is None
    )


# ---------------------------------------------------------------------------
# C-879687b1 — whitespace, control characters, percent signs and backslashes
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-879687b1")
def test_C_879687b1_forbidden_characters_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DENY_VAR, raising=False)
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    malformed = (
        "https://api.example.com/a b",  # whitespace
        "https://api.example.com/a\tb",  # tab
        "https://api.example.com/a\nb",  # newline
        "https://api.example.com/a\x1fb",  # another control character
        "https://api.example.com/a%20b",  # percent sign
        "https://api.example.com/a\\b",  # backslash
        "https://api.exa\tmple.com/",  # tab urlsplit would strip from the host
        "https://api.exa\nmple.com/",  # newline urlsplit would strip from the host
    )
    for url in malformed:
        _assert_refused(url)

    # An ordinary URL with none of those characters still passes.
    assert (
        asyncio.run(
            egress.check_agent_target_url("https://api.example.com/v1?x=1")
        )
        is None
    )


# ---------------------------------------------------------------------------
# C-879687b1 — last label all decimal digits or 0x-hexadecimal
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-879687b1")
def test_C_879687b1_numeric_last_labels_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DENY_VAR, raising=False)
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    malformed = (
        "https://example.123/",  # last label all decimal digits
        "https://127.1/",  # shorthand IPv4, last label all decimal digits
        "https://foo.0x7f/",  # last label 0x-hexadecimal
        "https://0x7f.1/",  # shorthand IPv4 written as hexadecimal
        "https://api.example.0X1F/",  # uppercase 0X-hexadecimal
    )
    for url in malformed:
        _assert_refused(url)

    # A normal name whose last label is not numeric still passes.
    assert (
        asyncio.run(egress.check_agent_target_url("https://api.example.com/"))
        is None
    )


# ---------------------------------------------------------------------------
# C-879687b1 — a resolver failure on a malformed name never escapes
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-879687b1")
def test_C_879687b1_resolver_error_on_malformed_host_never_escapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DENY_VAR, raising=False)

    async def raising(host: str) -> list[str]:
        # What getaddrinfo does for an empty label or a 64-character label.
        raise UnicodeError("label empty or too long")

    monkeypatch.setattr(egress, "resolve_host", raising)

    malformed = (
        "https://a.example..com/",
        f"https://{'a' * 64}.example.com/",
    )
    for url in malformed:
        _assert_refused(url)
