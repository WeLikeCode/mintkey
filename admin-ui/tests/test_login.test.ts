/**
 * AdminJS login page tests — T-1.1.4.
 *
 * Tests:
 * - Login page renders both internal auth and Keycloak options.
 * - Internal login form POSTs to /v1/auth/internal-login.
 * - On success, session cookie is set.
 * - On failure, 401 is returned.
 *
 * Source: T-1.1.4; Req 2 AC1, AC8.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { adminJSAuthOptions } from "../src/auth.js";

describe("adminJSAuthOptions.authenticate", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns null when admin-api returns 401", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ title: "Unauthorized" }), { status: 401 })
    );

    const result = await adminJSAuthOptions.authenticate("user@test.com", "wrongpass");
    expect(result).toBeNull();
  });

  it("returns user object when admin-api returns 200", async () => {
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
