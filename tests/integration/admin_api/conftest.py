"""
Integration-test fixtures for admin-api.

Boots a real PostgreSQL 16 testcontainer, runs all Liquibase changelogs
against it, then yields a FastAPI TestClient pointed at the test DB.

What is patched / why:
- `admin_api.db.session.DATABASE_URL` and the engine: the module-level
  engine is created at import time from DATABASE_URL. We re-create it
  after setting the env var so SQLAlchemy uses the testcontainer URL.
- `admin_api.db.session.engine` / `AsyncSessionLocal`: re-assigned so
  every part of the app that imports from `admin_api.db.session` gets
  the test engine.
- Nothing else is patched: /v1/health never touches the DB, so the test
  can pass without Vault Adapter or change-channel stubs.

Liquibase is run via the pre-pulled `liquibase/liquibase:4.27.0` Docker
image using subprocess + docker run, with the changelog directory
bind-mounted into the container. This keeps the migrations in sync with
the real changelogs automatically.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient
from testcontainers.postgres import PostgresContainer

# Ensure the source trees are on sys.path (mirrors the top-level conftest.py).
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
for _src in (
    _REPO_ROOT / "admin-api" / "src",
    _REPO_ROOT / "mintkey-models",
):
    _str = str(_src)
    if _str not in sys.path:
        sys.path.insert(0, _str)

_CHANGELOG_DIR = _REPO_ROOT / "admin-api" / "db" / "changelog"
_POSTGRES_IMAGE = "postgres:16"
_LIQUIBASE_IMAGE = "liquibase/liquibase:4.27.0"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL 16 container and yield it for the session."""
    with PostgresContainer(_POSTGRES_IMAGE) as pg:
        yield pg


def _get_container_bridge_ip(container_id: str) -> str:
    """
    Return the container's IP on the bridge network.

    On macOS, Docker Desktop containers communicate via the Docker bridge
    network — `--network host` and `localhost` do not work. We inspect the
    container to get its bridge IP so that a second docker-run (Liquibase)
    on the same bridge network can reach it.
    """
    result = subprocess.run(
        [
            "docker", "inspect",
            "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container_id,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture(scope="session")
def apply_migrations(postgres_container: PostgresContainer):
    """
    Run all Liquibase changelogs against the testcontainer DB.

    Uses `docker run` so we don't need a local Liquibase install — only
    the pre-pulled liquibase/liquibase:4.27.0 image is required.

    The Liquibase container is placed on the same Docker bridge network as
    the Postgres testcontainer, and we use the Postgres container's internal
    bridge IP for the JDBC URL. This works on both macOS (Docker Desktop)
    and Linux — unlike `--network host` which only works on Linux.
    """
    container_id = postgres_container.get_wrapped_container().id
    bridge_ip = _get_container_bridge_ip(container_id)
    db = postgres_container.dbname
    user = postgres_container.username
    password = postgres_container.password

    jdbc_url = f"jdbc:postgresql://{bridge_ip}:5432/{db}"

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{_CHANGELOG_DIR}:/liquibase/changelog",
        _LIQUIBASE_IMAGE,
        f"--url={jdbc_url}",
        f"--username={user}",
        f"--password={password}",
        "--changeLogFile=changelog/db.changelog-master.yaml",
        "update",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"Liquibase migration failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    return result


@pytest.fixture(scope="session")
def admin_app(postgres_container: PostgresContainer, apply_migrations):
    """
    Yield a TestClient for admin-api pointed at the testcontainer DB.

    The module-level `engine` in admin_api.db.session is re-created here
    so all route handlers use the test database.
    """
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    db = postgres_container.dbname
    user = postgres_container.username
    password = postgres_container.password

    db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    # Set env var before importing the app so any lazy references pick it up.
    os.environ["DATABASE_URL"] = db_url

    # Re-create the engine and session factory in-place so all importers of
    # admin_api.db.session get the testcontainer-backed objects.
    import admin_api.db.session as _session_mod

    new_engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    new_sessionmaker = async_sessionmaker(
        bind=new_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    _session_mod.engine = new_engine
    _session_mod.AsyncSessionLocal = new_sessionmaker

    from admin_api.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
