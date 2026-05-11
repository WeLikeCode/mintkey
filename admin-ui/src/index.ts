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

import { adminJSAuthOptions, registerOidcRoutes } from "./auth.js";
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
  // AdminJS instance
  const admin = new AdminJS({
    resources: [
      ServicesResource,
      CredentialsResource,
      AgentsResource,
      ApiKeysResource,
      PermissionsResource,
      AuditResource,
      TenantsResource,
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
