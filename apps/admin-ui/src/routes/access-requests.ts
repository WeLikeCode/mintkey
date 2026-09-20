/**
 * BFF route handlers for the Requests_Review_Area (agent access requests).
 *
 * GET  /admin/api/access-requests             → list (forward status/kind filters)
 * GET  /admin/api/access-requests/:requestId  → detail
 * POST /admin/api/access-requests/:requestId/approve → approve / finalize integration
 * POST /admin/api/access-requests/:requestId/reject  → reject with { reason }
 * POST /admin/api/access-requests/:requestId/test    → Connection_Test for a proposal
 *
 * All handlers extract tenant_id from the operator session (req.session.adminUser),
 * never from the URL. Reads are proxied with the session cookie; state-changing
 * calls go through apiWrite() (session cookie + signed Ed25519 AdminUiSignedRequest
 * JWT). The BFF holds no DB connection (ADR-0019).
 *
 * Secret-bearing bodies (approve finalize, test) carry x-mintkey-sensitive
 * credential/config material and MUST NOT be logged (Req 6.1, ADR-0026 D7).
 * These handlers forward the request body straight through to apiWrite without
 * logging it.
 *
 * Source: agent-access-requests spec Task 8.1; ADR-0019 (BFF pattern);
 * budget-management-ui precedent (routes/budget.ts); Requirements 4.7, 6.1.
 */

import type { Request, Response } from "express";
import { apiWrite, operatorOptsFromAdmin, traceHeadersFrom } from "../lib/api-client.js";

const ADMIN_API_URL =
  process.env.MINTKEY_ADMIN_API_URL ??
  process.env.ADMIN_API_URL ??
  "http://admin-api:8080";

/**
 * GET /admin/api/access-requests
 *
 * 1. Extract tenantId from req.session.adminUser
 * 2. Forward status/kind query filters
 * 3. Proxy to GET /v1/tenants/{tid}/access-requests with the session cookie
 * 4. Forward response status + body unchanged
 */
export async function accessRequestsListHandler(req: Request, res: Response): Promise<void> {
  const adminUser = req.session?.adminUser as { tenantId: string } | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;
  const cookie = req.headers.cookie ?? "";
  const traceHeaders = traceHeadersFrom(req.headers);

  const params = new URLSearchParams();
  const { status, kind } = req.query as { status?: string; kind?: string };
  if (typeof status === "string" && status) params.set("status", status);
  if (typeof kind === "string" && kind) params.set("kind", kind);
  const qs = params.toString();

  try {
    const upstream = await fetch(
      `${ADMIN_API_URL}/v1/tenants/${tenantId}/access-requests${qs ? `?${qs}` : ""}`,
      { headers: { Cookie: cookie, ...traceHeaders } }
    );
    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}

/**
 * GET /admin/api/access-requests/:requestId
 *
 * 1. Extract tenantId from req.session.adminUser
 * 2. Proxy to GET /v1/tenants/{tid}/access-requests/{requestId} with the session cookie
 * 3. Forward response status + body unchanged
 */
export async function accessRequestGetHandler(req: Request, res: Response): Promise<void> {
  const { requestId } = req.params;
  const adminUser = req.session?.adminUser as { tenantId: string } | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;
  const cookie = req.headers.cookie ?? "";
  const traceHeaders = traceHeadersFrom(req.headers);

  try {
    const upstream = await fetch(
      `${ADMIN_API_URL}/v1/tenants/${tenantId}/access-requests/${requestId}`,
      { headers: { Cookie: cookie, ...traceHeaders } }
    );
    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}

/**
 * POST /admin/api/access-requests/:requestId/approve
 *
 * 1. Extract tenantId + operator session from req.session.adminUser
 * 2. apiWrite POST /v1/tenants/{tid}/access-requests/{requestId}/approve
 * 3. Forward response status + body unchanged
 *
 * The body may carry x-mintkey-sensitive credential/config for integration
 * finalize. It is forwarded straight to apiWrite and is NEVER logged.
 */
export async function accessRequestApproveHandler(req: Request, res: Response): Promise<void> {
  const { requestId } = req.params;
  const adminUser = req.session?.adminUser as
    | { tenantId: string; operatorId: string; sessionToken: string; csrfToken: string }
    | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;

  try {
    const opts = operatorOptsFromAdmin(adminUser);
    // Body forwarded straight through — may carry secret material; do NOT log it.
    const upstream = await apiWrite(
      `/v1/tenants/${tenantId}/access-requests/${requestId}/approve`,
      "POST",
      req.body,
      opts,
      traceHeadersFrom(req.headers)
    );

    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}

/**
 * POST /admin/api/access-requests/:requestId/reject
 *
 * 1. Extract tenantId + operator session from req.session.adminUser
 * 2. apiWrite POST /v1/tenants/{tid}/access-requests/{requestId}/reject with { reason }
 * 3. Forward response status + body unchanged
 */
export async function accessRequestRejectHandler(req: Request, res: Response): Promise<void> {
  const { requestId } = req.params;
  const adminUser = req.session?.adminUser as
    | { tenantId: string; operatorId: string; sessionToken: string; csrfToken: string }
    | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;

  try {
    const { reason } = req.body as { reason?: string };
    const opts = operatorOptsFromAdmin(adminUser);
    const upstream = await apiWrite(
      `/v1/tenants/${tenantId}/access-requests/${requestId}/reject`,
      "POST",
      { reason },
      opts,
      traceHeadersFrom(req.headers)
    );

    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}

/**
 * POST /admin/api/access-requests/:requestId/test
 *
 * 1. Extract tenantId + operator session from req.session.adminUser
 * 2. apiWrite POST /v1/tenants/{tid}/access-requests/{requestId}/test
 * 3. Forward response status + body unchanged
 *
 * The body carries x-mintkey-sensitive credential/config for the Connection_Test.
 * It is forwarded straight to apiWrite and is NEVER logged.
 */
export async function accessRequestTestHandler(req: Request, res: Response): Promise<void> {
  const { requestId } = req.params;
  const adminUser = req.session?.adminUser as
    | { tenantId: string; operatorId: string; sessionToken: string; csrfToken: string }
    | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;

  try {
    const opts = operatorOptsFromAdmin(adminUser);
    // Body forwarded straight through — carries secret material; do NOT log it.
    const upstream = await apiWrite(
      `/v1/tenants/${tenantId}/access-requests/${requestId}/test`,
      "POST",
      req.body,
      opts,
      traceHeadersFrom(req.headers)
    );

    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}
