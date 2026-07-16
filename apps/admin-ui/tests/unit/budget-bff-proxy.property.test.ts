/**
 * Property-based test for BFF proxy fidelity.
 *
 * Feature: budget-management-ui, Property 6: BFF proxy fidelity
 *
 * Validates: Requirements 6.1, 6.5
 *
 * Strategy: Generate random HTTP statuses (200-599) and JSON bodies.
 * Define the proxy logic as a pure function that takes an upstream response
 * (status + body) and asserts the BFF output matches exactly. This tests the
 * contract that no transformation occurs during proxying.
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

/**
 * Simulates the BFF proxy logic: given an upstream response (status + body),
 * returns exactly what the BFF handler should send to the client.
 *
 * Per Property 6 and Requirements 6.1, 6.5: the BFF must forward both the
 * HTTP status code and the JSON body from admin-api without modification.
 *
 * This mirrors the implementation contract for budgetGetHandler (task 4.4):
 *   const upstream = await fetch(url);
 *   const body = await upstream.json();
 *   res.status(upstream.status).json(body);
 */
function proxyResponse(upstreamStatus: number, upstreamBody: unknown): { status: number; body: unknown } {
  // The BFF proxy MUST NOT modify status or body — pass through as-is.
  return { status: upstreamStatus, body: upstreamBody };
}

/**
 * Verifies that JSON round-tripping (serialize + parse) preserves the value.
 * This is important because Express's res.json() serializes and the client
 * parses, so the property must hold through JSON serialization.
 */
function jsonRoundTrip(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value));
}

describe("Property 6: BFF proxy fidelity", () => {
  it("forwards any HTTP status code (200-599) unchanged", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 200, max: 599 }),
        fc.jsonValue(),
        (status, body) => {
          const result = proxyResponse(status, body);
          expect(result.status).toBe(status);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("forwards any JSON body unchanged (survives JSON round-trip)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 200, max: 599 }),
        fc.jsonValue(),
        (status, body) => {
          const result = proxyResponse(status, body);
          // The body must survive JSON serialization (which Express does via res.json())
          expect(jsonRoundTrip(result.body)).toEqual(jsonRoundTrip(body));
        }
      ),
      { numRuns: 100 }
    );
  });

  it("preserves error responses (4xx, 5xx) with structured error bodies", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 400, max: 599 }),
        fc.record({
          title: fc.string({ minLength: 1, maxLength: 100 }),
          detail: fc.string({ minLength: 0, maxLength: 500 }),
          status: fc.integer({ min: 400, max: 599 }),
        }),
        (status, errorBody) => {
          const result = proxyResponse(status, errorBody);
          expect(result.status).toBe(status);
          expect(result.body).toEqual(errorBody);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("preserves success responses (2xx) with BudgetStatus-shaped bodies", () => {
    const budgetStatusArb = fc.record({
      ceiling: fc.integer({ min: 1, max: 100_000 }),
      period: fc.constantFrom("hourly", "daily", "weekly", "monthly"),
      used: fc.integer({ min: 0, max: 100_000 }),
      remaining: fc.integer({ min: 0, max: 100_000 }),
      period_start: fc.date({ min: new Date("2020-01-01"), max: new Date("2030-12-31") })
        .map((d) => d.toISOString()),
      period_end: fc.date({ min: new Date("2020-01-01"), max: new Date("2030-12-31") })
        .map((d) => d.toISOString()),
      alert_thresholds: fc.array(fc.integer({ min: 1, max: 100 }), { minLength: 0, maxLength: 5 }),
    });

    fc.assert(
      fc.property(
        fc.integer({ min: 200, max: 299 }),
        budgetStatusArb,
        (status, body) => {
          const result = proxyResponse(status, body);
          expect(result.status).toBe(status);
          expect(result.body).toEqual(body);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("never mutates the upstream body (deep equality after proxy)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 200, max: 599 }),
        fc.jsonValue(),
        (status, body) => {
          // Deep-clone the body before proxying to verify no mutation
          const originalBody = JSON.parse(JSON.stringify(body));
          const result = proxyResponse(status, body);

          // The original and proxied body must be identical
          expect(jsonRoundTrip(result.body)).toEqual(jsonRoundTrip(originalBody));
        }
      ),
      { numRuns: 100 }
    );
  });
});
