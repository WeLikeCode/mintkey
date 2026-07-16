/**
 * Property-based test for BFF URL construction + proxy fidelity.
 *
 * Feature: budget-consumers-dashboard, Properties 3 & 4
 *
 * Property 3 — URL construction: For any non-empty tenantId string the BFF
 *   handler must fetch a URL ending with /v1/tenants/{tenantId}/budget-consumers.
 *
 * Property 4 — Proxy fidelity: For any upstream HTTP status (200-599) and any
 *   JSON-serializable body, the handler must forward both unchanged to the caller.
 *
 * Validates: Requirements 3.1, 3.3, 3.4
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import fc from "fast-check";
import type { Request, Response } from "express";

import { budgetConsumersHandler } from "../../src/routes/budget-consumers.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal Express-like res mock that tracks status + send/json calls. */
function makeMockRes() {
  const mockSend = vi.fn();
  const mockJson = vi.fn();
  const mockType = vi.fn().mockReturnValue({ send: mockSend });
  const mockStatus = vi.fn().mockReturnValue({ type: mockType, json: mockJson });
  return { res: { status: mockStatus } as unknown as Response, mockStatus, mockSend, mockType, mockJson };
}

/** Minimal Express-like req with a session containing the given tenantId. */
function makeMockReq(tenantId: string) {
  return {
    session: { adminUser: { tenantId } },
    headers: { cookie: "" },
  } as unknown as Request;
}

// ---------------------------------------------------------------------------

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Property 3 — URL construction
// ---------------------------------------------------------------------------

describe("Property 3: BFF URL construction", () => {
  it("fetch URL ends with /v1/tenants/{tenantId}/budget-consumers for any tenantId", async () => {
    const mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);

    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 36 }),
        async (tenantId) => {
          let capturedUrl = "";

          mockFetch.mockImplementationOnce((url: string) => {
            capturedUrl = url;
            return Promise.resolve({
              status: 200,
              text: () => Promise.resolve("{}"),
            });
          });

          const { res } = makeMockRes();
          await budgetConsumersHandler(makeMockReq(tenantId), res);

          expect(capturedUrl).toMatch(`/v1/tenants/${tenantId}/budget-consumers`);
        }
      ),
      { numRuns: 50 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4 — Proxy fidelity
// ---------------------------------------------------------------------------

describe("Property 4: BFF proxy fidelity", () => {
  it("res.status() receives upstream status and res.send() receives upstream body text unchanged", async () => {
    const mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);

    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 200, max: 599 }),
        fc.jsonValue(),
        async (statusCode, bodyObj) => {
          const bodyString = JSON.stringify(bodyObj);

          mockFetch.mockImplementationOnce(() =>
            Promise.resolve({
              status: statusCode,
              text: () => Promise.resolve(bodyString),
            })
          );

          const { res, mockStatus, mockSend } = makeMockRes();
          await budgetConsumersHandler(makeMockReq("tenant_TEST"), res);

          expect(mockStatus).toHaveBeenCalledWith(statusCode);
          expect(mockSend).toHaveBeenCalledWith(bodyString);
        }
      ),
      { numRuns: 50 }
    );
  });
});
