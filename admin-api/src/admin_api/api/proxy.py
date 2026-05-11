"""
Credential-injecting reverse proxy endpoint.

POST /v1/proxy/call/{service_id}/{path_suffix}
GET  /v1/proxy/call/{service_id}/{path_suffix}
(all HTTP methods via the shared helper)

Flow:
  1. Validate mk_svckey_* Bearer token via argon2id against service_api_keys.
  2. Look up service base_url + auth_scheme.
  3. Retrieve plaintext credential from in-memory vault.
  4. Inject credential into outbound request headers.
  5. Forward request to backend; stream response back.

Architecture constraints:
  - Plaintext credential NEVER logged, audited, or returned — ADR-0014.4, S-SEC-1.
  - All SQL uses bound parameters — ADR-0008.
  - Bearer token auth → CSRF not applicable — route decorated @no_csrf.

Source: T-1.3.x; ADR-0004; ADR-0011; ADR-0014.4.
"""
from __future__ import annotations

import base64
import hashlib

import argon2
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from admin_api.middleware.csrf import no_csrf
from admin_api.services.vault_client import VaultAdapterClient, get_vault_client
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter()

_ph = argon2.PasswordHasher()


async def _proxy_call(
    service_id: str,
    path_suffix: str,
    request: Request,
    session: AsyncSession,
    vault: VaultAdapterClient,
) -> Response:
    """
    Core proxy logic shared by all HTTP method handlers.

    Validates the service API key, retrieves the credential from the vault,
    injects it into the outbound request, and returns the backend response.
    """
    # --- 1. Extract Bearer token ---
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})
    api_key = auth_header[len("Bearer "):]

    # --- 2. Compute fingerprint (first 8 bytes of SHA-256, hex) ---
    fingerprint = hashlib.sha256(api_key.encode()).digest()[:8].hex()

    # --- 3. Enable cross-tenant lookup. PostgreSQL does not short-circuit OR in
    #        USING clauses, so ''::uuid throws even when platform_admin_view='on'.
    #        Set a placeholder UUID so the cast is valid, then enable platform_admin_view.
    #        ADR-0016.3 — platform_admin_view is the correct escape hatch here.
    await session.execute(
        text(
            "SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true),"
            "       set_config('app.platform_admin_view', 'on', true)"
        )
    )
    result = await session.execute(
        text(
            "SELECT sk.id, sk.agent_id, sk.service_id, sk.key_hash,"
            "       sk.allowed_actions, sk.expires_at, sk.revoked_at, a.tenant_id"
            " FROM service_api_keys sk"
            " JOIN agents a ON a.id = sk.agent_id"
            " WHERE sk.key_fingerprint = :fp"
            " LIMIT 1"
        ),
        {"fp": fingerprint},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:invalid_key"})

    # --- 4. Argon2id verify ---
    try:
        _ph.verify(row.key_hash, api_key)
    except argon2.exceptions.VerifyMismatchError:
        return JSONResponse(status_code=401, content={"code": "mintkey:invalid_key"})
    except argon2.exceptions.VerificationError:
        return JSONResponse(status_code=401, content={"code": "mintkey:invalid_key"})

    # --- 5. Check revocation and expiry ---
    if row.revoked_at is not None:
        return JSONResponse(status_code=401, content={"code": "mintkey:invalid_key"})
    if row.expires_at is not None:
        from datetime import datetime, timezone
        if datetime.now(timezone.utc) > row.expires_at.replace(tzinfo=timezone.utc):
            return JSONResponse(status_code=401, content={"code": "mintkey:invalid_key"})

    tenant_id = row.tenant_id

    # --- 6. Get service metadata (tenant-scoped) ---
    await set_tenant_context(session, tenant_id)
    svc_result = await session.execute(
        text("SELECT base_url, auth_scheme FROM services WHERE id = :sid"),
        {"sid": str(service_id)},
    )
    svc_row = svc_result.fetchone()
    if svc_row is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:invalid_key"})

    # --- 7. Get credential from vault ---
    credential = await vault.get_credential(str(tenant_id), str(service_id))
    if credential is None:
        return JSONResponse(status_code=424, content={"code": "mintkey:credential_unavailable"})

    plaintext: str = credential["plaintext"]
    auth_scheme: str = svc_row.auth_scheme

    # --- 8. Build target URL ---
    base_url = svc_row.base_url.rstrip("/")
    suffix = path_suffix.lstrip("/")
    target_url = f"{base_url}/{suffix}" if suffix else base_url

    # --- 9. Build outbound headers with injected credential ---
    outbound_headers: dict[str, str] = {}
    if auth_scheme == "basic_auth":
        encoded = base64.b64encode(plaintext.encode()).decode()
        outbound_headers["Authorization"] = f"Basic {encoded}"
    elif auth_scheme == "bearer_token":
        outbound_headers["Authorization"] = f"Bearer {plaintext}"
    elif auth_scheme == "api_key_header":
        outbound_headers["X-Api-Key"] = plaintext
    # Other schemes: no injection; pass through without auth header

    # --- 10. Forward the request ---
    query_params = dict(request.query_params)
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            backend_response = await client.request(
                method=request.method,
                url=target_url,
                params=query_params if query_params else None,
                headers=outbound_headers,
                content=body if body else None,
            )
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"code": "mintkey:backend_unavailable"})
    except httpx.TimeoutException:
        return JSONResponse(status_code=502, content={"code": "mintkey:backend_unavailable"})

    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        media_type=backend_response.headers.get("content-type"),
    )


@router.api_route(
    "/v1/proxy/call/{service_id}/{path_suffix:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@no_csrf
async def proxy_call(
    service_id: str,
    path_suffix: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> Response:
    """
    Credential-injecting reverse proxy.

    Authenticates via mk_svckey_* Bearer token, retrieves the backend
    credential from the vault, injects it into the outbound request, and
    forwards to the configured service base_url.
    """
    return await _proxy_call(service_id, path_suffix, request, session, vault)
