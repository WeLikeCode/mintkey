"""
Service template endpoints — OPS-R.

GET /v1/service-templates          — list operator-curated starter templates
GET /v1/service-templates/{slug}   — get a single template by slug

Templates are static JSON files bundled with the admin-api image.
No auth beyond what the rest of /v1 enforces (OperatorSession or OperatorBearer).
Read-only, non-sensitive — no audit emission required.
"""
from pathlib import Path
import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1/service-templates")

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "service_templates"


def _load_all() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in _TEMPLATES_DIR.glob("*.json")}


@router.get("")
async def list_templates():
    tmpls = _load_all()
    summaries = [
        {
            "slug": t["slug"],
            "name": t["name"],
            "display_name": t["display_name"],
            "description": t["description"],
            "category": t.get("category"),
            "icon": t.get("icon"),
        }
        for t in tmpls.values()
    ]
    summaries.sort(key=lambda x: x["name"])
    return JSONResponse({"templates": summaries})


@router.get("/{slug}")
async def get_template(slug: str):
    tmpls = _load_all()
    if slug not in tmpls:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": f"template {slug!r} not found"},
        )
    return JSONResponse(tmpls[slug])
