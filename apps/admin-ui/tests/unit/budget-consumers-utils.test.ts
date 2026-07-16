/**
 * Unit tests for budget-consumers.utils.ts — filterConsumers() and isExhausted().
 *
 * TDD-first: these tests define expected behavior before the utility exists.
 *
 * Source: budget-consumers-dashboard spec; Requirements 5.1, 5.2, 5.3, 5.4, 6.1, 6.5, 8.1.
 */

import { describe, it, expect } from "vitest";
import {
  filterConsumers,
  isExhausted,
  type BudgetConsumerRecord,
  type FilterState,
} from "../../src/components/pages/budget-consumers.utils.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<BudgetConsumerRecord> = {}): BudgetConsumerRecord {
  return {
    permission_id: "perm_01J0000000000000000000000A",
    agent_id: "agent_01J0000000000000000000000B",
    agent_name: "TestAgent",
    service_id: "svc_01J0000000000000000000000C",
    service_name: "TestService",
    consumption_percentage: 50,
    used: 5,
    ceiling: 10,
    period: "daily",
    period_start: "2026-01-01T00:00:00Z",
    period_end: "2026-01-02T00:00:00Z",
    requests_last_30_min: 2,
    ...overrides,
  };
}

const noFilters: FilterState = { threshold: null, agentName: "", serviceName: "" };

// ---------------------------------------------------------------------------
// filterConsumers — threshold filter (Requirement 5.1)
// ---------------------------------------------------------------------------

describe("filterConsumers — threshold filter only (Req 5.1)", () => {
  it("shows rows with consumption_percentage > threshold", () => {
    const records = [
      makeRecord({ consumption_percentage: 90 }),
      makeRecord({ consumption_percentage: 80 }),
      makeRecord({ consumption_percentage: 50 }),
    ];
    const result = filterConsumers(records, { ...noFilters, threshold: 79 });
    expect(result).toHaveLength(2);
    expect(result[0].consumption_percentage).toBe(90);
    expect(result[1].consumption_percentage).toBe(80);
  });

  it("excludes rows with consumption_percentage == threshold", () => {
    const records = [makeRecord({ consumption_percentage: 80 })];
    const result = filterConsumers(records, { ...noFilters, threshold: 80 });
    expect(result).toHaveLength(0);
  });

  it("excludes rows with consumption_percentage < threshold", () => {
    const records = [makeRecord({ consumption_percentage: 30 })];
    const result = filterConsumers(records, { ...noFilters, threshold: 50 });
    expect(result).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// filterConsumers — agent name filter (Requirement 5.2)
// ---------------------------------------------------------------------------

describe("filterConsumers — agent name filter only (Req 5.2)", () => {
  it("shows rows where agent_name contains the filter value", () => {
    const records = [
      makeRecord({ agent_name: "DataProcessor" }),
      makeRecord({ agent_name: "ImageParser" }),
      makeRecord({ agent_name: "LogCleaner" }),
    ];
    const result = filterConsumers(records, { ...noFilters, agentName: "parser" });
    expect(result).toHaveLength(1);
    expect(result[0].agent_name).toBe("ImageParser");
  });

  it("matches case-insensitively", () => {
    const records = [makeRecord({ agent_name: "MyAgent" })];
    const result = filterConsumers(records, { ...noFilters, agentName: "MYAGENT" });
    expect(result).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// filterConsumers — service name filter (Requirement 5.3)
// ---------------------------------------------------------------------------

describe("filterConsumers — service name filter only (Req 5.3)", () => {
  it("shows rows where service_name contains the filter value", () => {
    const records = [
      makeRecord({ service_name: "Slack API" }),
      makeRecord({ service_name: "GitHub API" }),
      makeRecord({ service_name: "Jira" }),
    ];
    const result = filterConsumers(records, { ...noFilters, serviceName: "api" });
    expect(result).toHaveLength(2);
  });

  it("matches case-insensitively", () => {
    const records = [makeRecord({ service_name: "GitHub API" })];
    const result = filterConsumers(records, { ...noFilters, serviceName: "GITHUB" });
    expect(result).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// filterConsumers — all filters combined (Requirement 5.4)
// ---------------------------------------------------------------------------

describe("filterConsumers — all filters combined as logical AND (Req 5.4)", () => {
  it("only includes rows passing ALL active filters", () => {
    const records = [
      makeRecord({ agent_name: "Alpha", service_name: "Slack API", consumption_percentage: 90 }),
      makeRecord({ agent_name: "Alpha", service_name: "GitHub API", consumption_percentage: 90 }),
      makeRecord({ agent_name: "Beta", service_name: "Slack API", consumption_percentage: 90 }),
      makeRecord({ agent_name: "Alpha", service_name: "Slack API", consumption_percentage: 50 }),
    ];
    const result = filterConsumers(records, {
      threshold: 80,
      agentName: "alpha",
      serviceName: "slack",
    });
    // Only the first record passes all three filters
    expect(result).toHaveLength(1);
    expect(result[0].agent_name).toBe("Alpha");
    expect(result[0].service_name).toBe("Slack API");
    expect(result[0].consumption_percentage).toBe(90);
  });
});

// ---------------------------------------------------------------------------
// filterConsumers — case-insensitive matching (Requirements 5.2, 5.3)
// ---------------------------------------------------------------------------

describe("filterConsumers — case-insensitive matching (Reqs 5.2, 5.3)", () => {
  it("matches agent name regardless of case in filter or data", () => {
    const records = [makeRecord({ agent_name: "mYaGeNt" })];
    const result = filterConsumers(records, { ...noFilters, agentName: "MyAgent" });
    expect(result).toHaveLength(1);
  });

  it("matches service name regardless of case in filter or data", () => {
    const records = [makeRecord({ service_name: "sLaCk ApI" })];
    const result = filterConsumers(records, { ...noFilters, serviceName: "Slack API" });
    expect(result).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// filterConsumers — empty dataset and no active filters
// ---------------------------------------------------------------------------

describe("filterConsumers — edge cases", () => {
  it("returns empty array when given empty dataset", () => {
    const result = filterConsumers([], { threshold: 50, agentName: "x", serviceName: "y" });
    expect(result).toHaveLength(0);
  });

  it("returns all records when no filters are active", () => {
    const records = [
      makeRecord({ consumption_percentage: 10 }),
      makeRecord({ consumption_percentage: 99 }),
    ];
    const result = filterConsumers(records, noFilters);
    expect(result).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// isExhausted (Requirements 6.1, 6.5, 8.1)
// ---------------------------------------------------------------------------

describe("isExhausted (Reqs 6.1, 6.5, 8.1)", () => {
  it("returns true when used == ceiling", () => {
    const record = makeRecord({ used: 10, ceiling: 10 });
    expect(isExhausted(record)).toBe(true);
  });

  it("returns true when used > ceiling", () => {
    const record = makeRecord({ used: 15, ceiling: 10 });
    expect(isExhausted(record)).toBe(true);
  });

  it("returns false when used < ceiling", () => {
    const record = makeRecord({ used: 5, ceiling: 10 });
    expect(isExhausted(record)).toBe(false);
  });

  it("returns false at boundary ceiling - 1", () => {
    const record = makeRecord({ used: 9, ceiling: 10 });
    expect(isExhausted(record)).toBe(false);
  });
});
