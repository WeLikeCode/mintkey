/**
 * Audit Log page object — read-only view with filtering and pagination.
 *
 * Source: T-1.7.4; ADR-0014.7; Req 8.
 */

import { type Page, type Locator } from "@playwright/test";
import { BasePage } from "./base.js";

export class AuditPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async gotoList() {
    await this.goto("/admin/resources/audit_events");
  }

  // ── Filter controls ────────────────────────────────────
  getFilterInput(name: string | RegExp) {
    return this.page.getByLabel(name, { exact: false });
  }

  async filterByEventType(eventType: string) {
    await this.getFilterInput(/event.type|event_type/i).fill(eventType);
    // AdminJS auto-submits filters or we may need to press Enter
    await this.page.keyboard.press("Enter");
  }

  async filterByActorId(actorId: string) {
    await this.getFilterInput(/actor.id|actor_id/i).fill(actorId);
    await this.page.keyboard.press("Enter");
  }

  // ── Pagination ─────────────────────────────────────────
  getNextPageButton() {
    return this.page.getByRole("button", { name: /next|»|»»/i });
  }

  getPrevPageButton() {
    return this.page.getByRole("button", { name: /prev|«/i });
  }

  getPageNumber(): Promise<string | null> {
    return this.page.locator(".page-number, [data-testid='page-number']").textContent();
  }

  // ── Event rows ─────────────────────────────────────────
  getEventRows() {
    return this.page.locator("tbody tr");
  }

  getEventRowById(eventId: string) {
    return this.page.locator("tr").filter({ hasText: eventId });
  }

  // ── Hash chain columns (visible on show/detail) ────────
  async gotoShow(eventId: string) {
    await this.goto(`/admin/resources/audit_events/${eventId}/show`);
  }

  getHashValue(): Locator {
    return this.page.locator("td, dd").filter({ hasText: /^[a-f0-9]{64}$/ });
  }

  getPrevHashValue(): Locator {
    return this.page.locator("td, dd").filter({ hasText: /^[a-f0-9]{64}$/ });
  }
}