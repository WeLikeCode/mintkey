"""Acceptance checks for admin-api's memory limit and its verify concurrency.

Requirement: agent-key-auth › admin-api's memory limit fits its verify
concurrency. The three definitions that set a limit are read from the compose
files and the Helm chart; the rule itself lives in ``admin_api.capacity``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _path in (str(ADMIN_API_SRC), str(MODELS_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from admin_api.capacity import (  # noqa: E402
    capacity_problem,
    compose_concurrency,
    required_mib,
    to_mib,
)

COMPOSE_YML = REPO_ROOT / "infra" / "compose" / "docker-compose.yml"
COMPOSE_GHCR_YML = REPO_ROOT / "infra" / "compose" / "docker-compose.ghcr.yml"
HELM_VALUES = REPO_ROOT / "deploy" / "helm" / "mintkey" / "values.yaml"

CONCURRENCY_ENV = "MINTKEY_AGENT_KEY_VERIFY_CONCURRENCY"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        pytest.fail(f"missing file: {path}")
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        pytest.fail(f"{path}: expected a YAML mapping")
    return loaded


def _mapping(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        pytest.fail(message)
    return value


def _compose_definition(path: Path) -> tuple[str, dict[str, Any] | None]:
    data = _load_yaml(path)
    services = _mapping(data.get("services"), f"{path}: no services block")
    service = _mapping(
        services.get("admin-api"), f"{path}: no services.admin-api block"
    )
    limit = service.get("mem_limit")
    if not isinstance(limit, str):
        pytest.fail(f"{path}: services.admin-api.mem_limit is not a string")
    environment = service.get("environment")
    if environment is not None:
        environment = _mapping(
            environment,
            f"{path}: services.admin-api.environment is not a mapping",
        )
    return limit, environment


def _helm_memory(path: Path) -> str:
    data = _load_yaml(path)
    admin_api = _mapping(data.get("adminApi"), f"{path}: no adminApi block")
    resources = _mapping(
        admin_api.get("resources"), f"{path}: no adminApi.resources block"
    )
    limits = _mapping(
        resources.get("limits"), f"{path}: no adminApi.resources.limits block"
    )
    memory = limits.get("memory")
    if not isinstance(memory, str):
        pytest.fail(f"{path}: adminApi.resources.limits.memory is not a string")
    return memory


@pytest.mark.l4("C-cbd20f5c")
def test_C_cbd20f5c_three_definitions_fit_the_rule() -> None:
    for path in (COMPOSE_YML, COMPOSE_GHCR_YML):
        limit, environment = _compose_definition(path)
        concurrency = compose_concurrency(environment)
        assert concurrency == 4, f"{path}: compose_concurrency returned {concurrency}"
        assert to_mib(limit) == 512, f"{path}: {limit!r} does not convert to 512 MiB"
        problem = capacity_problem(str(path), limit, concurrency)
        assert problem is None, problem

    helm_memory = _helm_memory(HELM_VALUES)
    assert to_mib(helm_memory) == 512, (
        f"{HELM_VALUES}: {helm_memory!r} does not convert to 512 MiB"
    )
    helm_problem = capacity_problem(str(HELM_VALUES), helm_memory, 4)
    assert helm_problem is None, helm_problem


@pytest.mark.l4("C-06752b13")
def test_C_06752b13_capacity_problem_reports_a_definition_below_the_rule() -> None:
    assert required_mib(8) == 768
    assert capacity_problem("values.yaml", "512Mi", 8) == (
        "values.yaml: admin-api memory limit 512Mi (512 MiB) is below the "
        "required 768 MiB for 8 concurrent verifies"
    )


@pytest.mark.l4("C-f6faf63f")
def test_C_f6faf63f_capacity_problem_ignores_a_definition_without_a_limit() -> None:
    assert capacity_problem("x", None, 4) is None
    assert capacity_problem("x", "512Mi", 8) == (
        "x: admin-api memory limit 512Mi (512 MiB) is below the required "
        "768 MiB for 8 concurrent verifies"
    )


@pytest.mark.l4("C-434fcc7f")
def test_C_434fcc7f_to_mib_converts_memory_units_and_refuses_others() -> None:
    for value, expected in (
        ("512m", 512),
        ("512M", 512),
        ("512Mi", 512),
        ("1g", 1024),
        ("1G", 1024),
        ("1Gi", 1024),
    ):
        assert to_mib(value) == expected, value

    for value in ("512", "512k", "512 Mi", "", "abc"):
        with pytest.raises(ValueError) as excinfo:
            to_mib(value)
        assert value in str(excinfo.value)


@pytest.mark.l4("C-e54cc104")
def test_C_e54cc104_compose_concurrency_refuses_a_non_integer_value() -> None:
    with pytest.raises(ValueError) as excinfo:
        compose_concurrency({CONCURRENCY_ENV: "four"})
    assert "four" in str(excinfo.value)
