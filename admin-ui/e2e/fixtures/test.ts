/**
 * Extended Playwright `test` with a `consoleErrors` fixture.
 *
 * Every spec that imports `test` from this module automatically gets:
 *   - a console-error tracker attached before the test body runs
 *   - a post-test assertion that throws if any browser error was collected
 *
 * Specs that intentionally trigger a console error (e.g. the self-test)
 * must annotate with `test.fail()` so the expected failure is green.
 */

import { test as base, expect } from "@playwright/test";
import { attachConsoleErrorTracker, type ConsoleErrorTracker } from "./console-errors.js";

export { expect } from "@playwright/test";

type Fixtures = {
  consoleErrors: ConsoleErrorTracker;
};

export const test = base.extend<Fixtures>({
  consoleErrors: async ({ page }, use, testInfo) => {
    const tracker = attachConsoleErrorTracker(page);

    await use(tracker);

    // After the test body: throw if any browser error was recorded.
    // This turns silent browser errors into explicit test failures.
    if (tracker.errors.length > 0 && testInfo.status !== "failed") {
      const summary = tracker.errors
        .map((e) => `  [${e.type}] ${e.message}`)
        .join("\n");
      throw new Error(`Browser console errors detected:\n${summary}`);
    }
  },
});
