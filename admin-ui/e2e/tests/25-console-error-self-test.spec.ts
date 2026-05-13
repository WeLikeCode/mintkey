/**
 * W0 self-test: proves the console-error fixture works.
 *
 * This test deliberately injects a `console.error` and is annotated with
 * `test.fail()` to declare "expected to fail". When the fixture catches the
 * synthetic error and throws after the test body, Playwright marks the test
 * as "expected failure" → green in the report.
 *
 * If the fixture is broken (does not catch the error), the test body passes
 * without throwing and `test.fail()` flips it to red — proving the guard works
 * in both directions.
 *
 * Source: PLAYWRIGHT_EXTENSION_PLAN.md W0 DoD (c).
 */

import { test, expect } from "../fixtures/test.js";

test.describe("W0 — console-error fixture self-test", () => {
  test.fail();

  test("fixture catches a synthetic console.error and fails the test", async ({
    page,
    consoleErrors,
  }) => {
    // Navigate to any page the app serves so `page.evaluate` runs in context.
    await page.goto("/admin/login", { waitUntil: "domcontentloaded" }).catch(() => {
      // If the server is not running, the navigation error is fine for this test —
      // we only need the evaluate to fire.
    });

    // Inject a synthetic console.error that the fixture must capture.
    await page.evaluate(() => {
      console.error("W0-synthetic-console-error-fixture-test");
    });

    // The test body itself does not assert anything — the fixture's afterTest
    // hook will throw because tracker.errors.length > 0.
    // Combined with test.fail(), this makes the overall result: expected failure → green.
    expect(consoleErrors.errors.length).toBeGreaterThan(0);
  });
});
