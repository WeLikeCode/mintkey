/**
 * Login page object — handles both internal auth and OIDC flows.
 *
 * Source: F-OP-01; T-1.1.4.
 */

import { type Page, type Locator, expect } from "@playwright/test";
import { BasePage } from "./base.js";

export class LoginPage extends BasePage {
  readonly email: Locator;
  readonly password: Locator;
  readonly submitButton: Locator;
  readonly oidcButton: Locator;

  constructor(page: Page) {
    super(page);
    // AdminJS renders the login form via React bundles; use input selectors
    // in addition to getByLabel for robustness
    this.email = page.locator("input[type=email], input[name=email]").first();
    this.password = page.locator("input[type=password], input[name=password]").first();
    this.submitButton = page.getByRole("button", { name: /sign in|login/i });
    // OIDC button text varies — "Login with Keycloak" or similar
    this.oidcButton = page.getByRole("link", { name: /keycloak|oidc|external login/i });
  }

  async goto() {
    await super.goto("/admin/login");
    // Wait for React to render the login form
    await this.page.waitForSelector("input[type=email], input[name=email]", { timeout: 15_000 });
  }

  /**
   * Perform internal (Argon2id) login.
   * Returns when redirected to the dashboard.
   */
  async login(email: string, password: string) {
    await this.email.fill(email);
    await this.password.fill(password);
    await Promise.all([
      this.page.waitForURL(/\/admin/, { timeout: 10_000 }),
      this.submitButton.click(),
    ]);
  }

  /**
   * Check that login form is rendered.
   */
  async isVisible() {
    await expect(this.email).toBeVisible();
    await expect(this.password).toBeVisible();
  }
}