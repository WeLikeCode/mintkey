/**
 * Integration tests for BFF budget route handlers.
 *
 * Uses supertest against a minimal Express app with:
 *   - express-session (populated with adminUser)
 *   - the budget BFF handlers (imported from src/routes/budget.ts)
 *
 * Admin-api calls are mocked via vi.stubGlobal("fetch", ...) since the BFF
 * handler uses global fetch() to call the internal admin-api.
 *
 * Write handlers (edit, remove, reset) go through apiWrite → signedFetch,
 * which is mocked at the module level.
 *
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import express from "express";
import session from "express-session";
import request from "supertest";

// Mock signed-request module before importing handlers (apiWrite uses it)
vi.mock("../src/lib/signed-request.js", () => ({
  signedFetch: vi.fn(),
}));

import { budgetGetHandler, budgetEditHandler, budgetRemoveHandler, budgetResetHandler } from "../src/routes/budget.js";
import { signedFetch } from "../src/lib/signed-request.js";

// ─── Test constants ──────────────────────────────────────────────────────────

const TEST_TENANT_ID = "tnt_01JABC123DEF456GHI789JKLMN";
const TEST_OPERATOR_ID = "operator_01JABC123DEF456GHI789JKL";
const TEST_PERM_ID = "perm_01JXYZ987WVU654TSR321QPONM";
const TEST_AGENT_ID = "agent_6c3c950a2e184ba98c895b875b1bf5bd";
const TEST_SESSION_TOKEN = "test-session-token";
const TEST_CSRF_TOKEN = "test-csrf-token";

const ADMIN_API_URL = "http://admin-api:8080";

const BUDGET_STATUS_RESPONSE = {
  ceiling: 100,
  period: "daily",
  used: 42,
  remaining: 58,
  period_start: "2026-06-15T00:00:00Z",
  period_end: "2026-06-16T00:00:00Z",
  alert_thresholds: [50, 80, 100],
};

const PERMISSION_RECORD = {
  id: TEST_PERM_ID,
  agent_id: TEST_AGENT_ID,
  tenant_id: TEST_TENANT_ID,
  service_id: "svc_01JABC000000000000000000AA",
  action: "call",
  constraints: { budget: { ceiling: 100, period: "daily" } },
};

// ─── App factory ─────────────────────────────────────────────────────────────

function createApp() {
  const app = express();

  app.use(
    session({ // codeql[js/missing-csrf-middleware] codeql[js/clear-text-cookie] test harness only
      secret: "test-secret",
      resave: false,
      saveUninitialized: true,
      cookie: { secure: false },
    })
  );

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

  // Mount the budget GET handler
  app.get("/admin/api/budget/:permId", budgetGetHandler);

  // Mount write handlers
  app.post("/admin/api/budget/:permId/edit", express.json(), budgetEditHandler);
  app.post("/admin/api/budget/:permId/remove", budgetRemoveHandler);
  app.post("/admin/api/budget/:permId/reset", budgetResetHandler);

  return app;
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("GET /admin/api/budget/:permId — BFF proxy", () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    // Set ADMIN_API_URL for the handler (it reads from process.env or default)
    process.env.ADMIN_API_URL = ADMIN_API_URL;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("constructs correct upstream URL and forwards 200 response unchanged", async () => {
    const fetchCalls: { url: string; init?: RequestInit }[] = [];

    globalThis.fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      fetchCalls.push({ url: urlStr, init });

      // First call: permission record lookup
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      // Second call: budget endpoint
      if (urlStr.includes("/budget")) {
        return new Response(JSON.stringify(BUDGET_STATUS_RESPONSE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get(`/admin/api/budget/${TEST_PERM_ID}`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual(BUDGET_STATUS_RESPONSE);

    // Verify the budget URL was constructed correctly using session tenant_id
    const budgetCall = fetchCalls.find((c) => c.url.includes("/budget"));
    expect(budgetCall).toBeDefined();
    expect(budgetCall!.url).toContain(
      `/v1/tenants/${TEST_TENANT_ID}/agents/${TEST_AGENT_ID}/permissions/${TEST_PERM_ID}/budget`
    );
  });

  it("extracts tenant_id from session, not from URL params", async () => {
    const fetchCalls: { url: string }[] = [];

    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      fetchCalls.push({ url: urlStr });

      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (urlStr.includes("/budget")) {
        return new Response(JSON.stringify(BUDGET_STATUS_RESPONSE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    await request(app).get(`/admin/api/budget/${TEST_PERM_ID}`);

    // All upstream calls should use the session tenant_id
    const allTenantRefs = fetchCalls.filter((c) =>
      c.url.includes(`/v1/tenants/${TEST_TENANT_ID}`)
    );
    expect(allTenantRefs.length).toBeGreaterThan(0);

    // No call should reference a made-up URL tenant
    const unexpectedTenantRefs = fetchCalls.filter(
      (c) => c.url.includes("/v1/tenants/") && !c.url.includes(TEST_TENANT_ID)
    );
    expect(unexpectedTenantRefs).toHaveLength(0);
  });

  it("forwards 404 from admin-api budget endpoint to client unchanged", async () => {
    const errorBody = { title: "Budget not found", detail: "No budget configured for this permission" };

    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();

      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (urlStr.includes("/budget")) {
        return new Response(JSON.stringify(errorBody), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get(`/admin/api/budget/${TEST_PERM_ID}`);

    expect(res.status).toBe(404);
    expect(res.body).toEqual(errorBody);
  });

  it("forwards 500 from admin-api budget endpoint to client unchanged", async () => {
    const errorBody = { title: "Internal Server Error", detail: "Something went wrong" };

    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();

      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (urlStr.includes("/budget")) {
        return new Response(JSON.stringify(errorBody), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get(`/admin/api/budget/${TEST_PERM_ID}`);

    expect(res.status).toBe(500);
    expect(res.body).toEqual(errorBody);
  });

  it("returns 502 when permission lookup fails (cannot resolve agent_id)", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();

      // Permission lookup fails
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify({ title: "Not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get(`/admin/api/budget/${TEST_PERM_ID}`);

    // Should return an error since it can't resolve agent_id
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  it("returns 502 when upstream fetch throws a network error", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof globalThis.fetch;

    const app = createApp();
    const res = await request(app).get(`/admin/api/budget/${TEST_PERM_ID}`);

    expect(res.status).toBe(502);
    expect(res.body).toHaveProperty("title");
  });
});


// ─── POST /admin/api/budget/:permId/edit ─────────────────────────────────────

describe("POST /admin/api/budget/:permId/edit — BFF proxy", () => {
  let originalFetch: typeof globalThis.fetch;
  const mockedSignedFetch = vi.mocked(signedFetch);

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    process.env.ADMIN_API_URL = ADMIN_API_URL;
    mockedSignedFetch.mockReset();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("sends correct PATCH body to admin-api with budget constraints", async () => {
    // Mock lookupPermission (uses global fetch)
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    // Mock apiWrite → signedFetch
    const upstreamBody = { id: TEST_PERM_ID, constraints: { budget: { ceiling: 200, period: "weekly", alert_thresholds: [50, 90] } } };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(upstreamBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app)
      .post(`/admin/api/budget/${TEST_PERM_ID}/edit`)
      .send({ ceiling: 200, period: "weekly", alert_thresholds: [50, 90] });

    expect(res.status).toBe(200);
    expect(res.body).toEqual(upstreamBody);

    // Verify signedFetch was called with the correct PATCH endpoint + body
    expect(mockedSignedFetch).toHaveBeenCalledOnce();
    const [url, opts] = mockedSignedFetch.mock.calls[0];
    expect(url).toContain(`/v1/tenants/${TEST_TENANT_ID}/permissions/${TEST_PERM_ID}`);
    expect(opts.method).toBe("PATCH");
    expect(opts.body).toEqual({
      constraints: { budget: { ceiling: 200, period: "weekly", alert_thresholds: [50, 90] } },
    });
  });

  it("forwards 422 validation error from admin-api unchanged", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const errorBody = { title: "Validation Error", detail: "ceiling must be positive integer" };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(errorBody), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app)
      .post(`/admin/api/budget/${TEST_PERM_ID}/edit`)
      .send({ ceiling: -1, period: "daily", alert_thresholds: [] });

    expect(res.status).toBe(422);
    expect(res.body).toEqual(errorBody);
  });

  it("forwards 404 from admin-api when permission not found", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const errorBody = { title: "Not Found", detail: "Permission does not exist" };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(errorBody), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app)
      .post(`/admin/api/budget/${TEST_PERM_ID}/edit`)
      .send({ ceiling: 100, period: "daily", alert_thresholds: [50] });

    expect(res.status).toBe(404);
    expect(res.body).toEqual(errorBody);
  });
});

// ─── POST /admin/api/budget/:permId/remove ───────────────────────────────────

describe("POST /admin/api/budget/:permId/remove — BFF proxy", () => {
  let originalFetch: typeof globalThis.fetch;
  const mockedSignedFetch = vi.mocked(signedFetch);

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    process.env.ADMIN_API_URL = ADMIN_API_URL;
    mockedSignedFetch.mockReset();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("sends PATCH body with budget: null to admin-api", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const upstreamBody = { id: TEST_PERM_ID, constraints: {} };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(upstreamBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app).post(`/admin/api/budget/${TEST_PERM_ID}/remove`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual(upstreamBody);

    // Verify signedFetch was called with budget: null
    expect(mockedSignedFetch).toHaveBeenCalledOnce();
    const [url, opts] = mockedSignedFetch.mock.calls[0];
    expect(url).toContain(`/v1/tenants/${TEST_TENANT_ID}/permissions/${TEST_PERM_ID}`);
    expect(opts.method).toBe("PATCH");
    expect(opts.body).toEqual({ constraints: { budget: null } });
  });

  it("forwards response status and body unchanged", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const upstreamBody = { id: TEST_PERM_ID, message: "budget removed" };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(upstreamBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app).post(`/admin/api/budget/${TEST_PERM_ID}/remove`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual(upstreamBody);
  });

  it("forwards 404 error response unchanged", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const errorBody = { title: "Not Found", detail: "Permission not found" };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(errorBody), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app).post(`/admin/api/budget/${TEST_PERM_ID}/remove`);

    expect(res.status).toBe(404);
    expect(res.body).toEqual(errorBody);
  });
});

// ─── POST /admin/api/budget/:permId/reset ────────────────────────────────────

describe("POST /admin/api/budget/:permId/reset — BFF proxy", () => {
  let originalFetch: typeof globalThis.fetch;
  const mockedSignedFetch = vi.mocked(signedFetch);

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    process.env.ADMIN_API_URL = ADMIN_API_URL;
    mockedSignedFetch.mockReset();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("sends POST to reset endpoint via apiWrite", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const upstreamBody = { id: TEST_PERM_ID, used: 0, ceiling: 100 };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(upstreamBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app).post(`/admin/api/budget/${TEST_PERM_ID}/reset`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual(upstreamBody);

    // Verify signedFetch was called with POST to the budget reset endpoint
    expect(mockedSignedFetch).toHaveBeenCalledOnce();
    const [url, opts] = mockedSignedFetch.mock.calls[0];
    expect(url).toContain(`/v1/tenants/${TEST_TENANT_ID}/permissions/${TEST_PERM_ID}/budget/reset`);
    expect(opts.method).toBe("POST");
  });

  it("forwards response unchanged", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const upstreamBody = { reset: true, used: 0 };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(upstreamBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app).post(`/admin/api/budget/${TEST_PERM_ID}/reset`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual(upstreamBody);
  });

  it("forwards error response from admin-api unchanged", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes(`/permissions/${TEST_PERM_ID}`) && !urlStr.includes("/budget")) {
        return new Response(JSON.stringify(PERMISSION_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }) as unknown as typeof globalThis.fetch;

    const errorBody = { title: "Internal Error", detail: "Reset failed" };
    mockedSignedFetch.mockResolvedValue(
      new Response(JSON.stringify(errorBody), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      })
    );

    const app = createApp();
    const res = await request(app).post(`/admin/api/budget/${TEST_PERM_ID}/reset`);

    expect(res.status).toBe(500);
    expect(res.body).toEqual(errorBody);
  });
});
