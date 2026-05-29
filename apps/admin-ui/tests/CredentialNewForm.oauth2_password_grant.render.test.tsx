// @vitest-environment jsdom
/**
 * Render tests — CredentialNewForm with oauth2_password_grant scheme (OAUTH-C3).
 *
 * AC covered:
 *   AC-1: oauth2_password_grant appears in auth-scheme dropdown.
 *   AC-2: Selecting it renders token_url (URL), credential_fields kv-editor
 *          (default userName/password rows, values masked), token_response_path,
 *          exchange_timeout_seconds (number, default 10, min 1 max 120).
 *   AC-3: On submit, the assembled credential value JSON exactly matches the
 *          contract: token_url + credential_fields{...} + token_response_path +
 *          exchange_timeout_seconds (integer).
 *   AC-5: Other auth schemes (bearer_token) are unaffected.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

import { resourceAction as mockResourceAction } from "./__mocks__/adminjs-stub.js";
import { navigate as mockNavigate } from "./__mocks__/react-router-dom-stub.js";

import CredentialNewForm from "../src/components/actions/CredentialNewForm.js";

// ── helpers ───────────────────────────────────────────────────────────────────

async function renderForm() {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(React.createElement(CredentialNewForm));
  });
  return result;
}

async function selectScheme(scheme: string) {
  const select = screen.getByTestId("field-select-auth_scheme") as HTMLSelectElement;
  await act(async () => {
    fireEvent.change(select, { target: { value: scheme } });
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("CredentialNewForm — oauth2_password_grant (jsdom)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── AC-1: dropdown presence ────────────────────────────────────────────────

  it("AC-1: oauth2_password_grant appears in auth-scheme dropdown", async () => {
    await renderForm();

    const select = screen.getByTestId("field-select-auth_scheme") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain("oauth2_password_grant");

    // Verify the label
    const opt = Array.from(select.options).find((o) => o.value === "oauth2_password_grant");
    expect(opt?.text).toMatch(/password grant/i);
  });

  // ── AC-2: fields rendered ─────────────────────────────────────────────────

  it("AC-2: selecting oauth2_password_grant renders token_url field", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    expect(screen.getByTestId("field-input-token_url")).toBeInTheDocument();
  });

  it("AC-2: selecting oauth2_password_grant renders kv-editor with default userName and password rows", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    expect(screen.getByTestId("kv-editor")).toBeInTheDocument();

    // Default row 0: key = userName
    const key0 = screen.getByTestId("kv-key-0") as HTMLInputElement;
    expect(key0.value).toBe("userName");

    // Default row 1: key = password
    const key1 = screen.getByTestId("kv-key-1") as HTMLInputElement;
    expect(key1.value).toBe("password");
  });

  it("AC-2: credential value inputs in kv-editor are type=password (masked)", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    const val0 = screen.getByTestId("kv-value-0") as HTMLInputElement;
    const val1 = screen.getByTestId("kv-value-1") as HTMLInputElement;
    expect(val0.type).toBe("password");
    expect(val1.type).toBe("password");
  });

  it("AC-2: selecting oauth2_password_grant renders token_response_path field", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    expect(screen.getByTestId("field-input-token_response_path")).toBeInTheDocument();
  });

  it("AC-2: selecting oauth2_password_grant renders exchange_timeout_seconds as number input with default 10", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    const timeoutInput = screen.getByTestId("field-input-exchange_timeout_seconds") as HTMLInputElement;
    expect(timeoutInput).toBeInTheDocument();
    expect(timeoutInput.type).toBe("number");
    // The default value "10" should come from f.defaultValue
    expect(timeoutInput.value).toBe("10");
    expect(timeoutInput.min).toBe("1");
    expect(timeoutInput.max).toBe("120");
  });

  // ── AC-3: submit payload contract ─────────────────────────────────────────

  it("AC-3: submit assembles correct value JSON matching contract (userName + $.data.token + timeout=30)", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    // Fill service_id
    const serviceIdInput = screen.getByTestId("field-input-service_id");
    await act(async () => {
      fireEvent.change(serviceIdInput, { target: { value: "svc_spotus" } });
    });

    // Fill token_url
    const tokenUrlInput = screen.getByTestId("field-input-token_url");
    await act(async () => {
      fireEvent.change(tokenUrlInput, {
        target: { value: "https://dashboard-api-ps-stag.azurewebsites.net/api/v1/Token" },
      });
    });

    // Fill kv row 0: key=userName, value=vrusu
    const key0 = screen.getByTestId("kv-key-0");
    const val0 = screen.getByTestId("kv-value-0");
    await act(async () => {
      fireEvent.change(key0, { target: { value: "userName" } });
      fireEvent.change(val0, { target: { value: "vrusu" } });
    });

    // Fill kv row 1: key=password, value=Asd123!
    const val1 = screen.getByTestId("kv-value-1");
    await act(async () => {
      fireEvent.change(val1, { target: { value: "Asd123!" } });
    });

    // Fill token_response_path
    const trpInput = screen.getByTestId("field-input-token_response_path");
    await act(async () => {
      fireEvent.change(trpInput, { target: { value: "$.data.token" } });
    });

    // Fill exchange_timeout_seconds = 30
    const timeoutInput = screen.getByTestId("field-input-exchange_timeout_seconds");
    await act(async () => {
      fireEvent.change(timeoutInput, { target: { value: "30" } });
    });

    // Mock successful API response
    mockResourceAction.mockResolvedValueOnce({
      data: { notice: { type: "success" } },
    });

    const submitBtn = screen.getByTestId("credential-new-submit");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(mockResourceAction).toHaveBeenCalledTimes(1);
    });

    const [call] = mockResourceAction.mock.calls;
    const data = call[0].data as Record<string, string>;

    expect(data.auth_scheme).toBe("oauth2_password_grant");
    expect(data.service_id).toBe("svc_spotus");

    // Parse the assembled value JSON
    const valueObj = JSON.parse(data.value) as {
      token_url: string;
      credential_fields: Record<string, string>;
      token_response_path: string;
      exchange_timeout_seconds: number;
    };

    expect(valueObj.token_url).toBe(
      "https://dashboard-api-ps-stag.azurewebsites.net/api/v1/Token"
    );
    expect(valueObj.credential_fields).toEqual({ userName: "vrusu", password: "Asd123!" });
    expect(valueObj.token_response_path).toBe("$.data.token");
    expect(valueObj.exchange_timeout_seconds).toBe(30); // must be integer, not string
  });

  // ── AC-5: other schemes unaffected ────────────────────────────────────────

  it("AC-5: bearer_token scheme still renders only the value field (unaffected)", async () => {
    await renderForm();
    // bearer_token is the default
    expect(screen.queryByTestId("kv-editor")).not.toBeInTheDocument();
    expect(screen.getByTestId("field-input-value")).toBeInTheDocument();
  });

  it("AC-5: switching to oauth2_password_grant and back to bearer_token hides kv-editor", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");
    expect(screen.getByTestId("kv-editor")).toBeInTheDocument();

    await selectScheme("bearer_token");
    expect(screen.queryByTestId("kv-editor")).not.toBeInTheDocument();
    expect(screen.getByTestId("field-input-value")).toBeInTheDocument();
  });

  // ── kv-editor interaction ─────────────────────────────────────────────────

  it("kv-editor: clicking + Add field adds a new empty row", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    const addBtn = screen.getByTestId("kv-add-row");
    await act(async () => {
      fireEvent.click(addBtn);
    });

    // Now there should be 3 rows
    expect(screen.getByTestId("kv-row-2")).toBeInTheDocument();
    const key2 = screen.getByTestId("kv-key-2") as HTMLInputElement;
    expect(key2.value).toBe("");
  });

  it("kv-editor: clicking remove on row 0 removes it", async () => {
    await renderForm();
    await selectScheme("oauth2_password_grant");

    const removeBtn0 = screen.getByTestId("kv-remove-0");
    await act(async () => {
      fireEvent.click(removeBtn0);
    });

    // Row 0 gone — old row 1 is now row 0
    expect(screen.queryByTestId("kv-row-1")).not.toBeInTheDocument();
    const key0 = screen.getByTestId("kv-key-0") as HTMLInputElement;
    expect(key0.value).toBe("password");
  });
});
