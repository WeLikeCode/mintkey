/**
 * Req 23.5 — credential_hint pre-population for oauth2_password_grant templates.
 *
 * Criterion (verbatim, requirements.md §23.5):
 * "WHEN an operator instantiates the Azure Dashboard API template, THE Admin_API
 * SHALL pre-populate the credential structure with the correct token_url, field
 * names, and token_response_path so the operator only needs to supply the actual
 * username and password values."
 *
 * BFF contract (services.ts "from-template" handler): when admin-api responds 2xx
 * with credential_hint, the BFF must pass it through to the UI (the hint must appear
 * in service.credential_hint or record.params.credential_hint).
 *
 * UI contract (ServiceTemplatePicker.tsx): when selectedTemplate carries a
 * credential_hint with token_url, the detail panel must render a
 * data-testid="credential-hint-panel" element so the operator can see the
 * expected credential structure before submitting.
 *
 * Environment: node (no jsdom). Handler tests use direct invocation + mocked
 * global fetch. Source-inspection tests use fs.readFileSync.
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
// BFF: from-template handler passes credential_hint through to the UI
// ─────────────────────────────────────────────────────────────────────────────

describe("Req 23.5 — from-template BFF: credential_hint pass-through", () => {
  beforeEach(() => vi.clearAllMocks());

  it("when admin-api returns credential_hint, BFF passes it through in service object", async () => {
    const hint = {
      token_url: "https://dashboard-api-ps-prod.azurewebsites.net/api/auth/login",
      credential_fields: { username: "(your username)", password: "(your password)" },
      token_response_path: "$.token",
    };
    mockFetch.mockResolvedValueOnce(
      makeFetchResponse(
        {
          id: "svc_azure123",
          name: "azure-dashboard-api",
          auth_scheme: "oauth2_password_grant",
          credential_hint: hint,
        },
        true,
        201
      )
    );

    const handler = getAction("from-template");
    const result = await handler(
      { method: "post", payload: { template_id: "azure-dashboard-api" }, params: {} },
      {},
      makeContext()
    );

    // BFF must forward credential_hint — either on service or record.params
    const service = result.service as Record<string, unknown> | undefined;
    const paramsHint = (result.record as { params?: Record<string, unknown> })?.params
      ?.credential_hint;
    const hint_out = service?.credential_hint ?? paramsHint;

    expect(hint_out, "credential_hint must be forwarded by the BFF from-template handler").toBeDefined();
    expect(hint_out).not.toBeNull();
    const h = hint_out as Record<string, unknown>;
    expect(h.token_url).toBe("https://dashboard-api-ps-prod.azurewebsites.net/api/auth/login");
    expect(typeof h.credential_fields).toBe("object");
    const fields = h.credential_fields as Record<string, string>;
    expect(fields.username).toBeDefined();
    expect(fields.password).toBeDefined();
    expect(h.token_response_path).toBe("$.token");
  });

  it("when admin-api response has no credential_hint, BFF still succeeds (non-oauth2 templates)", async () => {
    mockFetch.mockResolvedValueOnce(
      makeFetchResponse(
        { id: "svc_stripe99", name: "stripe", auth_scheme: "bearer_token" },
        true,
        201
      )
    );
    const handler = getAction("from-template");
    const result = await handler(
      { method: "post", payload: { template_id: "stripe" }, params: {} },
      {},
      makeContext()
    );
    // No error notice — BFF must handle absence of credential_hint gracefully
    const notice = result.notice as { type?: string } | undefined;
    expect(notice?.type).not.toBe("error");
    const service = result.service as { id?: string } | undefined;
    expect(service?.id).toBe("svc_stripe99");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// UI: ServiceTemplatePicker renders credential-hint-panel for oauth2 templates
// ─────────────────────────────────────────────────────────────────────────────

describe("Req 23.5 — ServiceTemplatePicker: credential_hint panel in detail view", () => {
  it("source renders data-testid='credential-hint-panel' when credential_hint has token_url", () => {
    // The detail panel in ServiceTemplatePicker must conditionally render a
    // credential-hint-panel when the selected template carries an oauth2 credential_hint.
    expect(
      pickerSrc,
      "ServiceTemplatePicker must render a 'credential-hint-panel' when credential_hint.token_url is present"
    ).toMatch(/credential-hint-panel/);
  });

  it("source references credential_hint.token_url for conditional rendering", () => {
    // The component must gate the panel on credential_hint?.token_url presence
    expect(
      pickerSrc,
      "ServiceTemplatePicker must check credential_hint?.token_url (or similar) to gate rendering"
    ).toMatch(/credential_hint/);
  });

  it("source does not persist or submit credential_hint values as real credentials", () => {
    // The from-template submit payload must NOT include credential_hint field values
    // (only template_id + overrides). This ensures no placeholder is persisted.
    expect(
      servicesSrc,
      "from-template submit body must not include credential_hint in the POST payload"
    ).not.toMatch(/payload.*credential_hint/);
  });
});
