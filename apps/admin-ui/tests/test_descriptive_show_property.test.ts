/**
 * Unit tests for DescriptiveShowProperty component — UX-CLARITY chunk G.
 *
 * These tests use the same source-file-reading strategy as test_confirm_action.test.ts
 * because the vitest environment is `node` (no jsdom). The Playwright e2e
 * specs cover real-browser rendering of show-page descriptions.
 *
 * Assertions:
 *   1. The component file exists and exports a default.
 *   2. Source contains the show-description and show-value testid patterns.
 *   3. Description block guarded with truthiness (description && ().
 *   4. Uses ValueGroup wrapper (preserves AdminJS layout).
 *   5. Uses translateProperty + tm (i18n-correct).
 *   6. components/index.ts calls componentLoader.override("DefaultShowProperty", ...).
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const COMPONENT_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/properties/DescriptiveShowProperty.tsx"
);

const INDEX_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/index.ts"
);

const src = fs.readFileSync(COMPONENT_PATH, "utf-8");
const indexSrc = fs.readFileSync(INDEX_PATH, "utf-8");

describe("DescriptiveShowProperty — inline show-page description renderer (UX-CLARITY chunk G)", () => {
  it("exports a default component", () => {
    expect(src).toContain("export default DescriptiveShowProperty");
  });

  it("renders show-description testid (data-testid=\"show-description-\") and show-value testid (data-testid=\"show-value-\")", () => {
    expect(src).toContain('data-testid={`show-description-${property.path}`}');
    expect(src).toContain('data-testid={`show-value-${property.path}`}');
  });

  it("guards the description block so it only renders when truthy ({description && ()", () => {
    expect(src).toContain("{description && (");
  });

  it("uses ValueGroup wrapper from @adminjs/design-system (preserves AdminJS layout)", () => {
    expect(src).toContain("ValueGroup");
    expect(src).toContain("@adminjs/design-system");
  });

  it("uses translateProperty and tm for i18n-correct label and description rendering", () => {
    expect(src).toContain("translateProperty");
    expect(src).toContain("tm(");
  });

  it("components/index.ts calls componentLoader.override(\"DefaultShowProperty\", ...) for the global override", () => {
    expect(indexSrc).toContain('componentLoader.override(');
    expect(indexSrc).toContain('"DefaultShowProperty"');
    expect(indexSrc).toContain('./properties/DescriptiveShowProperty');
  });
});
