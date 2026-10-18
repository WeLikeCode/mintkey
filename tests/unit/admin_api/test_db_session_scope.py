"""Every route that uses the transactional DB session must commit before the response is sent.

FastAPI >= 0.118 runs the exit code of a yield-dependency AFTER the response has been sent unless
the dependency is declared with scope="function". get_db_session commits in that exit code, so a
route declared with a plain Depends(get_db_session) answered 201 first and committed afterwards: a
client that immediately read what it had just created got 404 (about 7 % of fast POST-then-GET
sequences, seen in the admin-ui e2e suite).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIRoute

from admin_api.db.deps import get_db_session
from admin_api.main import app

SRC = Path(__file__).resolve().parents[3] / "apps" / "admin-api" / "src" / "admin_api"


def _iter_api_routes(routes):
    """FastAPI >= 0.14x wraps include_router() results in lazy _IncludedRouter objects; unwrap them."""
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from _iter_api_routes(inner.routes)


def _db_session_dependants(dependant):
    """Yield every (sub-)dependant of `dependant` whose call is get_db_session."""
    for sub in dependant.dependencies:
        if sub.call is get_db_session:
            yield sub
        yield from _db_session_dependants(sub)


def test_source_scan_covers_files_and_finds_no_default_scope_use() -> None:
    files = list(SRC.rglob("*.py"))
    assert files, f"scanned 0 files under {SRC}: the path is wrong, the check would pass vacuously"
    uses = 0
    offenders: list[str] = []
    for path in files:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if "get_db_session" in line and "Depends(" in line:
                uses += 1
                if re.search(r"Depends\(\s*get_db_session\s*\)", line):
                    offenders.append(f"{path.relative_to(SRC)}:{lineno}")
    assert uses > 0, "found no Depends(get_db_session ...) at all: the scan is not looking at the right code"
    assert not offenders, (
        'Depends(get_db_session) without scope="function" commits after the response is sent: '
        + ", ".join(offenders)
    )


def test_every_route_using_the_db_session_is_function_scoped() -> None:
    routes = list(_iter_api_routes(app.routes))
    using = [(r, list(_db_session_dependants(r.dependant))) for r in routes]
    using = [(r, deps) for r, deps in using if deps]
    assert len(using) > 20, f"only {len(using)} routes use the DB session; the walker is probably broken"
    bad = [
        f"{sorted(r.methods)} {r.path}"
        for r, deps in using
        if any(d.scope != "function" for d in deps)
    ]
    assert not bad, f'routes with a request-scoped get_db_session (commit after the response): {bad}'
