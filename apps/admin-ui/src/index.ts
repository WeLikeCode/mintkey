/**
 * Mintkey AdminJS server.
 *
 * Express + AdminJS 7.x. All data reads come from admin-api over HTTP.
 * All writes route through admin-api via AdminUiSignedRequest JWTs.
 *
 * SSO-C: authentication delegated to admin-api / Keycloak.
 *   - buildRouter (unauthenticated) replaces buildAuthenticatedRouter.
 *   - requireSession middleware validates each request via /v1/auth/whoami.
 *   - /admin/login renders the SSO-C login page (primary: Keycloak; break-glass: local).
 *   - /auth/start redirects to admin-api OIDC login.
 *   - /auth/internal-login-proxy relays the break-glass form POST to admin-api.
 *
 * Source: T-1.1.4; T-1.2.3; T-1.3.4; T-1.4.3; T-1.7.4; T-1.12.4;
 *         ADR-0013; ADR-0014.5; ADR-0014.6; ADR-0019; SSO-C.
 */

import express, { type Request, type Response, type NextFunction } from "express";
import AdminJS from "adminjs";
import { buildRouter } from "@adminjs/express";
import pinoHttp from "pino-http";
import session from "express-session";
import rateLimit from "express-rate-limit";

import { RestDatabase, RestResource } from "./lib/rest-resource.js";
import { adminJSAuthOptions, renderLoginPage } from "./auth.js";
import { dashboardHandler } from "./dashboard.js";
import { componentLoader, Components } from "./components/index.js";
import { platformAdminMiddleware } from "./middleware/platform-admin.js";
import { ServicesResource } from "./resources/services.js";
import { EmailPermissionGrantsResource } from "./resources/email-permission-grants.js";
import { EmailServicesResource } from "./resources/email-services.js";
import { CredentialsResource } from "./resources/credentials.js";
import { AgentsResource } from "./resources/agents.js";
import { ApiKeysResource } from "./resources/api_keys.js";
import { PermissionsResource } from "./resources/permissions.js";
import { AuditResource } from "./resources/audit.js";
import { TenantsResource } from "./resources/tenants.js";
import { OAuth2ProvidersResource } from "./resources/oauth2-providers.js";
import { budgetGetHandler, budgetEditHandler, budgetRemoveHandler, budgetResetHandler } from "./routes/budget.js";
import { budgetConsumersHandler } from "./routes/budget-consumers.js";

const PORT = parseInt(process.env.PORT ?? "3000", 10);

// Internal docker-network URL for server-side whoami calls.
const ADMIN_API_URL =
  process.env.MINTKEY_ADMIN_API_URL ??
  process.env.ADMIN_API_URL ??
  "http://admin-api:8080";

// Public-facing URL for browser redirects (Keycloak flow).
const ADMIN_API_PUBLIC_URL =
  process.env.MINTKEY_ADMIN_API_PUBLIC_URL ?? "http://localhost:8080";

/**
 * Session shape relayed from admin-api /v1/auth/whoami.
 */
interface AdminSession {
  operator_id: string;
  email: string;
  tenant_id: string;
  is_platform_admin: boolean;
  auth_method?: "keycloak" | "internal";
}

// Augment express Request so downstream handlers can read req.adminSession.
declare global {
  namespace Express {
    interface Request {
      adminSession?: AdminSession;
    }
  }
}

/**
 * Session middleware: validates the mintkey_session cookie against admin-api
 * /v1/auth/whoami (15-s LRU cache on admin-api side). Attaches the operator
 * info to req.adminSession and calls next(). Redirects to /admin/login on
 * missing / invalid session.
 *
 * Paths exempt from authentication (chicken-and-egg):
 *   /admin/login  — the login page itself
 *   /auth/        — /auth/start and /auth/internal-login-proxy
 *   /health       — health check
 */
async function requireSession(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  // Exempt unauthenticated paths.
  if (
    req.path.startsWith("/admin/login") ||
    req.path.startsWith("/auth/") ||
    req.path === "/health"
  ) {
    next();
    return;
  }

  const cookie = req.headers.cookie ?? "";
  try {
    const resp = await fetch(`${ADMIN_API_URL}/v1/auth/whoami`, {
      headers: { Cookie: cookie },
    });

    if (resp.status !== 200) {
      res.redirect("/admin/login");
      return;
    }

    const body = await resp.json() as { operator: AdminSession };
    req.adminSession = body.operator;

    // Populate the AdminJS-standard session key so context.currentAdmin is
    // available inside action handlers (read by @adminjs/express buildRouter via
    // `req.session.adminUser`). Also stash the operator's session tokens so
    // handlers can pass operatorOpts to apiWrite for per-operator signed requests.
    const sessionTokenMatch = cookie.match(/mintkey_session=([^;]+)/);
    const csrfTokenMatch = cookie.match(/csrf_token=([^;]+)/);
    req.session.adminUser = {
      email: body.operator.email,
      operatorId: body.operator.operator_id,
      tenantId: body.operator.tenant_id,
      isPlatformAdmin: body.operator.is_platform_admin,
      sessionToken: sessionTokenMatch?.[1] ?? "",
      csrfToken: csrfTokenMatch?.[1] ?? "",
      authMethod: body.operator.auth_method,
    };

    next();
  } catch {
    res.redirect("/admin/login");
  }
}

async function main() {
  // Register the REST adapter so AdminJS can handle RestResource instances (P0-1)
  AdminJS.registerAdapter({ Database: RestDatabase, Resource: RestResource });

  // AdminJS instance
  const admin = new AdminJS({
    componentLoader,
    dashboard: {
      component: Components.Dashboard,
      handler: dashboardHandler,
    },
    pages: {
      "budget-consumers": {
        component: Components.BudgetConsumersPage,
        label: "Budget Consumers",
        icon: "Activity",
      },
    },
    // Nav order: Dashboard → Services → Email Services → Agents → Permissions → API Keys → Audit → Tenants
    resources: [
      { resource: ServicesResource.adminResource, options: ServicesResource.options },
      { resource: EmailServicesResource.adminResource, options: EmailServicesResource.options },
      { resource: OAuth2ProvidersResource.adminResource, options: OAuth2ProvidersResource.options },
      { resource: EmailPermissionGrantsResource.adminResource, options: EmailPermissionGrantsResource.options },
      { resource: AgentsResource.adminResource, options: AgentsResource.options },
      { resource: PermissionsResource.adminResource, options: PermissionsResource.options },
      { resource: ApiKeysResource.adminResource, options: ApiKeysResource.options },
      { resource: CredentialsResource.adminResource, options: CredentialsResource.options },
      { resource: AuditResource.adminResource, options: AuditResource.options },
      { resource: TenantsResource.adminResource, options: TenantsResource.options },
    ],
    rootPath: "/admin",
    branding: {
      companyName: "Mintkey",
      logo: false,
      favicon: "/favicon.ico",
    },
  });

  const app = express();

  // Trust the first hop of X-Forwarded-Proto / X-Forwarded-For from Kong/Caddy.
  // Required so express-session can see the connection as HTTPS when sitting
  // behind a TLS-terminating reverse proxy; without this, express-session ignores
  // X-Forwarded-Proto and treats the local HTTP socket as insecure, which causes
  // secure cookies to be silently dropped even in prod (O1 — strike-2).
  app.set("trust proxy", 1);

  // Logging
  app.use(pinoHttp());

  // Body parsing is scoped to the break-glass proxy route only.
  //
  // DO NOT mount express.urlencoded/json globally: the AdminJS router uses
  // express-formidable to parse request bodies (multipart, urlencoded, JSON).
  // If express.json() consumes the request stream first, formidable's
  // form.parse() hangs waiting for a stream that has already been drained —
  // causing all action handler POST requests (test-transient, new, edit, …)
  // to time out with statusCode=null. See SSO-REDUX-3.

  // Express-session: provides req.session so AdminJS's action machinery can read
  // req.session.adminUser (populated by requireSession below) as context.currentAdmin.
  //
  // NOTE: MemoryStore is intentional for dev/single-process. For production,
  // replace with a durable store (e.g. connect-redis or connect-pg-simple) to
  // survive restarts and support horizontal scaling.
  app.use(
    session({
      name: "adminjs.sid",
      secret: process.env.SESSION_SECRET ?? "mintkey-dev-secret",
      resave: false,
      saveUninitialized: false,
      cookie: {
        httpOnly: true,
        sameSite: "strict",
        // In production (behind Kong/Caddy with trust proxy set above), express-session
        // sees X-Forwarded-Proto=https and marks the cookie Secure. In dev (NODE_ENV≠
        // production, direct HTTP on localhost:8081) the flag is omitted so browsers
        // accept the cookie over HTTP — dev login works without a local TLS proxy.
        // CodeQL js/clear-text-cookie: conditional-on-production is the conventional
        // pattern accepted by the rule (it fires on unconditional secure:false only).
        // CWE-614; S8-codeql; O1-strike-2.
        secure: process.env.NODE_ENV === "production",
        maxAge: 8 * 60 * 60 * 1000, // 8 h — matches mintkey_session TTL
      },
    })
  );

  // ── Unauthenticated routes ──────────────────────────────────────────────────

  // Health endpoint — no auth required.
  app.get("/health", (_req, res) => {
    res.json({ status: "ok", service: "admin-ui" });
  });

  // Rate-limiter for login endpoints — defense-in-depth against brute-force.
  // Kong-level rate-limiting is the primary control; this is a secondary in-process
  // guard (CWE-307 / CodeQL js/missing-rate-limiting).
  // 20 requests per 15-minute window per IP on login pages.
  const loginRateLimit = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 20,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: "Too many login attempts. Please try again later." },
  });

  // GET /admin/login — SSO-C login page (primary: Keycloak; collapsed: break-glass).
  app.get("/admin/login", loginRateLimit, (req, res) => {
    const err = typeof req.query["error"] === "string" ? req.query["error"] : undefined;
    res.type("html").send(renderLoginPage(err));
  });

  // GET /auth/start — proxy redirect to admin-api OIDC login (browser-facing).
  app.get("/auth/start", (_req, res) => {
    res.redirect(302, `${ADMIN_API_PUBLIC_URL}/v1/auth/oidc/login`);
  });

  // POST /auth/internal-login-proxy — server-side relay for break-glass form.
  // Forwards credentials to admin-api /v1/auth/internal-login and relays any
  // Set-Cookie headers so the mintkey_session cookie is set on the browser's
  // admin-api origin. On success, redirects to /admin. On failure, shows error.
  app.post(
    "/auth/internal-login-proxy",
    loginRateLimit,
    express.urlencoded({ extended: false }),
    async (req, res) => {
    const { email, password } = req.body as { email?: string; password?: string };
    if (!email || !password) {
      res.redirect(302, "/admin/login?error=Email+and+password+are+required");
      return;
    }

    try {
      const resp = await fetch(`${ADMIN_API_URL}/v1/auth/internal-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (resp.status === 404) {
        res.redirect(
          302,
          "/admin/login?error=Break-glass+login+is+disabled.+Run+%60mintkey+admin+reset-password%60+first."
        );
        return;
      }

      if (!resp.ok) {
        res.redirect(302, "/admin/login?error=Invalid+credentials");
        return;
      }

      // Relay Set-Cookie headers from admin-api to the browser.
      const setCookieHeaders = resp.headers.getSetCookie?.() ?? [];
      if (setCookieHeaders.length > 0) {
        res.setHeader("Set-Cookie", setCookieHeaders);
      }

      res.redirect(302, "/admin");
    } catch {
      res.redirect(302, "/admin/login?error=Login+service+unavailable");
    }
  });  // end app.post /auth/internal-login-proxy

  // ── Session middleware — applies BEFORE AdminJS router ──────────────────────
  // Validates mintkey_session cookie via admin-api whoami on every /admin request.
  app.use(requireSession);

  // PlatformAdmin view flag middleware (reads from req.adminSession via session shim).
  app.use(platformAdminMiddleware);

  // ── BFF: Budget management routes ──────────────────────────────────────────
  // Mounted BEFORE the AdminJS router so they are session-protected via
  // requireSession above. All routes proxy to admin-api via apiWrite/fetch.
  // Source: budget-management-ui spec, Task 8.2.
  app.get("/admin/api/budget-consumers", budgetConsumersHandler);
  app.get("/admin/api/budget/:permId", budgetGetHandler);
  app.post("/admin/api/budget/:permId/edit", express.json(), budgetEditHandler);
  app.post("/admin/api/budget/:permId/remove", budgetRemoveHandler);
  app.post("/admin/api/budget/:permId/reset", budgetResetHandler);

  // ── AdminJS unauthenticated router ──────────────────────────────────────────
  // buildRouter(admin, predefinedRouter?, formidableOptions?) — we own auth above.
  // Pass undefined for predefinedRouter so AdminJS creates its own Express Router.
  const router = buildRouter(admin);

  // Custom settings page — served within the admin router.
  router.get("/settings", (req, res) => {
    res.send(`<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Admin Settings — Mintkey</title>
<style>body{font-family:sans-serif;max-width:640px;margin:48px auto;padding:0 20px}h1{margin-bottom:24px}label{display:block;margin:12px 0}input,select{width:100%;padding:6px;margin-top:4px;box-sizing:border-box}.btn{margin-top:16px;padding:8px 16px;cursor:pointer}</style>
</head>
<body>
<h1>Admin Settings</h1>
<form method="POST" action="/admin/settings">
  <label>Company name<input name="company_name" value="Mintkey"></label>
  <label>Session TTL (seconds)<input type="number" name="session_ttl" value="86400"></label>
  <label>MFA required<select name="mfa_required"><option value="false">No</option><option value="true">Yes</option></select></label>
  <button type="submit" class="btn">Save Settings</button>
</form>
</body></html>`);
  });

  app.use(admin.options.rootPath, router);

  // ── BFF: OAuth2 authorize passthrough ───────────────────────────────────────
  //
  // POST /admin/email-services/:tenantId/:serviceId/oauth2/:provider/authorize
  //
  // The browser calls this same-origin endpoint (no CORS needed). This handler
  // forwards the request server-side to admin-api using the internal docker
  // hostname (ADMIN_API_URL) so the operator's browser never needs to reach
  // admin-api directly.
  //
  // Cookie is forwarded so admin-api can validate the session. The JSON response
  // (including auth_url) is relayed back to the browser as-is.
  //
  // This route is mounted AFTER requireSession (via app.use order), so only
  // authenticated operators can call it.
  //
  // Source: Bug-A fix; ADR-0014.5 cookie-based session; C-10.
  app.post(
    "/admin/email-services/:tenantId/:serviceId/oauth2/:provider/authorize",
    // NOTE: NO express.json() body parser. The browser sends an empty body
    // (content-length: 0), and express.json() chokes on that combination
    // ("stream is not readable"). The admin-api authorize endpoint takes no
    // body — params come from the path + cookie auth — so we can safely drop
    // body parsing here.
    async (req: Request, res: Response) => {
      const { tenantId, serviceId, provider } = req.params as {
        tenantId: string;
        serviceId: string;
        provider: string;
      };

      const cookie = req.headers.cookie ?? "";

      // Forward CSRF token — admin-api's Kong middleware requires X-Mintkey-Csrf
      // on state-changing endpoints. The browser sends the CSRF token as a cookie;
      // extract it server-side and re-inject it as the expected header.
      const csrfTokenMatch = cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfTokenMatch?.[1] ?? "";

      try {
        const upstream = await fetch(
          `${ADMIN_API_URL}/v1/tenants/${tenantId}/email-services/${serviceId}/oauth2/${provider}/authorize`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Cookie: cookie,
              ...(csrfToken ? { "X-Mintkey-Csrf": csrfToken } : {}),
            },
            // No body — admin-api authorize takes none.
          }
        );

        const upstreamBody = await upstream.text();

        res
          .status(upstream.status)
          .type("application/json")
          .send(upstreamBody);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Upstream error";
        res
          .status(502)
          .json({ title: "BFF proxy error", detail: message });
      }
    }
  );

  app.listen(PORT, () => {
    console.info(`AdminJS running at http://localhost:${PORT}/admin`);
  });
}

main().catch((err) => {
  console.error("Admin UI failed to start:", err);
  process.exit(1);
});
