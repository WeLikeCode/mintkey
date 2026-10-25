"""Helpers for checking admin-api's memory limit against its verify concurrency."""

from __future__ import annotations

from collections.abc import Mapping


def to_mib(value: str) -> int:
    raise NotImplementedError


def required_mib(concurrency: int) -> int:
    raise NotImplementedError


def compose_concurrency(environment: Mapping[str, object] | None) -> int:
    raise NotImplementedError


def capacity_problem(name: str, limit: str | None, concurrency: int) -> str | None:
    raise NotImplementedError
