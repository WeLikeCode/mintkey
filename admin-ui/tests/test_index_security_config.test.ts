/**
 * Security configuration unit tests — S8 CodeQL remediation (incl. strike-2 O1).
 *
 * Verifies that:
 *   1. The session cookie has Secure gated on NODE_ENV=production, HttpOnly=true,
 *      SameSite=Strict (closes CodeQL js/clear-text-cookie @ index.ts:181).
 *      Convention: conditional-on-production is accepted by the rule; unconditional
 *      secure:false is what fires the alert.
 *   2. express-rate-limit is imported and applied to login routes
 *      (closes CodeQL js/missing-rate-limiting @ index.ts:203).
 *   3. app.set('trust proxy', 1) is present so express-session honours
 *      X-Forwarded-Proto from Kong/Caddy (O1 — strike-2 operational fix).
 *
 * Strategy: parse the index.ts source statically so these tests don't require
 * a live HTTP server. Source-inspection is appropriate here because the
 * security properties are configuration constants, not runtime behaviour.
 *
 * Source: S8-codeql; CWE-614 (clear-text-cookie); CWE-307 (missing rate-limiting);
 *         O1 (trust proxy — strike-2).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join, dirname } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const indexSrc = readFileSync(join(__dirname, "../src/index.ts"), "utf-8");

describe("S8-SEC: session cookie security flags (js/clear-text-cookie)", () => {
  it("session cookie must NOT have unconditional secure: false", () => {
    // Ensure the old insecure default is gone; the rule fires on unconditional false
    expect(indexSrc).not.toContain("secure: false");
  });

  it("session cookie secure flag must be gated on NODE_ENV=production", () => {
    // Option A (O1 strike-2): conditional secure so dev HTTP works without a TLS proxy
    // while prod (behind Kong with trust proxy) sends Secure cookies.
    expect(indexSrc).toMatch(/secure:\s*process\.env\.NODE_ENV\s*===\s*["']production["']/);
  });

  it("session cookie must have httpOnly: true", () => {
    expect(indexSrc).toMatch(/httpOnly:\s*true/);
  });

  it("session cookie sameSite must be 'strict' (not 'lax')", () => {
    // Ensure we upgraded from lax
    expect(indexSrc).not.toContain('sameSite: "lax"');
    expect(indexSrc).not.toContain("sameSite: 'lax'");
  });

  it("session cookie sameSite must be 'strict'", () => {
    expect(indexSrc).toMatch(/sameSite:\s*["']strict["']/);
  });
});

describe("S8-SEC O1 strike-2: trust proxy set for reverse-proxy TLS termination", () => {
  it("app.set('trust proxy', 1) is present", () => {
    // Without trust proxy, express-session ignores X-Forwarded-Proto from Kong/Caddy
    // and treats the local HTTP socket as insecure — secure cookies are silently dropped.
    // Source: O1 operational regression (strike-2).
    expect(indexSrc).toMatch(/app\.set\(\s*["']trust proxy["']\s*,\s*1\s*\)/);
  });

  it("trust proxy is set before session middleware", () => {
    // Ordering matters: trust proxy must be configured before app.use(session(...))
    const trustProxyIdx = indexSrc.indexOf("trust proxy");
    const sessionIdx = indexSrc.indexOf("app.use(\n    session(");
    expect(trustProxyIdx).toBeGreaterThan(-1);
    expect(sessionIdx).toBeGreaterThan(-1);
    expect(trustProxyIdx).toBeLessThan(sessionIdx);
  });
});

describe("S8-SEC: login endpoint rate limiting (js/missing-rate-limiting)", () => {
  it("express-rate-limit is imported", () => {
    expect(indexSrc).toContain("express-rate-limit");
  });

  it("rateLimit middleware is applied to /admin/login route", () => {
    // Verify that the login GET route uses loginRateLimit middleware
    // The route is: app.get("/admin/login", loginRateLimit, ...)
    expect(indexSrc).toContain('app.get("/admin/login", loginRateLimit,');
  });

  it("rateLimit middleware is applied to /auth/internal-login-proxy route", () => {
    // Verify that the break-glass POST route also uses loginRateLimit
    // The route is multi-line: app.post(\n  "/auth/internal-login-proxy",\n  loginRateLimit,
    expect(indexSrc).toContain('"/auth/internal-login-proxy"');
    expect(indexSrc).toContain("loginRateLimit");
    // Verify loginRateLimit appears between the route path and express.urlencoded
    const proxyBlock = indexSrc.slice(
      indexSrc.indexOf('"/auth/internal-login-proxy"'),
      indexSrc.indexOf("express.urlencoded", indexSrc.indexOf('"/auth/internal-login-proxy"'))
    );
    expect(proxyBlock).toContain("loginRateLimit");
  });

  it("rate limit window is at most 15 minutes", () => {
    // windowMs should be ≤ 15 * 60 * 1000 ms (900_000)
    const match = indexSrc.match(/windowMs:\s*(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)/);
    if (match) {
      const windowMs = parseInt(match[1]) * parseInt(match[2]) * parseInt(match[3]);
      expect(windowMs).toBeLessThanOrEqual(15 * 60 * 1000);
    } else {
      // Literal value form
      const literalMatch = indexSrc.match(/windowMs:\s*(\d+)/);
      if (literalMatch) {
        expect(parseInt(literalMatch[1])).toBeLessThanOrEqual(15 * 60 * 1000);
      }
    }
  });
});
