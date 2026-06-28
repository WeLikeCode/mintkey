/**
 * Unit tests for budget-format.ts — formatPeriod().
 *
 * TDD-first: these tests define expected behavior before the utility exists.
 *
 * Source: budget-management-ui spec; Requirements 1.3.
 */

import { describe, it, expect } from "vitest";
import { formatPeriod } from "../../src/components/utils/budget-format.js";

// ---------------------------------------------------------------------------
// 1. Daily period with simple date
// ---------------------------------------------------------------------------

describe("formatPeriod — daily period", () => {
  it("formats a daily period with simple dates", () => {
    const result = formatPeriod(
      "daily",
      "2026-06-15T00:00:00Z",
      "2026-06-16T00:00:00Z"
    );

    expect(result).toContain("Daily:");
    expect(result).toContain("Jun 15, 2026");
    expect(result).toContain("Jun 16, 2026");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 2. Hourly period (shows hours)
// ---------------------------------------------------------------------------

describe("formatPeriod — hourly period", () => {
  it("formats an hourly period showing hours", () => {
    const result = formatPeriod(
      "hourly",
      "2026-06-15T14:00:00Z",
      "2026-06-15T15:00:00Z"
    );

    expect(result).toContain("Hourly:");
    expect(result).toContain("14:00");
    expect(result).toContain("15:00");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 3. Weekly period spanning multiple days
// ---------------------------------------------------------------------------

describe("formatPeriod — weekly period", () => {
  it("formats a weekly period spanning multiple days", () => {
    const result = formatPeriod(
      "weekly",
      "2026-06-15T00:00:00Z",
      "2026-06-22T00:00:00Z"
    );

    expect(result).toContain("Weekly:");
    expect(result).toContain("Jun 15, 2026");
    expect(result).toContain("Jun 22, 2026");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 4. Monthly period (shows month start to next month)
// ---------------------------------------------------------------------------

describe("formatPeriod — monthly period", () => {
  it("formats a monthly period from month start to next month", () => {
    const result = formatPeriod(
      "monthly",
      "2026-06-01T00:00:00Z",
      "2026-07-01T00:00:00Z"
    );

    expect(result).toContain("Monthly:");
    expect(result).toContain("Jun 1, 2026");
    expect(result).toContain("Jul 1, 2026");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 5. Midnight boundaries (00:00:00Z)
// ---------------------------------------------------------------------------

describe("formatPeriod — midnight boundaries", () => {
  it("correctly shows 00:00 UTC for midnight timestamps", () => {
    const result = formatPeriod(
      "daily",
      "2026-06-15T00:00:00Z",
      "2026-06-16T00:00:00Z"
    );

    expect(result).toContain("00:00");
    expect(result).toContain("UTC");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 6. Month transition (Jan 31 → Feb 1)
// ---------------------------------------------------------------------------

describe("formatPeriod — month transition", () => {
  it("formats correctly across Jan 31 to Feb 1 boundary", () => {
    const result = formatPeriod(
      "daily",
      "2026-01-31T00:00:00Z",
      "2026-02-01T00:00:00Z"
    );

    expect(result).toContain("Daily:");
    expect(result).toContain("Jan 31, 2026");
    expect(result).toContain("Feb 1, 2026");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 7. Year boundary (Dec → Jan next year)
// ---------------------------------------------------------------------------

describe("formatPeriod — year boundary", () => {
  it("formats correctly across Dec to Jan year boundary", () => {
    const result = formatPeriod(
      "monthly",
      "2026-12-01T00:00:00Z",
      "2027-01-01T00:00:00Z"
    );

    expect(result).toContain("Monthly:");
    expect(result).toContain("Dec 1, 2026");
    expect(result).toContain("Jan 1, 2027");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 8. Same-day period (hourly: 14:00-15:00)
// ---------------------------------------------------------------------------

describe("formatPeriod — same-day period", () => {
  it("formats an hourly same-day period showing both hours", () => {
    const result = formatPeriod(
      "hourly",
      "2026-06-15T14:00:00Z",
      "2026-06-15T15:00:00Z"
    );

    expect(result).toContain("Hourly:");
    expect(result).toContain("Jun 15, 2026");
    expect(result).toContain("14:00");
    expect(result).toContain("15:00");
    expect(result.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// General output format contract
// ---------------------------------------------------------------------------

describe("formatPeriod — output format contract", () => {
  it("output contains the period type (capitalized) followed by colon", () => {
    const periods = ["hourly", "daily", "weekly", "monthly"] as const;
    const expected = ["Hourly:", "Daily:", "Weekly:", "Monthly:"];

    periods.forEach((period, i) => {
      const result = formatPeriod(
        period,
        "2026-06-15T00:00:00Z",
        "2026-06-16T00:00:00Z"
      );
      expect(result).toContain(expected[i]);
    });
  });

  it("output contains both start and end dates in human-readable format", () => {
    const result = formatPeriod(
      "daily",
      "2026-06-15T00:00:00Z",
      "2026-06-16T00:00:00Z"
    );

    // Should contain month abbreviation, day, year, time, and UTC indicator
    expect(result).toMatch(/Jun\s+15,?\s+2026/);
    expect(result).toMatch(/Jun\s+16,?\s+2026/);
    expect(result).toContain("UTC");
  });

  it("output is non-empty for all valid period types", () => {
    const periods = ["hourly", "daily", "weekly", "monthly"] as const;

    periods.forEach((period) => {
      const result = formatPeriod(
        period,
        "2026-06-15T00:00:00Z",
        "2026-06-16T00:00:00Z"
      );
      expect(result).not.toBe("");
      expect(result.length).toBeGreaterThan(0);
    });
  });
});
