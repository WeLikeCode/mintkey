/**
 * PlatformAdmin middleware for AdminJS.
 *
 * Sets req.session.platform_admin_view = true when the operator is a
 * PlatformAdmin and the "All tenants" view is requested. This flag is
 * forwarded to admin-api in the signed-request JWT payload, and admin-api
 * sets `app.platform_admin_view='on'` in PostgreSQL (ADR-0016.3).
 *
 * Source: T-1.12.4; ADR-0016.3; ADR-0017.4.
 */

import type { Request, Response, NextFunction } from "express";

declare module "express-session" {
  interface SessionData {
    operatorId?: string;
    tenantId?: string;
    isPlatformAdmin?: boolean;
    platformAdminView?: boolean;
  }
}

/**
 * Middleware: sets platformAdminView flag based on query param or session.
 *
 * ?all_tenants=true  → enable PlatformAdmin view (cross-tenant reads)
 * ?all_tenants=false → disable (scoped to session tenant)
 *
 * Non-PlatformAdmin operators are silently unaffected.
 */
export function platformAdminMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  if (!req.session?.isPlatformAdmin) {
    next();
    return;
  }

  if (req.query["all_tenants"] === "true") {
    req.session.platformAdminView = true;
  } else if (req.query["all_tenants"] === "false") {
    req.session.platformAdminView = false;
  }

  next();
}

/**
 * Returns true when the current session has the PlatformAdmin cross-tenant
 * view flag set. Used by resource handlers to decide whether to include the
 * X-Platform-Admin header in FastAPI requests.
 */
export function isPlatformAdminView(req: Request): boolean {
  return req.session?.isPlatformAdmin === true && req.session?.platformAdminView === true;
}
