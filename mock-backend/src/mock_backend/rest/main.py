import asyncio
import base64
import logging
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Mintkey Mock Backend")


@app.get("/health")
async def health(authorization: Optional[str] = Header(default=None)) -> dict[str, str]:
    logger.info("health: authorization=%s", authorization)
    return {"status": "ok"}


@app.get("/api-key-header")
async def api_key_header(
    x_api_key: Optional[str] = Header(default=None),
) -> JSONResponse:
    logger.info("api-key-header: x_api_key=%s", x_api_key)
    if x_api_key is None:
        return JSONResponse(status_code=401, content={"detail": "Missing X-Api-Key"})
    return JSONResponse(content={"received_key": x_api_key})


@app.get("/api-key-query")
async def api_key_query(
    api_key: Optional[str] = Query(default=None),
) -> JSONResponse:
    logger.info("api-key-query: api_key=%s", api_key)
    if api_key is None:
        return JSONResponse(status_code=401, content={"detail": "Missing api_key query param"})
    return JSONResponse(content={"received_key": api_key})


@app.get("/bearer")
async def bearer(authorization: Optional[str] = Header(default=None)) -> JSONResponse:
    logger.info("bearer: authorization=%s", authorization)
    if authorization is None or not authorization.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid Bearer token"})
    token = authorization[len("bearer "):].strip()
    return JSONResponse(content={"received_token": token})


@app.get("/basic-auth")
async def basic_auth(authorization: Optional[str] = Header(default=None)) -> JSONResponse:
    logger.info("basic-auth: authorization=%s", authorization)
    if authorization is None or not authorization.lower().startswith("basic "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid Basic credentials"})
    encoded = authorization[len("basic "):].strip()
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid Base64 encoding"})
    username = decoded.split(":", 1)[0]
    return JSONResponse(content={"received_user": username})


@app.get("/oauth-protected")
async def oauth_protected(authorization: Optional[str] = Header(default=None)) -> JSONResponse:
    logger.info("oauth-protected: authorization=%s", authorization)
    if authorization is None or not authorization.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid Bearer token"})
    token = authorization[len("bearer "):].strip()
    return JSONResponse(content={"received_token": token})


@app.post("/echo")
async def echo(request: Request) -> dict[str, Any]:
    headers = dict(request.headers)
    try:
        body = await request.json()
    except Exception:
        body = (await request.body()).decode("utf-8", errors="replace")
    logger.info("echo: headers=%s", headers)
    return {"headers": headers, "body": body}


@app.get("/timeout")
async def timeout() -> dict[str, str]:
    logger.info("timeout: sleeping 30s")
    await asyncio.sleep(30)
    return {"status": "ok"}


@app.get("/5xx")
async def five_xx() -> Response:
    logger.info("5xx: returning 500")
    return Response(status_code=500)


@app.get("/redirect-internal")
async def redirect_internal() -> RedirectResponse:
    logger.info("redirect-internal: redirecting to /health")
    return RedirectResponse(url="/health", status_code=302)


@app.get("/redirect-external")
async def redirect_external() -> RedirectResponse:
    logger.info("redirect-external: redirecting to https://example.com/")
    return RedirectResponse(url="https://example.com/", status_code=302)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
