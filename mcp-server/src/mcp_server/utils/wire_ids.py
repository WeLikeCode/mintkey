"""
Wire-form ID encoding/decoding — ADR-0017.11.

Copied (not imported) from admin-api/src/admin_api/utils/wire_ids.py so that
mcp-server has no runtime dependency on the admin-api package tree.
The container Dockerfile does not copy admin-api sources; mintkey-models is the
only shared package available at runtime.

DO NOT modify the encoding logic here independently — keep in sync with
admin-api/src/admin_api/utils/wire_ids.py (OPS-AA owns that copy).

Canonical encoder: db_uuid_to_wire(uuid_value, prefix) → "<prefix>_<26-char Crockford ULID>"
Canonical decoder: wire_to_db_uuid(wire_id, prefix) → UUID string (dashed form)

The decoder accepts BOTH wire forms for backward-compatibility:
  - <prefix>_<26 Crockford chars>  — canonical (post-R13 / ADR-0017 alignment)
  - <prefix>_<32 hex chars>        — legacy hex form emitted by pre-R13 list/get endpoints

DO NOT remove the dual-form decoder — older clients and stored audit_event references
may still carry the 32-hex form.  Only the encoder output has been standardised.

Source: ADR-0017.11; #13 (wire-form unification); OPS-CC.
"""
from __future__ import annotations

import uuid as _uuid_mod
from typing import Union

# Crockford base32 alphabet (uppercase, no I/L/O/U) — ADR-0017.11
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def db_uuid_to_wire(uuid_value: Union[str, _uuid_mod.UUID], prefix: str) -> str:
    """
    Encode a DB UUID into the canonical Crockford wire-form ID.

    Parameters
    ----------
    uuid_value : str | uuid.UUID
        The UUID as stored in the database (with or without dashes).
    prefix : str
        The resource prefix WITHOUT trailing underscore, e.g. "svc".

    Returns
    -------
    str
        "<prefix>_<26-char uppercase Crockford base32>"

    Example
    -------
    >>> db_uuid_to_wire("6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd", "svc")
    'svc_3CJKM80H0J5A1KJ2QM3WK6FKTH'
    """
    # Normalise to UUID integer
    if isinstance(uuid_value, _uuid_mod.UUID):
        val = uuid_value.int
    else:
        val = _uuid_mod.UUID(str(uuid_value).replace("-", "")).int

    # Encode 128 bits into 26 Crockford base32 chars
    chars: list[str] = []
    for _ in range(26):
        chars.append(_CROCKFORD[val & 0x1F])
        val >>= 5
    chars.reverse()

    return f"{prefix}_{chars[0]}{''.join(chars[1:])}"


def wire_to_db_uuid(wire_id: str, prefix: str) -> str:
    """
    Decode a prefixed wire-form ID to the dashed UUID string stored in the DB.

    Accepts BOTH wire forms (backward-compat):
      - <prefix>_<26 Crockford chars>  — canonical post-R13 form
      - <prefix>_<32 hex chars>        — legacy pre-R13 list/get form

    Falls back to returning wire_id unchanged if it does not match a known
    prefix pattern (allows callers to pass raw UUID strings too — backward compat).

    Raises ValueError if the wire_id matches the prefix but cannot be decoded.

    Source: ADR-0017.11; #13; OPS-CC.
    """
    if wire_id.startswith(f"{prefix}_"):
        tail = wire_id[len(prefix) + 1:]
        if len(tail) == 26:
            # Crockford base32 ULID form — canonical
            try:
                val = 0
                for ch in tail.upper():
                    val = (val << 5) | _CROCKFORD.index(ch)
                val &= (1 << 128) - 1
                h = f"{val:032x}"
                return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
            except (ValueError, IndexError):
                raise ValueError(f"Invalid wire ID (Crockford form): {wire_id}")
        if len(tail) == 32:
            # Hex form: <prefix>_<uuid-without-dashes>  — legacy
            try:
                return (
                    f"{tail[:8]}-{tail[8:12]}-{tail[12:16]}"
                    f"-{tail[16:20]}-{tail[20:]}"
                )
            except Exception:
                raise ValueError(f"Invalid wire ID (hex form): {wire_id}")
    # Not a prefixed ID — return as-is (plain UUID string, raw UUID, etc.)
    return wire_id
