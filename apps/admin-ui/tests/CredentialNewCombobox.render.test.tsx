// @vitest-environment jsdom
/**
 * Render tests for C-3: ServiceCombobox typeahead in CredentialNewForm.
 *
 * Covers:
 *   C3-1: When no ?service_id= query param, the AsyncCombobox is rendered
 *         (not a plain text input) and the service-combobox testId is present.
 *   C3-2: When ?service_id=<id> is present (pre-fill), the combobox is NOT
 *         rendered; the locked display box is shown instead (OPS-DDEE DD-1).
 *   C3-3: Selecting a service via the combobox updates the value; submit
 *         payload contains the wire-form service_id.
 *   C3-4: Pre-fill banner appears when service_id is pre-filled from query arg.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Control resourceAction responses (mapped via vitest.render.config.ts alias)
import { resourceAction as mockResourceAction } from "./__mocks__/adminjs-stub.js";

// Control useSearchParams (mapped via vitest.render.config.ts alias)
import { searchParamsMock } from "./__mocks__/react-router-dom-stub.js";

// Component under test
import CredentialNewForm from "../src/components/actions/CredentialNewForm.js";

// ── helpers ───────────────────────────────────────────────────────────────────

/**
 * Render CredentialNewForm with the initial resourceAction list call returning
 * the given service records. AsyncCombobox fetches top-50 on mount.
 */
async function renderForm(services: Array<{ id: string; name: string }> = []) {
  // AsyncCombobox fires a `list` resourceAction on mount to populate options.
  mockResourceAction.mockResolvedValueOnce({
    data: {
      records: services.map((s) => ({ params: { id: s.id, name: s.name } })),
    },
  });

  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(React.createElement(CredentialNewForm));
  });
  return result;
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("CredentialNewForm — ServiceCombobox typeahead (C-3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Clear any pre-set query params from previous tests.
    Array.from(searchParamsMock.keys()).forEach((k) =>
      searchParamsMock.delete(k)
    );
  });

  // ── C3-1: combobox rendered when no pre-fill ───────────────────────────────

  it("C3-1: renders the service combobox (not a plain text input) when no ?service_id= present", async () => {
    await renderForm([{ id: "svc_01TESTAAAAAAAAAAAAAAAAAAA1", name: "My Service" }]);

    // The AsyncCombobox renders with testId "field-combobox-service_id"
    expect(screen.getByTestId("field-combobox-service_id")).toBeInTheDocument();

    // The locked display box should NOT be present
    expect(screen.queryByTestId("field-service-id-locked")).not.toBeInTheDocument();

    // The old plain text input should NOT be present (was testId="field-input-service_id")
    expect(screen.queryByTestId("field-input-service_id")).not.toBeInTheDocument();
  });

  it("C3-1: the combobox search input is present and accepts text", async () => {
    await renderForm([{ id: "svc_01TESTAAAAAAAAAAAAAAAAAAA1", name: "My Service" }]);

    // AsyncCombobox renders an input with testId `${testId}-input`
    const comboInput = screen.getByTestId("field-combobox-service_id-input");
    expect(comboInput).toBeInTheDocument();

    // Should be enabled (not disabled)
    expect(comboInput).not.toBeDisabled();
  });

  // ── C3-2: locked display when pre-filled from query arg ───────────────────

  it("C3-2: renders locked display box (not combobox) when ?service_id= is present", async () => {
    // Set up the query param BEFORE rendering
    searchParamsMock.set("service_id", "svc_01PREFILLEDAAAAAAAAAAAAA1");

    // The combobox renders briefly on first paint (before useEffect fires) so
    // we must provide a mock for the initial list call it makes.
    mockResourceAction.mockResolvedValue({ data: { records: [] } });

    await act(async () => {
      render(React.createElement(CredentialNewForm));
    });

    // After effect runs serviceIdLocked=true, combobox is replaced by locked box
    expect(screen.getByTestId("field-service-id-locked")).toBeInTheDocument();

    // Combobox should NOT be present after state update
    expect(screen.queryByTestId("field-combobox-service_id")).not.toBeInTheDocument();
  });

  it("C3-2: locked display shows the pre-filled service ID", async () => {
    const SERVICE_ID = "svc_01PREFILLEDAAAAAAAAAAAAA1";
    searchParamsMock.set("service_id", SERVICE_ID);

    mockResourceAction.mockResolvedValue({ data: { records: [] } });

    await act(async () => {
      render(React.createElement(CredentialNewForm));
    });

    const lockedBox = screen.getByTestId("field-service-id-locked");
    expect(lockedBox).toHaveTextContent(SERVICE_ID);
  });

  // ── C3-4: pre-fill banner ─────────────────────────────────────────────────

  it("C3-4: pre-fill banner is visible when ?service_id= is in query params", async () => {
    searchParamsMock.set("service_id", "svc_01PREFILLEDAAAAAAAAAAAAA1");

    mockResourceAction.mockResolvedValue({ data: { records: [] } });

    await act(async () => {
      render(React.createElement(CredentialNewForm));
    });

    expect(screen.getByTestId("credential-prefill-banner")).toBeInTheDocument();
    expect(screen.getByTestId("credential-prefill-banner")).toHaveTextContent(
      "Adding credential for service:"
    );
  });

  it("C3-4: pre-fill banner is NOT shown when no query param", async () => {
    await renderForm();

    expect(screen.queryByTestId("credential-prefill-banner")).not.toBeInTheDocument();
  });

  // ── C3-3: selection flows into submit payload ─────────────────────────────

  it("C3-3: selecting a service via the combobox updates the wire-id and submit payload", async () => {
    const WIRE_ID = "svc_01TESTAAAAAAAAAAAAAAAAAAA1";
    await renderForm([{ id: WIRE_ID, name: "My Service" }]);

    // Open the dropdown by clicking the input
    const comboInput = screen.getByTestId("field-combobox-service_id-input");
    await act(async () => {
      fireEvent.click(comboInput);
    });

    // The option list should open — first option
    const option = screen.getByTestId("field-combobox-service_id-option-0");
    expect(option).toBeInTheDocument();
    expect(option).toHaveAttribute("data-value", WIRE_ID);

    // Select the option
    await act(async () => {
      fireEvent.mouseDown(option);
    });

    // The hidden value input should now carry the wire ID
    const hiddenInput = screen.getByTestId("field-combobox-service_id-value") as HTMLInputElement;
    expect(hiddenInput.value).toBe(WIRE_ID);

    // The chip label should show the display name + id
    const chipLabel = screen.getByTestId("field-combobox-service_id-chip-label");
    expect(chipLabel).toHaveTextContent("My Service");

    // Now submit — mock the new action response
    mockResourceAction.mockResolvedValueOnce({
      data: { notice: { message: "Created", type: "success" }, redirectUrl: "/admin/resources/credentials" },
    });

    const submitBtn = screen.getByTestId("credential-new-submit");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // Confirm resourceAction was called with the wire-form service_id
    const calls = mockResourceAction.mock.calls;
    // Find the `new` action call (the list call happens on mount)
    const newCall = calls.find(
      (c) =>
        c[0]?.resourceId === "credentials" && c[0]?.actionName === "new"
    );
    expect(newCall).toBeDefined();
    expect(newCall![0].data.service_id).toBe(WIRE_ID);
  });

  it("C3-3: submit with no service selected shows validation error", async () => {
    await renderForm([]);

    // Don't select any service — click submit directly
    const submitBtn = screen.getByTestId("credential-new-submit");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // Should show the "Service ID is required" error
    expect(screen.getByTestId("create-error")).toBeInTheDocument();
    expect(screen.getByTestId("create-error")).toHaveTextContent(
      "Service ID is required."
    );
  });
});
