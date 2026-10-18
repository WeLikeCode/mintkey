/**
 * Operators resource tests — operator-management.
 *
 * Tests verify:
 * - OperatorsResource list action is visible only to PlatformAdmin
 * - listProperties never leaks internal_password_hash (S-SEC-1)
 * - promote (new) handler POSTs to /v1/operators and returns a success notice
 * - promote handler returns an error notice (err.title) on failure
 * - promote handler blocks a non-PlatformAdmin currentAdmin
 *
 * Mirrors tests/test_agents.test.ts: mock global fetch + signed-request.js so no
 * private key / live admin-api is needed.
 *
 * Source: operator-management OpenSpec change; ADR-0031; ADR-0019; S-SEC-1.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { OperatorsResource } from "../src/resources/operators.js";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Mock signed-request to avoid needing the private key file.
vi.mock("../src/lib/signed-request.js", () => ({
  buildSignedRequest: vi.fn().mockResolvedValue("mock.jwt.token"),
}));

// A currentAdmin without sessionToken → operatorOptsFromAdmin returns null →
// apiWrite falls back to the (mocked) unauthenticated fetch, so no signedFetch.
const platformAdmin = { operatorId: "op_root", tenantId: "t_default", isPlatformAdmin: true };
const fakeContext = (currentAdmin: Record<string, unknown>) => ({
  currentAdmin,
  record: { toJSON: () => ({}) },
});

describe("OperatorsResource — platform-admin gating + property safety", () => {
  it("list action is visible only when currentAdmin.isPlatformAdmin === true", () => {
    const actions = OperatorsResource.options?.actions ?? {};
    const isVisible = (actions as Record<string, { isVisible?: Function }>).list?.isVisible;
    expect(typeof isVisible).toBe("function");
    expect((isVisible as Function)({ currentAdmin: { isPlatformAdmin: true } })).toBe(true);
    expect((isVisible as Function)({ currentAdmin: { isPlatformAdmin: false } })).toBe(false);
    expect((isVisible as Function)({ currentAdmin: {} })).toBe(false);
  });

  it("listProperties never leaks internal_password_hash", () => {
    const listProps = OperatorsResource.options?.listProperties ?? [];
    expect(listProps).not.toContain("internal_password_hash");
    expect(listProps).toContain("email");
    expect(listProps).toContain("is_platform_admin");
  });

  it("status property offers active and disabled values", () => {
    const props = OperatorsResource.options?.properties ?? {};
    const status = (props as Record<string, { availableValues?: { value: string }[] }>).status;
    const values = (status?.availableValues ?? []).map((v) => v.value);
    expect(values).toContain("active");
    expect(values).toContain("disabled");
  });
});

describe("OperatorsResource — promote (new) handler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POSTs to /v1/operators and returns a success notice for a platform admin", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "op_new001", email: "new@corp.example" }),
    });

    const actions = OperatorsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;
    expect(handler).toBeDefined();

    const result = await handler!(
      { method: "post", payload: { email: "new@corp.example", tenant_id: "t_default" } },
      {},
      fakeContext(platformAdmin)
    );

    // The write went to /v1/operators via POST.
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockFetch.mock.calls[0];
    expect(String(url)).toContain("/v1/operators");
    expect((opts as { method?: string }).method).toBe("POST");

    expect(result.notice?.type).toBe("success");
    expect(result.notice?.message).toContain("new@corp.example");
  });

  it("returns an error notice (err.title) on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "An operator with this email or oidc_sub already exists" }),
    });

    const actions = OperatorsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;

    const result = await handler!(
      { method: "post", payload: { email: "dupe@corp.example", tenant_id: "t_default" } },
      {},
      fakeContext(platformAdmin)
    );

    expect(result.notice?.type).toBe("error");
    expect(result.notice?.message).toContain("already exists");
  });

  it("blocks a non-platform-admin currentAdmin", async () => {
    const actions = OperatorsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;

    await expect(
      handler!(
        { method: "post", payload: { email: "x@corp.example", tenant_id: "t_default" } },
        {},
        fakeContext({ operatorId: "op_x", tenantId: "t_default", isPlatformAdmin: false })
      )
    ).rejects.toThrow(/PlatformAdmin required/);

    // No write attempted.
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
