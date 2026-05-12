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

const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";
const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? "admin@mintkey.internal";

function getAdminPassword(): string {
  // Try file-based secret first, then env var
  const passwordFile = process.env.ADMIN_PASSWORD_FILE;
  if (passwordFile) {
    try {
      return readFileSync(passwordFile, "utf-8").trim();
    } catch {
      // fall through to env var
    }
  }
  return process.env.ADMIN_PASSWORD ?? "";
}

interface ApiSession {
  sessionToken: string;
  csrfToken: string;
}

let _session: ApiSession | null = null;
let _sessionExpiry = 0;

/**
 * Obtain (or reuse) a server-side session for admin-api calls.
 * Calls /v1/auth/internal-login if no session exists or session expired.
 */
export async function getApiSession(): Promise<ApiSession | null> {
  const now = Date.now();
  if (_session && now < _sessionExpiry) {
    return _session;
  }

  const password = getAdminPassword();
  if (!password) {
    // In test environments or when no admin password is configured,
    // return null — callers will fall back to direct calls without CSRF
    return null;
  }

  try {
    const resp = await fetch(`${ADMIN_API_URL}/v1/auth/internal-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password }),
    });

    if (!resp.ok) return null;

    // Extract cookies from response headers
    const setCookieHeader = resp.headers.get("set-cookie") ?? "";
    const sessionMatch = setCookieHeader.match(/mintkey_session=([^;]+)/);
    const csrfMatch = setCookieHeader.match(/csrf_token=([^;]+)/);

    if (!sessionMatch || !csrfMatch) return null;

    _session = {
      sessionToken: sessionMatch[1],
      csrfToken: csrfMatch[1],
    };
    // Refresh 30min before the 8h expiry
    _sessionExpiry = now + (8 * 60 - 30) * 60 * 1000;

    return _session;
  } catch {
    return null;
  }
}

/**
 * Make an authenticated write call to admin-api.
 * Includes CSRF token (double-submit cookie pattern) and session cookie.
 */
export async function apiWrite(
  path: string,
  method: string,
  body?: unknown
): Promise<Response> {
  const session = await getApiSession();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (session) {
    headers["X-Mintkey-Csrf"] = session.csrfToken;
    headers["Cookie"] = `mintkey_session=${session.sessionToken}; csrf_token=${session.csrfToken}`;
  }

  return fetch(`${ADMIN_API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}
