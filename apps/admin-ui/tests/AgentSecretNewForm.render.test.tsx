// @vitest-environment jsdom
/**
 * Render tests for AgentSecretNewForm (Chunk C6, D11).
 *
 * Covers:
 *   R1: Component renders the create form on mount.
 *   R2: After successful submit, the reveal-once panel shows the typed value
 *       (NOT from the API response which has no value field).
 *   R3: The reveal-once panel shows a Copy button.
 *   R4: The reveal-once panel is NOT present before submission.
 *   R5: The value input is a password (masked) input.
 *   R6: When ?agent_id= is in query params, the agent_id field is pre-filled + locked.
 *   R7: Submit with no name shows a validation error.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// AsyncCombobox fetches the agents list on mount via the AdminJS API, which is
// unavailable under jsdom. Stub it as a plain controlled input so these tests
// exercise AgentSecretNewForm's own logic (AsyncCombobox has its own tests).
vi.mock("../src/components/properties/AsyncCombobox.js", () => ({
  default: ({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) =>
    React.createElement("input", {
      "data-testid": "field-input-agent_id",
      value: value ?? "",
      placeholder,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value),
    }),
}));

// Control resourceAction responses (mapped via vitest.render.config.ts alias)
import { resourceAction as mockResourceAction } from "./__mocks__/adminjs-stub.js";

// Control useSearchParams (mapped via vitest.render.config.ts alias)
import { searchParamsMock } from "./__mocks__/react-router-dom-stub.js";

// Component under test
import AgentSecretNewForm from "../src/components/actions/AgentSecretNewForm.js";

// ── helpers ───────────────────────────────────────────────────────────────────

async function renderForm() {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(React.createElement(AgentSecretNewForm));
  });
  return result;
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("AgentSecretNewForm — create form rendering (R1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Array.from(searchParamsMock.keys()).forEach((k) => searchParamsMock.delete(k));
  });

  it("R1: renders the create form with name, value, and content_type inputs", async () => {
    await renderForm();

    expect(screen.getByTestId("agent-secret-new-form")).toBeInTheDocument();
    expect(screen.getByTestId("field-input-name")).toBeInTheDocument();
    expect(screen.getByTestId("field-input-value")).toBeInTheDocument();
    expect(screen.getByTestId("field-input-content_type")).toBeInTheDocument();
    expect(screen.getByTestId("secret-new-submit")).toBeInTheDocument();
  });

  it("R4: reveal-once panel is NOT present before submission", async () => {
    await renderForm();

    expect(screen.queryByTestId("agent-secret-reveal-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secret-reveal-value")).not.toBeInTheDocument();
  });

  it("R5: value input is of type password (masked)", async () => {
    await renderForm();

    const valueInput = screen.getByTestId("field-input-value");
    expect(valueInput).toHaveAttribute("type", "password");
  });

  it("R6: pre-fills agent_id from ?agent_id= query param and shows locked banner", async () => {
    const AGENT_ID = "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA1";
    searchParamsMock.set("agent_id", AGENT_ID);

    await act(async () => {
      render(React.createElement(AgentSecretNewForm));
    });

    expect(screen.getByTestId("field-agent-id-locked")).toBeInTheDocument();
    expect(screen.getByTestId("field-agent-id-locked")).toHaveTextContent(AGENT_ID);
    expect(screen.getByTestId("secret-prefill-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("field-input-agent_id")).not.toBeInTheDocument();
  });

  it("R7: submit with no name shows validation error", async () => {
    searchParamsMock.set("agent_id", "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA1");

    await act(async () => {
      render(React.createElement(AgentSecretNewForm));
    });

    // Only fill value, not name
    const valueInput = screen.getByTestId("field-input-value");
    await act(async () => {
      fireEvent.change(valueInput, { target: { value: "supersecret" } });
    });

    const submitBtn = screen.getByTestId("secret-new-submit");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(screen.getByTestId("create-error")).toBeInTheDocument();
    expect(screen.getByTestId("create-error")).toHaveTextContent("Secret name is required");
  });
});

describe("AgentSecretNewForm — reveal-once panel (R2, R3)", () => {
  const AGENT_ID = "agent_01AAAAAAAAAAAAAAAAAAAAAAAAA1";
  const TYPED_VALUE = "super-secret-typed-value-12345";

  beforeEach(() => {
    vi.clearAllMocks();
    Array.from(searchParamsMock.keys()).forEach((k) => searchParamsMock.delete(k));
    searchParamsMock.set("agent_id", AGENT_ID);
  });

  it("R2: after successful submit, reveal-once panel shows the typed value exactly", async () => {
    // Mock successful resourceAction response — NOTE: response has NO value field
    mockResourceAction.mockResolvedValueOnce({
      data: {
        notice: { message: "Secret created", type: "success" },
        record: { params: { id: "secret_01AAA", name: "MY_SECRET" } },
      },
    });

    await act(async () => {
      render(React.createElement(AgentSecretNewForm));
    });

    // Fill in the form
    const nameInput = screen.getByTestId("field-input-name");
    const valueInput = screen.getByTestId("field-input-value");

    await act(async () => {
      fireEvent.change(nameInput, { target: { value: "MY_SECRET" } });
      fireEvent.change(valueInput, { target: { value: TYPED_VALUE } });
    });

    // Submit the form
    const submitBtn = screen.getByTestId("secret-new-submit");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // Await the reveal-once panel
    await waitFor(() => {
      expect(screen.getByTestId("agent-secret-reveal-panel")).toBeInTheDocument();
    });

    // The revealed value must be the TYPED value — not from the API response
    const revealedValueEl = screen.getByTestId("secret-reveal-value");
    expect(revealedValueEl).toHaveTextContent(TYPED_VALUE);
  });

  it("R3: reveal-once panel has a Copy affordance", async () => {
    mockResourceAction.mockResolvedValueOnce({
      data: { notice: { message: "Secret created", type: "success" } },
    });

    await act(async () => {
      render(React.createElement(AgentSecretNewForm));
    });

    const nameInput = screen.getByTestId("field-input-name");
    const valueInput = screen.getByTestId("field-input-value");

    await act(async () => {
      fireEvent.change(nameInput, { target: { value: "MY_SECRET" } });
      fireEvent.change(valueInput, { target: { value: TYPED_VALUE } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("secret-new-submit"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("agent-secret-reveal-panel")).toBeInTheDocument();
    });

    // Copy button must exist in the reveal panel
    expect(screen.getByTestId("secret-reveal-copy-btn")).toBeInTheDocument();
  });

  it("R2b: create form is NOT shown once reveal-once panel is displayed", async () => {
    mockResourceAction.mockResolvedValueOnce({
      data: { notice: { message: "Secret created", type: "success" } },
    });

    await act(async () => {
      render(React.createElement(AgentSecretNewForm));
    });

    await act(async () => {
      fireEvent.change(screen.getByTestId("field-input-name"), { target: { value: "MY_SECRET" } });
      fireEvent.change(screen.getByTestId("field-input-value"), { target: { value: TYPED_VALUE } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("secret-new-submit"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("agent-secret-reveal-panel")).toBeInTheDocument();
    });

    // The create form must not be present
    expect(screen.queryByTestId("agent-secret-new-form")).not.toBeInTheDocument();
    // The value input from the form must not be present
    expect(screen.queryByTestId("field-input-value")).not.toBeInTheDocument();
  });

  it("R2c: API error shows error notice, does NOT show reveal panel", async () => {
    mockResourceAction.mockResolvedValueOnce({
      data: { notice: { message: "Name already exists", type: "error" } },
    });

    await act(async () => {
      render(React.createElement(AgentSecretNewForm));
    });

    await act(async () => {
      fireEvent.change(screen.getByTestId("field-input-name"), { target: { value: "DUPE" } });
      fireEvent.change(screen.getByTestId("field-input-value"), { target: { value: TYPED_VALUE } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("secret-new-submit"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("create-error")).toBeInTheDocument();
    });

    expect(screen.getByTestId("create-error")).toHaveTextContent("Name already exists");
    expect(screen.queryByTestId("agent-secret-reveal-panel")).not.toBeInTheDocument();
  });
});
