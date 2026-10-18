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

import type { Request, Response } from "express";

export function createLogoutHandler(adminApiUrl: string) {
  return async function logoutHandler(req: Request, res: Response): Promise<void> {
    try {
      await fetch(`${adminApiUrl}/v1/auth/logout`, {
        method: "POST",
        headers: { Cookie: req.headers.cookie ?? "" },
      });
    } catch {
      // admin-api unreachable: still clear the browser-side cookies below.
    }
    res.clearCookie("mintkey_session", { path: "/" });
    res.clearCookie("csrf_token", { path: "/" });
    res.redirect(302, "/admin/login");
  };
}
