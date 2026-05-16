/**
 * Admin API client — wraps fetch calls to admin-api with the correct
 * session cookie and CSRF token for server-to-server calls.
 *
 * Admin-UI calls admin-api from Node.js (server-to-server), not from the
 * browser. CSRF protection is needed to satisfy admin-api middleware, which
 * uses the double-submit cookie pattern. We obtain a session token at startup
 * by calling /v1/auth/internal-login once, then reuse the CSRF token for
 * all subsequent write calls.
 *
 * For read calls (GET), no CSRF is needed.
 *
 * Source: ADR-0014.5; ADR-0013; admin-api CSRF middleware.
 */

import { readFileSync } from "fs";
import { signedFetch } from "./signed-request.js";

const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";
const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? "admin@mintkey.internal";

function getAdminPassword(): string {
  const passwordFile = process.env.ADMIN_PASSWORD_FILE;
  if (passwordFile) {
    try {
      return readFileSync(passwordFile, "utf-8").trim();
    } catch { /* fall through */ }
  }
  return process.env.ADMIN_PASSWORD ?? "";
}

interface ApiSession {
  sessionToken: string;
  csrfToken: string;
  operatorId: string;
  tenantId: string;
}

let _session: ApiSession | null = null;
let _sessionExpiry = 0;

/**
 * Obtain (or reuse) a server-side bootstrap admin session for admin-api writes.
 * Used when the per-operator session is not threaded through (e.g. dashboard handler).
 */
export async function getApiSession(): Promise<ApiSession | null> {
  const now = Date.now();
  if (_session && now < _sessionExpiry) return _session;

  const password = getAdminPassword();
  if (!password) return null;

  try {
    const resp = await fetch(`${ADMIN_API_URL}/v1/auth/internal-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password }),
    });

    if (!resp.ok) return null;

    const data = await resp.json() as { operator_id: string; tenant_id: string };

    const cookieHeaders: string[] =
      typeof (resp.headers as { getSetCookie?: () => string[] }).getSetCookie === "function"
        ? (resp.headers as { getSetCookie: () => string[] }).getSetCookie()
        : [resp.headers.get("set-cookie") ?? ""];

    let sessionToken = "";
    let csrfToken = "";
    for (const c of cookieHeaders) {
      const sm = c.match(/mintkey_session=([^;,\s]+)/);
      if (sm) sessionToken = sm[1];
      const cm = c.match(/csrf_token=([^;,\s]+)/);
      if (cm) csrfToken = cm[1];
    }

    if (!sessionToken || !csrfToken) return null;

    _session = { sessionToken, csrfToken, operatorId: data.operator_id, tenantId: data.tenant_id };
    _sessionExpiry = now + (8 * 60 - 30) * 60 * 1000;
    return _session;
  } catch {
    return null;
  }
}

/**
 * Extract per-operator session credentials from context.currentAdmin.
 *
 * requireSession (index.ts) stashes sessionToken + csrfToken on
 * req.session.adminUser after every successful whoami call. AdminJS exposes
 * req.session.adminUser as context.currentAdmin inside action handlers.
 *
 * Passing the returned object as operatorOpts to apiWrite ensures write calls
 * are authenticated as the logged-in operator, not via a stale bootstrap
 * session that may fail when internal_password_hash IS NULL (SSO-REDUX-3 /
 * D2-b). This is the canonical fix for the apiWrite session threading gap
 * flagged in SSO-REDUX-3 OPEN items.
 *
 * Returns null only if currentAdmin is absent (e.g. unauthenticated requests —
 * which requireSession should have already blocked).
 */
export function operatorOptsFromAdmin(
  currentAdmin: Record<string, unknown> | null | undefined
): { operatorId: string; tenantId: string; sessionToken: string; csrfToken: string } | null {
  if (!currentAdmin) return null;
  const operatorId = (currentAdmin["operatorId"] ?? "") as string;
  const tenantId   = (currentAdmin["tenantId"]   ?? "") as string;
  const sessionToken = (currentAdmin["sessionToken"] ?? "") as string;
  const csrfToken    = (currentAdmin["csrfToken"]    ?? "") as string;
  if (!operatorId || !tenantId || !sessionToken) return null;
  return { operatorId, tenantId, sessionToken, csrfToken };
}

/**
 * Make an authenticated write call to admin-api.
 *
 * When operatorOpts is provided (per-operator session from currentAdmin), uses
 * that session and builds the signed-request JWT with the operator's identity.
 * Falls back to the bootstrap admin session when operatorOpts is absent.
 *
 * ADR-0019: every state-changing call needs BOTH mintkey_session cookie AND the
 * x-mintkey-signed-request Ed25519 JWT (iss/aud/sub/tnt/exp/jti).
 */
export async function apiWrite(
  path: string,
  method: string,
  body?: unknown,
  operatorOpts?: { operatorId: string; tenantId: string; sessionToken: string; csrfToken: string } | null
): Promise<Response> {
  const opts = operatorOpts ?? await getApiSession();

  if (opts) {
    return signedFetch(`${ADMIN_API_URL}${path}`, {
      operatorId: opts.operatorId,
      tenantId: opts.tenantId,
      sessionToken: opts.sessionToken,
      csrfToken: opts.csrfToken,
      method,
      body,
    });
  }

  // No session available — unauthenticated fallback (dev mode)
  return fetch(`${ADMIN_API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}
