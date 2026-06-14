/**
 * Tests for agent-secrets resource — editValue (rotate) and delete record actions (Chunk C6b).
 *
 * Covers:
 *   (a) Rotate handler: calls apiWrite with PUT to /v1/tenants/{tid}/agent-secrets/{sid}
 *       and body {value, content_type} + operatorOpts.
 *   (b) Delete handler: calls apiWrite with DELETE to /v1/tenants/{tid}/agent-secrets/{sid}
 *       + operatorOpts; returns success notice.
 *   (c) editValue action is actionType "record" with a component registered.
 *   (d) delete action is actionType "record" with ConfirmAction component.
 *   (e) No console.log / logger of value/body in agent-secrets.ts or AgentSecretUpdateForm.tsx.
 *   (f) AgentSecretUpdateForm is registered in components/index.ts.
 *
 * Source: Chunk C6b acceptance criteria.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "fs";
import * as path from "path";

// ── file paths ──────────────────────────────────────────────────────────────
const ROOT = path.resolve(new URL(".", import.meta.url).pathname, "..");
const RESOURCE_PATH = path.join(ROOT, "src/resources/agent-secrets.ts");
const UPDATE_FORM_PATH = path.join(ROOT, "src/components/actions/AgentSecretUpdateForm.tsx");
const INDEX_PATH = path.join(ROOT, "src/components/index.ts");

// ── mock signed-request ─────────────────────────────────────────────────────
vi.mock("../src/lib/signed-request.js", () => ({
  buildSignedRequest: vi.fn().mockResolvedValue("mock.jwt.token"),
  signedFetch: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({}),
  }),
}));

// ── source loaders ──────────────────────────────────────────────────────────
let resourceSrc: string;
let updateFormSrc: string;
let indexSrc: string;

function loadSources() {
  resourceSrc = fs.readFileSync(RESOURCE_PATH, "utf-8");
  updateFormSrc = fs.readFileSync(UPDATE_FORM_PATH, "utf-8");
  indexSrc = fs.readFileSync(INDEX_PATH, "utf-8");
}

// ── resource action structure tests ─────────────────────────────────────────
describe("AgentSecretsResource — editValue (rotate) action structure (C6b)", () => {
  beforeEach(loadSources);

  it("editValue action is defined in agent-secrets.ts", () => {
    expect(resourceSrc).toMatch(/editValue\s*:/);
  });

  it("editValue action is actionType 'record'", () => {
    const idx = resourceSrc.search(/editValue\s*:/);
    expect(idx).toBeGreaterThan(-1);
    // The block after editValue: must contain actionType: "record"
    const snippet = resourceSrc.slice(idx, idx + 500);
    expect(snippet).toContain("record");
  });

  it("editValue action has a component (AgentSecretUpdateForm)", () => {
    expect(resourceSrc).toContain("AgentSecretUpdateForm");
  });

  it("editValue handler calls apiWrite with PUT method", () => {
    const idx = resourceSrc.search(/editValue\s*:/);
    const snippet = resourceSrc.slice(idx, idx + 2000);
    expect(snippet).toContain('"PUT"');
    expect(snippet).toContain("apiWrite");
  });

  it("editValue handler path includes /agent-secrets/ and uses recordId", () => {
    const idx = resourceSrc.search(/editValue\s*:/);
    const snippet = resourceSrc.slice(idx, idx + 2000);
    // Must use the secretId (recordId) in the path
    expect(snippet).toMatch(/agent-secrets.*secretId|secretId.*agent-secrets/);
  });
});

describe("AgentSecretsResource — delete action structure (C6b)", () => {
  beforeEach(loadSources);

  it("delete action is redefined as a record action (not isVisible:false)", () => {
    // The delete action must now be a record action with a handler, not just { isVisible: false }
    const idx = resourceSrc.search(/delete\s*:/);
    expect(idx).toBeGreaterThan(-1);
    const snippet = resourceSrc.slice(idx, idx + 500);
    // Must have a handler or component — not just isVisible: false
    expect(snippet).toMatch(/handler|component/);
  });

  it("delete action uses ConfirmAction component", () => {
    const idx = resourceSrc.search(/delete\s*:/);
    const snippet = resourceSrc.slice(idx, idx + 500);
    expect(snippet).toContain("ConfirmAction");
  });

  it("delete handler calls apiWrite with DELETE method", () => {
    const idx = resourceSrc.search(/delete\s*:/);
    const snippet = resourceSrc.slice(idx, idx + 2000);
    expect(snippet).toContain('"DELETE"');
    expect(snippet).toContain("apiWrite");
  });

  it("delete handler path includes /agent-secrets/ with secretId", () => {
    const idx = resourceSrc.search(/delete\s*:/);
    const snippet = resourceSrc.slice(idx, idx + 2000);
    expect(snippet).toMatch(/agent-secrets.*secretId|secretId.*agent-secrets/);
  });
});

// ── integration: rotate handler tests ─────────────────────────────────────
describe("AgentSecretsResource — editValue handler integration (C6b-a)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rotate handler calls apiWrite PUT to /v1/tenants/{tid}/agent-secrets/{sid} with {value, content_type}", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const editValue = (actions as Record<string, { handler?: Function }>).editValue;
    expect(editValue).toBeDefined();
    const handler = editValue?.handler;
    expect(handler).toBeDefined();

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "secret_01AAA", version: 2 }),
    });

    const result = await handler!(
      {
        method: "post",
        payload: {
          value: "new-secret-value",
          content_type: "application/json",
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

    // signedFetch must have been called once
    expect(mockSignedFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockSignedFetch.mock.calls[0];
    // URL must contain the tenant ID and the secret ID
    expect(url).toContain("/v1/tenants/tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1/agent-secrets/");
    expect(url).toContain("secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1");
    // Method must be PUT
    expect(opts.method).toBe("PUT");
    // Body must contain value and content_type
    const body = opts.body as Record<string, string>;
    expect(body.value).toBe("new-secret-value");
    expect(body.content_type).toBe("application/json");
    // operatorOpts must be used (signed-request path)
    expect(opts.sessionToken ?? opts.csrfToken).toBeTruthy();

    expect(result.notice?.type).toBe("success");
  });

  it("rotate handler returns error notice on API failure", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).editValue?.handler;

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "Secret not found" }),
    });

    const result = await handler!(
      {
        method: "post",
        payload: { value: "newval" },
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
    expect(result.notice?.message).toContain("Secret not found");
  });

  it("rotate handler GET returns record without side-effects", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).editValue?.handler;

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;

    await handler!(
      { method: "get", payload: {}, params: { recordId: "secret_01AAA" } },
      {},
      {
        currentAdmin: { operatorId: "op_01AAA", tenantId: "tenant_01AAA", sessionToken: "tok", csrfToken: "csrf" },
        record: {
          get: () => undefined,
          toJSON: () => ({ params: {}, errors: {} }),
        },
        resource: { build: async () => ({ toJSON: () => ({ params: {}, errors: {} }) }) },
      }
    );

    // GET must NOT call the API
    expect(mockSignedFetch).not.toHaveBeenCalled();
  });
});

// ── integration: delete handler tests ─────────────────────────────────────
describe("AgentSecretsResource — delete handler integration (C6b-c)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("delete handler calls apiWrite DELETE to /v1/tenants/{tid}/agent-secrets/{sid}", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const deleteAction = (actions as Record<string, { handler?: Function }>).delete;
    expect(deleteAction).toBeDefined();
    const handler = deleteAction?.handler;
    expect(handler).toBeDefined();

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: true,
      // DELETE returns 204 — no body
      json: async () => { throw new Error("no body"); },
    });

    const result = await handler!(
      {
        method: "post",
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

    expect(mockSignedFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockSignedFetch.mock.calls[0];
    expect(url).toContain("/v1/tenants/tenant_01AAAAAAAAAAAAAAAAAAAAAAAA1/agent-secrets/");
    expect(url).toContain("secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1");
    expect(opts.method).toBe("DELETE");

    expect(result.notice?.type).toBe("success");
  });

  it("delete handler returns error notice on API failure", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).delete?.handler;

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;
    mockSignedFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "Secret not found" }),
    });

    const result = await handler!(
      { method: "post", payload: {}, params: { recordId: "secret_01AAA" } },
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

  it("delete handler GET returns record without side-effects", async () => {
    const { AgentSecretsResource } = await import("../src/resources/agent-secrets.js");
    const actions = AgentSecretsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).delete?.handler;

    const { signedFetch } = await import("../src/lib/signed-request.js");
    const mockSignedFetch = signedFetch as ReturnType<typeof vi.fn>;

    await handler!(
      { method: "get", payload: {}, params: { recordId: "secret_01AAA" } },
      {},
      {
        currentAdmin: { operatorId: "op_01AAA", tenantId: "tenant_01AAA", sessionToken: "tok", csrfToken: "csrf" },
        record: {
          get: () => undefined,
          toJSON: () => ({ params: {}, errors: {} }),
        },
        resource: { build: async () => ({ toJSON: () => ({ params: {}, errors: {} }) }) },
      }
    );

    expect(mockSignedFetch).not.toHaveBeenCalled();
  });
});

// ── D13: no logging of secret value ─────────────────────────────────────────
describe("D13 — no plaintext logging in agent-secrets.ts or AgentSecretUpdateForm.tsx (C6b)", () => {
  beforeEach(loadSources);

  it("agent-secrets.ts has no console.log statements", () => {
    expect(resourceSrc).not.toMatch(/console\.log/);
  });

  it("agent-secrets.ts does not log req.body or value", () => {
    expect(resourceSrc).not.toMatch(/req\.body/);
    expect(resourceSrc).not.toMatch(/logger\s*\.\s*\w+\s*\(.*value/);
  });

  it("AgentSecretUpdateForm.tsx has no console.log statements", () => {
    expect(updateFormSrc).not.toMatch(/console\.log/);
  });

  it("AgentSecretUpdateForm.tsx does not log req.body or value", () => {
    expect(updateFormSrc).not.toMatch(/req\.body/);
    expect(updateFormSrc).not.toMatch(/JSON\.stringify.*value/);
  });
});

// ── component registration ────────────────────────────────────────────────
describe("AgentSecretUpdateForm — registration in components/index.ts (C6b)", () => {
  beforeEach(loadSources);

  it("AgentSecretUpdateForm is registered in components/index.ts", () => {
    expect(indexSrc).toContain("AgentSecretUpdateForm");
    expect(indexSrc).toContain("./actions/AgentSecretUpdateForm");
  });

  it("AgentSecretUpdateForm.tsx exports a default component", () => {
    expect(updateFormSrc).toContain("export default AgentSecretUpdateForm");
  });

  it("AgentSecretUpdateForm.tsx has a masked value input", () => {
    expect(updateFormSrc).toContain("password");
  });

  it("AgentSecretUpdateForm.tsx shows secret name read-only for context", () => {
    // The form should display the secret name in a read-only way
    expect(updateFormSrc).toMatch(/name|secret-name/);
  });

  it("AgentSecretUpdateForm.tsx implements reveal-once on success", () => {
    expect(updateFormSrc).toContain("reveal");
    // Should show typed value, not response value
    expect(updateFormSrc).toContain("typedValue");
  });
});
