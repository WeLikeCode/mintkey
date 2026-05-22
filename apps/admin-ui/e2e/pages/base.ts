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

  /**
   * Select a value in an AdminJS React Select dropdown.
   * AdminJS uses react-select for properties with availableValues.
   *
   * The label and react-select combobox are siblings inside the same parent div.
   * react-select exposes role="combobox" on its input and role="option" on each item.
   */
  async selectFromReactSelect(labelText: string | RegExp, optionText: string | RegExp, timeout = 10_000): Promise<void> {
    const label = this.page.locator("label").filter({ hasText: labelText }).first();
    // The react-select combobox is a sibling descendant of the label's parent div.
    // force:true bypasses the placeholder overlay that intercepts clicks in webkit.
    await label.locator("xpath=parent::*").locator("[role='combobox']").first().click({ timeout, force: true });
    await this.page.locator("[role='option']").filter({ hasText: optionText }).first().click({ timeout });
  }
}