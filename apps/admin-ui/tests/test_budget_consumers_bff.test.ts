/**
 * Integration tests for BFF budget-consumers route handler.
 *
 * Uses supertest against a minimal Express app with:
 *   - express-session (populated with adminUser)
 *   - the budgetConsumersHandler (imported from src/routes/budget-consumers.ts)
 *
 * Admin-api calls are mocked via vi.stubGlobal("fetch", ...) since the BFF
 * handler uses global fetch() to call the internal admin-api.
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import express from "express";
import session from "express-session";
import request from "supertest";

import { budgetConsumersHandler } from "../src/routes/budget-consumers.js";

// ─── Test constants ──────────────────────────────────────────────────────────

const TEST_TENANT_ID = "tnt_01JABC123DEF456GHI789JKLMN";
const TEST_OPERATOR_ID = "operator_01JABC123DEF456GHI789JKL";
const TEST_SESSION_TOKEN = "test-session-token";
const TEST_CSRF_TOKEN = "test-csrf-token";

const ADMIN_API_URL = "http://admin-api:8080";

const BUDGET_CONSUMERS_RESPONSE = [
  {
    permission_id: "perm_01JXYZ987WVU654TSR321QPONM",
    agent_id: "agent_6c3c950a2e184ba98c895b875b1bf5bd",
    agent_name: "Data Collector",
    service_id: "svc_01JABC000000000000000000AA",
    service_name: "Weather API",
    consumption_percentage: 85,
    used: 85,
    ceiling: 100,
    period: "daily",
    period_start: "2026-06-15T00:00:00Z",
    period_end: "2026-06-16T00:00:00Z",
    requests_last_30_min: 12,
  },
  {
    permission_id: "perm_01JABC000000000000000000BB",
    agent_id: "agent_7d4d060b3f295cb09d906c986c2cg6ce",
    agent_name: "Report Generator",
    service_id: "svc_01JABC000000000000000000CC",
    service_name: "Slack API",
    consumption_percentage: 42,
    used: 42,
    ceiling: 100,
    period: "weekly",
    period_start: "2026-06-10T00:00:00Z",
    period_end: "2026-06-17T00:00:00Z",
    requests_last_30_min: 3,
  },
];

// ─── App factory ─────────────────────────────────────────────────────────────

function createApp(options?: { noSession?: boolean }) {
  const app = express();

  app.use(
    session({ // codeql[js/missing-token-validation] codeql[js/clear-text-cookie] test harness only
      secret: "test-secret",
      resave: false,
      saveUninitialized: true,
      cookie: { secure: false },
    })
  );

  if (!options?.noSession) {
    // Inject session data (simulates requireSession having populated adminUser)
    app.use((req, _res, next) => {
      req.session.adminUser = {
        email: "admin@test.dev",
        operatorId: TEST_OPERATOR_ID,
        tenantId: TEST_TENANT_ID,
        isPlatformAdmin: false,
        sessionToken: TEST_SESSION_TOKEN,
        csrfToken: TEST_CSRF_TOKEN,
      };
      next();
    });
  }

  // Mount the budget-consumers GET handler
  app.get("/admin/api/budget-consumers", budgetConsumersHandler);

  return app;
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("GET /admin/api/budget-consumers — BFF proxy", () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    process.env.MINTKEY_ADMIN_API_URL = ADMIN_API_URL;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    delete process.env.MINTKEY_ADMIN_API_URL;
    vi.restoreAllMocks();
  });

  it("proxies correctly with tenant from session — constructs correct upstream URL", async () => {
    const fetchCalls: { url: string; init?: RequestInit }[] = [];

    globalThis.fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      fetchCalls.push({ url: urlStr, init });

      return new Response(JSON.stringify(BUDGET_CONSUMERS_RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(200);
    expect(res.body).toEqual(BUDGET_CONSUMERS_RESPONSE);

    // Verify the upstream URL was constructed using session tenant_id
    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0].url).toBe(
      `${ADMIN_API_URL}/v1/tenants/${TEST_TENANT_ID}/budget-consumers`
    );
  });

  it("returns 401 without valid session", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("Should not be called");
    }) as unknown as typeof globalThis.fetch;

    const app = createApp({ noSession: true });
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(401);
    expect(res.body).toHaveProperty("title", "Unauthorized");
    expect(res.body).toHaveProperty("detail");
  });

  it("returns 502 when admin-api is unreachable (network error)", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(502);
    expect(res.body).toHaveProperty("title");
    expect(res.body.detail).toContain("ECONNREFUSED");
  });

  it("forwards 200 status and JSON body unchanged (proxy fidelity)", async () => {
    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify(BUDGET_CONSUMERS_RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(200);
    expect(res.body).toEqual(BUDGET_CONSUMERS_RESPONSE);
  });

  it("forwards 404 from admin-api unchanged", async () => {
    const errorBody = { title: "Not Found", detail: "Tenant has no budget consumers" };

    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify(errorBody), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(404);
    expect(res.body).toEqual(errorBody);
  });

  it("forwards 500 from admin-api unchanged", async () => {
    const errorBody = { title: "Internal Server Error", detail: "Database connection failed" };

    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify(errorBody), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(500);
    expect(res.body).toEqual(errorBody);
  });

  it("forwards JSON body unchanged (complex payload)", async () => {
    const complexBody = [
      {
        permission_id: "perm_01JXYZ987WVU654TSR321QPONM",
        agent_id: "agent_6c3c950a2e184ba98c895b875b1bf5bd",
        agent_name: "Agent With Special Chars: <>&",
        service_id: "svc_01JABC000000000000000000AA",
        service_name: "Service/With/Slashes",
        consumption_percentage: 100,
        used: 200,
        ceiling: 200,
        period: "hourly",
        period_start: null,
        period_end: null,
        requests_last_30_min: 0,
      },
    ];

    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify(complexBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(200);
    expect(res.body).toEqual(complexBody);
  });

  it("forwards empty array response unchanged", async () => {
    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get("/admin/api/budget-consumers");

    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it("forwards cookie header to admin-api for auth passthrough", async () => {
    let capturedHeaders: Record<string, string> = {};

    globalThis.fetch = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      const headers = init?.headers as Record<string, string> | undefined;
      if (headers) {
        capturedHeaders = { ...headers };
      }
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    await request(app)
      .get("/admin/api/budget-consumers")
      .set("Cookie", "mintkey_session=abc123");

    // The handler should forward the cookie header
    expect(capturedHeaders.Cookie || capturedHeaders.cookie).toContain("mintkey_session");
  });
});
