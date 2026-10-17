"""Every route that uses the transactional DB session must commit before the response is sent.

FastAPI >= 0.118 runs the exit code of a yield-dependency AFTER the response has been sent unless
the dependency is declared with scope="function". get_db_session commits in that exit code, so a
route declared with a plain Depends(get_db_session) answered 201 first and committed afterwards: a
client that immediately read what it had just created got 404 (about 7 % of runs in the admin-ui e2e
suite: POST /services then GET /services/{id}).
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "apps" / "admin-api" / "src" / "admin_api"


def test_get_db_session_is_always_function_scoped() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(r"Depends\(\s*get_db_session\s*\)", line):
                offenders.append(f"{path.relative_to(SRC)}:{lineno}")
    assert not offenders, (
        'Depends(get_db_session) without scope="function" commits after the response is sent: '
        + ", ".join(offenders)
    )
