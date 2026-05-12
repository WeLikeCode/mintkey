/**
 * Base page — shared helpers for all AdminJS pages.
 */

import { type Page, type Locator, expect } from "@playwright/test";

export class BasePage {
  readonly page: Page;
  readonly baseURL: string;

  constructor(page: Page) {
    this.page = page;
    this.baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8081";
  }

  async goto(path: string) {
    await this.page.goto(`${this.baseURL}${path}`);
    await this.page.waitForLoadState("domcontentloaded");
  }

  /**
   * Wait for a toast/notice to appear and return its text.
   * AdminJS renders notices as alert boxes at the top of the page.
   */
  async waitForNotice(text: string | RegExp, timeout = 10_000): Promise<Locator> {
    const notice = this.page.locator(".alert, [role='alert'], .toast, .notice").filter({
      hasText: typeof text === "string" ? new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) : text,
    });
    await expect(notice).toBeVisible({ timeout });
    return notice;
  }

  /**
   * Confirm a browser dialog (window.confirm).
   */
  async confirmDialog(accept = true) {
    this.page.on("dialog", async (dialog) => {
      accept ? await dialog.accept() : await dialog.dismiss();
    });
  }

  /**
   * Click a row action button by row identifier and button label.
   * AdminJS renders rows in <table> with action links.
   */
  async clickRowAction(rowId: string, actionLabel: string | RegExp) {
    const row = this.page.locator("tr").filter({ hasText: new RegExp(rowId) });
    const action = row.locator("a, button").filter({ hasText: actionLabel });
    await action.click();
  }
}