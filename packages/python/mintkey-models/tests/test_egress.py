"""
Tests for the agent egress policy.

Source: openspec/changes/agent-principal-and-egress (task 1.1; spec
agent-egress-policy, requirement "Agent-supplied URLs must be public https
targets").
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


def _raising_resolver(error: BaseException) -> Resolver:
    async def fake(host: str) -> list[str]:
        raise error

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
# C-90151371 — refused URLs, in the order the requirement lists them
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-90151371")
def test_C_90151371_refused_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DENY_VAR, "corp.example.com,*.corp.example.net")
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    refused: list[tuple[str, str]] = [
        ("http://example.com/", "not_https"),
        ("https://u:p@example.com/", "userinfo_present"),
        ("https:///x", "host_missing"),
        ("https://ex\u00e4mple.com/", "host_invalid"),
        ("https://10.0.0.5/", "ip_literal"),
        ("https://[::1]/", "ip_literal"),
        ("https://93.184.216.34/", "ip_literal"),
        ("https://localhost/", "denied_name"),
        ("https://intranet/", "denied_name"),
        ("https://intranet./", "denied_name"),
        ("https://localhost./", "denied_name"),
        ("https://db.internal/", "denied_name"),
        ("https://printer.local/", "denied_name"),
        ("https://corp.example.com/", "denied_name"),
        ("https://a.corp.example.net/", "denied_name"),
    ]

    reasons = [_refusal_reason(url) for url, _expected in refused]
    assert reasons == [expected for _url, expected in refused]


# ---------------------------------------------------------------------------
# C-3a64dd27 — names that resolve badly, accepted URLs, address_is_public
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3a64dd27")
def test_C_3a64dd27_names_that_resolve_badly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DENY_VAR, raising=False)
    monkeypatch.delenv("MINTKEY_SSRF_ALLOW_PRIVATE", raising=False)

    non_public = [
        ["10.1.2.3"],
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["100.64.0.1"],
        ["fc00::1"],
        ["224.0.0.1"],
        ["0.0.0.0"],
        ["::ffff:10.0.0.1"],
        ["fe80::1%eth0"],
        ["not-an-address"],
        ["93.184.216.34", "10.0.0.1"],
    ]
    for addresses in non_public:
        monkeypatch.setattr(egress, "resolve_host", _resolver_for(addresses))
        reason = _refusal_reason("https://api.example.com/")
        assert reason == "non_public_address", addresses

    monkeypatch.setattr(egress, "resolve_host", _resolver_for([]))
    assert _refusal_reason("https://api.example.com/") == "unresolvable"

    monkeypatch.setattr(
        egress, "resolve_host", _raising_resolver(OSError("resolver failed"))
    )
    assert _refusal_reason("https://api.example.com/") == "unresolvable"

    # MINTKEY_SSRF_ALLOW_PRIVATE does not apply to agent-supplied URLs.
    monkeypatch.setenv("MINTKEY_SSRF_ALLOW_PRIVATE", "1")
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["10.1.2.3"]))
    assert _refusal_reason("https://api.example.com/") == "non_public_address"


@pytest.mark.l4("C-3a64dd27")
def test_C_3a64dd27_accepted_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DENY_VAR, "*.corp.example.net")
    monkeypatch.setattr(egress, "resolve_host", _resolver_for(["93.184.216.34"]))

    accepted = [
        "https://API.Example.com./v1",
        "https://api.example.com:8443/v1?x=1",
        "https://corp.example.net/",
    ]
    for url in accepted:
        assert asyncio.run(egress.check_agent_target_url(url)) is None, url


@pytest.mark.l4("C-3a64dd27")
def test_C_3a64dd27_address_is_public() -> None:
    assert egress.address_is_public("93.184.216.34") is True
    assert egress.address_is_public("2606:2800:220:1:248:1893:25c8:1946") is True

    assert egress.address_is_public("192.168.1.1") is False
    assert egress.address_is_public("::1") is False
    assert egress.address_is_public("100.64.0.1") is False
    assert egress.address_is_public("fe80::1%eth0") is False
    assert egress.address_is_public("nonsense") is False

    # IPv4-mapped IPv6 is unwrapped before the public check.
    assert egress.address_is_public("::ffff:93.184.216.34") is True
    assert egress.address_is_public("::ffff:10.0.0.1") is False


# ---------------------------------------------------------------------------
# C-97e80bfe — the deny list reader
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-97e80bfe")
def test_C_97e80bfe_deny_names_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DENY_VAR, raising=False)
    assert egress.egress_deny_names() == ()

    monkeypatch.setenv(DENY_VAR, " Corp.Example.com , ,*.X.net")
    assert egress.egress_deny_names() == ("corp.example.com", "*.x.net")

    monkeypatch.setenv(DENY_VAR, "")
    assert egress.egress_deny_names() == ()
