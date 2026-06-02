// @vitest-environment jsdom
/**
 * Render tests for EmailServiceCombobox — feat/email-perm-grants-pickers.
 *
 * Covers:
 *   ESC-1: Component renders with testId "email-service-combobox" (not a plain input).
 *   ESC-2: Typing filters options in the dropdown (local filter on static options).
 *   ESC-3: Clicking an option sets the hidden wire-id value.
 *   ESC-4: Label format is "{name} ({imap_host}:{imap_port})".
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Control resourceAction responses (mapped via vitest.render.config.ts alias)
import { resourceAction as mockResourceAction } from "./__mocks__/adminjs-stub.js";

// Component under test
import EmailServiceCombobox from "../src/components/properties/EmailServiceCombobox.js";

// ── helpers ───────────────────────────────────────────────────────────────────

interface EmailServiceStub {
  id: string;
  name: string;
  imap_host: string;
  imap_port: number;
}

/**
 * Render EmailServiceCombobox. AsyncCombobox fires a resourceAction list call
 * on mount to populate initial options.
 */
async function renderCombobox(
  services: EmailServiceStub[] = [],
  value = "",
  onChange = vi.fn()
) {
  mockResourceAction.mockResolvedValueOnce({
    data: {
      records: services.map((s) => ({
        params: {
          id: s.id,
          name: s.name,
          imap_host: s.imap_host,
          imap_port: s.imap_port,
        },
      })),
    },
  });

  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      React.createElement(EmailServiceCombobox, {
        property: { path: "email_service_id", label: "Email Service" },
        record: { params: { email_service_id: value } },
        onChange,
      })
    );
  });
  return { result, onChange };
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("EmailServiceCombobox — feat/email-perm-grants-pickers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── ESC-1: component renders ──────────────────────────────────────────────

  it("ESC-1: renders with data-testid='email-service-combobox'", async () => {
    await renderCombobox([]);
    expect(screen.getByTestId("email-service-combobox")).toBeInTheDocument();
  });

  it("ESC-1: renders a search input (not a plain text input for UUID)", async () => {
    await renderCombobox([]);
    const input = screen.getByTestId("email-service-combobox-input");
    expect(input).toBeInTheDocument();
    expect(input.tagName).toBe("INPUT");
  });

  // ── ESC-2: typing filters options ─────────────────────────────────────────

  it("ESC-2: dropdown opens when input is focused and shows options", async () => {
    const services: EmailServiceStub[] = [
      { id: "es_01AAA", name: "cici-softuraj", imap_host: "imap.gmail.com", imap_port: 993 },
      { id: "es_01BBB", name: "work-outlook", imap_host: "imap.outlook.com", imap_port: 993 },
    ];
    await renderCombobox(services);

    const input = screen.getByTestId("email-service-combobox-input");

    // Open the dropdown by clicking
    await act(async () => {
      fireEvent.click(input);
    });

    // Both options should appear
    expect(screen.getByTestId("email-service-combobox-option-0")).toBeInTheDocument();
    expect(screen.getByTestId("email-service-combobox-option-1")).toBeInTheDocument();
  });

  it("ESC-2: typing 'cici' filters the dropdown to matching services", async () => {
    const services: EmailServiceStub[] = [
      { id: "es_01AAA", name: "cici-softuraj", imap_host: "imap.gmail.com", imap_port: 993 },
      { id: "es_01BBB", name: "work-outlook", imap_host: "imap.outlook.com", imap_port: 993 },
    ];
    // Second resourceAction call is for the debounced search
    mockResourceAction.mockResolvedValueOnce({
      data: {
        records: [
          {
            params: {
              id: "es_01AAA",
              name: "cici-softuraj",
              imap_host: "imap.gmail.com",
              imap_port: 993,
            },
          },
        ],
      },
    });

    await renderCombobox(services);

    const input = screen.getByTestId("email-service-combobox-input");

    await act(async () => {
      fireEvent.change(input, { target: { value: "cici" } });
    });

    // Wait for the debounced search to fire and list to update
    await waitFor(() => {
      expect(screen.queryByTestId("email-service-combobox-option-0")).toBeInTheDocument();
    });

    // Only the cici service should be visible after search resolves
    expect(screen.queryByTestId("email-service-combobox-option-1")).not.toBeInTheDocument();
  });

  // ── ESC-3: clicking an option sets the wire-id ────────────────────────────

  it("ESC-3: selecting an option calls onChange with (propertyPath, wireId)", async () => {
    const WIRE_ID = "es_01AAA";
    const services: EmailServiceStub[] = [
      { id: WIRE_ID, name: "cici-softuraj", imap_host: "imap.gmail.com", imap_port: 993 },
    ];
    const { onChange } = await renderCombobox(services);

    const input = screen.getByTestId("email-service-combobox-input");

    // Open dropdown
    await act(async () => {
      fireEvent.click(input);
    });

    // Click the first option
    const option = screen.getByTestId("email-service-combobox-option-0");
    await act(async () => {
      fireEvent.mouseDown(option);
    });

    // onChange called with (propertyPath, wireId) — AdminJS convention
    expect(onChange).toHaveBeenCalledWith("email_service_id", WIRE_ID);
  });

  it("ESC-3: after selection the chip displays the selected service label", async () => {
    const WIRE_ID = "es_01AAA";
    const services: EmailServiceStub[] = [
      { id: WIRE_ID, name: "cici-softuraj", imap_host: "imap.gmail.com", imap_port: 993 },
    ];
    await renderCombobox(services);

    const input = screen.getByTestId("email-service-combobox-input");
    await act(async () => { fireEvent.click(input); });

    const option = screen.getByTestId("email-service-combobox-option-0");
    await act(async () => { fireEvent.mouseDown(option); });

    // The chip label should show the selected service
    const chipLabel = screen.getByTestId("email-service-combobox-chip-label");
    expect(chipLabel).toHaveTextContent("cici-softuraj");
  });

  // ── ESC-4: label format ───────────────────────────────────────────────────

  it("ESC-4: label format is '{name} ({imap_host}:{imap_port})'", async () => {
    const services: EmailServiceStub[] = [
      { id: "es_01AAA", name: "cici-softuraj", imap_host: "imap.gmail.com", imap_port: 993 },
    ];
    await renderCombobox(services);

    const input = screen.getByTestId("email-service-combobox-input");

    await act(async () => {
      fireEvent.click(input);
    });

    const option = screen.getByTestId("email-service-combobox-option-0");
    expect(option).toHaveTextContent("cici-softuraj (imap.gmail.com:993)");
  });

  it("ESC-4: selecting shows chip with name and imap details", async () => {
    const WIRE_ID = "es_01AAA";
    const services: EmailServiceStub[] = [
      { id: WIRE_ID, name: "cici-softuraj", imap_host: "imap.gmail.com", imap_port: 993 },
    ];
    await renderCombobox(services);

    const input = screen.getByTestId("email-service-combobox-input");
    await act(async () => { fireEvent.click(input); });

    const option = screen.getByTestId("email-service-combobox-option-0");
    await act(async () => { fireEvent.mouseDown(option); });

    const chipLabel = screen.getByTestId("email-service-combobox-chip-label");
    expect(chipLabel).toHaveTextContent("cici-softuraj (imap.gmail.com:993)");
  });
});
