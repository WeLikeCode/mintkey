/**
 * MANDATORY headless Admin UI end-to-end test — Requests_Review_Area (Req 15).
 *
 * Reviewable evidence that the operator review screen for agent access requests
 * actually exists and works. Two independent test cases:
 *
 *   • Approve            — seed a pending request, approve it in the UI, assert
 *                          the displayed status becomes "approved" (Req 15.5).
 *   • Reject-with-reason — seed a SEPARATE pending request, submit a non-empty
 *                          reason, assert the status becomes "rejected" and the
 *                          reason is displayed (Req 15.6).
 *
 * Both cases:
 *   - log into the Admin Console and navigate to the Requests_Review_Area,
 *     failing if that is not reached within 30s (Req 15.2 / 15.3);
 *   - assert the pre-seeded pending request is rendered by its request_id with
 *     status "pending" (Req 15.4);
 *   - capture a SCREENSHOT + Playwright TRACE at (a) first-visible pending and
 *     (b) post-action status, retained as CI artifacts a reviewer can open
 *     (Req 15.7 / 15.8);
 *   - fail if the Requests_Review_Area or its Approve / Reject controls are
 *     absent or non-functional (Req 15.10).
 *
 * Artifact retention:
 *   - `test.use({ trace: "on" })` forces a Playwright trace to be recorded and
 *     retained for EVERY run (not only on retry), landing under
 *     apps/admin-ui/e2e/test-results/ — which .github/workflows/playwright.yml
 *     uploads. The two mid-test trace groups mark the required capture points.
 *   - `testInfo.attach()` writes each screenshot into the HTML report
 *     (apps/admin-ui/e2e/playwright-report/), also uploaded by the workflow.
 *
 * NEW spec — no existing test is modified (Req 15.9 / Req 14.2).
 *
 * Source: agent-access-requests spec Task 10.1; Req 15.1–15.10;
 *         .github/workflows/playwright.yml; AccessRequestsPage.tsx (testids).
 */

import { test, expect, type TestInfo, type Page } from "@playwright/test";
import { AccessRequestsPage } from "../pages/access-requests.js";
import { seedPendingAccessRequest, type SeededAccessRequest } from "../fixtures/access-requests-seed.js";
import { resetCleanupQueue } from "../fixtures/test-data.js";

// Force a full trace for every run (Req 15.7 / 15.8) — retained regardless of
// pass/fail, unlike the config default of "on-first-retry".
test.use({ trace: "on" });

const TENANT_ID = process.env.PLAYWRIGHT_TENANT_ID ?? "";
const API_JWT = process.env.PLAYWRIGHT_API_JWT ?? "";

/** Attach a PNG screenshot of the current page as a retained report artifact. */
async function captureScreenshot(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const png = await page.screenshot({ fullPage: true });
  await testInfo.attach(name, { body: png, contentType: "image/png" });
}

test.describe("44 — Requests_Review_Area e2e (Req 15)", () => {
  test.beforeAll(() => {
    // The stack + OIDC login are provided by the workflow (global-setup builds
    // state.json). Without a password there is no authenticated session, so the
    // mandatory review-screen evidence cannot be produced — fail loudly rather
    // than silently skip (this is a MANDATORY test, Req 15.1).
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS is required — the mandatory Requests_Review_Area e2e cannot run unauthenticated",
    ).not.toEqual("");
    expect(
      TENANT_ID,
      "PLAYWRIGHT_TENANT_ID is required to seed a pending access request",
    ).not.toEqual("");
  });

  test.beforeEach(() => {
    resetCleanupQueue();
  });

  test("Approve: pending request → operator approves → status becomes approved", async ({
    page,
  }, testInfo) => {
    const seeded: SeededAccessRequest = await seedPendingAccessRequest(
      { tenantId: TENANT_ID, label: "approve" },
      API_JWT,
    );

    const review = new AccessRequestsPage(page);

    // Req 15.2 / 15.3 — login (via stored state) + navigate within 30s.
    await review.gotoReviewArea();

    // Req 15.4 — the seeded pending request is rendered by its request_id.
    await test.step("first-visible pending → capture screenshot + trace", async () => {
      await review.expectRowStatus(seeded.requestId, "pending");
      // (a) capture point — first-visible pending (Req 15.7).
      await captureScreenshot(page, testInfo, `approve-01-pending-${seeded.requestId}.png`);
    });

    // Req 15.5 — exercise Approve on the visible request.
    await review.openDetail(seeded.requestId);
    await expect(review.detailStatus(), "detail should show pending before approve").toContainText(
      /pending/i,
    );
    await review.approve();

    // Req 15.5 — the displayed status changes to "approved".
    await test.step("post-action approved → capture screenshot + trace", async () => {
      await review.expectRowStatus(seeded.requestId, "approved");
      // Re-open the detail so the resulting status is displayed there too.
      await review.openDetail(seeded.requestId);
      await expect(
        review.detailStatus(),
        `request ${seeded.requestId} status should be "approved" after Approve — Req 15.5`,
      ).toContainText(/approved/i);
      // (b) capture point — post-action status (Req 15.7).
      await captureScreenshot(page, testInfo, `approve-02-approved-${seeded.requestId}.png`);
    });
  });

  test("Reject-with-reason: pending request → operator rejects → status rejected + reason shown", async ({
    page,
  }, testInfo) => {
    const rejectReason = "Denied by e2e: agent scope not justified for this action.";
    const seeded: SeededAccessRequest = await seedPendingAccessRequest(
      { tenantId: TENANT_ID, label: "reject" },
      API_JWT,
    );

    const review = new AccessRequestsPage(page);

    // Req 15.2 / 15.3 — login (via stored state) + navigate within 30s.
    await review.gotoReviewArea();

    // Req 15.4 — the seeded pending request is rendered by its request_id.
    await test.step("first-visible pending → capture screenshot + trace", async () => {
      await review.expectRowStatus(seeded.requestId, "pending");
      // (a) capture point — first-visible pending (Req 15.7).
      await captureScreenshot(page, testInfo, `reject-01-pending-${seeded.requestId}.png`);
    });

    // Req 15.6 — exercise Reject-with-reason on the visible request.
    await review.openDetail(seeded.requestId);
    await review.rejectWithReason(rejectReason);

    // Req 15.6 — the displayed status changes to "rejected" and the reason shows.
    await test.step("post-action rejected → capture screenshot + trace", async () => {
      await review.expectRowStatus(seeded.requestId, "rejected");
      await review.openDetail(seeded.requestId);
      await expect(
        review.detailStatus(),
        `request ${seeded.requestId} status should be "rejected" after Reject — Req 15.6`,
      ).toContainText(/rejected/i);
      // The submitted reason must be displayed on the request detail (Req 15.6).
      await expect(
        page.locator('[data-testid="access-request-detail"]'),
        "the submitted rejection reason must be displayed — Req 15.6",
      ).toContainText(rejectReason);
      // (b) capture point — post-action status (Req 15.7).
      await captureScreenshot(page, testInfo, `reject-02-rejected-${seeded.requestId}.png`);
    });
  });
});
