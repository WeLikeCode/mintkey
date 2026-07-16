/**
 * Property-based tests for filter composition and exhausted state.
 *
 * Feature: budget-consumers-dashboard, Tasks 4.3 + 4.4
 *
 * Property A — Filter composition (logical AND):
 *   Every record returned by filterConsumers passes all active filters.
 *   Every record excluded fails at least one active filter.
 *
 * Property B — Exhausted state:
 *   isExhausted returns true iff used >= ceiling (both non-null).
 *
 * Validates: Requirements 4.3, 4.4, 5.1, 5.2
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";
import {
  filterConsumers,
  isExhausted,
  type BudgetConsumerRecord,
  type FilterState,
} from "../../src/components/pages/budget-consumers.utils.js";

// ---------------------------------------------------------------------------
// Arbitrary generators
// ---------------------------------------------------------------------------

function arbitraryRecord(): fc.Arbitrary<BudgetConsumerRecord> {
  return fc.record<BudgetConsumerRecord>({
    permission_id: fc.string(),
    agent_id: fc.string(),
    agent_name: fc.string(),
    service_id: fc.string(),
    service_name: fc.string(),
    consumption_percentage: fc.option(fc.integer({ min: 0, max: 200 }), { nil: null }),
    ceiling: fc.option(fc.integer({ min: 1, max: 10000 }), { nil: null }),
    used: fc.option(fc.nat({ max: 10000 }), { nil: null }),
    period: fc.option(
      fc.constantFrom("hourly" as const, "daily" as const, "weekly" as const, "monthly" as const),
      { nil: null }
    ),
    period_start: fc.constant(null),
    period_end: fc.constant(null),
    requests_last_30_min: fc.nat(),
  });
}

const filterStateArb = fc.record<FilterState>({
  threshold: fc.option(fc.nat({ max: 100 }), { nil: null }),
  agentName: fc.string(),
  serviceName: fc.string(),
});

// ---------------------------------------------------------------------------
// Mirror of the filterConsumers predicate (used as ground truth in the property)
// ---------------------------------------------------------------------------

function passesFilter(r: BudgetConsumerRecord, filters: FilterState): boolean {
  const pct = r.consumption_percentage ?? 0;
  if (filters.threshold != null && pct <= filters.threshold) return false;
  if (
    filters.agentName &&
    !r.agent_name.toLowerCase().includes(filters.agentName.toLowerCase())
  )
    return false;
  if (
    filters.serviceName &&
    !r.service_name.toLowerCase().includes(filters.serviceName.toLowerCase())
  )
    return false;
  return true;
}

// ---------------------------------------------------------------------------
// Property A — Filter composition
// ---------------------------------------------------------------------------

describe("Property A: filterConsumers — logical AND composition", () => {
  it("every record returned passes all active filters", () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryRecord(), { maxLength: 20 }),
        filterStateArb,
        (records, filters) => {
          const result = filterConsumers(records, filters);
          for (const r of result) {
            expect(passesFilter(r, filters)).toBe(true);
          }
        }
      ),
      { numRuns: 200 }
    );
  });

  it("every record excluded fails at least one active filter", () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryRecord(), { maxLength: 20 }),
        filterStateArb,
        (records, filters) => {
          const included = new Set(filterConsumers(records, filters));
          for (const r of records) {
            if (!included.has(r)) {
              expect(passesFilter(r, filters)).toBe(false);
            }
          }
        }
      ),
      { numRuns: 200 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property B — Exhausted state
// ---------------------------------------------------------------------------

const baseRecord: BudgetConsumerRecord = {
  permission_id: "perm_test",
  agent_id: "agent_test",
  agent_name: "test-agent",
  service_id: "svc_test",
  service_name: "test-service",
  consumption_percentage: null,
  used: 0,
  ceiling: 1,
  period: null,
  period_start: null,
  period_end: null,
  requests_last_30_min: 0,
};

describe("Property B: isExhausted — exhausted iff used >= ceiling", () => {
  it("returns used >= ceiling for any non-null used and ceiling", () => {
    fc.assert(
      fc.property(
        fc.record({ used: fc.nat(), ceiling: fc.nat({ min: 1 }) }),
        ({ used, ceiling }) => {
          const result = isExhausted({ ...baseRecord, used, ceiling });
          expect(result).toBe(used >= ceiling);
        }
      ),
      { numRuns: 200 }
    );
  });

  it("returns false when ceiling is null", () => {
    expect(isExhausted({ ...baseRecord, ceiling: null, used: 5 })).toBe(false);
  });

  it("returns false when used is null", () => {
    expect(isExhausted({ ...baseRecord, ceiling: 5, used: null })).toBe(false);
  });
});
