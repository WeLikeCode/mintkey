/**
 * Login page object — drives the Keycloak OIDC login flow.
 *
 * The old AdminJS internal password form (input[name=email] + submit) is dead:
 *  - The break-glass inputs are inside a collapsed <details> accordion (hidden).
 *  - The /auth/internal-login-proxy endpoint returns 404 (no password hash set).
 *
 * Real login flow:
 *  1. Navigate to /admin/login and click "Sign in with Keycloak" OR go to /auth/start
 *  2. Fill Keycloak form: #username, #password, #kc-login
 *  3. Wait for redirect back to /admin (mintkey_session + csrf_token cookies set)
 *
 * Source: F-OP-01; T-1.1.4.
 */

import { type Page, type Locator, expect } from "@playwright/test";
import { BasePage } from "./base.js";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8081";

export class LoginPage extends BasePage {
  /** Keycloak username input */
  readonly kcUsername: Locator;
  /** Keycloak password input */
  readonly kcPassword: Locator;
  /** Keycloak submit button */
  readonly kcSubmit: Locator;

  // Legacy aliases kept so any spec that destructures {email, password, submitButton}
  // still compiles — they now point at the Keycloak selectors.
  get email() { return this.kcUsername; }
  get password() { return this.kcPassword; }
  get submitButton() { return this.kcSubmit; }

  constructor(page: Page) {
    super(page);
    this.kcUsername = page.locator("#username");
    this.kcPassword = page.locator("#password");
    this.kcSubmit   = page.locator("#kc-login");
  }

  /**
   * Navigate to /auth/start to initiate the OIDC flow.
   * After navigation, the browser will be on the Keycloak login page.
   */
  async goto() {
    await this.page.goto(`${BASE_URL}/auth/start`, { waitUntil: "domcontentloaded" });
    // Wait for Keycloak username field
    await this.page.waitForSelector("#username", { timeout: 30_000 });
  }

  /**
   * Perform OIDC login via Keycloak.
   * Returns when the browser has redirected to /admin after successful authentication.
   */
  async login(email: string, password: string) {
    await this.kcUsername.fill(email);
    await this.kcPassword.fill(password);
    await Promise.all([
      this.page.waitForURL(
        (url) => url.href.includes("/admin") && !url.href.includes("/auth/"),
        { timeout: 30_000 },
      ),
      this.kcSubmit.click(),
    ]);
  }

  /**
   * Check that the Keycloak login form is rendered.
   */
  async isVisible() {
    await expect(this.kcUsername).toBeVisible();
    await expect(this.kcPassword).toBeVisible();
  }
}
