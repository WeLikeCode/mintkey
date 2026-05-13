/**
 * Console-error tracker fixture helper.
 *
 * Attaches listeners to `page.on("pageerror")` and `page.on("console")`
 * so tests can assert that no unexpected browser errors fired.
 *
 * Usage: pass `page` after navigation; collect errors; assert at end of test.
 */

import type { Page } from "@playwright/test";

export interface ConsoleError {
  type: "pageerror" | "console";
  message: string;
}

export interface ConsoleErrorTracker {
  errors: ConsoleError[];
}

/** Attach listeners and return the tracker. Call before any navigation. */
export function attachConsoleErrorTracker(page: Page): ConsoleErrorTracker {
  const tracker: ConsoleErrorTracker = { errors: [] };

  page.on("pageerror", (err) => {
    tracker.errors.push({ type: "pageerror", message: err.message });
  });

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      tracker.errors.push({ type: "console", message: msg.text() });
    }
  });

  return tracker;
}
