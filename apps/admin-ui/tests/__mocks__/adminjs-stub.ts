/**
 * Stub for adminjs — used only by the jsdom render test harness.
 * ApiClient is exported as a class whose resourceAction and recordAction methods
 * are vi.fn()s that can be controlled per-test.
 */
import { vi } from "vitest";

export const resourceAction = vi.fn();
export const recordAction = vi.fn();

export class ApiClient {
  resourceAction = resourceAction;
  recordAction = recordAction;
}
