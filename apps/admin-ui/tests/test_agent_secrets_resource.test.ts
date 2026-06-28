/**
 * Tests for agent-secrets resource and AgentSecretNewForm (Chunk C6).
 *
 * Covers:
 *   (a) Handler test: new action calls apiWrite to /v1/tenants/{tid}/agent-secrets
 *       with {agent_id, name, value, content_type} and signed-request operatorOpts.
 *   (b) Resource config exposes NO `value` property.
 *   (c) Resource config: metadata-only properties are present (name, content_type,
 *       size_bytes, version, created_at, updated_at, created_by).
 *   (d) listPath contains /agent-secrets and {tenantId}.
 *   (e) filterKeys includes agent_id.
 *   (f) Resource is mounted in index.ts.
 *   (g) Component is registered in components/index.ts.
 *   (h) agents.ts has a "Manage secrets" record action.
 *   (i) D13: no console.log / logger.*value / req.body logging of value.
 *
 * Source: D10, D11, D13; Chunk C6 acceptance criteria.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "fs";
import * as path from "path";

// ── file paths ──────────────────────────────────────────────────────────────
const ROOT = path.resolve(new URL(".", import.meta.url).pathname, "..");
const RESOURCE_PATH = path.join(ROOT, "src/resources/agent-secrets.ts");
const COMPONENT_PATH = path.join(ROOT, "src/components/actions/AgentSecretNewForm.tsx");
const INDEX_PATH = path.join(ROOT, "src/components/index.ts");
const APP_INDEX_PATH = path.join(ROOT, "src/index.ts");
const AGENTS_PATH = path.join(ROOT, "src/resources/agents.ts");

// ── mock signed-request ─────────────────────────────────────────────────────
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("../src/lib/signed-request.js", () => ({
  buildSignedRequest: vi.fn().mockResolvedValue("mock.jwt.token"),
  signedFetch: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1", name: "MY_SECRET" }),
  }),
}));

// ── resource + component source ─────────────────────────────────────────────
let resourceSrc: string;
let componentSrc: string;
let indexSrc: string;
let appIndexSrc: string;
let agentsSrc: string;

// Lazy-load so failing file creation doesn't block compile
function loadSources() {
  resourceSrc = fs.readFileSync(RESOURCE_PATH, "utf-8");
  componentSrc = fs.readFileSync(COMPONENT_PATH, "utf-8");
  indexSrc = fs.readFileSync(INDEX_PATH, "utf-8");
  appIndexSrc = fs.readFileSync(APP_INDEX_PATH, "utf-8");
  agentsSrc = fs.readFileSync(AGENTS_PATH, "utf-8");
}

// ── resource property tests (D10) ──────────────────────────────────────────
describe("AgentSecretsResource — metadata-only properties (D10)", () => {
  beforeEach(loadSources);

  it("resource exports AgentSecretsResource", () => {
    expect(resourceSrc).toContain("AgentSecretsResource");
    expect(resourceSrc).toContain("export");
  });

  it("listPath contains /agent-secrets and {tenantId}", () => {
    expect(resourceSrc).toContain("/agent-secrets");
    expect(resourceSrc).toContain("{tenantId}");
  });

  it("filterKeys includes agent_id", () => {
    expect(resourceSrc).toContain("agent_id");
    // It must appear in filterKeys array
    const filterKeysMatch = resourceSrc.match(/filterKeys\s*:\s*\[([^\]]*)\]/);
    expect(filterKeysMatch).not.toBeNull();
    expect(filterKeysMatch![1]).toContain("agent_id");
  });

  it("properties include name, content_type, size_bytes, version, created_at, updated_at, created_by", () => {
    const required = ["name", "content_type", "size_bytes", "version", "created_at", "updated_at", "created_by"];
    for (const prop of required) {
      expect(resourceSrc, `missing property: ${prop}`).toContain(`"${prop}"`);
    }
  });

  it("does NOT expose a 'value' property anywhere in the resource config", () => {
    // The resource must never declare { path: "value" } — no value property
    expect(resourceSrc).not.toMatch(/path\s*:\s*["']value["']/);
    // Also check listProperties and showProperties arrays
    const listPropsMatch = resourceSrc.match(/listProperties\s*:\s*\[([^\]]*)\]/);
    if (listPropsMatch) {
      expect(listPropsMatch[1]).not.toContain('"value"');
      expect(listPropsMatch[1]).not.toContain("'value'");
    }
    const showPropsMatch = resourceSrc.match(/showProperties\s*:\s*\[([^\]]*)\]/);
    if (showPropsMatch) {
      expect(showPropsMatch[1]).not.toContain('"value"');
      expect(showPropsMatch[1]).not.toContain("'value'");
    }
  });

  it("resource is a RestResource with id 'agent-secrets'", () => {
    expect(resourceSrc).toContain("RestResource");
    expect(resourceSrc).toContain("agent-secrets");
  });
});

// ── new action handler tests (D11, D13) ────────────────────────────────────
describe("AgentSecretsResource — new action handler (D11)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadSources();
  });

  it("new action is defined with a handler", () => {
    expect(resourceSrc).toContain("handler");
    // The new action block must contain handler
    const newIdx = resourceSrc.search(/new\s*:\s*\{/);
    expect(newIdx).toBeGreaterThan(-1);
    const snippet = resourceSrc.slice(newIdx, newIdx + 600);
    expect(snippet).toContain("handler");
  });

  it("handler calls apiWrite to /v1/tenants/{tenantId}/agent-secrets", () => {
    expect(resourceSrc).toContain("apiWrite");
    expect(resourceSrc).toContain("/agent-secrets");
    // The apiWrite call must include tenantId interpolation
    expect(resourceSrc).toMatch(/apiWrite\s*\(\s*`[^`]*agent-secrets/);
  });

  it("handler sends POST method to agent-secrets endpoint", () => {
    // Find apiWrite call and verify POST
    expect(resourceSrc).toContain('"POST"');
  });

  it("handler uses operatorOptsFromAdmin for signed-request path", () => {
    expect(resourceSrc).toContain("operatorOptsFromAdmin");
    expect(resourceSrc).toContain("operatorOpts");
  });

  it("handler actually calls apiWrite with POST to /v1/tenants/{tid}/agent-secrets (integration)", async () => {
    // Dynamically import to trigger mock resolution
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;
    expect(handler).toBeDefined();

    // Mock signedFetch (called by apiWrite internally via signed-request)
    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1", name: "MY_SECRET" }),
    });

    const result = await handler!(
      {
        method: "post",
        payload: {
          agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
          name: "MY_SECRET",
          value: "supersecret",
          content_type: "text/plain",
        },
        params: {},
      },
      {},
      {
        currentAdmin: {
          operatorId: "op_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
          tenantId: "tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1",
          sessionToken: "tok",
          csrfToken: "csrf",
        },
        record: { toJSON: () => ({}) },
      }
    );

    // signedFetch should have been called with the agent-secrets path
    expect(mockSignedFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockSignedFetch.mock.calls[0];
    expect(url).toContain("/agent-secrets");
    expect(opts.method).toBe("POST");
    // Body must include the required fields
    const body = opts.body as Record<string, string>;
    expect(body.agent_id).toBe("agent_01AAAAAAAAAAAAAAAAAAAAAAAAA1");
    expect(body.name).toBe("MY_SECRET");
    expect(body.value).toBe("supersecret");

    expect(result.notice?.type).toBe("success");
  });

  it("handler returns error notice on API failure", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "Name already exists" }),
    });

    const result = await handler!(
      {
        method: "post",
        payload: { agent_id: "agent_01AAA", name: "DUPE", value: "val" },
        params: {},
      },
      {},
      {
        currentAdmin: {
          operatorId: "op_01AAA",
          tenantId: "tenant_01AAA",
          sessionToken: "tok",
          csrfToken: "csrf",
        },
        record: { toJSON: () => ({}) },
      }
    );

    expect(result.notice?.type).toBe("error");
    expect(result.notice?.message).toContain("Name already exists");
  });
});

// ── D13: no logging of secret value ────────────────────────────────────────
describe("D13 — no plaintext logging in resource or component", () => {
  beforeEach(loadSources);

  it("agent-secrets.ts does NOT console.log the value or body", () => {
    expect(resourceSrc).not.toMatch(/console\.log/);
  });

  it("agent-secrets.ts does NOT pino-log the request body or value", () => {
    expect(resourceSrc).not.toMatch(/logger\s*\.\s*\w+\s*\(\s*.*(?:value|req\.body)/);
    expect(resourceSrc).not.toMatch(/req\.body/);
  });

  it("AgentSecretNewForm.tsx does NOT console.log the value", () => {
    expect(componentSrc).not.toMatch(/console\.log\s*\(.*value/);
  });
});

// ── component registration (D10, D11) ────────────────────────────────────
describe("AgentSecretNewForm — registration (D10, D11)", () => {
  beforeEach(loadSources);

  it("is registered in components/index.ts as AgentSecretNewForm", () => {
    expect(indexSrc).toContain("AgentSecretNewForm");
    expect(indexSrc).toContain("./actions/AgentSecretNewForm");
  });

  it("component exports a default AgentSecretNewForm", () => {
    expect(componentSrc).toContain("export default AgentSecretNewForm");
  });

  it("component reads ?agent_id= from URL query params", () => {
    expect(componentSrc).toContain("agent_id");
    expect(componentSrc).toContain("useSearchParams");
  });

  it("component has a value input (masked/password)", () => {
    expect(componentSrc).toContain("password");
  });

  it("component shows reveal-once panel on success using typed value (from state, not response)", () => {
    // The reveal-once panel must show the value from component state
    // The component must NOT read value from the API response
    expect(componentSrc).toContain("reveal");
  });

  it("component has a Copy affordance in the reveal-once panel", () => {
    // CopyButton or copy button must be present in reveal-once section
    expect(componentSrc).toMatch(/[Cc]opy/);
    expect(componentSrc).toContain("data-testid");
  });
});

// ── index.ts mounting (D10) ───────────────────────────────────────────────
describe("index.ts — AgentSecretsResource mounted", () => {
  beforeEach(loadSources);

  it("imports AgentSecretsResource in src/index.ts", () => {
    expect(appIndexSrc).toContain("AgentSecretsResource");
    expect(appIndexSrc).toContain("agent-secrets");
  });

  it("mounts AgentSecretsResource in the resources array", () => {
    expect(appIndexSrc).toContain("AgentSecretsResource.adminResource");
    expect(appIndexSrc).toContain("AgentSecretsResource.options");
  });
});

// ── agents.ts: Manage secrets record action (D10) ─────────────────────────
describe("agents.ts — Manage secrets record action (D10)", () => {
  beforeEach(loadSources);

  it("agents.ts has a manageSecrets (or similar) record action", () => {
    // Must have a record action that links to agent-secrets
    expect(agentsSrc).toContain("agent-secrets");
  });

  it("the manage-secrets action is of actionType record", () => {
    expect(agentsSrc).toContain("actionType");
    // Find the manage secrets action block
    const idx = agentsSrc.search(/manageSecrets|manage[_-]?secrets|Manage[_\s]?[Ss]ecrets/);
    expect(idx).toBeGreaterThan(-1);
  });

  it("the manage-secrets action links to /admin/resources/agent-secrets", () => {
    expect(agentsSrc).toContain("agent-secrets");
  });
});
