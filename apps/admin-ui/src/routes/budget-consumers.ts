/**
 * BFF route handler for budget consumers dashboard.
 *
 * GET /admin/api/budget-consumers → proxy aggregation endpoint from admin-api
 *
 * Extracts tenant_id from session and proxies to the admin-api aggregation
 * endpoint that returns all budget-configured permission grants ranked by
 * consumption percentage.
 *
 * Source: budget-consumers-dashboard spec; ADR-0019 (BFF pattern); Requirements 3.1-3.4.
 */

import type { Request, Response } from "express";

const ADMIN_API_URL =
  process.env.MINTKEY_ADMIN_API_URL ??
  process.env.ADMIN_API_URL ??
  "http://admin-api:8080";

/**
 * GET /admin/api/budget-consumers
 *
 * 1. Extract tenantId from req.session.adminUser
 * 2. Proxy to GET /v1/tenants/{tid}/budget-consumers with cookie forwarded
 * 3. Forward response status + body unchanged
 * 4. Return 502 on network error
 */
export async function budgetConsumersHandler(req: Request, res: Response): Promise<void> {
  const adminUser = req.session?.adminUser as { tenantId: string } | undefined;

  if (!adminUser?.tenantId) {
    res.status(401).json({ title: "Unauthorized", detail: "No session" });
    return;
  }

  const tenantId = adminUser.tenantId;
  const cookie = req.headers.cookie ?? "";

  try {
    const upstream = await fetch(
      `${ADMIN_API_URL}/v1/tenants/${tenantId}/budget-consumers`,
      { headers: { Cookie: cookie } }
    );
    const body = await upstream.text();
    res.status(upstream.status).type("application/json").send(body);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Upstream error";
    res.status(502).json({ title: "BFF proxy error", detail: message });
  }
}
