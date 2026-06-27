// @vitest-environment jsdom
/**
 * Render tests for AgentSecretUpdateForm (Chunk C6b).
 *
 * Covers:
 *   R1: Component renders the rotate form with masked value input.
 *   R2: After successful submit, the reveal-once panel shows the TYPED value
 *       (NOT from the API response, which has no value field).
 *   R3: The reveal-once panel has a Copy button.
 *   R4: The reveal-once panel is NOT present before submission.
 *   R5: The form shows the secret name read-only for context.
 *   R6: Value input is of type password (masked).
 *   R7: Submit with no value shows a validation error.
 *   R8: API error shows error notice, does NOT show reveal panel.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Control recordAction responses (mapped via vitest.render.config.ts alias)
import { recordAction as mockRecordAction } from "./__mocks__/adminjs-stub.js";

// Component under test
import AgentSecretUpdateForm from "../src/components/actions/AgentSecretUpdateForm.js";

// ── helpers ───────────────────────────────────────────────────────────────────

const DEFAULT_RECORD = {
  id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
  params: {
    id: "secret_01AAAAAAAAAAAAAAAAAAAAAAAAA1",
    name: "MY_API_KEY",
    content_type: "text/plain",
    version: 1,
  },
  errors: {},
};

const DEFAULT_RESOURCE = { id: "agent-secrets" };
const DEFAULT_ACTION = { name: "editValue", label: "Rotate Secret Value" };

async function renderUpdateForm(record = DEFAULT_RECORD) {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      React.createElement(AgentSecretUpdateForm, {
        record,
        resource: DEFAULT_RESOURCE,
        action: DEFAULT_ACTION,
      })
    );
  });
  return result;
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("AgentSecretUpdateForm — rotate form rendering (R1, R4, R5, R6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("R1: renders the rotate form with value input and submit button", async () => {
    await renderUpdateForm();

    expect(screen.getByTestId("agent-secret-update-form")).toBeInTheDocument();
    expect(screen.getByTestId("field-input-value")).toBeInTheDocument();
    expect(screen.getByTestId("secret-update-submit")).toBeInTheDocument();
  });

  it("R4: reveal-once panel is NOT present before submission", async () => {
    await renderUpdateForm();

    expect(screen.queryByTestId("agent-secret-update-reveal-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secret-reveal-value")).not.toBeInTheDocument();
  });

  it("R5: secret name is shown read-only for context", async () => {
    await renderUpdateForm();

    // The form must display the existing secret name
    expect(screen.getByTestId("secret-name-display")).toBeInTheDocument();
    expect(screen.getByTestId("secret-name-display")).toHaveTextContent("MY_API_KEY");
  });

  it("R6: value input is of type password (masked)", async () => {
    await renderUpdateForm();

    const valueInput = screen.getByTestId("field-input-value");
    expect(valueInput).toHaveAttribute("type", "password");
  });
});

describe("AgentSecretUpdateForm — validation (R7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("R7: submit with no value shows validation error", async () => {
    await renderUpdateForm();

    const submitBtn = screen.getByTestId("secret-update-submit");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(screen.getByTestId("update-error")).toBeInTheDocument();
    expect(screen.getByTestId("update-error")).toHaveTextContent(/value.*required|required.*value/i);
  });
});

describe("AgentSecretUpdateForm — reveal-once panel (R2, R3, R8)", () => {
  const TYPED_VALUE = "new-rotated-secret-value-xyz";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("R2: after successful submit, reveal-once panel shows the typed value (not from response)", async () => {
    // Mock successful recordAction response — NOTE: response has NO value field
    mockRecordAction.mockResolvedValueOnce({
      data: {
        notice: { message: "Secret updated", type: "success" },
        record: { params: { id: "secret_01AAA", version: 2 } },
      },
    });

    await renderUpdateForm();

    const valueInput = screen.getByTestId("field-input-value");
    await act(async () => {
      fireEvent.change(valueInput, { target: { value: TYPED_VALUE } });
    });

    const submitBtn = screen.getByTestId("secret-update-submit");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("agent-secret-update-reveal-panel")).toBeInTheDocument();
    });

    // The revealed value must be the TYPED value — not from the API response
    const revealedValueEl = screen.getByTestId("secret-reveal-value");
    expect(revealedValueEl).toHaveTextContent(TYPED_VALUE);
  });

  it("R3: reveal-once panel has a Copy affordance", async () => {
    mockRecordAction.mockResolvedValueOnce({
      data: { notice: { message: "Secret updated", type: "success" } },
    });

    await renderUpdateForm();

    const valueInput = screen.getByTestId("field-input-value");
    await act(async () => {
      fireEvent.change(valueInput, { target: { value: TYPED_VALUE } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("secret-update-submit"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("agent-secret-update-reveal-panel")).toBeInTheDocument();
    });

    expect(screen.getByTestId("secret-reveal-copy-btn")).toBeInTheDocument();
  });

  it("R8: API error shows error notice, does NOT show reveal panel", async () => {
    mockRecordAction.mockResolvedValueOnce({
      data: { notice: { message: "Secret value cannot be empty", type: "error" } },
    });

    await renderUpdateForm();

    const valueInput = screen.getByTestId("field-input-value");
    await act(async () => {
      fireEvent.change(valueInput, { target: { value: TYPED_VALUE } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("secret-update-submit"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("update-error")).toBeInTheDocument();
    });

    expect(screen.getByTestId("update-error")).toHaveTextContent("Secret value cannot be empty");
    expect(screen.queryByTestId("agent-secret-update-reveal-panel")).not.toBeInTheDocument();
  });

  it("R2b: rotate form is NOT shown once reveal-once panel is displayed", async () => {
    mockRecordAction.mockResolvedValueOnce({
      data: { notice: { message: "Secret updated", type: "success" } },
    });

    await renderUpdateForm();

    await act(async () => {
      fireEvent.change(screen.getByTestId("field-input-value"), { target: { value: TYPED_VALUE } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("secret-update-submit"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("agent-secret-update-reveal-panel")).toBeInTheDocument();
    });

    // Rotate form must not be present
    expect(screen.queryByTestId("agent-secret-update-form")).not.toBeInTheDocument();
    expect(screen.queryByTestId("field-input-value")).not.toBeInTheDocument();
  });
});
