// @vitest-environment jsdom
/**
 * REAL render tests for ServiceTemplatePicker (Kiro task 12.2).
 *
 * Uses @testing-library/react + jsdom.  External deps that are not installed as
 * direct deps (ApiClient, @adminjs/design-system, react-router-dom) are resolved
 * via vitest.config.ts aliases to local stubs in tests/__mocks__/.
 *
 * Covers:
 *   12.2 — category groups render; search filters; template selection pre-fills
 *           form; submit calls from-template BFF endpoint.
 *   FIX-8 re-verify — BUG-7a: 2xx-without-id / non-2xx → RED error, not green;
 *                     BUG-19: only the selected card is highlighted.
 *   FIX-9 re-verify — credential-hint-panel renders token_url / field names /
 *                     token_response_path for oauth2_password_grant template.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Import the resourceAction mock handle from the adminjs stub so tests can
// control return values.  The alias in vitest.config.ts maps "adminjs" to this
// stub for both the test file and the component under test.
import { resourceAction as mockResourceAction } from "./__mocks__/adminjs-stub.js";

// Import the navigate mock from the react-router-dom stub.
import { navigate as mockNavigate } from "./__mocks__/react-router-dom-stub.js";

// Component under test — imported AFTER all stubs are set up.
import ServiceTemplatePicker from "../src/components/actions/ServiceTemplatePicker.js";

// ── Fixtures ─────────────────────────────────────────────────────────────────

const TEMPLATE_CI = {
  template_id: "tpl-ci-001",
  slug: "github-actions",
  name: "github-actions",
  display_name: "GitHub Actions",
  description: "CI/CD via GitHub Actions API",
  category: "ci_cd",
  auth_type: "bearer",
  version: "1.0",
};

const TEMPLATE_PLATFORM = {
  template_id: "tpl-plat-001",
  slug: "aws-platform",
  name: "aws-platform",
  display_name: "AWS Platform",
  description: "AWS API integration",
  category: "platform",
  auth_type: "bearer",
  version: "2.0",
};

const TEMPLATE_OAUTH = {
  template_id: "tpl-oauth-001",
  slug: "azure-dashboard",
  name: "azure-dashboard",
  display_name: "Azure Dashboard API",
  description: "oauth2_password_grant-based Azure service",
  category: "platform",
  auth_type: "oauth2_password_grant",
  version: "1.0",
  credential_hint: {
    token_url: "https://login.microsoftonline.com/tenant/oauth2/token",
    credential_fields: { username: "string", password: "string" },
    token_response_path: "$.access_token",
  },
};

// Helper: render the picker with a successful template-list response.
// The first resourceAction call is always the template-list fetch on mount.
async function renderWithTemplates(templates: unknown[] = [TEMPLATE_CI, TEMPLATE_PLATFORM]) {
  mockResourceAction.mockResolvedValueOnce({ data: { templates } });
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(React.createElement(ServiceTemplatePicker));
  });
  return result;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ServiceTemplatePicker — render (jsdom)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── 12.2 category groups ──────────────────────────────────────────────────

  it("12.2: renders category group headers for each category in the template list", async () => {
    await renderWithTemplates([TEMPLATE_CI, TEMPLATE_PLATFORM]);

    expect(screen.getByTestId("template-category-ci_cd")).toBeInTheDocument();
    expect(screen.getByTestId("template-category-platform")).toBeInTheDocument();

    expect(screen.getByTestId("template-category-header-ci_cd")).toHaveTextContent("CI/CD");
    expect(screen.getByTestId("template-category-header-platform")).toHaveTextContent("Platform");
  });

  it("12.2: renders individual template cards inside their category group", async () => {
    await renderWithTemplates([TEMPLATE_CI, TEMPLATE_PLATFORM]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    expect(ciCard).toBeInTheDocument();
    expect(ciCard).toHaveTextContent("GitHub Actions");

    const platCard = screen.getByTestId(`template-card-${TEMPLATE_PLATFORM.template_id}`);
    expect(platCard).toBeInTheDocument();
    expect(platCard).toHaveTextContent("AWS Platform");
  });

  // ── 12.2 search filtering ─────────────────────────────────────────────────

  it("12.2: typing in search input filters templates — only matching cards are visible", async () => {
    await renderWithTemplates([TEMPLATE_CI, TEMPLATE_PLATFORM]);

    const searchInput = screen.getByTestId("template-search-input");
    expect(searchInput).toBeInTheDocument();

    await act(async () => {
      fireEvent.change(searchInput, { target: { value: "github" } });
    });

    expect(screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`)).toBeInTheDocument();
    expect(screen.queryByTestId(`template-card-${TEMPLATE_PLATFORM.template_id}`)).not.toBeInTheDocument();
  });

  it("12.2: clearing search term restores all templates", async () => {
    await renderWithTemplates([TEMPLATE_CI, TEMPLATE_PLATFORM]);

    const searchInput = screen.getByTestId("template-search-input");

    await act(async () => {
      fireEvent.change(searchInput, { target: { value: "github" } });
    });
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: "" } });
    });

    expect(screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`)).toBeInTheDocument();
    expect(screen.getByTestId(`template-card-${TEMPLATE_PLATFORM.template_id}`)).toBeInTheDocument();
  });

  // ── 12.2 template selection pre-fills form ────────────────────────────────

  it("12.2: clicking a template card opens the detail panel and pre-fills the override form", async () => {
    await renderWithTemplates([TEMPLATE_CI, TEMPLATE_PLATFORM]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(ciCard);
    });

    expect(screen.getByTestId("template-detail-panel")).toBeInTheDocument();

    const nameInput = screen.getByTestId("override-name") as HTMLInputElement;
    expect(nameInput.value).toBe(TEMPLATE_CI.name);

    const displayNameInput = screen.getByTestId("override-display_name") as HTMLInputElement;
    expect(displayNameInput.value).toBe(TEMPLATE_CI.display_name);
  });

  // ── 12.2 submit calls from-template endpoint ──────────────────────────────

  it("12.2: clicking submit calls resourceAction for 'from-template' with the template_id", async () => {
    await renderWithTemplates([TEMPLATE_CI]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(ciCard);
    });

    mockResourceAction.mockResolvedValueOnce({
      data: { service: { id: "svc-new-abc" } },
    });

    const submitBtn = screen.getByTestId("template-submit-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(mockResourceAction).toHaveBeenCalledWith(
      expect.objectContaining({
        resourceId: "services",
        actionName: "from-template",
        method: "post",
        data: expect.objectContaining({ template_id: TEMPLATE_CI.template_id }),
      })
    );
  });

  it("12.2: successful submit (real id) shows green success banner, NOT an error", async () => {
    await renderWithTemplates([TEMPLATE_CI]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(ciCard);
    });

    mockResourceAction.mockResolvedValueOnce({
      data: { service: { id: "svc-123" } },
    });

    const submitBtn = screen.getByTestId("template-submit-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("template-submit-success")).toBeInTheDocument();
    });

    expect(screen.queryByTestId("template-submit-error")).not.toBeInTheDocument();
  });

  // ── FIX-8 re-verify — BUG-7a ─────────────────────────────────────────────

  it("FIX-8 BUG-7a: 2xx response without 'id' shows RED error, not green success", async () => {
    await renderWithTemplates([TEMPLATE_CI]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(ciCard);
    });

    // 2xx-shaped response from BFF but service has no id
    mockResourceAction.mockResolvedValueOnce({
      data: { service: {} },
    });

    const submitBtn = screen.getByTestId("template-submit-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("template-submit-error")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("template-submit-success")).not.toBeInTheDocument();
    expect(screen.getByTestId("template-submit-error")).toHaveTextContent(/unexpected response/i);
  });

  it("FIX-8 BUG-7a: notice.type=error in response shows RED error, not green success", async () => {
    await renderWithTemplates([TEMPLATE_CI]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(ciCard);
    });

    mockResourceAction.mockResolvedValueOnce({
      data: {
        notice: { message: "Template not found", type: "error" },
      },
    });

    const submitBtn = screen.getByTestId("template-submit-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("template-submit-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("template-submit-error")).toHaveTextContent("Template not found");
    expect(screen.queryByTestId("template-submit-success")).not.toBeInTheDocument();
  });

  it("FIX-8 BUG-7a: rejected promise (network error) shows RED error, not green success", async () => {
    await renderWithTemplates([TEMPLATE_CI]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(ciCard);
    });

    mockResourceAction.mockRejectedValueOnce(new Error("Network failure"));

    const submitBtn = screen.getByTestId("template-submit-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("template-submit-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("template-submit-error")).toHaveTextContent("Network failure");
    expect(screen.queryByTestId("template-submit-success")).not.toBeInTheDocument();
  });

  // ── FIX-8 re-verify — BUG-19 (only selected card highlighted) ────────────

  it("FIX-8 BUG-19: only the selected template card has the selected highlight style", async () => {
    // Two templates with same name — this was the BUG-19 trigger: name-based matching
    // caused both to highlight. Fix: match on template_id only.
    const TEMPLATE_CI2 = {
      ...TEMPLATE_CI,
      template_id: "tpl-ci-002",
      slug: "github-actions-v2",
    };
    await renderWithTemplates([TEMPLATE_CI, TEMPLATE_CI2]);

    const card1 = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(card1);
    });

    // card1 has the selected border
    expect(card1).toHaveStyle({ border: "2px solid #0d6efd" });

    // card2 does NOT have the selected border
    const card2 = screen.getByTestId(`template-card-${TEMPLATE_CI2.template_id}`);
    expect(card2).not.toHaveStyle({ border: "2px solid #0d6efd" });

    // Click card2 — now only card2 is selected
    await act(async () => {
      fireEvent.click(card2);
    });

    expect(card2).toHaveStyle({ border: "2px solid #0d6efd" });
    const card1After = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    expect(card1After).not.toHaveStyle({ border: "2px solid #0d6efd" });
  });

  // ── FIX-9 re-verify — credential-hint-panel for oauth2_password_grant ─────

  it("FIX-9: selecting oauth2_password_grant template renders credential-hint-panel with token_url, field names, token_response_path", async () => {
    await renderWithTemplates([TEMPLATE_OAUTH]);

    const oauthCard = screen.getByTestId(`template-card-${TEMPLATE_OAUTH.template_id}`);
    await act(async () => {
      fireEvent.click(oauthCard);
    });

    const hintPanel = screen.getByTestId("credential-hint-panel");
    expect(hintPanel).toBeInTheDocument();

    // token_url rendered
    expect(hintPanel).toHaveTextContent(
      "https://login.microsoftonline.com/tenant/oauth2/token"
    );

    // credential field names rendered
    expect(hintPanel).toHaveTextContent("username");
    expect(hintPanel).toHaveTextContent("password");

    // token_response_path rendered
    expect(hintPanel).toHaveTextContent("$.access_token");
  });

  it("FIX-9: selecting a template WITHOUT credential_hint does NOT render credential-hint-panel", async () => {
    await renderWithTemplates([TEMPLATE_CI]);

    const ciCard = screen.getByTestId(`template-card-${TEMPLATE_CI.template_id}`);
    await act(async () => {
      fireEvent.click(ciCard);
    });

    expect(screen.queryByTestId("credential-hint-panel")).not.toBeInTheDocument();
  });
});
