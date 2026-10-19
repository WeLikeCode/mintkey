/**
 * GET /admin/logout -- end the operator session and return to the login page.
 *
 * The AdminJS router is built without authentication (buildRouter, not buildAuthenticatedRouter), so
 * it has no /admin/logout of its own: before this route a visit to /admin/logout fell through to the
 * SPA and the mintkey_session cookie stayed valid. This tells admin-api to drop the cookie, clears the
 * session + CSRF cookies here too (cookies are host-scoped, so this also covers the admin-api origin on
 * localhost) and redirects to /admin/login.
 *
 * Known limitation (issue #345): admin-api's POST /v1/auth/logout only deletes the cookie, so a
 * copy of the old cookie stays valid server-side until the session row expires.
 */

import { timingSafeEqual } from "crypto";
import type { NextFunction, Request, Response } from "express";

const REFUSED_BODY = "Logout refused: missing or invalid CSRF token";

export const ADMINJS_SESSION_COOKIE = "adminjs.sid";

/**
 * Read a cookie value from a raw Cookie header.
 *
 * The name matches exactly (not as a suffix), the value is everything after the
 * first "=" and is only trimmed -- never percent-decoded. A missing header,
 * name or empty value yields undefined; a repeated name yields the first one.
 */
export function readCookie(header: string | undefined, name: string): string | undefined {
  if (!header) return undefined;
  for (const part of header.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() !== name) continue;
    const value = part.slice(separator + 1).trim();
    return value === "" ? undefined : value;
  }
  return undefined;
}

function tokensEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

/**
 * CSRF guard for POST /admin/logout (the double-submit cookie already used by
 * admin-api): the form field `_csrf` must equal the `csrf_token` cookie.
 *
 * A request with neither a `mintkey_session` cookie nor an AdminJS adminUser
 * has nothing to end and goes to the login page without any change, so a stale
 * page or a cross-site POST lands there instead of a 403.
 */
export function logoutGuard(req: Request, res: Response, next: NextFunction): void {
  const header = req.headers.cookie;
  const hasSessionCookie = readCookie(header, "mintkey_session") !== undefined;
  const hasAdminUser = Boolean(req.session?.adminUser);

  if (!hasSessionCookie && !hasAdminUser) {
    res.redirect(302, "/admin/login");
    return;
  }

  const body = req.body as Record<string, unknown> | undefined;
  const formToken = typeof body?._csrf === "string" ? body._csrf : undefined;
  const cookieToken = readCookie(header, "csrf_token");

  if (!formToken || !cookieToken || !tokensEqual(formToken, cookieToken)) {
    res.status(403).type("text/plain").send(REFUSED_BODY);
    return;
  }

  next();
}

function destroySession(session: Request["session"]): Promise<void> {
  return new Promise((resolve) => {
    if (!session) {
      resolve();
      return;
    }
    session.destroy((error: unknown) => {
      if (error) {
        console.warn("logout: failed to destroy the AdminJS session", error);
      }
      resolve();
    });
  });
}

export function createLogoutHandler(adminApiUrl: string) {
  return async function logoutHandler(req: Request, res: Response): Promise<void> {
    if (readCookie(req.headers.cookie, "mintkey_session") !== undefined) {
      try {
        await fetch(`${adminApiUrl}/v1/auth/logout`, {
          method: "POST",
          headers: { Cookie: req.headers.cookie ?? "" },
        });
      } catch {
        // admin-api unreachable: still clear the browser-side cookies below.
      }
    }

    if (req.session) {
      await destroySession(req.session);
      res.clearCookie(ADMINJS_SESSION_COOKIE, { path: "/" });
    }

    res.clearCookie("mintkey_session", { path: "/" });
    res.clearCookie("csrf_token", { path: "/" });
    res.redirect(302, "/admin/login");
  };
}
