// @vitest-environment jsdom
/**
 * Render tests — EmailServiceOAuth2Setup component (C-10).
 *
 * AC covered:
 *   1. Component renders nothing (null) for non-oauth2 auth_scheme.
 *   2. Shows "Not yet authorized" warning when oauth2_authorized = false.
 *   3. Shows "Connected" status when oauth2_authorized = true.
 *   4. Authorize button label changes based on authorization status.
 *   5. Clicking Authorize button POSTs to the correct endpoint and opens popup.
 *   6. Network/fetch error shows error message.
 *   7. Non-ok API response shows error message from response body.
 *   8. oauth2_error=state_mismatch in URL query params shows correct error text.
 *   9. oauth2_error=state_expired in URL query params shows correct error text.
 *  10. oauth2_success=1 in URL query params shows success banner.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Import stubs to set up the search params mock before the component
import { searchParamsMock } from "./__mocks__/react-router-dom-stub.js";

import EmailServiceOAuth2Setup from "../src/components/actions/EmailServiceOAuth2Setup.js";

// ── helpers ───────────────────────────────────────────────────────────────────

type RecordProps = {
  id?: string;
  params?: Record<string, unknown>;
};

function makeProps(
  params: Record<string, unknown> = {},
  id = "esvc_abc123"
): { record: RecordProps } {
  return {
    record: {
      id,
      params: {
        tenant_id: "t_test",
        ...params,
      },
    },
  };
}

async function renderComponent(props: { record: RecordProps }) {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(React.createElement(EmailServiceOAuth2Setup, props as never));
  });
  return result;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("EmailServiceOAuth2Setup — C-10 (jsdom)", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    // Clear URL search params between tests
    searchParamsMock.delete("oauth2_error");
    searchParamsMock.delete("oauth2_success");
    // Spy on window.fetch
    fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ auth_url: "https://accounts.google.com/oauth2/auth?state=xyz" }),
    } as Response);
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  // ── Test 1: null render for non-oauth2 scheme ─────────────────────────────

  it("renders nothing for auth_scheme != email_oauth2", async () => {
    const { container } = await renderComponent(
      makeProps({ auth_scheme: "email_password", provider: "gmail" })
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when auth_scheme is undefined", async () => {
    const { container } = await renderComponent(makeProps({}));
    expect(container.firstChild).toBeNull();
  });

  // ── Test 2: unauthorized state ────────────────────────────────────────────

  it("shows unauthorized warning when oauth2_authorized = false", async () => {
    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );
    expect(screen.getByTestId("oauth2-unauthorized-status")).toBeInTheDocument();
    expect(screen.queryByTestId("oauth2-authorized-status")).not.toBeInTheDocument();
  });

  // ── Test 3: authorized state ──────────────────────────────────────────────

  it("shows connected status when oauth2_authorized = true", async () => {
    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: true,
      })
    );
    expect(screen.getByTestId("oauth2-authorized-status")).toBeInTheDocument();
    expect(screen.queryByTestId("oauth2-unauthorized-status")).not.toBeInTheDocument();
  });

  // ── Test 4: button label ──────────────────────────────────────────────────

  it('authorize button says "Authorize with Gmail →" when not yet authorized', async () => {
    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );
    const btn = screen.getByTestId("oauth2-authorize-button");
    expect(btn.textContent).toMatch(/Authorize with Gmail/i);
  });

  it('authorize button says "Re-authorize with Gmail →" when already authorized', async () => {
    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: true,
      })
    );
    const btn = screen.getByTestId("oauth2-authorize-button");
    expect(btn.textContent).toMatch(/Re-authorize with Gmail/i);
  });

  // ── Test 5: clicking authorize POSTs to the correct endpoint ─────────────

  it("clicking Authorize calls POST /v1/tenants/{tid}/email-services/{sid}/oauth2/gmail/authorize", async () => {
    // Mock window.open to avoid JSDOM issues
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);

    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );

    const btn = screen.getByTestId("oauth2-authorize-button");
    await act(async () => {
      fireEvent.click(btn);
    });

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/v1/tenants/t_test/email-services/esvc_abc123/oauth2/gmail/authorize"),
        expect.objectContaining({ method: "POST" })
      );
    });

    openSpy.mockRestore();
  });

  it("opens popup with auth_url returned by the authorize endpoint", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue({} as Window);

    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("oauth2-authorize-button"));
    });

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        "https://accounts.google.com/oauth2/auth?state=xyz",
        "oauth2_authorize",
        expect.any(String)
      );
    });

    openSpy.mockRestore();
  });

  // ── Test 6: fetch network error ───────────────────────────────────────────

  it("shows error message when fetch throws", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("Network failure"));

    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("oauth2-authorize-button"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("oauth2-error")).toBeInTheDocument();
      expect(screen.getByTestId("oauth2-error").textContent).toMatch(/Network failure/i);
    });
  });

  // ── Test 7: non-ok API response ───────────────────────────────────────────

  it("shows error from response body when authorize endpoint returns non-ok", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "Provider not configured" }),
    } as Response);

    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("oauth2-authorize-button"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("oauth2-error")).toBeInTheDocument();
      expect(screen.getByTestId("oauth2-error").textContent).toContain("Provider not configured");
    });
  });

  // ── Test 8: oauth2_error=state_mismatch in URL ────────────────────────────

  it("shows CSRF state mismatch error when oauth2_error=state_mismatch is in URL", async () => {
    searchParamsMock.set("oauth2_error", "state_mismatch");

    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );

    expect(screen.getByTestId("oauth2-error")).toBeInTheDocument();
    expect(screen.getByTestId("oauth2-error").textContent).toMatch(/state mismatch/i);
  });

  // ── Test 9: oauth2_error=state_expired in URL ─────────────────────────────

  it("shows state expired error when oauth2_error=state_expired is in URL", async () => {
    searchParamsMock.set("oauth2_error", "state_expired");

    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: false,
      })
    );

    expect(screen.getByTestId("oauth2-error")).toBeInTheDocument();
    expect(screen.getByTestId("oauth2-error").textContent).toMatch(/state expired/i);
  });

  // ── Test 10: oauth2_success=1 in URL ──────────────────────────────────────

  it("shows success banner when oauth2_success=1 is in URL", async () => {
    searchParamsMock.set("oauth2_success", "1");

    await renderComponent(
      makeProps({
        auth_scheme: "email_oauth2",
        provider: "gmail",
        oauth2_authorized: true,
      })
    );

    expect(screen.getByTestId("oauth2-success-banner")).toBeInTheDocument();
    expect(screen.getByTestId("oauth2-success-banner").textContent).toMatch(/successful/i);
  });
});
