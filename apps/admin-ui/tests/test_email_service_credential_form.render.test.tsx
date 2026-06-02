// @vitest-environment jsdom
/**
 * Render tests — EmailServiceCredentialForm component.
 * (feat/email-credentials-and-ui-fixes)
 *
 * AC covered:
 *   1. Component renders a username input with type="text".
 *   2. Component renders a password input with type="password".
 *   3. Submit button is present and labeled "Save credential".
 *   4. Submitting with no username shows validation error (no API call).
 *   5. Submitting with no password shows validation error (no API call).
 *   6. handleAction is called with {username, password, auth_scheme} on valid submit.
 *   7. Password input has type="password" — explicit NFR-17 assertion.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

import EmailServiceCredentialForm from "../src/components/actions/EmailServiceCredentialForm.js";

// ── helpers ───────────────────────────────────────────────────────────────────

type RecordProps = {
  id?: string;
  params?: Record<string, unknown>;
};

function makeProps(
  params: Record<string, unknown> = {},
  handleAction?: (payload: Record<string, unknown>) => Promise<void>
): { record: RecordProps; handleAction?: typeof handleAction } {
  return {
    record: {
      id: "esvc_test123",
      params: {
        tenant_id: "t_test",
        auth_scheme: "email_password",
        ...params,
      },
    },
    handleAction,
  };
}

async function renderComponent(
  props: ReturnType<typeof makeProps>
) {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      React.createElement(EmailServiceCredentialForm, props as never)
    );
  });
  return result;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("EmailServiceCredentialForm", () => {
  it("renders username and password inputs", async () => {
    await renderComponent(makeProps());

    const usernameInput = screen.getByTestId("credential-username-input");
    const passwordInput = screen.getByTestId("credential-password-input");

    expect(usernameInput).toBeInTheDocument();
    expect(passwordInput).toBeInTheDocument();
  });

  it("password input has type='password' (NFR-17)", async () => {
    await renderComponent(makeProps());

    const passwordInput = screen.getByTestId("credential-password-input");
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("username input has type='text'", async () => {
    await renderComponent(makeProps());

    const usernameInput = screen.getByTestId("credential-username-input");
    expect(usernameInput).toHaveAttribute("type", "text");
  });

  it("renders Save credential submit button", async () => {
    await renderComponent(makeProps());

    const submitButton = screen.getByTestId("credential-submit-button");
    expect(submitButton).toBeInTheDocument();
    expect(submitButton.textContent).toContain("Save credential");
  });

  it("shows validation error when username is empty on submit", async () => {
    const handleAction = vi.fn();
    await renderComponent(makeProps({}, handleAction));

    const submitButton = screen.getByTestId("credential-submit-button");

    await act(async () => {
      fireEvent.click(submitButton);
    });

    // handleAction must NOT have been called
    expect(handleAction).not.toHaveBeenCalled();

    // Error message must appear
    const errorEl = screen.getByTestId("credential-error");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toContain("Username is required");
  });

  it("shows validation error when password is empty on submit", async () => {
    const handleAction = vi.fn();
    await renderComponent(makeProps({}, handleAction));

    // Fill in username but leave password blank
    const usernameInput = screen.getByTestId("credential-username-input");
    await act(async () => {
      fireEvent.change(usernameInput, { target: { value: "user@example.com" } });
    });

    const submitButton = screen.getByTestId("credential-submit-button");
    await act(async () => {
      fireEvent.click(submitButton);
    });

    expect(handleAction).not.toHaveBeenCalled();

    const errorEl = screen.getByTestId("credential-error");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toContain("Password is required");
  });

  it("calls handleAction with username, password, auth_scheme on valid submit", async () => {
    const handleAction = vi.fn().mockResolvedValue(undefined);
    await renderComponent(makeProps({ auth_scheme: "email_password" }, handleAction));

    const usernameInput = screen.getByTestId("credential-username-input");
    const passwordInput = screen.getByTestId("credential-password-input");
    const submitButton = screen.getByTestId("credential-submit-button");

    await act(async () => {
      fireEvent.change(usernameInput, { target: { value: "user@example.com" } });
      fireEvent.change(passwordInput, { target: { value: "mypassword123" } });
    });

    await act(async () => {
      fireEvent.click(submitButton);
    });

    await waitFor(() => {
      expect(handleAction).toHaveBeenCalledTimes(1);
    });

    const callArgs = handleAction.mock.calls[0][0] as Record<string, unknown>;
    expect(callArgs["username"]).toBe("user@example.com");
    expect(callArgs["password"]).toBe("mypassword123");
    expect(callArgs["auth_scheme"]).toBe("email_password");
  });

  it("calls handleAction with correct API path shape for email_app_password", async () => {
    const handleAction = vi.fn().mockResolvedValue(undefined);
    await renderComponent(
      makeProps({ auth_scheme: "email_app_password" }, handleAction)
    );

    const usernameInput = screen.getByTestId("credential-username-input");
    const passwordInput = screen.getByTestId("credential-password-input");
    const submitButton = screen.getByTestId("credential-submit-button");

    await act(async () => {
      fireEvent.change(usernameInput, { target: { value: "appuser@icloud.com" } });
      fireEvent.change(passwordInput, { target: { value: "xxxx-yyyy-zzzz-aaaa" } });
    });

    await act(async () => {
      fireEvent.click(submitButton);
    });

    await waitFor(() => {
      expect(handleAction).toHaveBeenCalledTimes(1);
    });

    const callArgs = handleAction.mock.calls[0][0] as Record<string, unknown>;
    expect(callArgs["auth_scheme"]).toBe("email_app_password");
  });

  it("shows success message and clears form after successful submit", async () => {
    const handleAction = vi.fn().mockResolvedValue(undefined);
    await renderComponent(makeProps({}, handleAction));

    const usernameInput = screen.getByTestId("credential-username-input");
    const passwordInput = screen.getByTestId("credential-password-input");
    const submitButton = screen.getByTestId("credential-submit-button");

    await act(async () => {
      fireEvent.change(usernameInput, { target: { value: "user@example.com" } });
      fireEvent.change(passwordInput, { target: { value: "secret" } });
    });

    await act(async () => {
      fireEvent.click(submitButton);
    });

    await waitFor(() => {
      expect(screen.getByTestId("credential-success")).toBeInTheDocument();
    });

    // Form should be cleared after success
    expect(usernameInput).toHaveValue("");
    expect(passwordInput).toHaveValue("");
  });
});
