/**
 * Tests for agent-secret grants surface (Chunk C6c).
 *
 * Covers:
 *   (a) Create-grant handler: calls apiWrite POST to
 *       /v1/tenants/{tid}/agent-secrets/{sid}/grants with {recipient_agent_id}
 *       + operatorOpts (signed-request).
 *   (b) Revoke handler: calls apiWrite DELETE to
 *       /v1/tenants/{tid}/agent-secrets/{sid}/grants/{grantId} + operatorOpts.
 *   (c) manageGrants GET handler: fetches grants list via session cookie and
 *       stashes metadata (recipient_agent_id, created_by, created_at) in the
 *       returned record's params._grants array; no secret value is involved.
 *   (d) manageGrants is registered as a record action on agent-secrets.
 *   (e) AgentSecretGrantsPanel component is registered in components/index.ts.
 *   (f) No console.log / logger logging of bodies in the resource or component.
 *
 * Source: Chunk C6c acceptance criteria.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "fs";
import * as path from "path";

// ── file paths ───────────────────────────────────────────────────────────────
const ROOT = path.resolve(new URL(".", import.meta.url).pathname, "..");
const RESOURCE_PATH = path.join(ROOT, "src/resources/agent-secrets.ts");
const GRANTS_PANEL_PATH = path.join(ROOT, "src/components/actions/AgentSecretGrantsPanel.tsx");
const INDEX_PATH = path.join(ROOT, "src/components/index.ts");

// ── mock signed-request ──────────────────────────────────────────────────────
vi.mock("../src/lib/signed-request.js", () => ({
  buildSignedRequest: vi.fn().mockResolvedValue("mock.jwt.token"),
  signedFetch: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({}),
  }),
}));

// ── source loaders ────────────────────────────────────────────────────────────
let resourceSrc: string;
let grantsPanelSrc: string;
let indexSrc: string;

function loadSources() {
  resourceSrc = fs.readFileSync(RESOURCE_PATH, "utf-8");
  grantsPanelSrc = fs.readFileSync(GRANTS_PANEL_PATH, "utf-8");
  indexSrc = fs.readFileSync(INDEX_PATH, "utf-8");
}

// ── structure: manageGrants action on agent-secrets ───────────────────────────
describe("AgentSecretsResource — manageGrants action structure (C6c)", () => {
  beforeEach(loadSources);

  it("agent-secrets.ts defines a manageGrants action", () => {
    expect(resourceSrc).toMatch(/manageGrants\s*:/);
  });

  it("manageGrants action is actionType 'record'", () => {
    const idx = resourceSrc.search(/manageGrants\s*:/);
    expect(idx).toBeGreaterThan(-1);
    const snippet = resourceSrc.slice(idx, idx + 200);
    expect(snippet).toContain("record");
  });

  it("manageGrants action uses AgentSecretGrantsPanel component", () => {
    const idx = resourceSrc.search(/manageGrants\s*:/);
    const snippet = resourceSrc.slice(idx, idx + 400);
    expect(snippet).toContain("AgentSecretGrantsPanel");
  });

  it("manageGrants action has a handler", () => {
    const idx = resourceSrc.search(/manageGrants\s*:/);
    const snippet = resourceSrc.slice(idx, idx + 2000);
    expect(snippet).toContain("handler");
  });

  it("manageGrants handler hits the /grants path on GET", () => {
    // The GET branch must fetch /agent-secrets/{id}/grants
    expect(resourceSrc).toMatch(/\/grants/);
  });
});

// ── integration: create-grant handler ────────────────────────────────────────
describe("AgentSecretsResource — manageGrants create handler (C6c-a)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("create-grant handler calls apiWrite POST to /v1/tenants/{tid}/agent-secrets/{sid}/grants with {recipient_agent_id}", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const manageGrants = (actions as Record<string, { handler?: Function }>).manageGrants;
    expect(manageGrants).toBeDefined();
    const handler = manageGrants?.handler;
    expect(handler).toBeDefined();

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "perm_01GRANT111111111111111111111",
        secret_id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
        recipient_agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA2",
        created_by: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
        created_at: "2026-06-14T00:00:00Z",
      }),
    });

    // Also mock the GET call for the grants list (handler fetches list after creation)
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: [
          {
            id: "perm_01GRANT111111111111111111111",
            secret_id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
            recipient_agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA2",
            created_by: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
            created_at: "2026-06-14T00:00:00Z",
          },
        ],
        next_cursor: null,
      }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await handler!(
      {
        method: "post",
        payload: {
          _action: "create",
          recipient_agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA2",
        },
        params: { recordId: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1" },
      },
      {},
      {
        currentAdmin: {
          operatorId: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
          tenantId: "tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1",
          sessionToken: "tok",
          csrfToken: "csrf",
        },
        record: {
          get: (key: string) => key === "id" ? "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1" : undefined,
          toJSON: () => ({ params: {}, errors: {} }),
        },
        resource: {
          build: async () => ({ toJSON: () => ({ params: {}, errors: {} }) }),
        },
      }
    );

    // signedFetch called for the POST grant creation
    expect(mockSignedFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockSignedFetch.mock.calls[0];
    expect(url).toContain("/v1/tenants/tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1/agent-secrets/secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1/grants");
    expect(opts.method).toBe("POST");
    const body = opts.body as Record<string, string>;
    expect(body.recipient_agent_id).toBe("agent_01AAAAAAAAAAAAAAAAAAAAAAAAA2");

    expect(result.notice?.type).toBe("success");
  });

  it("create-grant handler returns error notice on API failure", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).manageGrants?.handler;

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "Recipient agent not found" }),
    });

    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await handler!(
      {
        method: "post",
        payload: { _action: "create", recipient_agent_id: "agent_NOTEXIST" },
        params: { recordId: "secret_01AAA" },
      },
      {},
      {
        currentAdmin: {
          operatorId: "op_01AAA",
          tenantId: "tenant_01AAA",
          sessionToken: "tok",
          csrfToken: "csrf",
        },
        record: {
          get: (key: string) => key === "id" ? "secret_01AAA" : undefined,
          toJSON: () => ({ params: {}, errors: {} }),
        },
        resource: { build: async () => ({ toJSON: () => ({ params: {}, errors: {} }) }) },
      }
    );

    expect(result.notice?.type).toBe("error");
    expect(result.notice?.message).toContain("Recipient agent not found");
  });
});

// ── integration: revoke handler ───────────────────────────────────────────────
describe("AgentSecretsResource — manageGrants revoke handler (C6c-b)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("revoke handler calls apiWrite DELETE to /v1/tenants/{tid}/agent-secrets/{sid}/grants/{grantId}", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).manageGrants?.handler;
    expect(handler).toBeDefined();

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => { throw new Error("204 no body"); },
    });

    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await handler!(
      {
        method: "post",
        payload: {
          _action: "revoke",
          grant_id: "perm_01GRANT111111111111111111111",
        },
        params: { recordId: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1" },
      },
      {},
      {
        currentAdmin: {
          operatorId: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
          tenantId: "tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1",
          sessionToken: "tok",
          csrfToken: "csrf",
        },
        record: {
          get: (key: string) => key === "id" ? "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1" : undefined,
          toJSON: () => ({ params: {}, errors: {} }),
        },
        resource: { build: async () => ({ toJSON: () => ({ params: {}, errors: {} }) }) },
      }
    );

    expect(mockSignedFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockSignedFetch.mock.calls[0];
    expect(url).toContain(
      "/v1/tenants/tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1/agent-secrets/secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1/grants/perm_01GRANT111111111111111111111"
    );
    expect(opts.method).toBe("DELETE");

    expect(result.notice?.type).toBe("success");
  });

  it("revoke handler returns error notice on API failure", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).manageGrants?.handler;

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "Grant not found" }),
    });

    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await handler!(
      {
        method: "post",
        payload: { _action: "revoke", grant_id: "perm_NOTEXIST" },
        params: { recordId: "secret_01AAA" },
      },
      {},
      {
        currentAdmin: {
          operatorId: "op_01AAA",
          tenantId: "tenant_01AAA",
          sessionToken: "tok",
          csrfToken: "csrf",
        },
        record: {
          get: (key: string) => key === "id" ? "secret_01AAA" : undefined,
          toJSON: () => ({ params: {}, errors: {} }),
        },
        resource: { build: async () => ({ toJSON: () => ({ params: {}, errors: {} }) }) },
      }
    );

    expect(result.notice?.type).toBe("error");
  });
});

// ── integration: GET handler lists grants metadata ────────────────────────────
describe("AgentSecretsResource — manageGrants GET lists grants metadata (C6c-c)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("GET handler fetches grants and includes recipient_agent_id, created_by, created_at in record params", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).manageGrants?.handler;

    const grantsList = [
      {
        id: "perm_01GRANT111111111111111111111",
        secret_id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
        recipient_agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA2",
        created_by: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
        created_at: "2026-06-14T00:00:00Z",
      },
      {
        id: "perm_01GRANT222222222222222222222",
        secret_id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
        recipient_agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA3",
        created_by: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
        created_at: "2026-06-14T01:00:00Z",
      },
    ];

    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: grantsList, next_cursor: null }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await handler!(
      {
        method: "get",
        payload: {},
        params: { recordId: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1" },
      },
      {},
      {
        currentAdmin: {
          operatorId: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
          tenantId: "tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1",
          sessionToken: "tok",
          csrfToken: "csrf",
        },
        record: {
          get: (key: string) => key === "id" ? "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1" : undefined,
          toJSON: () => ({ params: {}, errors: {} }),
        },
        resource: { build: async () => ({ toJSON: () => ({ params: {}, errors: {} }) }) },
      }
    );

    // The list fetch goes via plain fetch (session cookie), not signedFetch
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain(
      "/v1/tenants/tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1/agent-secrets/secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1/grants"
    );

    // Result record params must include _grants with metadata
    const recordParams = result.record?.params ?? {};
    const grants = recordParams._grants as typeof grantsList;
    expect(Array.isArray(grants)).toBe(true);
    expect(grants).toHaveLength(2);
    expect(grants[0].recipient_agent_id).toBe("agent_01AAAAAAAAAAAAAAAAAAAAAAAAA2");
    expect(grants[0].created_by).toBe("op_01AAAAAAAAAAAAAAAAAAAAAAAAA1");
    expect(grants[0].created_at).toBe("2026-06-14T00:00:00Z");
    // No secret value in any grant
    for (const g of grants) {
      expect("value" in g).toBe(false);
    }
  });
});

// ── component registration ────────────────────────────────────────────────────
describe("AgentSecretGrantsPanel — registration (C6c-e)", () => {
  beforeEach(loadSources);

  it("AgentSecretGrantsPanel is registered in components/index.ts", () => {
    expect(indexSrc).toContain("AgentSecretGrantsPanel");
    expect(indexSrc).toContain("./actions/AgentSecretGrantsPanel");
  });

  it("AgentSecretGrantsPanel.tsx exports a default component", () => {
    expect(grantsPanelSrc).toContain("export default AgentSecretGrantsPanel");
  });

  it("AgentSecretGrantsPanel.tsx renders a recipient_agent_id input", () => {
    expect(grantsPanelSrc).toContain("recipient_agent_id");
  });

  it("AgentSecretGrantsPanel.tsx has a revoke action path", () => {
    expect(grantsPanelSrc).toMatch(/revoke|Revoke/);
  });

  it("AgentSecretGrantsPanel.tsx shows grant metadata: recipient_agent_id, created_by, created_at", () => {
    expect(grantsPanelSrc).toContain("recipient_agent_id");
    expect(grantsPanelSrc).toContain("created_by");
    expect(grantsPanelSrc).toContain("created_at");
  });
});

// ── no plaintext logging ──────────────────────────────────────────────────────
describe("C6c — no plaintext logging in resource or panel component", () => {
  beforeEach(loadSources);

  it("agent-secrets.ts manageGrants section has no console.log", () => {
    // Full file check — consistent with existing D13 tests
    expect(resourceSrc).not.toMatch(/console\.log/);
  });

  it("AgentSecretGrantsPanel.tsx has no console.log", () => {
    expect(grantsPanelSrc).not.toMatch(/console\.log/);
  });

  it("agent-secrets.ts does not log request body", () => {
    expect(resourceSrc).not.toMatch(/req\.body/);
  });

  it("AgentSecretGrantsPanel.tsx does not log recipient_agent_id", () => {
    expect(grantsPanelSrc).not.toMatch(/console\.\w+.*recipient/);
  });
});
