/**
 * BFF route handlers for budget management.
 *
 * GET  /admin/api/budget/:permId       → proxy budget status from admin-api
 * POST /admin/api/budget/:permId/edit   → proxy budget edit via apiWrite
 * POST /admin/api/budget/:permId/remove → proxy budget removal via apiWrite
 * POST /admin/api/budget/:permId/reset  → proxy budget reset via apiWrite
 *
 * All handlers extract tenant_id from session (not URL). The permission record
 * is looked up to resolve agent_id (since the BFF route only has permId).
 *
 * Source: budget-management-ui spec; ADR-0019 (BFF pattern); Requirements 6.1-6.5.
 */

import type { Request, Response } from "express";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";

const ADMIN_API_URL =
  process.env.MINTKEY_ADMIN_API_URL ??
  process.env.ADMIN_API_URL ??
  "http://admin-api:8080";

/**
 * Look up a permission record to extract agent_id.
 * Calls GET /v1/tenants/{tid}/permissions/{pid} on admin-api.
 */
async function lookupPermission(
  tenantId: string,
  permId: string,
  cookie: string
): Promise<{ agent_id: string } | null> {
  const resp = await fetch(
    `${ADMIN_API_URL}/v1/tenants/${tenantId}/permissions/${permId}`,
    { headers: { Cookie: cookie } }
  );
  if (!resp.ok) return null;
  const data = (await resp.json()) as { agent_id?: string };
  return data.agent_id ? { agent_id: data.agent_id } : null;
}

/**
 * GET /admin/api/budget/:permId
 *
 * 1. Extract tenantId from req.session.adminUser
 * 2. Look up the permission record to get agent_id
 * 3. Proxy to GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget
 * 4. Forward response status + body unchanged
 */
export async function budgetGetHandler(req: Request, res: Response): Promise<void> {
  const { permId } = req.params;
  const adminUser = req.session?.adminUser as
    | { tenantId: string; sessionToken: string; csrfToken: string }
    | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;
  const cookie = req.headers.cookie ?? "";

  try {
    const upstream = await fetch(
      `${ADMIN_API_URL}/v1/tenants/${tenantId}/permissions/${permId}/budget`,
      { headers: { Cookie: cookie } }
    );
    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}

/**
 * POST /admin/api/budget/:permId/edit
 *
 * 1. Extract tenantId + operator session from req.session.adminUser
 * 2. Look up the permission record to get agent_id
 * 3. Call apiWrite(PATCH /v1/tenants/{tid}/permissions/{pid}, { constraints: { budget: {...} } })
 * 4. Forward response status + body unchanged
 */
export async function budgetEditHandler(req: Request, res: Response): Promise<void> {
  const { permId } = req.params;
  const adminUser = req.session?.adminUser as
    | { tenantId: string; operatorId: string; sessionToken: string; csrfToken: string }
    | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;
  const cookie = req.headers.cookie ?? "";

  try {
    const perm = await lookupPermission(tenantId, permId, cookie);
    if (!perm) {
      res
        .status(502)
        .json({ title: "BFF proxy error", detail: "Failed to resolve permission record" });
      return;
    }

    const { ceiling, period, alert_thresholds } = req.body as {
      ceiling?: number;
      period?: string;
      alert_thresholds?: number[];
    };

    const opts = operatorOptsFromAdmin(adminUser);
    const upstream = await apiWrite(
      `/v1/tenants/${tenantId}/agents/${perm.agent_id}/permissions/${permId}`,
      "PATCH",
      { constraints: { budget: { ceiling, period, alert_thresholds } } },
      opts
    );

    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}

/**
 * POST /admin/api/budget/:permId/remove
 *
 * 1. Extract tenantId + operator session from req.session.adminUser
 * 2. Look up the permission record to get agent_id
 * 3. Call apiWrite(PATCH /v1/tenants/{tid}/permissions/{pid}, { constraints: { budget: null } })
 * 4. Forward response status + body unchanged
 */
export async function budgetRemoveHandler(req: Request, res: Response): Promise<void> {
  const { permId } = req.params;
  const adminUser = req.session?.adminUser as
    | { tenantId: string; operatorId: string; sessionToken: string; csrfToken: string }
    | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;
  const cookie = req.headers.cookie ?? "";

  try {
    const perm = await lookupPermission(tenantId, permId, cookie);
    if (!perm) {
      res
        .status(502)
        .json({ title: "BFF proxy error", detail: "Failed to resolve permission record" });
      return;
    }

    const opts = operatorOptsFromAdmin(adminUser);
    const upstream = await apiWrite(
      `/v1/tenants/${tenantId}/agents/${perm.agent_id}/permissions/${permId}`,
      "PATCH",
      { constraints: { budget: null } },
      opts
    );

    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}

/**
 * POST /admin/api/budget/:permId/reset
 *
 * 1. Extract tenantId + operator session from req.session.adminUser
 * 2. Look up the permission record to get agent_id
 * 3. Call apiWrite(POST /v1/tenants/{tid}/permissions/{pid}/budget/reset)
 * 4. Forward response status + body unchanged
 */
export async function budgetResetHandler(req: Request, res: Response): Promise<void> {
  const { permId } = req.params;
  const adminUser = req.session?.adminUser as
    | { tenantId: string; operatorId: string; sessionToken: string; csrfToken: string }
    | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;
  const cookie = req.headers.cookie ?? "";

  try {
    const perm = await lookupPermission(tenantId, permId, cookie);
    if (!perm) {
      res
        .status(502)
        .json({ title: "BFF proxy error", detail: "Failed to resolve permission record" });
      return;
    }

    const opts = operatorOptsFromAdmin(adminUser);
    const upstream = await apiWrite(
      `/v1/tenants/${tenantId}/agents/${perm.agent_id}/permissions/${permId}/budget/reset`,
      "POST",
      undefined,
      opts
    );

    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}
