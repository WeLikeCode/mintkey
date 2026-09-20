// @vitest-environment jsdom
/**
 * Render tests for AccessRequestsPage — the Requests_Review_Area (Task 8.2).
 *
 * Covers:
 *   - List renders expected columns (Kind, Status, Requesting Agent, Target,
 *     Created, Expires) and rows
 *   - Empty state when zero records
 *   - Status + kind filter controls render and filter client-side
 *   - Fetches from /admin/api/access-requests on mount
 *   - Row "View" opens the detail; detail fetches /admin/api/access-requests/:id
 *   - Integration proposal detail renders non-secret config + EMPTY, labelled
 *     operator-supplied secret inputs (Req 4.6)
 *   - Action controls (Approve/Reject/Test/Finalize) render as disabled seams
 *     for Task 8.3
 *
 * Requirements: 4.1, 4.2, 4.5, 4.6.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";

import AccessRequestsPage from "../src/components/pages/AccessRequestsPage.js";
import type { AccessRequest } from "../src/components/pages/access-requests.utils.js";

function makeRequest(overrides: Partial<AccessRequest> = {}): AccessRequest {
  return {
    request_id: "request_01ACCESS00000000000000001",
    kind: "access",
    status: "pending",
    requesting_agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAA1",
    service_id: "svc_01SERVICE0000000000000001",
    action: "read",
    target_agent_id: null,
    share_direction: null,
    proposed_config: null,
    reason: null,
    created_at: "2026-06-01T00:00:00Z",
    expires_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

const accessReq = makeRequest();

const shareReq = makeRequest({
  request_id: "request_01SHARE000000000000000001",
  kind: "share",
  target_agent_id: "agent_01TARGET00000000000000001",
  share_direction: "outbound",
  action: "write",
});

const integrationReq = makeRequest({
  request_id: "request_01INTEGRATION00000000001",
  kind: "integration",
  service_id: null,
  action: null,
  proposed_config: {
    name: "Stripe API",
    auth_scheme: "api_key_header",
    base_url: "https://api.stripe.com",
    header_name: "Authorization",
  },
});

function mockFetchList(records: AccessRequest[]) {
  global.fetch = vi.fn().mockImplementation((url: string) => {
    // list endpoint (no /:id)
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(records),
    });
  });
}

describe("AccessRequestsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches from /admin/api/access-requests on mount", async () => {
    mockFetchList([accessReq]);
    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/admin/api/access-requests");
    });
  });

  it("renders all expected list columns", async () => {
    mockFetchList([accessReq]);
    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() => expect(screen.getByText("Kind")).toBeInTheDocument());
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Requesting Agent")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Expires")).toBeInTheDocument();
  });

  it("renders a row with the target summary", async () => {
    mockFetchList([accessReq]);
    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId(`row-${accessReq.request_id}`)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(`${accessReq.service_id} · ${accessReq.action}`),
    ).toBeInTheDocument();
  });

  it("renders empty state when zero records", async () => {
    mockFetchList([]);
    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId("empty-state")).toBeInTheDocument(),
    );
  });

  it("renders status and kind filter controls", async () => {
    mockFetchList([accessReq]);
    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId("filter-status")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("filter-kind")).toBeInTheDocument();
  });

  it("kind filter hides non-matching rows client-side", async () => {
    mockFetchList([accessReq, shareReq]);
    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() => {
      expect(screen.getByTestId(`row-${accessReq.request_id}`)).toBeInTheDocument();
      expect(screen.getByTestId(`row-${shareReq.request_id}`)).toBeInTheDocument();
    });

    const kindFilter = screen.getByTestId("filter-kind");
    await act(async () => {
      fireEvent.change(kindFilter, { target: { value: "share" } });
    });

    await waitFor(() => {
      expect(
        screen.queryByTestId(`row-${accessReq.request_id}`),
      ).not.toBeInTheDocument();
      expect(
        screen.getByTestId(`row-${shareReq.request_id}`),
      ).toBeInTheDocument();
    });
  });

  it("View opens detail and fetches the request by id", async () => {
    // list returns accessReq; detail fetch returns the same
    global.fetch = vi.fn().mockImplementation((url: string) => {
      const body = url.includes(accessReq.request_id) && url.endsWith(accessReq.request_id)
        ? accessReq
        : [accessReq];
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
      });
    });

    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId(`view-${accessReq.request_id}`)).toBeInTheDocument(),
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId(`view-${accessReq.request_id}`));
    });

    await waitFor(() =>
      expect(screen.getByTestId("access-request-detail")).toBeInTheDocument(),
    );
    expect(global.fetch).toHaveBeenCalledWith(
      `/admin/api/access-requests/${accessReq.request_id}`,
    );
  });

  it("integration detail renders non-secret config + EMPTY labelled secret inputs", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      const isDetail = url.endsWith(integrationReq.request_id);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(isDetail ? integrationReq : [integrationReq]),
      });
    });

    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId(`view-${integrationReq.request_id}`)).toBeInTheDocument(),
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId(`view-${integrationReq.request_id}`));
    });

    await waitFor(() =>
      expect(screen.getByTestId("integration-detail")).toBeInTheDocument(),
    );

    // Non-secret config rendered as EDITABLE inputs seeded from proposed_config
    // (Task 8.3 — operator may edit before finalize, Req 6.2).
    expect((screen.getByTestId("config-input-name") as HTMLInputElement).value).toBe(
      "Stripe API",
    );
    expect(
      (screen.getByTestId("config-input-base_url") as HTMLInputElement).value,
    ).toBe("https://api.stripe.com");

    // api_key_header → the "value" field is the secret; rendered EMPTY + labelled
    const secretInput = screen.getByTestId("secret-input-value") as HTMLInputElement;
    expect(secretInput).toBeInTheDocument();
    expect(secretInput.value).toBe("");
    expect(secretInput.type).toBe("password");
    expect(screen.getByTestId("secret-field-value")).toHaveTextContent(
      "operator-supplied",
    );
  });

  it("renders functional action controls for an integration proposal (Task 8.3)", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      const isDetail = url.endsWith(integrationReq.request_id);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(isDetail ? integrationReq : [integrationReq]),
      });
    });

    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId(`view-${integrationReq.request_id}`)).toBeInTheDocument(),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId(`view-${integrationReq.request_id}`));
    });
    await waitFor(() =>
      expect(screen.getByTestId("action-seam")).toBeInTheDocument(),
    );

    // Integration proposals finalize (not approve) → no Approve button; Test + Finalize present.
    expect(screen.queryByTestId("action-approve")).not.toBeInTheDocument();
    expect(screen.getByTestId("action-test")).toBeInTheDocument();
    expect(screen.getByTestId("action-finalize")).toBeInTheDocument();

    // Reject is disabled until a reason is entered (Req 8.5).
    expect(screen.getByTestId("action-reject")).toBeDisabled();
    // Finalize is disabled until the required operator secret is supplied (Req 6.8).
    expect(screen.getByTestId("action-finalize")).toBeDisabled();
    // Test connection is available (does not require a reason).
    expect(screen.getByTestId("action-test")).not.toBeDisabled();
  });

  it("enables Reject once a non-empty reason is entered (Req 8.5)", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      const isDetail = url.endsWith(accessReq.request_id);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(isDetail ? accessReq : [accessReq]),
      });
    });

    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId(`view-${accessReq.request_id}`)).toBeInTheDocument(),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId(`view-${accessReq.request_id}`));
    });
    await waitFor(() => expect(screen.getByTestId("action-reject")).toBeInTheDocument());

    // Access request → Approve rendered and enabled; Reject blocked until reason present.
    expect(screen.getByTestId("action-approve")).not.toBeDisabled();
    expect(screen.getByTestId("action-reject")).toBeDisabled();

    await act(async () => {
      fireEvent.change(screen.getByTestId("reject-reason"), {
        target: { value: "not appropriate" },
      });
    });
    expect(screen.getByTestId("action-reject")).not.toBeDisabled();

    // Whitespace-only does not count (Req 8.5).
    await act(async () => {
      fireEvent.change(screen.getByTestId("reject-reason"), {
        target: { value: "   " },
      });
    });
    expect(screen.getByTestId("action-reject")).toBeDisabled();
  });

  it("enables Finalize only after the required secret is supplied (Req 6.8)", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      const isDetail = url.endsWith(integrationReq.request_id);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(isDetail ? integrationReq : [integrationReq]),
      });
    });

    await act(async () => {
      render(React.createElement(AccessRequestsPage));
    });
    await waitFor(() =>
      expect(screen.getByTestId(`view-${integrationReq.request_id}`)).toBeInTheDocument(),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId(`view-${integrationReq.request_id}`));
    });
    await waitFor(() =>
      expect(screen.getByTestId("action-finalize")).toBeInTheDocument(),
    );

    expect(screen.getByTestId("action-finalize")).toBeDisabled();

    await act(async () => {
      fireEvent.change(screen.getByTestId("secret-input-value"), {
        target: { value: "sk_live_supersecret" },
      });
    });
    expect(screen.getByTestId("action-finalize")).not.toBeDisabled();
  });
});
