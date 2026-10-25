"""Helpers for checking admin-api's memory limit against its verify concurrency."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

_CONCURRENCY_ENV = "MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY"
_DEFAULT_CONCURRENCY = 4
_MIB_PER_VERIFY = 64
_BASE_MIB = 256

_MEMORY_RE = re.compile(r"(\d+)(Mi|Gi|m|M|g|G)", re.ASCII)


def to_mib(value: str) -> int:
    match = _MEMORY_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"unsupported memory value: {value!r}")
    amount, unit = match.groups()
    factor = 1024 if unit[0] in ("g", "G") else 1
    return int(amount) * factor


def required_mib(concurrency: int) -> int:
    return concurrency * _MIB_PER_VERIFY + _BASE_MIB


def compose_concurrency(environment: Mapping[str, object] | None) -> int:
    if environment is None or _CONCURRENCY_ENV not in environment:
        return _DEFAULT_CONCURRENCY
    return int(cast("str | int", environment[_CONCURRENCY_ENV]))


def capacity_problem(
    name: str, limit: str | None, concurrency: int
) -> str | None:
    if limit is None:
        return None
    limit_mib = to_mib(limit)
    required = required_mib(concurrency)
    if limit_mib >= required:
        return None
    return (
        f"{name}: admin-api memory limit {limit} ({limit_mib} MiB) is below the "
        f"required {required} MiB for {concurrency} concurrent verifies"
    )
