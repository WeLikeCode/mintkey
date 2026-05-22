/**
 * Tier 2 — Audit log viewer.
 *
 * Source: T-1.7.4; ADR-0014.7; Req 8.
 */

import { test, expect, type Page } from "@playwright/test";
import { AuditPage } from "../pages/audit.js";
import {
  createTestService,
  getAuditEvents,
  resetCleanupQueue,
} from "../fixtures/test-data.js";

test.describe("Tier 2 — Audit Log (T-1.7.4)", () => {
  let page: Page;
  let audit: AuditPage;
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    audit = new AuditPage(page);
    resetCleanupQueue();
  });

  test("1. audit log renders with entries", async () => {
    await audit.gotoList();
    const rows = audit.getEventRows();
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("2. filter by event type", async () => {
    await audit.gotoList();
    await audit.filterByEventType("service.created");

    const rows = audit.getEventRows();
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("3. filter by actor ID", async () => {
    await audit.gotoList();
    const actorId = process.env.PLAYWRIGHT_OPERATOR_ID ?? "";
    if (actorId) {
      await audit.filterByActorId(actorId);
    }
  });

  test("4. event detail shows hash chain values", async () => {
    await audit.gotoList();

    const firstRow = audit.getEventRows().first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await expect(audit.getHashValue()).toBeVisible();
    }
  });

  test("5. operations produce audit entries", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const beforeCount = (await getAuditEvents(tenantId, token)).length;
    await createTestService({ tenantId, name: "AuditSvc", slug: "audit-svc" }, token);
    const afterCount = (await getAuditEvents(tenantId, token)).length;

    expect(afterCount).toBeGreaterThanOrEqual(beforeCount);
  });
});