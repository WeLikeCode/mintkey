/**
 * Stub for adminjs — used only by the jsdom render test harness.
 * ApiClient is exported as a class whose resourceAction method is a vi.fn()
 * that can be controlled per-test.
 */
import { vi } from "vitest";

export const resourceAction = vi.fn();

export class ApiClient {
  resourceAction = resourceAction;
}
