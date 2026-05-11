/**
 * AdminJS authentication configuration — login page and session handling.
 *
 * Provides two login options:
 *   1. Internal auth — POSTs to admin-api /v1/auth/internal-login (Argon2id).
 *   2. Login with Keycloak — OIDC via passport-openidconnect.
 *
 * The login surface does NOT use AdminUiSignedRequest middleware — login is
 * the bootstrap surface. The signed-request JWT applies only to write
 * operations after the operator is authenticated (ADR-0014.5).
 *
 * Source: T-1.1.4; Req 2 AC1, AC8.
 */

import type { Router } from "express";
import type AdminJS from "adminjs";

const ADMIN_API_URL =
  process.env.ADMIN_API_URL ?? "http://admin-api:8080";

/**
 * Authentication options for AdminJS buildAuthenticatedRouter.
 *
 * authenticate() is called by AdminJS on every login attempt.
 * It validates the credentials against admin-api and returns a user record
 * or null on failure.
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
 * Register OIDC (Keycloak) login route.
 * Source: T-1.1.2; ADR-0014.2 (Keycloak default).
 */
export function registerOidcRoutes(app: Router, adminJs: AdminJS): void {
  const oidcIssuer = process.env.OIDC_ISSUER ?? "http://keycloak:8086/realms/mintkey";
  const oidcClientId = process.env.OIDC_CLIENT_ID ?? "mintkey-admin-ui";
  const oidcClientSecret = process.env.OIDC_CLIENT_SECRET ?? "";
  const publicUrl = process.env.PUBLIC_URL ?? "http://localhost:3000";

  // Dynamic import to avoid runtime errors when passport-openidconnect is missing
  import("passport").then(async ({ default: passport }) => {
    const { Strategy } = await import("passport-openidconnect");

    passport.use(
      new Strategy(
        {
          issuer: oidcIssuer,
          authorizationURL: `${oidcIssuer}/protocol/openid-connect/auth`,
          tokenURL: `${oidcIssuer}/protocol/openid-connect/token`,
          userInfoURL: `${oidcIssuer}/protocol/openid-connect/userinfo`,
          clientID: oidcClientId,
          clientSecret: oidcClientSecret,
          callbackURL: `${publicUrl}/auth/oidc/callback`,
          scope: ["openid", "email", "profile"],
        },
        (_issuer, profile, done) => done(null, profile)
      )
    );

    app.get("/auth/oidc", passport.authenticate("openidconnect"));
    app.get(
      "/auth/oidc/callback",
      passport.authenticate("openidconnect", {
        failureRedirect: `${adminJs.options.rootPath}/login`,
      }),
      (_req, res) => res.redirect(adminJs.options.rootPath)
    );
  }).catch(() => {
    // OIDC not configured — internal auth only
  });
}
