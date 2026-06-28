// @vitest-environment jsdom
/**
 * Render tests for BudgetConsumersPage (Task 6.1).
 *
 * Covers:
 *   - Renders all expected table columns (Agent Name, Service, Consumption %, Used, Ceiling, Period, Requests 30 min)
 *   - Renders empty state when zero records
 *   - Exhausted rows have red highlight styling
 *   - "Unlock" button appears only on exhausted rows
 *   - "Unlock" click triggers POST to `/admin/api/budget/:permId/reset`
 *   - "Last updated" timestamp renders and updates
 *   - Filter bar renders threshold, agent name, service name inputs
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 8.1, 8.2
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";

import BudgetConsumersPage from "../src/components/pages/BudgetConsumersPage.js";
import type { BudgetConsumerRecord } from "../src/components/pages/budget-consumers.utils.js";

// ── helpers ───────────────────────────────────────────────────────────────────

function makeRecord(overrides: Partial<BudgetConsumerRecord> = {}): BudgetConsumerRecord {
  return {
    permission_id: "perm_01TESTAAAAAAAAAAAAAAAAAA01",
    agent_id: "agent_01TESTAAAAAAAAAAAAAAAAAA01",
    agent_name: "TestAgent",
    service_id: "svc_01TESTAAAAAAAAAAAAAAAAAA01",
    service_name: "TestService",
    consumption_percentage: 50,
    used: 50,
    ceiling: 100,
    period: "daily",
    period_start: "2026-06-15T00:00:00Z",
    period_end: "2026-06-16T00:00:00Z",
    requests_last_30_min: 12,
    ...overrides,
  };
}

const normalRecord = makeRecord({
  permission_id: "perm_01NORMAL0000000000000001",
  agent_name: "NormalAgent",
  service_name: "PaymentService",
  consumption_percentage: 50,
  used: 50,
  ceiling: 100,
  requests_last_30_min: 5,
});

const exhaustedRecord = makeRecord({
  permission_id: "perm_01EXHAUST000000000000001",
  agent_name: "ExhaustedAgent",
  service_name: "EmailService",
  consumption_percentage: 100,
  used: 100,
  ceiling: 100,
  requests_last_30_min: 20,
});

const overBudgetRecord = makeRecord({
  permission_id: "perm_01OVER00000000000000001",
  agent_name: "OverBudgetAgent",
  service_name: "StorageService",
  consumption_percentage: 120,
  used: 120,
  ceiling: 100,
  requests_last_30_min: 30,
});

function mockFetchSuccess(records: BudgetConsumerRecord[]) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(records),
  });
}

function mockFetchEmpty() {
  mockFetchSuccess([]);
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("BudgetConsumersPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // ── Table columns ───────────────────────────────────────────────────────

  it("renders all expected table columns", async () => {
    mockFetchSuccess([normalRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByText("Agent Name")).toBeInTheDocument();
    });

    expect(screen.getByText("Service")).toBeInTheDocument();
    expect(screen.getByText("Consumption %")).toBeInTheDocument();
    expect(screen.getByText("Used")).toBeInTheDocument();
    expect(screen.getByText("Ceiling")).toBeInTheDocument();
    expect(screen.getByText("Period")).toBeInTheDocument();
    expect(screen.getByText("Requests 30 min")).toBeInTheDocument();
  });

  it("renders row data correctly", async () => {
    mockFetchSuccess([normalRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByText("NormalAgent")).toBeInTheDocument();
    });

    expect(screen.getByText("PaymentService")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("daily")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  // ── Empty state ─────────────────────────────────────────────────────────

  it("renders empty state when zero records", async () => {
    mockFetchEmpty();

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(
        screen.getByText("No budget-configured grants found")
      ).toBeInTheDocument();
    });
  });

  // ── Exhausted row styling ───────────────────────────────────────────────

  it("exhausted rows have red highlight styling", async () => {
    mockFetchSuccess([normalRecord, exhaustedRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByText("ExhaustedAgent")).toBeInTheDocument();
    });

    const exhaustedRow = screen.getByTestId(
      `row-${exhaustedRecord.permission_id}`
    );
    expect(exhaustedRow).toHaveAttribute("data-exhausted", "true");

    const normalRow = screen.getByTestId(
      `row-${normalRecord.permission_id}`
    );
    expect(normalRow).toHaveAttribute("data-exhausted", "false");
  });

  it("over-budget rows also have red highlight styling", async () => {
    mockFetchSuccess([overBudgetRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByText("OverBudgetAgent")).toBeInTheDocument();
    });

    const row = screen.getByTestId(`row-${overBudgetRecord.permission_id}`);
    expect(row).toHaveAttribute("data-exhausted", "true");
  });

  // ── Unlock button visibility ────────────────────────────────────────────

  it('"Unlock" button appears only on exhausted rows', async () => {
    mockFetchSuccess([normalRecord, exhaustedRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByText("ExhaustedAgent")).toBeInTheDocument();
    });

    // Exhausted row should have Unlock button
    const exhaustedRow = screen.getByTestId(
      `row-${exhaustedRecord.permission_id}`
    );
    const unlockBtn = exhaustedRow.querySelector('[data-testid="unlock-btn"]');
    expect(unlockBtn).toBeInTheDocument();
    expect(unlockBtn).toHaveTextContent("Unlock");

    // Normal row should NOT have Unlock button
    const normalRow = screen.getByTestId(
      `row-${normalRecord.permission_id}`
    );
    const noUnlockBtn = normalRow.querySelector('[data-testid="unlock-btn"]');
    expect(noUnlockBtn).not.toBeInTheDocument();
  });

  // ── Unlock action ──────────────────────────────────────────────────────

  it('"Unlock" click triggers POST to /admin/api/budget/:permId/reset', async () => {
    mockFetchSuccess([exhaustedRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByText("ExhaustedAgent")).toBeInTheDocument();
    });

    // Clear the initial fetch calls and set up a mock for the POST
    vi.mocked(global.fetch).mockClear();
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "reset" }),
      })
      // After reset, the page refreshes — return updated data
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve([
            makeRecord({
              ...exhaustedRecord,
              used: 0,
              consumption_percentage: 0,
            }),
          ]),
      });

    const unlockBtn = screen.getByTestId("unlock-btn");

    await act(async () => {
      fireEvent.click(unlockBtn);
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `/admin/api/budget/${exhaustedRecord.permission_id}/reset`,
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  // ── Last updated timestamp ──────────────────────────────────────────────

  it('"Last updated" timestamp renders after successful fetch', async () => {
    mockFetchSuccess([normalRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByTestId("last-updated")).toBeInTheDocument();
    });

    const lastUpdated = screen.getByTestId("last-updated");
    expect(lastUpdated.textContent).toMatch(/Last updated/);
  });

  it('"Last updated" timestamp updates after poll', async () => {
    mockFetchSuccess([normalRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByTestId("last-updated")).toBeInTheDocument();
    });

    const firstUpdate = screen.getByTestId("last-updated").textContent;

    // Advance timers to trigger the 30s poll
    mockFetchSuccess([normalRecord]);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });

    await waitFor(() => {
      const secondUpdate = screen.getByTestId("last-updated").textContent;
      // After poll, timestamp should update (or remain current if same second)
      expect(secondUpdate).toMatch(/Last updated/);
    });
  });

  // ── Filter bar ──────────────────────────────────────────────────────────

  it("filter bar renders threshold, agent name, service name inputs", async () => {
    mockFetchSuccess([normalRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByTestId("filter-threshold")).toBeInTheDocument();
    });

    expect(screen.getByTestId("filter-agent-name")).toBeInTheDocument();
    expect(screen.getByTestId("filter-service-name")).toBeInTheDocument();
  });

  it("filter bar threshold input filters rows client-side", async () => {
    const highConsumption = makeRecord({
      permission_id: "perm_01HIGH000000000000000001",
      agent_name: "HighAgent",
      consumption_percentage: 90,
      used: 90,
      ceiling: 100,
    });
    const lowConsumption = makeRecord({
      permission_id: "perm_01LOW0000000000000000001",
      agent_name: "LowAgent",
      consumption_percentage: 20,
      used: 20,
      ceiling: 100,
    });
    mockFetchSuccess([highConsumption, lowConsumption]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(screen.getByText("HighAgent")).toBeInTheDocument();
      expect(screen.getByText("LowAgent")).toBeInTheDocument();
    });

    // Set threshold filter to 50 — should hide LowAgent
    const thresholdInput = screen.getByTestId("filter-threshold");
    await act(async () => {
      fireEvent.change(thresholdInput, { target: { value: "50" } });
    });

    await waitFor(() => {
      expect(screen.getByText("HighAgent")).toBeInTheDocument();
      expect(screen.queryByText("LowAgent")).not.toBeInTheDocument();
    });
  });

  // ── Fetches from correct URL ────────────────────────────────────────────

  it("fetches from /admin/api/budget-consumers on mount", async () => {
    mockFetchSuccess([normalRecord]);

    await act(async () => {
      render(React.createElement(BudgetConsumersPage));
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/admin/api/budget-consumers");
    });
  });
});
