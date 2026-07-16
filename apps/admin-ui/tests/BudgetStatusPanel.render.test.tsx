// @vitest-environment jsdom
/**
 * Render tests for BudgetStatusPanel (Task 6.1).
 *
 * Covers:
 *   - Renders progress bar with correct percentage (used/ceiling)
 *   - Renders threshold markers at correct positions
 *   - Renders period info via formatPeriod
 *   - Exhaustion state (used >= ceiling) shows red indicator
 *   - Empty state when API returns 404 ("No budget configured")
 *   - Error state when API returns 5xx
 *   - Action buttons rendered (Edit, Reset, Remove)
 *
 * Requirements: 1.2, 1.3, 1.4, 1.5, 1.6
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";

import BudgetStatusPanel from "../src/components/sections/BudgetStatusPanel.js";

// ── helpers ───────────────────────────────────────────────────────────────────

const PERM_ID = "perm_01TESTAAAAAAAAAAAAAAAAAAA1";

const defaultRecord = {
  id: PERM_ID,
  params: { id: PERM_ID },
};

const budgetResponse = {
  ceiling: 100,
  period: "daily",
  used: 42,
  remaining: 58,
  period_start: "2026-06-15T00:00:00Z",
  period_end: "2026-06-16T00:00:00Z",
  alert_thresholds: [50, 80, 100],
};

function mockFetchSuccess(body: unknown, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

function mockFetchError(status: number) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: () => Promise.resolve({ detail: "error" }),
  });
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("BudgetStatusPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── Progress bar percentage ─────────────────────────────────────────────

  it("renders progress bar with correct percentage (used/ceiling)", async () => {
    mockFetchSuccess(budgetResponse);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-progress-bar")).toBeInTheDocument();
    });

    const progressBar = screen.getByTestId("budget-progress-bar");
    expect(progressBar).toHaveAttribute("data-percentage", "42");

    // Percentage label
    expect(screen.getByTestId("budget-percentage-label")).toHaveTextContent("42%");

    // Usage text
    expect(screen.getByTestId("budget-usage-text")).toHaveTextContent("42 / 100");
  });

  // ── Threshold markers ───────────────────────────────────────────────────

  it("renders threshold markers at correct positions", async () => {
    mockFetchSuccess(budgetResponse);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-progress-bar")).toBeInTheDocument();
    });

    const markers = screen.getAllByTestId(/^budget-threshold-marker-/);
    expect(markers).toHaveLength(3);

    expect(screen.getByTestId("budget-threshold-marker-50")).toHaveStyle({ left: "50%" });
    expect(screen.getByTestId("budget-threshold-marker-80")).toHaveStyle({ left: "80%" });
    expect(screen.getByTestId("budget-threshold-marker-100")).toHaveStyle({ left: "100%" });
  });

  // ── Period info ─────────────────────────────────────────────────────────

  it("renders period info via formatPeriod", async () => {
    mockFetchSuccess(budgetResponse);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-period-info")).toBeInTheDocument();
    });

    const periodInfo = screen.getByTestId("budget-period-info");
    // formatPeriod("daily", ...) should produce "Daily: Jun 15, 2026 00:00 UTC – Jun 16, 2026 00:00 UTC"
    expect(periodInfo).toHaveTextContent("Daily");
    expect(periodInfo).toHaveTextContent("Jun 15, 2026");
    expect(periodInfo).toHaveTextContent("Jun 16, 2026");
  });

  // ── Exhaustion state ────────────────────────────────────────────────────

  it("shows red indicator when used >= ceiling (exhaustion)", async () => {
    const exhausted = { ...budgetResponse, used: 100, remaining: 0 };
    mockFetchSuccess(exhausted);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-progress-bar")).toBeInTheDocument();
    });

    const progressBar = screen.getByTestId("budget-progress-bar");
    expect(progressBar).toHaveAttribute("data-exhausted", "true");
  });

  it("does not show exhaustion when used < ceiling", async () => {
    mockFetchSuccess(budgetResponse);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-progress-bar")).toBeInTheDocument();
    });

    const progressBar = screen.getByTestId("budget-progress-bar");
    expect(progressBar).toHaveAttribute("data-exhausted", "false");
  });

  // ── Empty state (404) ───────────────────────────────────────────────────

  it("shows 'No budget configured' when API returns 404", async () => {
    mockFetchError(404);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-empty-state")).toBeInTheDocument();
    });

    expect(screen.getByTestId("budget-empty-state")).toHaveTextContent(
      "No budget configured"
    );
  });

  // ── Error state (5xx) ───────────────────────────────────────────────────

  it("shows error message with retry when API returns 5xx", async () => {
    mockFetchError(500);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-error-state")).toBeInTheDocument();
    });

    expect(screen.getByTestId("budget-error-state")).toHaveTextContent(
      "Unable to load budget status"
    );

    // Retry button present
    expect(screen.getByTestId("budget-retry-btn")).toBeInTheDocument();
  });

  it("retry button re-fetches data", async () => {
    mockFetchError(500);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-retry-btn")).toBeInTheDocument();
    });

    // Now mock a successful retry
    mockFetchSuccess(budgetResponse);

    await act(async () => {
      fireEvent.click(screen.getByTestId("budget-retry-btn"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-progress-bar")).toBeInTheDocument();
    });
  });

  // ── Action buttons ──────────────────────────────────────────────────────

  it("renders action buttons: Edit Budget, Reset Budget, Remove Budget", async () => {
    mockFetchSuccess(budgetResponse);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("budget-progress-bar")).toBeInTheDocument();
    });

    expect(screen.getByTestId("budget-btn-edit")).toBeInTheDocument();
    expect(screen.getByTestId("budget-btn-edit")).toHaveTextContent("Edit Budget");

    expect(screen.getByTestId("budget-btn-reset")).toBeInTheDocument();
    expect(screen.getByTestId("budget-btn-reset")).toHaveTextContent("Reset Budget");

    expect(screen.getByTestId("budget-btn-remove")).toBeInTheDocument();
    expect(screen.getByTestId("budget-btn-remove")).toHaveTextContent("Remove Budget");
  });

  // ── Fetch URL construction ──────────────────────────────────────────────

  it("fetches from correct BFF URL using record permId", async () => {
    mockFetchSuccess(budgetResponse);

    await act(async () => {
      render(React.createElement(BudgetStatusPanel, { record: defaultRecord }));
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/admin/api/budget/${PERM_ID}`
    );
  });
});
