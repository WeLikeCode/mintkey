/**
 * Unit tests for budget-validate.ts — validateBudgetInput().
 *
 * TDD-first: these tests define expected behavior before the utility exists.
 *
 * Source: budget-management-ui spec; Requirements 2.4, 2.5.
 */

import { describe, it, expect } from "vitest";
import { validateBudgetInput } from "../../src/components/utils/budget-validate.js";

// ---------------------------------------------------------------------------
// Valid inputs
// ---------------------------------------------------------------------------

describe("validateBudgetInput — valid inputs", () => {
  it("accepts ceiling=1 with a valid period and default thresholds", () => {
    const result = validateBudgetInput(1, "daily", [50, 80, 100]);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it("accepts ceiling=1000 with hourly period and no thresholds", () => {
    const result = validateBudgetInput(1000, "hourly", []);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it("accepts all valid periods (hourly, daily, weekly, monthly)", () => {
    for (const period of ["hourly", "daily", "weekly", "monthly"] as const) {
      const result = validateBudgetInput(10, period, [50]);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    }
  });

  it("accepts threshold values at boundary: 1 and 100", () => {
    const result = validateBudgetInput(5, "weekly", [1, 100]);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it("accepts when both ceiling and period are undefined (no budget)", () => {
    const result = validateBudgetInput(undefined, undefined, []);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Invalid ceiling values (Requirement 2.4)
// ---------------------------------------------------------------------------

describe("validateBudgetInput — invalid ceiling (Req 2.4)", () => {
  it("rejects ceiling=0", () => {
    const result = validateBudgetInput(0, "daily", []);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects ceiling=-1", () => {
    const result = validateBudgetInput(-1, "daily", []);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects ceiling=1.5 (non-integer)", () => {
    const result = validateBudgetInput(1.5, "daily", []);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects ceiling=NaN", () => {
    const result = validateBudgetInput(NaN, "daily", []);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Invalid threshold values (Requirement 2.5)
// ---------------------------------------------------------------------------

describe("validateBudgetInput — invalid thresholds (Req 2.5)", () => {
  it("rejects threshold=0 (below minimum)", () => {
    const result = validateBudgetInput(10, "daily", [0]);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects threshold=101 (above maximum)", () => {
    const result = validateBudgetInput(10, "daily", [101]);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects threshold=-5 (negative)", () => {
    const result = validateBudgetInput(10, "daily", [-5]);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects threshold=50.5 (non-integer)", () => {
    const result = validateBudgetInput(10, "daily", [50.5]);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects when one threshold is valid and another invalid", () => {
    const result = validateBudgetInput(10, "daily", [50, 150]);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Ceiling + period co-dependency (Requirements 2.4, 2.5 — design constraint)
// ---------------------------------------------------------------------------

describe("validateBudgetInput — ceiling/period co-dependency", () => {
  it("rejects ceiling provided without period", () => {
    const result = validateBudgetInput(10, undefined, []);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("rejects period provided without ceiling", () => {
    const result = validateBudgetInput(undefined, "daily", []);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});
