"""
Tenant context middleware helper for mcp-server.

Re-exports set_tenant_context from mintkey_models so callers import from a
single location within this package.

Source: ADR-0008; ADR-0016.3; Req MT-2.
"""
from __future__ import annotations

from mintkey_models.tenant_ctx import set_tenant_context  # noqa: F401
