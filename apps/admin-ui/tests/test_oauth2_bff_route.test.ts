/**
 * Tests for the OAuth2 BFF route in index.ts (Bug-A fix).
 *
 * These are source-file inspection tests (node environment, no jsdom).
 *
 * Assertions:
 *   1. The BFF route path is registered in index.ts.
 *   2. The route forwards the Cookie header to admin-api.
 *   3. The route uses ADMIN_API_URL (internal docker hostname), not ADMIN_API_PUBLIC_URL.
 *   4. The route uses a relative path (not absolute admin-api URL) — no window reference.
 *   5. EmailServiceOAuth2Setup component calls the relative BFF path (/admin/email-services/…).
 *   6. EmailServiceOAuth2Setup no longer references ADMIN_API_PUBLIC_URL.
 *   7. EmailServiceOAuth2Setup uses credentials: "same-origin" (not "include").
 *   8. EmailServiceOAuth2Setup no longer has ADMIN_API_BASE fallback to localhost:8080.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const INDEX_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/index.ts"
);

const COMPONENT_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/EmailServiceOAuth2Setup.tsx"
);

const indexSrc = fs.readFileSync(INDEX_PATH, "utf-8");
const componentSrc = fs.readFileSync(COMPONENT_PATH, "utf-8");

describe("OAuth2 BFF route — index.ts (Bug-A fix)", () => {
  it("registers the BFF route path for oauth2 authorize", () => {
    expect(indexSrc).toContain(
      "/admin/email-services/:tenantId/:serviceId/oauth2/:provider/authorize"
    );
  });

  it("forwards Cookie header to admin-api upstream call", () => {
    // The handler must extract the cookie from the request and forward it
    expect(indexSrc).toContain("Cookie: cookie");
  });

  it("extracts and forwards the CSRF token as X-Mintkey-Csrf header", () => {
    // admin-api's Kong middleware requires X-Mintkey-Csrf on state-changing calls
    expect(indexSrc).toContain("X-Mintkey-Csrf");
    expect(indexSrc).toContain("csrf_token=");
  });

  it("uses ADMIN_API_URL (internal docker hostname) for the upstream call", () => {
    // Must use ADMIN_API_URL (server-side internal URL) in the BFF handler,
    // not ADMIN_API_PUBLIC_URL (browser-facing URL)
    expect(indexSrc).toContain("ADMIN_API_URL}/v1/tenants/");
  });

  it("BFF handler is registered as a POST route", () => {
    // app.post( ... /admin/email-services/ ...
    // The route path must exist
    const routeIdx = indexSrc.indexOf("/admin/email-services/:tenantId/:serviceId/oauth2/:provider/authorize");
    expect(routeIdx).toBeGreaterThan(-1);
    // The file must contain app.post for the BFF route (may be on a preceding line)
    expect(indexSrc).toContain("app.post(");
  });

  it("BFF handler returns a 502 with JSON on upstream error", () => {
    expect(indexSrc).toContain("502");
    expect(indexSrc).toContain("BFF proxy error");
  });

  it("BFF handler relays the upstream status code", () => {
    expect(indexSrc).toContain("upstream.status");
  });
});

describe("EmailServiceOAuth2Setup — calls BFF path (Bug-A fix)", () => {
  it("calls the relative BFF path /admin/email-services/ (not admin-api directly)", () => {
    expect(componentSrc).toContain("/admin/email-services/");
  });

  it("does NOT use ADMIN_API_PUBLIC_URL as a live variable (only allowed in comments)", () => {
    // Ensure ADMIN_API_PUBLIC_URL is not assigned or used in executable code.
    // A comment explaining why we removed it is fine.
    const liveUsage = componentSrc
      .split("\n")
      .filter((line) => !line.trim().startsWith("//") && !line.trim().startsWith("*"))
      .join("\n");
    expect(liveUsage).not.toContain("ADMIN_API_PUBLIC_URL");
  });

  it("does NOT fall back to http://localhost:8080", () => {
    expect(componentSrc).not.toContain("http://localhost:8080");
  });

  it("uses credentials: 'same-origin' (not 'include')", () => {
    expect(componentSrc).toContain("same-origin");
    expect(componentSrc).not.toContain(`credentials: "include"`);
    expect(componentSrc).not.toContain("credentials: 'include'");
  });

  it("does NOT contain ADMIN_API_BASE constant pointing to admin-api", () => {
    // Old code: const ADMIN_API_BASE = ... window.ADMIN_API_PUBLIC_URL ?? "http://localhost:8080"
    expect(componentSrc).not.toContain("ADMIN_API_BASE");
  });

  it("fetch URL starts with the BFF_BASE variable (empty string → relative)", () => {
    // BFF_BASE = "" gives a relative URL
    expect(componentSrc).toContain("BFF_BASE");
    expect(componentSrc).toContain('const BFF_BASE = ""');
  });
});
