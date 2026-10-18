/**
 * Single place that decides which stack the e2e suite talks to.
 *
 * Why this exists: the old per-file `?? "http://localhost:8081"` / `?? "http://localhost:8080"`
 * fallbacks silently pointed a run at whatever stack owns the default ports -- on a developer
 * machine that is the live dev stack. A run now has to name its stack explicitly:
 *
 *   PLAYWRIGHT_BASE_URL  admin-ui origin   (required)
 *   ADMIN_API_URL        admin-api origin  (required unless the admin-ui is the default one)
 *   PLAYWRIGHT_TENANT_ID tenant used by the API-driven fixtures
 *
 * CI (CI=true) and E2E_ALLOW_DEFAULT_STACK=1 keep the old defaults (8081 / 8080) because the
 * workflow boots a throw-away stack on exactly those ports. `make e2e-isolated-test` always
 * passes explicit values for the isolated stack.
 */

import path from "path";
import { fileURLToPath } from "url";
import { config as loadDotenv } from "dotenv";

// ES imports are hoisted, so the .env.local load has to happen here (before the values below are
// resolved), not in playwright.config.ts.
loadDotenv({
  path: path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".env.local"),
  override: false,
});

export const DEFAULT_UI_URL = "http://localhost:8081";
export const DEFAULT_API_URL = "http://localhost:8080";

const allowDefaults = !!process.env.CI || process.env.E2E_ALLOW_DEFAULT_STACK === "1";

function resolveBaseUrl(): string {
  const v = process.env.PLAYWRIGHT_BASE_URL;
  if (v) return v.replace(/\/+$/, "");
  if (allowDefaults) return DEFAULT_UI_URL;
  throw new Error(
    "PLAYWRIGHT_BASE_URL is not set. The e2e suite no longer falls back to http://localhost:8081 " +
      "(that is the live dev stack on a developer machine). Point it at the stack under test, " +
      "e.g. via `make e2e-isolated-test`, or set E2E_ALLOW_DEFAULT_STACK=1 to opt in to the default ports.",
  );
}

export const BASE_URL = resolveBaseUrl();

function resolveAdminApi(): string {
  const v = process.env.ADMIN_API_URL;
  if (v) return v.replace(/\/+$/, "");
  if (BASE_URL === DEFAULT_UI_URL) return DEFAULT_API_URL;
  throw new Error(
    `ADMIN_API_URL is not set while PLAYWRIGHT_BASE_URL=${BASE_URL} is not the default admin-ui. ` +
      "Set ADMIN_API_URL to the admin-api of the same stack (otherwise API-driven fixtures would hit port 8080).",
  );
}

export const ADMIN_API = resolveAdminApi();

/** Tenant the API-driven fixtures work in (CI extracts t_default's id from postgres). */
export const TENANT_ID = process.env.MINTKEY_TENANT_ID ?? process.env.PLAYWRIGHT_TENANT_ID ?? "";
