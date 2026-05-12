/**
 * CHUNK 1: Dashboard tests — custom Mintkey onboarding dashboard.
 *
 * Tests verify:
 * - dashboardHandler returns counts shaped correctly
 * - Checklist items reflect DB state (mocked)
 * - Empty state when nothing exists
 *
 * Source: T-1.1.4; ADMIN_UI_SPEC.md §2.1; ADR-0013.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { dashboardHandler, type DashboardData } from "../src/dashboard.js";

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function makeFetchResponse(data: unknown, ok = true): Response {
  return {
    ok,
    json: async () => data,
    status: ok ? 200 : 500,
  } as unknown as Response;
}

describe("dashboardHandler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns zeroed counts when API returns empty lists", async () => {
    mockFetch.mockResolvedValue(makeFetchResponse({ services: [], agents: [], events: [] }));

    const result = await dashboardHandler(
      {} as never,
      {} as never,
      { currentAdmin: { tenantId: "tenant_test", email: "op@test.com" } } as never
    );

    const data = result as DashboardData;
    expect(data.servicesCount).toBe(0);
    expect(data.agentsCount).toBe(0);
    expect(data.permissionsCount).toBe(0);
    expect(data.auditCount24h).toBe(0);
  });

  it("returns correct counts from API data", async () => {
    mockFetch
      .mockResolvedValueOnce(makeFetchResponse({ services: [{ id: "s1" }, { id: "s2" }] }))
      .mockResolvedValueOnce(makeFetchResponse({ agents: [{ id: "a1" }] }))
      .mockResolvedValueOnce(makeFetchResponse({ permissions: [{ id: "p1" }, { id: "p2" }, { id: "p3" }] }))
      .mockResolvedValueOnce(makeFetchResponse({ events: [{ id: "e1" }, { id: "e2" }] }));

    const result = await dashboardHandler(
      {} as never,
      {} as never,
      { currentAdmin: { tenantId: "tenant_abc", email: "op@test.com" } } as never
    );

    const data = result as DashboardData;
    expect(data.servicesCount).toBe(2);
    expect(data.agentsCount).toBe(1);
    expect(data.permissionsCount).toBe(3);
    expect(data.auditCount24h).toBe(2);
  });

  it("checklist hasServices is true when services > 0", async () => {
    mockFetch
      .mockResolvedValueOnce(makeFetchResponse({ services: [{ id: "s1" }] }))
      .mockResolvedValueOnce(makeFetchResponse({ agents: [] }))
      .mockResolvedValueOnce(makeFetchResponse({ permissions: [] }))
      .mockResolvedValueOnce(makeFetchResponse({ events: [] }));

    const result = await dashboardHandler(
      {} as never,
      {} as never,
      { currentAdmin: { tenantId: "tenant_abc", email: "op@test.com" } } as never
    ) as DashboardData;

    expect(result.checklist.hasServices).toBe(true);
    expect(result.checklist.hasAgents).toBe(false);
    expect(result.checklist.hasPermissions).toBe(false);
  });

  it("checklist all false for empty state", async () => {
    mockFetch.mockResolvedValue(makeFetchResponse({ services: [], agents: [], permissions: [], events: [] }));

    const result = await dashboardHandler(
      {} as never,
      {} as never,
      { currentAdmin: { tenantId: "tenant_abc", email: "op@test.com" } } as never
    ) as DashboardData;

    expect(result.checklist.hasServices).toBe(false);
    expect(result.checklist.hasAgents).toBe(false);
    expect(result.checklist.hasPermissions).toBe(false);
    expect(result.checklist.hasCredentials).toBe(false);
  });

  it("includes email and tenantId from currentAdmin", async () => {
    mockFetch.mockResolvedValue(makeFetchResponse({ services: [], agents: [], permissions: [], events: [] }));

    const result = await dashboardHandler(
      {} as never,
      {} as never,
      { currentAdmin: { tenantId: "tenant_xyz", email: "operator@example.com" } } as never
    ) as DashboardData;

    expect(result.email).toBe("operator@example.com");
    expect(result.tenantId).toBe("tenant_xyz");
  });

  it("returns gracefully when API errors", async () => {
    mockFetch.mockRejectedValue(new Error("Network error"));

    const result = await dashboardHandler(
      {} as never,
      {} as never,
      { currentAdmin: { tenantId: "tenant_abc", email: "op@test.com" } } as never
    ) as DashboardData;

    // Should not throw — returns zero counts
    expect(result.servicesCount).toBe(0);
    expect(result.agentsCount).toBe(0);
  });
});
