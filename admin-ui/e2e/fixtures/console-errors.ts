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

/**
 * Benign error patterns that do not indicate application code failures.
 * These are filtered out to prevent false-positive cross-browser failures:
 *  - Firefox reports Google Font CDN download failures as console errors
 *    when the test environment has no external network access.
 */
const BENIGN_PATTERNS: RegExp[] = [
  /downloadable font: download failed/i,
  /fonts\.gstatic\.com/i,
  /fonts\.googleapis\.com/i,
];

function isBenign(message: string): boolean {
  return BENIGN_PATTERNS.some((p) => p.test(message));
}

/** Attach listeners and return the tracker. Call before any navigation. */
export function attachConsoleErrorTracker(page: Page): ConsoleErrorTracker {
  const tracker: ConsoleErrorTracker = { errors: [] };

  page.on("pageerror", (err) => {
    if (!isBenign(err.message)) {
      tracker.errors.push({ type: "pageerror", message: err.message });
    }
  });

  page.on("console", (msg) => {
    if (msg.type() === "error" && !isBenign(msg.text())) {
      tracker.errors.push({ type: "console", message: msg.text() });
    }
  });

  return tracker;
}
