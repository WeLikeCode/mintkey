// @vitest-environment jsdom
/**
 * Render tests for BudgetForm component (task 6.5).
 *
 * Covers:
 *   - Renders all fields: ceiling input, period dropdown, alert_thresholds input
 *   - Create mode (empty fields, optional)
 *   - Edit mode (pre-populated from BudgetStatus)
 *   - Client-side validation errors displayed for invalid input
 *   - Form submission calls correct BFF endpoint
 *
 * Requirements: 2.1, 2.4, 2.5, 3.1
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Component under test
import BudgetForm from "../src/components/actions/BudgetForm.js";

// ── helpers ───────────────────────────────────────────────────────────────────

/** Build AdminJS-style props for create mode (no existing budget). */
function createModeProps() {
  return {
    record: {
      id: "perm_01TESTAAAAAAAAAAAAAAAAAA01",
      params: {
        id: "perm_01TESTAAAAAAAAAAAAAAAAAA01",
        agent_id: "agent_01TESTAAAAAAAAAAAAAAAAAA01",
      },
    },
    resource: { id: "permission_grants" },
    action: { name: "editBudget", label: "Edit Budget" },
  };
}

/** Build AdminJS-style props for edit mode (existing budget). */
function editModeProps() {
  return {
    record: {
      id: "perm_01TESTAAAAAAAAAAAAAAAAAA01",
      params: {
        id: "perm_01TESTAAAAAAAAAAAAAAAAAA01",
        agent_id: "agent_01TESTAAAAAAAAAAAAAAAAAA01",
        "constraints.budget.ceiling": 100,
        "constraints.budget.period": "daily",
        "constraints.budget.alert_thresholds": [50, 80, 100],
      },
    },
    resource: { id: "permission_grants" },
    action: { name: "editBudget", label: "Edit Budget" },
  };
}

// ── setup ─────────────────────────────────────────────────────────────────────

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  global.fetch = fetchMock;
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── tests ─────────────────────────────────────────────────────────────────────

describe("BudgetForm — renders all fields", () => {
  it("renders ceiling input field", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling");
    expect(ceilingInput).toBeInTheDocument();
    expect(ceilingInput.tagName.toLowerCase()).toBe("input");
  });

  it("renders period dropdown", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const periodSelect = screen.getByTestId("budget-field-period");
    expect(periodSelect).toBeInTheDocument();
    expect(periodSelect.tagName.toLowerCase()).toBe("select");
  });

  it("renders alert_thresholds input field", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const threshInput = screen.getByTestId("budget-field-alert-thresholds");
    expect(threshInput).toBeInTheDocument();
    expect(threshInput.tagName.toLowerCase()).toBe("input");
  });

  it("renders submit button", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const submitBtn = screen.getByTestId("budget-form-submit");
    expect(submitBtn).toBeInTheDocument();
  });
});

describe("BudgetForm — create mode (empty fields)", () => {
  it("ceiling field starts empty", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    expect(ceilingInput.value).toBe("");
  });

  it("period field starts with empty/placeholder selection", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const periodSelect = screen.getByTestId("budget-field-period") as HTMLSelectElement;
    expect(periodSelect.value).toBe("");
  });

  it("alert_thresholds field starts empty", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const threshInput = screen.getByTestId("budget-field-alert-thresholds") as HTMLInputElement;
    expect(threshInput.value).toBe("");
  });
});

describe("BudgetForm — edit mode (pre-populated from BudgetStatus)", () => {
  it("ceiling field pre-populated with existing value", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, editModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    expect(ceilingInput.value).toBe("100");
  });

  it("period field pre-populated with existing value", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, editModeProps()));
    });

    const periodSelect = screen.getByTestId("budget-field-period") as HTMLSelectElement;
    expect(periodSelect.value).toBe("daily");
  });

  it("alert_thresholds field pre-populated with comma-separated values", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, editModeProps()));
    });

    const threshInput = screen.getByTestId("budget-field-alert-thresholds") as HTMLInputElement;
    expect(threshInput.value).toBe("50, 80, 100");
  });
});

describe("BudgetForm — client-side validation errors", () => {
  it("shows error for invalid ceiling (0)", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    const periodSelect = screen.getByTestId("budget-field-period") as HTMLSelectElement;
    const submitBtn = screen.getByTestId("budget-form-submit");

    await act(async () => {
      fireEvent.change(ceilingInput, { target: { value: "0" } });
      fireEvent.change(periodSelect, { target: { value: "daily" } });
    });

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    const errorEl = screen.getByTestId("budget-form-errors");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toContain("Ceiling must be a positive integer");
  });

  it("shows error for invalid ceiling (non-integer 1.5)", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    const periodSelect = screen.getByTestId("budget-field-period") as HTMLSelectElement;
    const submitBtn = screen.getByTestId("budget-form-submit");

    await act(async () => {
      fireEvent.change(ceilingInput, { target: { value: "1.5" } });
      fireEvent.change(periodSelect, { target: { value: "daily" } });
    });

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    const errorEl = screen.getByTestId("budget-form-errors");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toContain("Ceiling must be a positive integer");
  });

  it("shows error for invalid threshold (101)", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    const periodSelect = screen.getByTestId("budget-field-period") as HTMLSelectElement;
    const threshInput = screen.getByTestId("budget-field-alert-thresholds") as HTMLInputElement;
    const submitBtn = screen.getByTestId("budget-form-submit");

    await act(async () => {
      fireEvent.change(ceilingInput, { target: { value: "100" } });
      fireEvent.change(periodSelect, { target: { value: "daily" } });
      fireEvent.change(threshInput, { target: { value: "50, 101" } });
    });

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    const errorEl = screen.getByTestId("budget-form-errors");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toContain("integer in [1, 100]");
  });

  it("shows error when ceiling is provided without period", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    const submitBtn = screen.getByTestId("budget-form-submit");

    await act(async () => {
      fireEvent.change(ceilingInput, { target: { value: "100" } });
    });

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    const errorEl = screen.getByTestId("budget-form-errors");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toContain("Period is required");
  });
});

describe("BudgetForm — form submission calls correct BFF endpoint", () => {
  it("submits POST to /admin/api/budget/:permId/edit with correct body", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });

    await act(async () => {
      render(React.createElement(BudgetForm, editModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    const periodSelect = screen.getByTestId("budget-field-period") as HTMLSelectElement;
    const threshInput = screen.getByTestId("budget-field-alert-thresholds") as HTMLInputElement;
    const submitBtn = screen.getByTestId("budget-form-submit");

    // Change ceiling to 200
    await act(async () => {
      fireEvent.change(ceilingInput, { target: { value: "200" } });
      fireEvent.change(periodSelect, { target: { value: "weekly" } });
      fireEvent.change(threshInput, { target: { value: "25, 75" } });
    });

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/admin/api/budget/perm_01TESTAAAAAAAAAAAAAAAAAA01/edit");
    expect(options.method).toBe("POST");

    const body = JSON.parse(options.body);
    expect(body.ceiling).toBe(200);
    expect(body.period).toBe("weekly");
    expect(body.alert_thresholds).toEqual([25, 75]);
  });

  it("uses default thresholds [50, 80, 100] when alert_thresholds field is empty", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });

    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    const periodSelect = screen.getByTestId("budget-field-period") as HTMLSelectElement;
    const submitBtn = screen.getByTestId("budget-form-submit");

    await act(async () => {
      fireEvent.change(ceilingInput, { target: { value: "50" } });
      fireEvent.change(periodSelect, { target: { value: "monthly" } });
    });

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.alert_thresholds).toEqual([50, 80, 100]);
  });

  it("does not call fetch when validation fails", async () => {
    await act(async () => {
      render(React.createElement(BudgetForm, createModeProps()));
    });

    const ceilingInput = screen.getByTestId("budget-field-ceiling") as HTMLInputElement;
    const submitBtn = screen.getByTestId("budget-form-submit");

    await act(async () => {
      fireEvent.change(ceilingInput, { target: { value: "0" } });
    });

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
