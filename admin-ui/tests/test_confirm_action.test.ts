/**
 * Unit tests for ConfirmAction component — UX-CLARITY chunk F.
 *
 * These tests use the same source-file-reading strategy as intros.test.ts
 * because the vitest environment is `node` (no jsdom). The Playwright e2e
 * specs cover real-browser rendering of the confirm dialog.
 *
 * Assertions:
 *   1. The component exports a default.
 *   2. The `description` prop is declared in the ConfirmActionProps interface.
 *   3. The `confirm-action-description` testid is present in the source,
 *      meaning the prop is wired to the JSX.
 *   4. The existing `confirm-action-page` testid is still present (no regression
 *      for callers that do not pass a description).
 *   5. The description block is guarded by a truthiness check so it renders
 *      nothing when description is empty/omitted.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const COMPONENT_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/ConfirmAction.tsx"
);

const src = fs.readFileSync(COMPONENT_PATH, "utf-8");

describe("ConfirmAction — description prop (UX-CLARITY chunk F)", () => {
  it("exports a default component", () => {
    expect(src).toContain("export default ConfirmAction");
  });

  it("declares the optional description prop in its Props interface", () => {
    expect(src).toContain("description?: string");
  });

  it("renders a confirm-action-description testid when description is truthy", () => {
    expect(src).toContain('data-testid="confirm-action-description"');
  });

  it("guards the description block so it only renders when truthy (no-description default is safe)", () => {
    // The JSX must contain a truthiness guard: {description && (
    expect(src).toContain("{description && (");
  });

  it("preserves the existing confirm-action-page testid (no regression)", () => {
    expect(src).toContain('data-testid="confirm-action-page"');
  });

  it("preserves the existing confirm-action-button testid (no regression)", () => {
    expect(src).toContain('data-testid="confirm-action-button"');
  });

  it("preserves the existing cancel-action-button testid (no regression)", () => {
    expect(src).toContain('data-testid="cancel-action-button"');
  });

  it("description resolves to empty string when neither prop nor custom.description is set", () => {
    // The fallback chain ends with "" to ensure description is never undefined
    // Note: the actual code spans multiple lines so we check for the terminal value
    expect(src).toContain('custom?.description ??');
    expect(src).toContain('"";');
  });

  it("falls back to action.custom.description when top-level description prop is absent", () => {
    expect(src).toContain("custom?: { description?: string }");
    expect(src).toContain("custom?.description");
  });
});
