/**
 * Mintkey AdminJS server.
 *
 * Express + AdminJS 7.x + @adminjs/sql adapter (read-only DB user).
 * All writes route through admin-api via AdminUiSignedRequest JWTs.
 *
 * Source: T-1.1.4; T-1.2.3; T-1.3.4; T-1.4.3; T-1.7.4; T-1.12.4;
 *         ADR-0013; ADR-0014.5; ADR-0014.6.
 */

import express from "express";
import session from "express-session";
import AdminJS from "adminjs";
import { buildAuthenticatedRouter } from "@adminjs/express";
import pinoHttp from "pino-http";
import pg from "pg";
import ConnectPgSimple from "connect-pg-simple";

import { adminJSAuthOptions, registerOidcRoutes } from "./auth.js";
import { platformAdminMiddleware } from "./middleware/platform-admin.js";
import { ServicesResource } from "./resources/services.js";
import { CredentialsResource } from "./resources/credentials.js";
import { AgentsResource } from "./resources/agents.js";
import { PermissionsResource } from "./resources/permissions.js";
import { AuditResource } from "./resources/audit.js";
import { TenantsResource } from "./resources/tenants.js";

const PORT = parseInt(process.env.PORT ?? "3000", 10);
const DB_URL = process.env.DATABASE_URL ?? "postgresql://mintkey_app_ro:@localhost:5432/mintkey";
const SESSION_SECRET = process.env.SESSION_SECRET ?? "mintkey-session-secret-change-in-production";

async function main() {
  // PostgreSQL pool (read-only role for @adminjs/sql)
  const pool = new pg.Pool({ connectionString: DB_URL });

  // AdminJS instance
  const admin = new AdminJS({
    resources: [
      ServicesResource,
      CredentialsResource,
      AgentsResource,
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

  // Session store
  const PgSession = ConnectPgSimple(session);
  app.use(
    session({
      store: new PgSession({ pool, tableName: "session" }),
      secret: SESSION_SECRET,
      resave: false,
      saveUninitialized: false,
      cookie: {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "strict",
        maxAge: 8 * 60 * 60 * 1000, // 8 hours
      },
    })
  );

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
