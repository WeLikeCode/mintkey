"""
canonical_agents — startup-time agent roster consistency check.

Reads data/seed-agents.yaml (relative to the repo root) and compares
the canonical agent names against the live DB.  Logs a one-line summary
and emits a structured audit event on startup.

This is a SOFT signal: admin-api continues to start regardless of drift.
Operators see the summary in 'docker logs mintkey-admin-api-1'.

Usage (called from main.py lifespan on startup):

    from admin_api.services.canonical_agents import check_canonical_agents
    async def _lifespan(app):
        await check_canonical_agents(db_session)
        yield

Source: data/seed-agents.yaml; Fix 3 of anti-drift remediation.
"""
from __future__ import annotations

import logging
import os
import pathlib
from typing import Any

logger = logging.getLogger(__name__)

# Resolve seed file.  Two strategies, in order:
# 1. MINTKEY_SEED_AGENTS_PATH env var — explicit override (use in Docker via volume mount)
# 2. Walk up from this module's location to find data/seed-agents.yaml
#    (works in local dev where the full repo is on disk)
_MODULE_DIR = pathlib.Path(__file__).parent
_REPO_ROOT = (_MODULE_DIR / ".." / ".." / ".." / ".." / "..").resolve()
_SEED_FILE = pathlib.Path(
    os.environ.get("MINTKEY_SEED_AGENTS_PATH", str(_REPO_ROOT / "data" / "seed-agents.yaml"))
)


def _load_canonical_names() -> list[str]:
    """Return the list of canonical agent names from seed-agents.yaml."""
    if not _SEED_FILE.exists():
        logger.warning("canonical_agents: seed file not found at %s — skipping check", _SEED_FILE)
        return []
    try:
        import yaml
    except ImportError:
        logger.warning("canonical_agents: PyYAML not installed — skipping check (pip install pyyaml)")
        return []

    try:
        with open(_SEED_FILE) as fh:
            doc = yaml.safe_load(fh)
        entries: list[dict[str, Any]] = doc.get("agents", []) if isinstance(doc, dict) else []
        return [e["name"] for e in entries if isinstance(e, dict) and "name" in e]
    except Exception as exc:  # noqa: BLE001
        logger.warning("canonical_agents: failed to parse %s: %s", _SEED_FILE, exc)
        return []


async def check_canonical_agents(session: Any) -> None:
    """
    Query the DB for current agent names and log a drift summary.

    Accepts any SQLAlchemy AsyncSession.  Never raises; all errors are logged
    as warnings so startup is never blocked.
    """
    canonical_names = _load_canonical_names()
    if not canonical_names:
        return

    try:
        from sqlalchemy import text

        result = await session.execute(text("SELECT name FROM agents"))
        live_names: set[str] = {row[0] for row in result.fetchall()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("canonical_agents: DB query failed: %s — skipping check", exc)
        return

    canonical_set = set(canonical_names)
    present = canonical_set & live_names
    missing = canonical_set - live_names
    orphans = live_names - canonical_set

    # Filter out ephemeral test agents (agent_test_* prefix) from orphans count
    # so routine test runs don't pollute the drift signal.
    real_orphans = {n for n in orphans if not n.startswith("agent_test_")}

    logger.info(
        "agents: %d canonical present, %d orphans, %d missing%s",
        len(present),
        len(real_orphans),
        len(missing),
        (
            f" — MISSING: {sorted(missing)}" if missing else ""
        ) + (
            f" — ORPHANS: {sorted(real_orphans)}" if real_orphans else ""
        ),
    )

    if missing or real_orphans:
        # Emit a structured JSON log line so operators can grep / alert on it.
        # Format: {"event":"agent.drift","missing":[...],"orphans":[...]}
        import json as _json

        logger.warning(
            "canonical_agents: drift detected — %s",
            _json.dumps(
                {
                    "event": "agent.drift",
                    "canonical_count": len(canonical_names),
                    "present_count": len(present),
                    "orphan_count": len(real_orphans),
                    "missing_count": len(missing),
                    "missing_names": sorted(missing),
                    "orphan_names": sorted(real_orphans),
                }
            ),
        )
