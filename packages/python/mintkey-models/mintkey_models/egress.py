"""
Agent egress policy: the rule for URLs an agent supplies as service targets.

Source: openspec/changes/agent-principal-and-egress (task 1.1; spec
agent-egress-policy, requirement "Agent-supplied URLs must be public https
targets").
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
from urllib.parse import urlsplit

DENY_ENV = "MINTKEY_AGENT_EGRESS_DENY"

# A DNS label may be at most 63 characters and may not be empty.
_MAX_LABEL_LENGTH = 63

# A host whose last label is all decimal digits or 0x-hexadecimal is a numeric
# shorthand (``127.1``, ``0x7f.1``) that the resolver would interpret as an IP
# address, so it is refused rather than resolved.
_NUMERIC_LAST_LABEL = re.compile(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)\Z")

# IPv6 forms that carry an IPv4 address: NAT64, 6to4 and Teredo. They are
# classified by their IPv6 prefix, so an embedded private IPv4 address could
# otherwise slip through ``ip.is_global`` (which treats 64:ff9b::/96 as global
# on some Python versions). The proxy's connect-time guard refuses the same
# ranges, and this set keeps the create-time check in step with it.
_IPV4_EMBEDDING_V6: tuple[ipaddress.IPv6Network, ...] = tuple(
    ipaddress.IPv6Network(cidr)
    for cidr in ("64:ff9b::/96", "2002::/16", "2001::/32")
)


class TargetNotAllowed(Exception):
    """An agent-supplied target URL was refused; ``reason`` names the rule."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def resolve_host(host: str) -> list[str]:
    """Resolve *host* to its addresses.

    The seam tests replace; a resolver failure surfaces as ``OSError``.
    """
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None)
    addresses: list[str] = []
    for info in infos:
        address = info[4][0]
        if isinstance(address, str):
            addresses.append(address)
    return addresses


def egress_deny_names() -> tuple[str, ...]:
    """Return the lower-cased, non-empty names of ``MINTKEY_AGENT_EGRESS_DENY``."""
    raw = os.environ.get(DENY_ENV, "")
    return tuple(name.strip().lower() for name in raw.split(",") if name.strip())


def address_is_public(address: str) -> bool:
    """Return True when *address* is a global unicast address."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif any(ip in network for network in _IPV4_EMBEDDING_V6):
            return False
    return ip.is_global and not ip.is_multicast


def _has_forbidden_character(url: str) -> bool:
    """Return True when *url* carries whitespace, a control, ``%`` or ``\\``.

    Checked on the raw string before ``urlsplit``, which silently removes tabs
    and newlines (so the validated host would otherwise differ from the stored
    URL).
    """
    for character in url:
        if character in "%\\" or character.isspace():
            return True
        if ord(character) < 0x20 or ord(character) == 0x7F:
            return True
    return False


def _labels_are_valid(host: str) -> bool:
    """Return True when every dot-separated label is non-empty and short enough."""
    return all(
        label and len(label) <= _MAX_LABEL_LENGTH for label in host.split(".")
    )


def _is_denied_name(host: str) -> bool:
    for entry in egress_deny_names():
        if entry.startswith("*."):
            if host.endswith(entry[1:]):
                return True
        elif host == entry:
            return True
    return False


async def check_agent_target_url(url: str) -> None:
    """Raise ``TargetNotAllowed`` unless *url* is a public https target."""
    if _has_forbidden_character(url):
        raise TargetNotAllowed("host_invalid")

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise TargetNotAllowed("host_invalid") from exc

    if parts.scheme != "https":
        raise TargetNotAllowed("not_https")
    if parts.username is not None or parts.password is not None:
        raise TargetNotAllowed("userinfo_present")

    try:
        host = parts.hostname
    except ValueError as exc:
        raise TargetNotAllowed("host_invalid") from exc
    if not host:
        raise TargetNotAllowed("host_missing")

    host = host.lower()
    if host.endswith("."):
        host = host[:-1]

    try:
        host.encode("ascii")
    except UnicodeEncodeError as exc:
        raise TargetNotAllowed("host_invalid") from exc

    if not _labels_are_valid(host):
        raise TargetNotAllowed("host_invalid")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise TargetNotAllowed("ip_literal")

    if _NUMERIC_LAST_LABEL.fullmatch(host.rsplit(".", 1)[-1]):
        raise TargetNotAllowed("host_invalid")

    if (
        host == "localhost"
        or "." not in host
        or host.endswith(".internal")
        or host.endswith(".local")
        or _is_denied_name(host)
    ):
        raise TargetNotAllowed("denied_name")

    try:
        addresses = await resolve_host(host)
    except (OSError, UnicodeError) as exc:
        raise TargetNotAllowed("unresolvable") from exc

    if not addresses:
        raise TargetNotAllowed("unresolvable")
    if not all(address_is_public(address) for address in addresses):
        raise TargetNotAllowed("non_public_address")
