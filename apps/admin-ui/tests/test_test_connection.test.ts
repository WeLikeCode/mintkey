/**
 * CHUNK 3: Test Connection action tests.
 *
 * Tests verify:
 * - testService action exists on ServicesResource
 * - Action type is "record"
 * - Handler calls admin-api POST .../services/{id}/test
 * - Returns testResult embedded in record.params (option C — UX-CLARITY P0)
 *
 * Source: ADMIN_UI_SPEC.md §2.3; T-1.2.3; ADR-0014.5.
 * Updated: UX-CLARITY P0 switched from notice-based response to option-C
 *   (record.params.testResult) so the React component can render the full
 *   result panel (final_url, response_body_truncated, etc.).
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

  it("handler embeds testResult in record.params when test succeeds (option C)", async () => {
    // UX-CLARITY P0: handler no longer returns a notice; it embeds the full
    // TestRunResponse in record.params.testResult for the React component to render.
    mockFetch
      .mockResolvedValueOnce(makeFetchResponse({
        ok: true,
        status_code: 200,
        latency_ms: 42,
        final_url: "https://api.example.com/health",
        response_body_truncated: '{"status":"ok"}',
      }));

    const actions = ServicesResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).testService?.handler;
    expect(handler).toBeDefined();

    const result = await handler!(
      { method: "post", params: { recordId: "svc_test123" }, payload: { method: "GET", path: "/health", timeout_ms: 5000 } },
      {},
      {
        currentAdmin: mockCurrentAdmin(),
        record: { toJSON: () => ({ id: "svc_test123", params: { id: "svc_test123" }, errors: {}, populated: {} }) },
        resource: { build: async (p: Record<string, unknown>) => ({ toJSON: () => ({ id: null, params: p, errors: {}, populated: {} }) }) },
      }
    );

    const tr = result.record?.params?.testResult;
    expect(tr).toBeDefined();
    expect(tr?.ok).toBe(true);
    expect(tr?.status_code).toBe(200);
    expect(tr?.latency_ms).toBe(42);
    expect(tr?.final_url).toBe("https://api.example.com/health");
  });

  it("handler embeds testResult with ok=false when test fails", async () => {
    mockFetch
      .mockResolvedValueOnce(makeFetchResponse({ ok: false, status_code: 502, latency_ms: 1000 }));

    const actions = ServicesResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).testService?.handler;

    const result = await handler!(
      { method: "post", params: { recordId: "svc_test123" }, payload: { method: "GET", path: "/health", timeout_ms: 5000 } },
      {},
      {
        currentAdmin: mockCurrentAdmin(),
        record: { toJSON: () => ({ id: "svc_test123", params: { id: "svc_test123" }, errors: {}, populated: {} }) },
        resource: { build: async (p: Record<string, unknown>) => ({ toJSON: () => ({ id: null, params: p, errors: {}, populated: {} }) }) },
      }
    );

    const tr = result.record?.params?.testResult;
    expect(tr).toBeDefined();
    expect(tr?.ok).toBe(false);
    expect(tr?.status_code).toBe(502);
  });
});
