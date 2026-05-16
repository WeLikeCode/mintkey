/**
 * PlatformAdmin middleware for AdminJS.
 *
 * SSO-C: reads operator info from req.adminSession (populated by the
 * requireSession middleware via admin-api /v1/auth/whoami), rather than
 * from req.session.adminUser (the old AdminJS-internal session shape).
 *
 * Sets req.session.platform_admin_view = true when the operator is a
 * PlatformAdmin and the "All tenants" view is requested. This flag is
 * forwarded to admin-api in the signed-request JWT payload, and admin-api
 * sets `app.platform_admin_view='on'` in PostgreSQL (ADR-0016.3).
 *
 * Source: T-1.12.4; ADR-0016.3; ADR-0017.4; SSO-C.
 */

import type { Request, Response, NextFunction } from "express";

declare module "express-session" {
  interface SessionData {
    operatorId?: string;
    tenantId?: string;
    isPlatformAdmin?: boolean;
    platformAdminView?: boolean;
    /**
     * AdminJS-standard key: read by @adminjs/express buildRouter to populate
     * context.currentAdmin in action handlers. Populated by requireSession
     * (index.ts) after each successful /v1/auth/whoami call.
     *
     * Includes sessionToken + csrfToken so action handlers can pass
     * operatorOpts to apiWrite for per-operator signed requests.
     */
    adminUser?: {
      email: string;
      operatorId: string;
      tenantId: string;
      isPlatformAdmin: boolean;
      sessionToken: string;
      csrfToken: string;
    };
  }
}

/**
 * Middleware: sets platformAdminView flag based on query param or session.
 *
 * Reads isPlatformAdmin from req.adminSession (whoami-relayed shape) with a
 * fallback to req.session.isPlatformAdmin for any path that still goes through
 * the old AdminJS session (none expected post-SSO-C, but kept for safety).
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
  // Read isPlatformAdmin from the whoami-relayed session (SSO-C) or fall back
  // to the legacy express-session field for any old-path requests.
  const isPlatformAdmin =
    (req as any).adminSession?.is_platform_admin === true ||
    req.session?.isPlatformAdmin === true;

  if (!isPlatformAdmin) {
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
 *
 * Reads isPlatformAdmin from req.adminSession (SSO-C primary path) with a
 * fallback to req.session.isPlatformAdmin (legacy / break-glass path).
 */
export function isPlatformAdminView(req: Request): boolean {
  const isPlatformAdmin =
    (req as any).adminSession?.is_platform_admin === true ||
    req.session?.isPlatformAdmin === true;
  return isPlatformAdmin && req.session?.platformAdminView === true;
}
