/**
 * Property-based test for BFF URL construction from session.
 *
 * Feature: budget-management-ui, Property 7: BFF URL construction from session
 *
 * Validates: Requirements 6.4
 *
 * Strategy: Generate random valid tenantId strings and permId path parameters.
 * Define a pure URL construction function inline and verify the constructed
 * upstream URL contains `/v1/tenants/{tenantId}/agents/{agentId}/permissions/{permId}/budget`.
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

// Pure function under test — extracts the URL construction logic that the BFF
// handler will use to build the upstream admin-api URL.
function buildBudgetStatusUrl(
  baseUrl: string,
  tenantId: string,
  agentId: string,
  permId: string
): string {
  return `${baseUrl}/v1/tenants/${tenantId}/agents/${agentId}/permissions/${permId}/budget`;
}

describe("Property 7: BFF URL construction from session", () => {
  // Generator for ULID-prefixed IDs (matches mintkey's `prefix_<26 Crockford Base32 chars>` format)
  const crockfordBase32Char = fc.constantFrom(
    ..."0123456789ABCDEFGHJKMNPQRSTVWXYZ".split("")
  );
  const ulidBody = fc.array(crockfordBase32Char, { minLength: 26, maxLength: 26 })
    .map((chars) => chars.join(""));

  const tenantIdArb = ulidBody.map((body) => `tenant_${body}`);
  const agentIdArb = ulidBody.map((body) => `agent_${body}`);
  const permIdArb = ulidBody.map((body) => `perm_${body}`);

  const baseUrlArb = fc.constantFrom(
    "http://admin-api:8000",
    "http://localhost:8000",
    "https://api.internal.example.com"
  );

  it("constructed URL contains the expected path structure with all IDs", () => {
    fc.assert(
      fc.property(
        baseUrlArb,
        tenantIdArb,
        agentIdArb,
        permIdArb,
        (baseUrl, tenantId, agentId, permId) => {
          const url = buildBudgetStatusUrl(baseUrl, tenantId, agentId, permId);

          // Assert the URL contains the expected path structure
          expect(url).toContain(
            `/v1/tenants/${tenantId}/agents/${agentId}/permissions/${permId}/budget`
          );
        }
      ),
      { numRuns: 100 }
    );
  });

  it("constructed URL starts with the provided base URL", () => {
    fc.assert(
      fc.property(
        baseUrlArb,
        tenantIdArb,
        agentIdArb,
        permIdArb,
        (baseUrl, tenantId, agentId, permId) => {
          const url = buildBudgetStatusUrl(baseUrl, tenantId, agentId, permId);

          expect(url).toMatch(new RegExp(`^${baseUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
        }
      ),
      { numRuns: 100 }
    );
  });

  it("URL is parseable and path segments match the input IDs", () => {
    fc.assert(
      fc.property(
        baseUrlArb,
        tenantIdArb,
        agentIdArb,
        permIdArb,
        (baseUrl, tenantId, agentId, permId) => {
          const url = buildBudgetStatusUrl(baseUrl, tenantId, agentId, permId);
          const parsed = new URL(url);
          const segments = parsed.pathname.split("/").filter(Boolean);

          // Expected: ["v1", "tenants", <tenantId>, "agents", <agentId>, "permissions", <permId>, "budget"]
          expect(segments).toEqual([
            "v1",
            "tenants",
            tenantId,
            "agents",
            agentId,
            "permissions",
            permId,
            "budget",
          ]);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("each generated ID appears exactly once in the URL path", () => {
    fc.assert(
      fc.property(
        baseUrlArb,
        tenantIdArb,
        agentIdArb,
        permIdArb,
        (baseUrl, tenantId, agentId, permId) => {
          const url = buildBudgetStatusUrl(baseUrl, tenantId, agentId, permId);
          const path = new URL(url).pathname;

          // Each ID appears exactly once in the path
          const tenantMatches = path.split(tenantId).length - 1;
          const agentMatches = path.split(agentId).length - 1;
          const permMatches = path.split(permId).length - 1;

          expect(tenantMatches).toBe(1);
          expect(agentMatches).toBe(1);
          expect(permMatches).toBe(1);
        }
      ),
      { numRuns: 100 }
    );
  });
});
