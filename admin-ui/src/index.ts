/**
 * Mintkey AdminJS server.
 *
 * Express + AdminJS 7.x. All data reads come from admin-api over HTTP.
 * All writes route through admin-api via AdminUiSignedRequest JWTs.
 *
 * Source: T-1.1.4; T-1.2.3; T-1.3.4; T-1.4.3; T-1.7.4; T-1.12.4;
 *         ADR-0013; ADR-0014.5; ADR-0014.6.
 */

import express from "express";
import AdminJS from "adminjs";
import { buildAuthenticatedRouter } from "@adminjs/express";
import pinoHttp from "pino-http";

import { RestDatabase, RestResource } from "./lib/rest-resource.js";
import { adminJSAuthOptions, registerOidcRoutes } from "./auth.js";
import { dashboardHandler } from "./dashboard.js";
import { componentLoader, Components } from "./components/index.js";
import { platformAdminMiddleware } from "./middleware/platform-admin.js";
import { ServicesResource } from "./resources/services.js";
import { CredentialsResource } from "./resources/credentials.js";
import { AgentsResource } from "./resources/agents.js";
import { ApiKeysResource } from "./resources/api_keys.js";
import { PermissionsResource } from "./resources/permissions.js";
import { AuditResource } from "./resources/audit.js";
import { TenantsResource } from "./resources/tenants.js";

const PORT = parseInt(process.env.PORT ?? "3000", 10);
const SESSION_SECRET = process.env.SESSION_SECRET ?? "mintkey-session-secret-change-in-production";

async function main() {
  // Register the REST adapter so AdminJS can handle RestResource instances (P0-1)
  AdminJS.registerAdapter({ Database: RestDatabase, Resource: RestResource });

  // AdminJS instance
  const admin = new AdminJS({
    componentLoader,
    dashboard: {
      // `component` (a registered React component) is what makes AdminJS replace
      // the stock "Welcome on Board!" tips screen; `handler` feeds it data.
      component: Components.Dashboard,
      handler: dashboardHandler,
    },
    // Nav order: Dashboard → Services → Agents → Permissions → API Keys → Audit → Tenants
    resources: [
      { resource: ServicesResource.adminResource, options: ServicesResource.options },
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

  // Logging
  app.use(pinoHttp());

  // PlatformAdmin view flag middleware
  app.use(platformAdminMiddleware);

  // AdminJS authenticated router
  const router = buildAuthenticatedRouter(admin, adminJSAuthOptions, null, {
    resave: false,
    saveUninitialized: false,
    secret: SESSION_SECRET,
  });

  // Custom settings page — served within the admin router so session middleware applies
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

  // OIDC routes (Keycloak)
  registerOidcRoutes(app, admin);

  // Health endpoint
  app.get("/health", (_req, res) => {
    res.json({ status: "ok", service: "admin-ui" });
  });

  app.listen(PORT, () => {
    console.info(`AdminJS running at http://localhost:${PORT}/admin`);
  });
}

main().catch((err) => {
  console.error("Admin UI failed to start:", err);
  process.exit(1);
});
