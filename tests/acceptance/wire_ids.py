"""Wire-id helpers shared by the stack-based acceptance tests.

Post-#13 (ADR-0017.11) admin-api, MCP and Kong all use Crockford-ULID wire ids (`svc_<26 chars>`),
and the database UUID is the same 128 bits. Kong routes are published as /v1/call/svc_<26 chars>
(OPS-GG, fc29696); the tests used to look for /v1/call/<uuid>.
"""

from __future__ import annotations

import uuid

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def wire_to_uuid(wire_id: str, prefix: str) -> str:
    """svc_<26 Crockford> (or svc_<32 hex>) -> dashed UUID string."""
    tail = wire_id[len(prefix) + 1:]
    if len(tail) == 26:
        val = 0
        for ch in tail.upper():
            val = (val << 5) | CROCKFORD.index(ch)
        return str(uuid.UUID(int=val & ((1 << 128) - 1)))
    if len(tail) == 32:
        return str(uuid.UUID(tail))
    raise ValueError(f"Cannot decode wire ID: {wire_id!r}")


def uuid_to_wire(uuid_str: str, prefix: str) -> str:
    """Dashed UUID string -> prefix_<26 Crockford>."""
    val = uuid.UUID(uuid_str).int
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD[val & 31])
        val >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"
