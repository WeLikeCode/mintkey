/**
 * Requests_Review_Area page object — the agent access-requests review screen.
 *
 * Backed by the AdminJS custom page registered as `pages["requests-review"]`
 * (label "Requests Review", component AccessRequestsPage) with rootPath
 * "/admin" ⇒ the page URL is `/admin/pages/requests-review`
 * (apps/admin-ui/src/index.ts).
 *
 * The page is an in-page master/detail component. Stable data-testids
 * (AccessRequestsPage.tsx, tasks 8.2 / 8.3):
 *   - access-requests-page            list container
 *   - row-<request_id>                a request row (contains a status Badge)
 *   - view-<request_id>               opens the detail view
 *   - access-request-detail           detail container
 *   - detail-status                   status text in the detail view
 *   - reject-reason                   reject reason textarea
 *   - action-approve / action-reject  action buttons
 *
 * NEW file — adds only new exports; touches no existing page object.
 *
 * Source: agent-access-requests spec Task 10.1; Req 15.1, 15.4, 15.5, 15.6, 15.10.
 */

import { type Page, type Locator, expect } from "@playwright/test";
import { BasePage } from "./base.js";

/** The AdminJS custom-page route for the Requests_Review_Area. */
export const REQUESTS_REVIEW_PATH = "/admin/pages/requests-review";

/** Hard navigation bound from Req 15.3 — login+nav must reach the area within 30s. */
export const NAV_TIMEOUT_MS = 30_000;

export class AccessRequestsPage extends BasePage {
  readonly listContainer: Locator;

  constructor(page: Page) {
    super(page);
    this.listContainer = page.locator('[data-testid="access-requests-page"]');
  }

  /**
   * Navigate to the Requests_Review_Area and assert it is reached within 30s
   * (Req 15.2 / 15.3). Tries the direct custom-page URL first, then falls back
   * to the "Requests Review" nav link (belt-and-suspenders against route drift).
   *
   * Throws (fails the test) with an explicit message if the area is not reached
   * in time — satisfying Req 15.3 and Req 15.10 (area absent ⇒ fail).
   */
  async gotoReviewArea(): Promise<void> {
    // Direct navigation to the AdminJS custom-page route. The SPA mounts the
    // page component after the shell loads, so wait for the container with a
    // generous bound (the probe shows it renders in <1s once mounted).
    await this.goto(REQUESTS_REVIEW_PATH);
    const reached = await this.listContainer
      .waitFor({ state: "visible", timeout: NAV_TIMEOUT_MS })
      .then(() => true)
      .catch(() => false);

    if (reached) return;

    // Fallback: click the dedicated nav-section link, then re-assert. The link
    // lives in a scrollable sidebar and can be outside the viewport, so scroll
    // it into view and force the click past any overlay before re-navigating.
    const navLink = this.page
      .locator("nav a, .sidebar a, a")
      .filter({ hasText: /Requests Review/i })
      .first();
    if (await navLink.count().then((n) => n > 0).catch(() => false)) {
      await navLink.scrollIntoViewIfNeeded().catch(() => {});
      await navLink.click({ force: true }).catch(() => {});
      await this.page.waitForLoadState("domcontentloaded");
    }

    await expect(
      this.listContainer,
      "Requests_Review_Area was not reached within 30s (login or navigation did not complete) — Req 15.3",
    ).toBeVisible({ timeout: NAV_TIMEOUT_MS });
  }

  /** Row locator for a request by its wire id. */
  row(requestId: string): Locator {
    return this.page.locator(`[data-testid="row-${requestId}"]`);
  }

  /**
   * Assert the seeded request is rendered by its request_id with the given
   * displayed status (Req 15.4). Status is rendered as a Badge inside the row.
   */
  async expectRowStatus(requestId: string, status: string): Promise<void> {
    const row = this.row(requestId);
    await expect(
      row,
      `request ${requestId} row should be rendered in the review area`,
    ).toBeVisible({ timeout: NAV_TIMEOUT_MS });
    await expect(
      row,
      `request ${requestId} should display status "${status}"`,
    ).toContainText(new RegExp(status, "i"));
  }

  /** Open the detail view for a request. Fails if the "View" control is absent (Req 15.10). */
  async openDetail(requestId: string): Promise<void> {
    const view = this.page.locator(`[data-testid="view-${requestId}"]`);
    await expect(
      view,
      `View control for ${requestId} must be present and functional — Req 15.10`,
    ).toBeVisible({ timeout: NAV_TIMEOUT_MS });
    await view.click();
    await expect(this.page.locator('[data-testid="access-request-detail"]')).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
  }

  /** The status text shown in the detail view. */
  detailStatus(): Locator {
    return this.page.locator('[data-testid="detail-status"]');
  }

  /**
   * Approve the currently-open request (Req 15.5). Fails if the Approve control
   * is absent or non-functional (Req 15.10).
   */
  async approve(): Promise<void> {
    const approveBtn = this.page.locator('[data-testid="action-approve"]');
    await expect(
      approveBtn,
      "Approve control must be present and functional — Req 15.10",
    ).toBeVisible({ timeout: NAV_TIMEOUT_MS });
    await expect(approveBtn, "Approve control must be enabled").toBeEnabled();
    await approveBtn.click();
    // After a successful action the page returns to the list and refreshes.
    await expect(this.listContainer).toBeVisible({ timeout: NAV_TIMEOUT_MS });
  }

  /**
   * Reject the currently-open request with a non-empty reason (Req 15.6). Fails
   * if the Reject control or reason field is absent or non-functional (Req 15.10).
   */
  async rejectWithReason(reason: string): Promise<void> {
    const reasonBox = this.page.locator('[data-testid="reject-reason"]');
    const rejectBtn = this.page.locator('[data-testid="action-reject"]');
    await expect(
      reasonBox,
      "Reject reason field must be present — Req 15.10",
    ).toBeVisible({ timeout: NAV_TIMEOUT_MS });
    await expect(
      rejectBtn,
      "Reject control must be present — Req 15.10",
    ).toBeVisible({ timeout: NAV_TIMEOUT_MS });

    await reasonBox.fill(reason);
    // The Reject button is disabled while the reason is empty (Req 8.5); a
    // non-empty reason must enable it — else the control is non-functional.
    await expect(
      rejectBtn,
      "Reject control must enable once a non-empty reason is entered — Req 15.10",
    ).toBeEnabled({ timeout: NAV_TIMEOUT_MS });
    await rejectBtn.click();
    await expect(this.listContainer).toBeVisible({ timeout: NAV_TIMEOUT_MS });
  }
}
