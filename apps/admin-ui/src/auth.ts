/**
 * AdminJS authentication configuration — session cookie name/password
 * for @adminjs/express buildRouter, and break-glass internal-login helper.
 *
 * SSO-C: admin-ui no longer holds any Keycloak client_secret and no longer
 * runs OIDC directly. All Keycloak traffic goes through admin-api (ADR-0019
 * BFF, ADR-0014 §14.2). The primary login path is:
 *
 *   browser → /auth/start → admin-api /v1/auth/oidc/login → Keycloak →
 *   admin-api /v1/auth/oidc/callback → admin-api sets mintkey_session cookie →
 *   redirect to /admin
 *
 * Break-glass (D2-b): the /admin/login page exposes a collapsed accordion
 * with an email+password form. This POSTs to admin-api /v1/auth/internal-login,
 * which returns 404 when operators.internal_password_hash IS NULL (default),
 * and 200 only after `mintkey admin reset-password` has been run by an operator.
 *
 * Source: ADR-0014 §14.2, ADR-0019 §3; REQ 2 AC8; SSO-C.
 */

const ADMIN_API_URL =
  process.env.ADMIN_API_URL ??
  process.env.MINTKEY_ADMIN_API_URL ??
  "http://admin-api:8080";

/**
 * adminJSAuthOptions — used by buildRouter for cookie configuration.
 *
 * authenticate() is kept as the break-glass internal-login handler:
 * it POSTs to admin-api /v1/auth/internal-login and returns a user object
 * on success or null on failure (including 404 when break-glass is disabled).
 *
 * cookieName / cookiePassword are referenced by the session middleware
 * and read by tests that verify session configuration.
 */
export const adminJSAuthOptions = {
  authenticate: async (
    email: string,
    password: string
  ): Promise<{ email: string; operatorId: string; tenantId: string; isPlatformAdmin: boolean } | null> => {
    try {
      const resp = await fetch(`${ADMIN_API_URL}/v1/auth/internal-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      // 404 = break-glass disabled (no internal_password_hash set for operator)
      if (!resp.ok) return null;

      const data = await resp.json() as {
        operator_id: string;
        tenant_id: string;
        is_platform_admin: boolean;
      };

      return {
        email,
        operatorId: data.operator_id,
        tenantId: data.tenant_id,
        isPlatformAdmin: data.is_platform_admin,
      };
    } catch {
      return null;
    }
  },
  cookieName: "mintkey_session",
  cookiePassword:
    process.env.SESSION_SECRET ?? "mintkey-session-secret-change-in-production",
};

/**
 * Render the /admin/login HTML page.
 *
 * Primary CTA: "Sign in with Keycloak" → /auth/start → admin-api OIDC flow.
 * Secondary (collapsed): Break-glass accordion with email+password form that
 * proxies to admin-api /v1/auth/internal-login via a server-side relay route
 * (/auth/internal-login-proxy) to avoid CORS issues.
 *
 * The accordion is always rendered but collapsed by default (<details> element).
 * Operators only see it if they expand it; it only works after
 * `mintkey admin reset-password` has been run (otherwise admin-api returns 404).
 */
export function renderLoginPage(errorMessage?: string): string {
  const errorHtml = errorMessage
    ? `<div style="background:#ffeaea;border:1px solid #e57373;border-radius:4px;padding:12px 16px;margin-bottom:16px;color:#c0392b;font-size:14px;">${escapeHtml(errorMessage)}</div>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in — Mintkey Admin</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0; padding: 0;
      background: #f0f4f8;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10);
      padding: 40px 36px;
      width: 100%;
      max-width: 420px;
    }
    .logo { font-size: 22px; font-weight: 700; color: #1a3c5e; margin-bottom: 8px; }
    .subtitle { color: #6c757d; font-size: 14px; margin-bottom: 28px; }
    .btn-primary {
      display: block; width: 100%; padding: 12px 16px;
      background: #3795BE; color: #fff;
      border: none; border-radius: 6px;
      font-size: 16px; font-weight: 600; cursor: pointer;
      text-decoration: none; text-align: center;
      transition: background 0.15s;
    }
    .btn-primary:hover { background: #2c7aa3; }
    .divider {
      margin: 24px 0;
      border: none; border-top: 1px solid #e9ecef;
    }
    details { margin-top: 8px; }
    summary {
      cursor: pointer; color: #6c757d; font-size: 13px;
      user-select: none; outline: none;
      padding: 6px 0;
    }
    summary::-webkit-details-marker { color: #adb5bd; }
    .breakglass-body { padding-top: 16px; }
    .breakglass-notice {
      background: #fff8e1; border: 1px solid #ffe082;
      border-radius: 4px; padding: 10px 14px;
      font-size: 13px; color: #7c5c00;
      margin-bottom: 16px;
    }
    label { display: block; font-size: 13px; color: #495057; margin-bottom: 4px; font-weight: 500; }
    input[type=email], input[type=password] {
      display: block; width: 100%; padding: 9px 12px;
      border: 1px solid #ced4da; border-radius: 4px;
      font-size: 14px; margin-bottom: 12px;
      outline: none; transition: border-color 0.15s;
    }
    input[type=email]:focus, input[type=password]:focus { border-color: #3795BE; }
    .btn-secondary {
      display: block; width: 100%; padding: 9px 16px;
      background: #fff; color: #3795BE;
      border: 1px solid #3795BE; border-radius: 6px;
      font-size: 14px; font-weight: 600; cursor: pointer;
      transition: background 0.15s;
    }
    .btn-secondary:hover { background: #f0f8ff; }
    #bg-error {
      display: none;
      background: #ffeaea; border: 1px solid #e57373;
      border-radius: 4px; padding: 10px 14px;
      font-size: 13px; color: #c0392b; margin-top: 10px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">Mintkey Admin</div>
    <div class="subtitle">Credential broker for AI agents</div>

    ${errorHtml}

    <a href="/auth/start" class="btn-primary">Sign in with Keycloak</a>

    <hr class="divider">

    <details>
      <summary>Break-glass (local password)</summary>
      <div class="breakglass-body">
        <div class="breakglass-notice">
          Local login is disabled unless an operator ran
          <code>mintkey admin reset-password</code> (Keycloak unreachable break-glass).
        </div>
        <form id="bg-form" method="POST" action="/auth/internal-login-proxy">
          <label for="bg-email">Email</label>
          <input type="email" id="bg-email" name="email" required autocomplete="username">
          <label for="bg-password">Password</label>
          <input type="password" id="bg-password" name="password" required autocomplete="current-password">
          <button type="submit" class="btn-secondary">Sign in (break-glass)</button>
          <div id="bg-error"></div>
        </form>
      </div>
    </details>
  </div>
</body>
</html>`;
}

/**
 * Minimal HTML escaping to prevent XSS in the error message slot.
 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
