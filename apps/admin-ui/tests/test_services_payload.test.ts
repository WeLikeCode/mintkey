/**
 * UX-CLARITY P0: TestServiceForm — handler payload threading tests.
 *
 * Verifies:
 *   1. The testService handler uses request.payload (not a hardcoded body).
 *   2. Submitting with GET /health (defaults) sends exactly those values.
 *   3. Submitting with POST + custom path sends those values.
 *   4. Submitting with optional headers/body forwards them too.
 *   5. GET (form-load) request returns record without calling admin-api.
 *   6. POST with no payload.method falls through gracefully (no admin-api call).
 *   7. Handler embeds testResult in record.params (option C).
 *   8. Component is TestServiceForm (not ConfirmAction).
 *
 * Source: UX-CLARITY P0; ADMIN_UI_SPEC.md §1.4.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { ServicesResource } from "../src/resources/services.js";

// ── Global fetch mock ────────────────────────────────────────────────────────

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function mockCurrentAdmin() {
  return { operatorId: "op_test", tenantId: "tenant_xyz", email: "op@test.com" };
}

function makeFetchResponse(data: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 502,
    json: async () => data,
  } as unknown as Response;
}

function makeContext(extra: Record<string, unknown> = {}) {
  return {
    currentAdmin: mockCurrentAdmin(),
    record: {
      toJSON: () => ({
        id: "svc_test123",
        params: { id: "svc_test123", name: "Test Svc", base_url: "https://api.example.com" },
        errors: {},
        populated: {},
      }),
    },
    resource: {
      build: async (params: Record<string, unknown>) => ({
        toJSON: () => ({ id: null, params, errors: {}, populated: {} }),
      }),
    },
    ...extra,
  };
}

// ── helpers ──────────────────────────────────────────────────────────────────

type ActionHandler = (
  request: Record<string, unknown>,
  response: unknown,
  context: ReturnType<typeof makeContext>
) => Promise<unknown>;

function getHandler(): ActionHandler {
  const actions = ServicesResource.options?.actions ?? {};
  const handler = (actions as Record<string, { handler?: ActionHandler }>).testService?.handler;
  if (!handler) throw new Error("testService handler not found");
  return handler;
}

// ── tests ────────────────────────────────────────────────────────────────────

describe("testService handler — payload threading (UX-CLARITY P0)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mock("../src/lib/signed-request.js", () => ({
      buildSignedRequest: vi.fn().mockResolvedValue("fake.jwt"),
    }));
  });

  // ── 1. component registration ─────────────────────────────────────────────

  it("component is TestServiceForm (not ConfirmAction)", () => {
    const actions = ServicesResource.options?.actions ?? {};
    const comp = (actions as Record<string, { component?: unknown }>).testService?.component;
    // The component is a string key registered by ComponentLoader
    expect(String(comp), "component must not be ConfirmAction").not.toContain("ConfirmAction");
    // It should be a non-null/non-undefined value
    expect(comp).toBeTruthy();
  });

  // ── 2. GET returns record without calling admin-api ───────────────────────

  it("GET request returns record without calling admin-api", async () => {
    const handler = getHandler();
    const result = await handler(
      { method: "get", params: { recordId: "svc_test123" }, payload: {} },
      {},
      makeContext()
    );
    // fetch should NOT have been called (no admin-api write on form load)
    expect(mockFetch).not.toHaveBeenCalled();
    expect((result as Record<string, unknown>).record).toBeDefined();
  });

  // ── 3. POST with no payload.method falls through ──────────────────────────

  it("POST with no payload.method falls through without calling admin-api", async () => {
    const handler = getHandler();
    const result = await handler(
      { method: "post", params: { recordId: "svc_test123" }, payload: {} },
      {},
      makeContext()
    );
    expect(mockFetch).not.toHaveBeenCalled();
    expect((result as Record<string, unknown>).record).toBeDefined();
  });

  // ── 4. Default payload (GET /health / 5000ms) ─────────────────────────────

  it("POST with GET /health/5000ms sends exactly that payload to admin-api", async () => {
    const testApiResult = {
      ok: true,
      status_code: 200,
      latency_ms: 31,
      final_url: "https://api.example.com/health",
      response_body_truncated: '{"status":"ok"}',
    };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(testApiResult));

    const handler = getHandler();
    await handler(
      {
        method: "post",
        params: { recordId: "svc_test123" },
        payload: { method: "GET", path: "/health", timeout_ms: 5000 },
      },
      {},
      makeContext()
    );

    // Verify admin-api was called
    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/services/svc_test123/test");
    const sentBody = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(sentBody.method).toBe("GET");
    expect(sentBody.path).toBe("/health");
    expect(sentBody.timeout_ms).toBe(5000);
  });

  // ── 5. Custom method + path threads through ───────────────────────────────

  it("POST with POST /v1/ingest sends exactly those operator-supplied values", async () => {
    const testApiResult = {
      ok: false,
      status_code: 404,
      latency_ms: 88,
      final_url: "https://api.example.com/v1/ingest",
      response_body_truncated: '{"error":"not found"}',
    };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(testApiResult, false));

    const handler = getHandler();
    await handler(
      {
        method: "post",
        params: { recordId: "svc_test123" },
        payload: { method: "POST", path: "/v1/ingest", timeout_ms: 10000 },
      },
      {},
      makeContext()
    );

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const sentBody = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(sentBody.method).toBe("POST");
    expect(sentBody.path).toBe("/v1/ingest");
    expect(sentBody.timeout_ms).toBe(10000);
    // No hardcoded GET /health
    expect(sentBody.path).not.toBe("/health");
  });

  // ── 6. Headers + body forwarded ───────────────────────────────────────────

  it("POST with headers and body forwards them to admin-api", async () => {
    const testApiResult = { ok: true, status_code: 201, latency_ms: 45 };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(testApiResult));

    const handler = getHandler();
    await handler(
      {
        method: "post",
        params: { recordId: "svc_test123" },
        payload: {
          method: "POST",
          path: "/v1/events",
          headers: { "X-Trace": "abc123" },
          body: '{"event":"test"}',
          timeout_ms: 3000,
        },
      },
      {},
      makeContext()
    );

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const sentBody = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(sentBody.headers).toEqual({ "X-Trace": "abc123" });
    expect(sentBody.body).toBe('{"event":"test"}');
  });

  // ── 7. Result embedded in record.params ───────────────────────────────────

  it("embeds testResult in record.params.testResult (option C)", async () => {
    const testApiResult = {
      ok: true,
      status_code: 200,
      latency_ms: 22,
      final_url: "https://api.example.com/health",
      response_body_truncated: "OK",
    };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(testApiResult));

    const handler = getHandler();
    const result = await handler(
      {
        method: "post",
        params: { recordId: "svc_test123" },
        payload: { method: "GET", path: "/health", timeout_ms: 5000 },
      },
      {},
      makeContext()
    );

    const record = (result as { record: { params: Record<string, unknown> } }).record;
    expect(record.params.testResult).toBeDefined();
    const tr = record.params.testResult as typeof testApiResult;
    expect(tr.ok).toBe(true);
    expect(tr.status_code).toBe(200);
    expect(tr.latency_ms).toBe(22);
    expect(tr.final_url).toBe("https://api.example.com/health");
    expect(tr.response_body_truncated).toBe("OK");
  });

  // ── 8. No hardcoded GET /health in POST path ──────────────────────────────

  it("handler never hardcodes method=GET or path=/health in the POST body", async () => {
    const testApiResult = { ok: true, status_code: 200, latency_ms: 5 };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(testApiResult));

    const handler = getHandler();
    await handler(
      {
        method: "post",
        params: { recordId: "svc_test123" },
        payload: { method: "DELETE", path: "/v1/data/42", timeout_ms: 2000 },
      },
      {},
      makeContext()
    );

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const sentBody = JSON.parse(init.body as string) as Record<string, unknown>;
    // Must NOT override operator's DELETE with GET
    expect(sentBody.method).toBe("DELETE");
    // Must NOT override operator's path with /health
    expect(sentBody.path).toBe("/v1/data/42");
  });
});
