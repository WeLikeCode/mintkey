/**
 * Property-based test for formatPeriod.
 *
 * Feature: budget-management-ui, Property 2: Period formatter produces valid output
 *
 * Validates: Requirements 1.3
 *
 * Strategy: Generate random valid period strings and ISO 8601 UTC timestamps.
 * Assert non-empty string containing period type and both date representations.
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { formatPeriod } from "../../src/components/utils/budget-format.js";

describe("Property 2: Period formatter produces valid output", () => {
  // Valid period types per the design document
  const validPeriod = fc.constantFrom("hourly", "daily", "weekly", "monthly");

  // Generate random valid ISO 8601 UTC timestamps using fc.date()
  const validIsoTimestamp = fc
    .date({
      min: new Date("2000-01-01T00:00:00Z"),
      max: new Date("2099-12-31T23:59:59Z"),
    })
    .map((d) => d.toISOString());

  it("returns a non-empty string for any valid period, periodStart, and periodEnd", () => {
    fc.assert(
      fc.property(
        validPeriod,
        validIsoTimestamp,
        validIsoTimestamp,
        (period, periodStart, periodEnd) => {
          const result = formatPeriod(period, periodStart, periodEnd);
          expect(typeof result).toBe("string");
          expect(result.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("contains the period type (case-insensitive) in the output", () => {
    fc.assert(
      fc.property(
        validPeriod,
        validIsoTimestamp,
        validIsoTimestamp,
        (period, periodStart, periodEnd) => {
          const result = formatPeriod(period, periodStart, periodEnd);
          expect(result.toLowerCase()).toContain(period.toLowerCase());
        }
      ),
      { numRuns: 100 }
    );
  });

  it("produces output with reasonable length (> 10 chars)", () => {
    fc.assert(
      fc.property(
        validPeriod,
        validIsoTimestamp,
        validIsoTimestamp,
        (period, periodStart, periodEnd) => {
          const result = formatPeriod(period, periodStart, periodEnd);
          expect(result.length).toBeGreaterThan(10);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("contains date representations for both periodStart and periodEnd", () => {
    fc.assert(
      fc.property(
        validPeriod,
        validIsoTimestamp,
        validIsoTimestamp,
        (period, periodStart, periodEnd) => {
          const result = formatPeriod(period, periodStart, periodEnd);

          // The output should contain the year from periodStart
          const startDate = new Date(periodStart);
          const endDate = new Date(periodEnd);

          expect(result).toContain(String(startDate.getUTCFullYear()));
          expect(result).toContain(String(endDate.getUTCFullYear()));
        }
      ),
      { numRuns: 100 }
    );
  });
});
