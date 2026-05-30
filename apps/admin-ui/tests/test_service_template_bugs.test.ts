/**
 * Regression tests for FIX-8 service-template bugs.
 *
 * BUG-7a: false-success + masked submit errors.
 *   - BFF from-template handler returns 2xx with no `id` → should NOT set success;
 *     UI success branch only fires when service.id (or record.params.service_id) is present.
 *   - services.ts:from-template handler must propagate non-ok response as error notice.
 *   - BFF must NOT swallow resp.json() failures for the from-template path.
 *
 * BUG-7b: BFF template-list masks upstream failure as empty list.
 *   - When /v1/service-templates returns non-ok, the BFF must signal an error (notice)
 *     rather than returning an empty templates array.
 *
 * BUG-16: field-name mismatch in template-detail BFF.
 *   - Admin-API returns `auth_type` and `openapi_spec_url`; BFF must map to the names
 *     the UI consumes: `auth_scheme` / `openapi_url`. The normalisation in template-detail
 *     must read raw.auth_type (falling back to raw.auth_scheme) and
 *     raw.openapi_spec_url (falling back to raw.openapi_url).
 *   - template-list must also normalise the field names in the returned template array.
 *
 * BUG-19: card highlight uses name fallback.
 *   - ServiceTemplatePicker.tsx must match cards on template_id alone (stable),
 *     not fall back to name comparison.
 *
 * vitest environment: node (no jsdom). Handler tests use direct invocation +
 * mocked global fetch. Source-inspection tests use fs.readFileSync.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "fs";
import * as path from "path";
import { ServicesResource } from "../src/resources/services.js";

// ── Source snapshots ─────────────────────────────────────────────────────────

const PICKER_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/ServiceTemplatePicker.tsx"
);
const SERVICES_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/services.ts"
);

const pickerSrc = fs.readFileSync(PICKER_PATH, "utf-8");
const servicesSrc = fs.readFileSync(SERVICES_PATH, "utf-8");

// ── Global fetch mock ────────────────────────────────────────────────────────

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function makeFetchResponse(data: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response;
}

function makeContext(extra: Record<string, unknown> = {}) {
  return {
    currentAdmin: { operatorId: "op1", tenantId: "ten_abc", email: "op@test.com" },
    record: {
      toJSON: () => ({
        id: null,
        params: {},
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

type ActionHandler = (
  req: Record<string, unknown>,
  res: unknown,
  ctx: ReturnType<typeof makeContext>
) => Promise<Record<string, unknown>>;

function getAction(name: string): ActionHandler {
  const actions = ServicesResource.options?.actions ?? {};
  const handler = (actions as Record<string, { handler?: ActionHandler }>)[name]?.handler;
  if (!handler) throw new Error(`Handler for '${name}' not found`);
  return handler;
}

// ─────────────────────────────────────────────────────────────────────────────
// BUG-7a: from-template — false-success on 2xx with no id
// ─────────────────────────────────────────────────────────────────────────────

describe("BUG-7a: from-template BFF handler — false-success on 2xx with no id", () => {
  beforeEach(() => vi.clearAllMocks());

  it("2xx response WITH id returns service object containing id (happy path)", async () => {
    mockFetch.mockResolvedValueOnce(makeFetchResponse({ id: "svc_new123", name: "test" }, true));
    const handler = getAction("from-template");
    const result = await handler(
      { method: "post", payload: { template_id: "tpl_a" }, params: {} },
      {},
      makeContext()
    );
    // Must carry the real service id back to the UI
    const service = result.service as { id?: string } | undefined;
    expect(service?.id, "service.id must be present on success").toBe("svc_new123");
    // Must NOT carry an error notice
    const notice = result.notice as { type?: string } | undefined;
    expect(notice?.type).not.toBe("error");
  });

  it("2xx response with NO id returns error notice (not a silent 'success')", async () => {
    // This is the bug: admin-api returns 200 but body has no id (malformed / wrong shape)
    mockFetch.mockResolvedValueOnce(makeFetchResponse({ status: "ok" }, true));
    const handler = getAction("from-template");
    const result = await handler(
      { method: "post", payload: { template_id: "tpl_a" }, params: {} },
      {},
      makeContext()
    );
    // Must NOT emit a success path with empty serviceId — must show an error
    const notice = result.notice as { type?: string; message?: string } | undefined;
    expect(notice?.type, "notice.type must be 'error' when id is absent on a 2xx").toBe("error");
    // And must not have redirectUrl that silently routes away without an id
    expect(result.redirectUrl).toBeUndefined();
  });

  it("non-2xx response returns error notice (not success)", async () => {
    mockFetch.mockResolvedValueOnce(makeFetchResponse({ title: "Template not found" }, false, 404));
    const handler = getAction("from-template");
    const result = await handler(
      { method: "post", payload: { template_id: "bad_tpl" }, params: {} },
      {},
      makeContext()
    );
    const notice = result.notice as { type?: string; message?: string } | undefined;
    expect(notice?.type).toBe("error");
    expect(notice?.message).toContain("Template not found");
  });

  it("malformed JSON body (resp.json() throws) surfaces an error, not silent empty", async () => {
    // resp.ok = false + json throws — must NOT swallow the error
    const badResponse = {
      ok: false,
      status: 500,
      json: async () => { throw new Error("invalid json"); },
    } as unknown as Response;
    mockFetch.mockResolvedValueOnce(badResponse);
    const handler = getAction("from-template");
    const result = await handler(
      { method: "post", payload: { template_id: "tpl_x" }, params: {} },
      {},
      makeContext()
    );
    const notice = result.notice as { type?: string } | undefined;
    expect(notice?.type).toBe("error");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BUG-7b: template-list — upstream failure masked as empty list
// ─────────────────────────────────────────────────────────────────────────────

describe("BUG-7b: template-list BFF handler — upstream failure must not be masked", () => {
  beforeEach(() => vi.clearAllMocks());

  it("upstream 200 with templates array → returns templates list", async () => {
    const tplData = { templates: [{ template_id: "t1", name: "GitHub", slug: "github" }] };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(tplData, true));
    const handler = getAction("template-list");
    const result = await handler(
      { method: "get", payload: {}, params: {} },
      {},
      makeContext()
    );
    // templates must be at top-level OR inside record.params
    const topLevel = result.templates as unknown[] | undefined;
    const fromParams = (result.record as { params?: { templates?: unknown[] } })?.params?.templates;
    const list = topLevel ?? fromParams;
    expect(Array.isArray(list), "templates should be an array on success").toBe(true);
    expect((list as unknown[]).length).toBeGreaterThan(0);
    // No error notice
    expect((result.notice as { type?: string } | undefined)?.type).not.toBe("error");
  });

  it("upstream non-2xx → returns error notice, NOT an empty templates list", async () => {
    // BUG: current code returns { record: { params: { templates: [] } } } on failure
    mockFetch.mockResolvedValueOnce(makeFetchResponse({ detail: "Forbidden" }, false, 403));
    const handler = getAction("template-list");
    const result = await handler(
      { method: "get", payload: {}, params: {} },
      {},
      makeContext()
    );
    const notice = result.notice as { type?: string; message?: string } | undefined;
    expect(notice?.type, "non-2xx upstream must produce error notice, not silent empty list").toBe("error");
    // The templates array must NOT silently be empty (it must not be present or must be null/undefined)
    const topLevel = result.templates as unknown[] | undefined;
    const fromParams = (result.record as { params?: { templates?: unknown[] } })?.params?.templates;
    // Either no templates key, or not an empty-list pretending to be success
    const list = topLevel ?? fromParams;
    // If list IS returned it must be empty AND there must be a notice (above assertion handles notice)
    // Key invariant: notice.type === "error" (already asserted above)
    // Belt-and-suspenders: list should be absent or empty when there's an error
    if (list !== undefined) {
      expect(Array.isArray(list)).toBe(true);
    }
  });

  it("upstream fetch throws (network error) → returns error notice", async () => {
    mockFetch.mockRejectedValueOnce(new Error("ECONNREFUSED"));
    const handler = getAction("template-list");
    const result = await handler(
      { method: "get", payload: {}, params: {} },
      {},
      makeContext()
    );
    const notice = result.notice as { type?: string } | undefined;
    expect(notice?.type, "network error must produce error notice").toBe("error");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BUG-16: field-name mismatch — auth_type / openapi_spec_url dropped on prefill
// ─────────────────────────────────────────────────────────────────────────────

describe("BUG-16: template-detail BFF — auth_type / openapi_spec_url field mapping", () => {
  beforeEach(() => vi.clearAllMocks());

  it("raw.auth_type is mapped to auth_scheme in the normalised template object", async () => {
    const rawTemplate = {
      slug: "stripe",
      name: "Stripe",
      display_name: "Stripe Payments",
      description: "Stripe API",
      base_url: "https://api.stripe.com",
      auth_type: "bearer",           // API returns auth_type, not auth_scheme
      openapi_spec_url: "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
      test_path: "/v1/charges",
    };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(rawTemplate, true));
    const handler = getAction("template-detail");
    const result = await handler(
      { method: "get", params: {}, payload: {}, query: { slug: "stripe" } },
      {},
      makeContext()
    );
    // The normalised template should carry auth_scheme (not auth_type)
    const tpl = (
      (result.template as Record<string, unknown> | undefined) ??
      (result.record as { params?: { template?: Record<string, unknown> } })?.params?.template
    );
    expect(tpl, "template object must be returned").toBeDefined();
    expect(
      (tpl as Record<string, unknown>)?.auth_scheme,
      "auth_scheme must be populated from raw.auth_type"
    ).toBe("bearer");
  });

  it("raw.openapi_spec_url is mapped to openapi_url in the normalised template object", async () => {
    const rawTemplate = {
      slug: "stripe",
      name: "Stripe",
      display_name: "Stripe Payments",
      description: "Stripe API",
      base_url: "https://api.stripe.com",
      auth_type: "bearer",
      openapi_spec_url: "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
    };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(rawTemplate, true));
    const handler = getAction("template-detail");
    const result = await handler(
      { method: "get", params: {}, payload: {}, query: { slug: "stripe" } },
      {},
      makeContext()
    );
    const tpl = (
      (result.template as Record<string, unknown> | undefined) ??
      (result.record as { params?: { template?: Record<string, unknown> } })?.params?.template
    );
    expect(
      (tpl as Record<string, unknown>)?.openapi_url,
      "openapi_url must be populated from raw.openapi_spec_url"
    ).toBe("https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json");
  });

  it("flat param 'template.auth_scheme' also carries the mapped value", async () => {
    const rawTemplate = {
      slug: "gh",
      name: "GitHub",
      display_name: "GitHub",
      description: "GitHub API",
      base_url: "https://api.github.com",
      auth_type: "token",
      openapi_spec_url: "https://example.com/gh.json",
    };
    mockFetch.mockResolvedValueOnce(makeFetchResponse(rawTemplate, true));
    const handler = getAction("template-detail");
    const result = await handler(
      { method: "get", params: {}, payload: {}, query: { slug: "gh" } },
      {},
      makeContext()
    );
    const flatParams = (result.record as { params?: Record<string, unknown> })?.params ?? {};
    expect(
      flatParams["template.auth_scheme"],
      "flat template.auth_scheme must be populated"
    ).toBe("token");
    expect(
      flatParams["template.openapi_url"],
      "flat template.openapi_url must be populated"
    ).toBe("https://example.com/gh.json");
  });

  it("source inspection: template-detail normalisation reads raw.auth_type", () => {
    // The services.ts normalisation block must reference raw.auth_type
    expect(servicesSrc).toMatch(/auth_scheme:\s*raw\.auth_type/);
  });

  it("source inspection: template-detail normalisation reads raw.openapi_spec_url", () => {
    expect(servicesSrc).toMatch(/openapi_url:\s*raw\.openapi_spec_url/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BUG-19: card highlight uses name fallback (must key off template_id only)
// ─────────────────────────────────────────────────────────────────────────────

describe("BUG-19: ServiceTemplatePicker — card highlight must use template_id only", () => {
  it("isSelected check does NOT include a name-based fallback", () => {
    // BUG: current code has:
    //   selectedTemplate?.template_id === tpl.template_id || selectedTemplate?.name === tpl.name
    // Fix: only compare template_id
    expect(
      pickerSrc,
      "card highlight must not fall back to name comparison"
    ).not.toMatch(/selectedTemplate\?\.name\s*===\s*tpl\.name/);
  });

  it("isSelected check uses template_id for comparison", () => {
    expect(
      pickerSrc,
      "card highlight must compare template_id"
    ).toContain("selectedTemplate?.template_id === tpl.template_id");
  });

  it("isSelected is a single condition (no || with name)", () => {
    // Extract the isSelected line and verify it only has one condition
    const match = pickerSrc.match(/const isSelected\s*=\s*([^\n;]+)/);
    expect(match, "isSelected assignment must exist").toBeTruthy();
    const condition = match![1];
    // Must not include a name fallback
    expect(condition).not.toContain("name");
    // Must include template_id
    expect(condition).toContain("template_id");
  });
});
