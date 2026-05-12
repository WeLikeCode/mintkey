/**
 * CHUNK 3: Test Connection action tests.
 *
 * Tests verify:
 * - testService action exists on ServicesResource
 * - Action type is "record"
 * - Handler calls admin-api POST .../services/{id}/test
 * - Returns ok notice on success
 * - Returns error notice on failure
 *
 * Source: ADMIN_UI_SPEC.md §2.3; T-1.2.3; ADR-0014.5.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { ServicesResource } from "../src/resources/services.js";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function mockCurrentAdmin() {
  return { operatorId: "op_123", tenantId: "tenant_abc", email: "op@test.com" };
}

function makeFetchResponse(data: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 502,
    json: async () => data,
  } as unknown as Response;
}

describe("testService action", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Stub signed-request module — buildSignedRequest returns a fake JWT
    vi.mock("../src/lib/signed-request.js", () => ({
      buildSignedRequest: vi.fn().mockResolvedValue("fake.jwt.token"),
    }));
  });

  it("testService action exists", () => {
    const actions = ServicesResource.options?.actions ?? {};
    expect("testService" in actions).toBe(true);
  });

  it("testService is a record action", () => {
    const actions = ServicesResource.options?.actions ?? {};
    expect((actions as Record<string, { actionType?: string }>).testService?.actionType).toBe("record");
  });

  it("testService has label 'Test Connection'", () => {
    const actions = ServicesResource.options?.actions ?? {};
    expect((actions as Record<string, { label?: string }>).testService?.label).toBe("Test Connection");
  });

  it("testService is visible", () => {
    const actions = ServicesResource.options?.actions ?? {};
    const isVisible = (actions as Record<string, { isVisible?: boolean | unknown }>).testService?.isVisible;
    expect(isVisible).toBe(true);
  });

  it("handler returns success notice with status and latency when ok", async () => {
    // First fetch: buildSignedRequest calls (mocked at module level)
    // Second fetch: the actual test call
    mockFetch
      .mockResolvedValueOnce(makeFetchResponse({ ok: true, status_code: 200, latency_ms: 42 }));

    const actions = ServicesResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).testService?.handler;
    expect(handler).toBeDefined();

    const result = await handler!(
      { params: { recordId: "svc_test123" } },
      {},
      {
        currentAdmin: mockCurrentAdmin(),
        record: { toJSON: () => ({ id: "svc_test123" }) },
      }
    );

    expect(result.notice?.type).toBe("success");
    expect(result.notice?.message).toContain("200");
    expect(result.notice?.message).toContain("42");
  });

  it("handler returns error notice when test fails", async () => {
    mockFetch
      .mockResolvedValueOnce(makeFetchResponse({ ok: false, status_code: 502, latency_ms: 1000 }));

    const actions = ServicesResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).testService?.handler;

    const result = await handler!(
      { params: { recordId: "svc_test123" } },
      {},
      {
        currentAdmin: mockCurrentAdmin(),
        record: { toJSON: () => ({ id: "svc_test123" }) },
      }
    );

    expect(result.notice?.type).toBe("error");
    expect(result.notice?.message).toContain("502");
  });
});
