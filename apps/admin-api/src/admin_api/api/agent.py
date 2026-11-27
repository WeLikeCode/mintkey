"""The one ``/v1/agent`` router.

Every agent-facing area attaches its sub-router here (design D1). ``main.py``
imports this module as ``agent_router`` and includes it once; no other agent
router is imported there.

Source: openspec/changes/agent-service-routes/spec.md — The agent routes are
separate from the operator routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from admin_api.api import agent_services
from admin_api.auth.agent_principal import require_agent_key_shape

router = APIRouter(
    prefix="/v1/agent",
    dependencies=[Depends(require_agent_key_shape)],
)
router.include_router(agent_services.router)
