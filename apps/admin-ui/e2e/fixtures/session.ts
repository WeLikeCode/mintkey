/**
 * API session for fixtures that call admin-api directly (setup / cleanup).
 *
 * The suite used to obtain this by POSTing the bootstrap password to
 * /v1/auth/internal-login. That endpoint answers 404 for OIDC-provisioned operators (the seeded
 * admin has no internal_password_hash; login moved to Keycloak), so every fixture silently ran
 * unauthenticated. The browser session that global-setup.ts obtained through Keycloak is already
 * on disk in state.json; reuse its mintkey_session + csrf_token cookies instead.
 */

import { existsSync, readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATE_FILE = path.resolve(here, "..", "state.json");

export interface ApiSession {
  sessionToken: string;
  csrfToken: string;
}

let cached: ApiSession | null = null;

export function getApiSession(): ApiSession | null {
  if (cached) return cached;
  if (!existsSync(STATE_FILE)) return null;
  const state = JSON.parse(readFileSync(STATE_FILE, "utf-8")) as {
    cookies?: { name: string; value: string }[];
  };
  const sessionToken = state.cookies?.find((c) => c.name === "mintkey_session")?.value;
  const csrfToken = state.cookies?.find((c) => c.name === "csrf_token")?.value;
  if (!sessionToken || !csrfToken) return null;
  cached = { sessionToken, csrfToken };
  return cached;
}
