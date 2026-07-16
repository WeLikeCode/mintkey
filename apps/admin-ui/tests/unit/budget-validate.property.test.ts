/**
 * Property-based test for validateBudgetInput.
 *
 * Feature: budget-management-ui, Property 5: Budget validation rejects all invalid inputs
 *
 * Validates: Requirements 2.4, 2.5
 *
 * Strategy: Generate random invalid ceilings (zero, negative, float, NaN, non-numeric)
 * and thresholds outside [1,100]. Assert { valid: false } with non-empty errors array for all.
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { validateBudgetInput } from "../../src/components/utils/budget-validate.js";

describe("Property 5: Budget validation rejects all invalid inputs", () => {
  // --- Invalid ceiling generators ---

  const zeroCeiling = fc.constant(0);
  const negativeCeiling = fc.integer({ max: -1 });
  const floatCeiling = fc.double({ min: 0.01, max: 1000, noNaN: true }).filter(
    (n) => !Number.isInteger(n)
  );
  const nanCeiling = fc.constant(NaN);
  const nonNumericCeiling = fc.oneof(
    fc.string().filter((s) => s.length > 0 && isNaN(Number(s))),
    fc.constant(undefined),
    fc.constant(null),
    fc.constant(true),
    fc.constant(false),
    fc.constant([]),
    fc.constant({})
  );

  const invalidCeiling = fc.oneof(
    zeroCeiling,
    negativeCeiling,
    floatCeiling,
    nanCeiling,
    nonNumericCeiling
  );

  // --- Invalid threshold generators ---

  const thresholdTooLow = fc.integer({ max: 0 });
  const thresholdTooHigh = fc.integer({ min: 101 });
  const thresholdFloat = fc.double({ min: 1, max: 100, noNaN: true }).filter(
    (n) => !Number.isInteger(n)
  );
  const thresholdNaN = fc.constant(NaN);
  const thresholdNonNumeric = fc.oneof(
    fc.string().filter((s) => s.length > 0 && isNaN(Number(s))),
    fc.constant(null),
    fc.constant(undefined)
  );

  const invalidThreshold = fc.oneof(
    thresholdTooLow,
    thresholdTooHigh,
    thresholdFloat,
    thresholdNaN,
    thresholdNonNumeric
  );

  // Valid helpers for combining with invalid parts
  const validPeriod = fc.constantFrom("hourly", "daily", "weekly", "monthly");
  const validCeiling = fc.integer({ min: 1, max: 100_000 });
  const validThreshold = fc.integer({ min: 1, max: 100 });

  it("rejects any invalid ceiling with a valid period and valid thresholds", () => {
    fc.assert(
      fc.property(
        invalidCeiling,
        validPeriod,
        fc.array(validThreshold, { minLength: 0, maxLength: 5 }),
        (ceiling, period, thresholds) => {
          const result = validateBudgetInput(ceiling, period, thresholds);
          expect(result.valid).toBe(false);
          expect(result.errors.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("rejects any array containing at least one invalid threshold with a valid ceiling and period", () => {
    fc.assert(
      fc.property(
        validCeiling,
        validPeriod,
        fc.array(validThreshold, { minLength: 0, maxLength: 4 }),
        invalidThreshold,
        (ceiling, period, validThresholds, badThreshold) => {
          // Insert the invalid threshold at a random position
          const thresholds = [...validThresholds, badThreshold];
          const result = validateBudgetInput(ceiling, period, thresholds);
          expect(result.valid).toBe(false);
          expect(result.errors.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("rejects when both ceiling is invalid AND thresholds contain invalid values", () => {
    fc.assert(
      fc.property(
        invalidCeiling,
        validPeriod,
        fc.array(invalidThreshold, { minLength: 1, maxLength: 5 }),
        (ceiling, period, thresholds) => {
          const result = validateBudgetInput(ceiling, period, thresholds);
          expect(result.valid).toBe(false);
          expect(result.errors.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});
