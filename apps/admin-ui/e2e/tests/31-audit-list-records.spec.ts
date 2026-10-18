/**
 * Phase 1a — audit_events listKey fix verification.
 *
 * Root cause: audit.ts had `listKey: "items"` but admin-api returns `{"events": [...]}`.
 * Fix: change listKey to "events".
 *
 * Curl baseline: GET /v1/tenants/9593e3ba-4102-4235-9748-28d35b473214/audit?limit=500
 * returned 500 events (paged). We assert ≥10 rows visible in the UI.
 *
 * Source: Phase 1a of action-grid completion; ADMIN_UI_ACTION_MATRIX.md.
 */

import { TENANT_ID } from "../env.js";
import { createTestService } from "../fixtures/test-data.js";
import { test, expect } from "../fixtures/test.js";
import { AuditPage } from "../pages/audit.js";

test.describe("Phase 1a — audit_events list shows records (listKey fix)", () => {
  test("audit_events list renders ≥10 rows after listKey corrected to events", async ({ page }) => {
    const audit = new AuditPage(page);
    await audit.gotoList();
    await page.waitForLoadState("networkidle");

    const rows = audit.getEventRows();
    const count = await rows.count();

    // Baseline from curl: ≥500 events exist; a page should show ≥10.
    // Before the fix (listKey: "items") count === 0 — table shows "No records".
    expect(count, `Expected ≥10 audit rows visible, got ${count} (listKey mismatch?)`).toBeGreaterThanOrEqual(10);
  });

  test("audit_events list rows contain expected columns (event_type visible)", async ({ page }) => {
    // Seed a service.registered event so the assertion does not depend on what ran before.
    await createTestService({ tenantId: TENANT_ID, name: "audit-seed", baseUrl: "https://audit-seed.example.com" });

    const audit = new AuditPage(page);
    await audit.gotoList();
    await page.waitForLoadState("networkidle");

    // The listProperties include event_type — at least one cell should contain a known event type.
    const rows = audit.getEventRows();
    const count = await rows.count();

    // Guard: only assert column content when rows are actually populated.
    expect(count, "Need rows to verify column content").toBeGreaterThanOrEqual(1);

    // At least one row should contain a recognisable event_type pattern. (The list is not
    // ordered by entity type: on a fresh stack the first row can be an operator.session.created
    // event, so look at the whole page, as this comment always intended.)
    // The list renders known event types as human labels ("Agent Created", "Agent Permission Granted")
    // and unknown ones raw ("service.permission_grants.cascade_deleted"), so accept both spellings.
    const allRowsText = (await rows.allTextContents()).join("\n");
    expect(allRowsText).toMatch(/(service|agent|credential|permission|api[_ ]key)[. ]/i);
  });
});
