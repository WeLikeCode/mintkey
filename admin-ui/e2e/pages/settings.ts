/**
 * Settings page object — view and edit admin settings.
 */

import { type Page, type Locator } from "@playwright/test";
import { BasePage } from "./base.js";

export class SettingsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async goto() {
    await super.goto("/admin/settings");
  }

  getFieldValue(name: string | RegExp) {
    return this.page.getByLabel(name, { exact: false });
  }

  async getMfaRequiredValue(): Promise<string | null> {
    const value = await this.page.locator("dd:has-text('mfa'), td:has-text('mfa')").textContent();
    return value?.trim() ?? null;
  }
}