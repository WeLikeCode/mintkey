/**
 * SSO-C login tests — break-glass internal-login helper.
 *
 * The primary login path (Keycloak SSO) is browser-driven:
 *   /auth/start → admin-api /v1/auth/oidc/login → Keycloak → admin-api callback → /admin
 *
 * adminJSAuthOptions.authenticate() is the break-glass helper: it POSTs to
 * admin-api /v1/auth/internal-login, which returns 404 when the operator has
 * not run `mintkey admin reset-password` (break-glass disabled), and 200 on
 * success. This test suite validates that helper directly.
 *
 * Source: T-1.1.4; Req 2 AC8; ADR-0014 §14.2; SSO-C D2-b.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { adminJSAuthOptions } from "../src/auth.js";

describe("adminJSAuthOptions.authenticate (break-glass internal-login)", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns null when admin-api returns 401 (wrong password)", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ title: "Unauthorized" }), { status: 401 })
    );

    const result = await adminJSAuthOptions.authenticate("user@test.com", "wrongpass");
    expect(result).toBeNull();
  });

  it("returns null when admin-api returns 404 (break-glass disabled — no internal_password_hash)", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })
    );

    const result = await adminJSAuthOptions.authenticate("user@test.com", "anypass");
    expect(result).toBeNull();
  });

  it("returns user object when admin-api returns 200 (break-glass enabled)", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          operator_id: "operator_123",
          tenant_id: "tenant_456",
          is_platform_admin: false,
        }),
        { status: 200 }
      )
    );

    const result = await adminJSAuthOptions.authenticate("user@test.com", "correctpass");
    expect(result).not.toBeNull();
    expect(result?.operatorId).toBe("operator_123");
    expect(result?.tenantId).toBe("tenant_456");
    expect(result?.isPlatformAdmin).toBe(false);
    expect(result?.email).toBe("user@test.com");
  });

  it("returns null on network error", async () => {
    global.fetch = vi.fn().mockRejectedValueOnce(new Error("network error"));

    const result = await adminJSAuthOptions.authenticate("user@test.com", "pass");
    expect(result).toBeNull();
  });

  it("platform admin flag is propagated", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          operator_id: "operator_admin",
          tenant_id: "tenant_456",
          is_platform_admin: true,
        }),
        { status: 200 }
      )
    );

    const result = await adminJSAuthOptions.authenticate("admin@mintkey.internal", "pass");
    expect(result?.isPlatformAdmin).toBe(true);
  });

  it("POSTs to the correct admin-api endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ operator_id: "x", tenant_id: "y", is_platform_admin: false }), {
        status: 200,
      })
    );

    await adminJSAuthOptions.authenticate("user@test.com", "pass");

    const [url, opts] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/auth/internal-login");
    expect(opts?.method).toBe("POST");
    const body = JSON.parse(opts?.body as string);
    expect(body.email).toBe("user@test.com");
    expect(body.password).toBe("pass");
  });
});

describe("renderLoginPage", () => {
  it("contains Sign in with Keycloak CTA", async () => {
    const { renderLoginPage } = await import("../src/auth.js");
    const html = renderLoginPage();
    expect(html).toContain("Sign in with Keycloak");
  });

  it("contains Break-glass accordion", async () => {
    const { renderLoginPage } = await import("../src/auth.js");
    const html = renderLoginPage();
    expect(html).toContain("Break-glass");
  });

  it("contains /auth/start href", async () => {
    const { renderLoginPage } = await import("../src/auth.js");
    const html = renderLoginPage();
    expect(html).toContain("/auth/start");
  });

  it("shows custom error message when provided", async () => {
    const { renderLoginPage } = await import("../src/auth.js");
    const html = renderLoginPage("Something went wrong");
    expect(html).toContain("Something went wrong");
  });
});
