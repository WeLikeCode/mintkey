/**
 * Unit tests for CopyableValue component (OPS-X).
 *
 * vitest environment is `node` (no jsdom), so tests use source-file inspection.
 * Playwright e2e specs cover real-browser rendering + clipboard interaction.
 *
 * Assertions:
 *   1. Component file exists and exports a default.
 *   2. Renders the value via data-testid="copyable-value-text".
 *   3. "Copy" button is present with data-testid="copyable-value-copy-btn".
 *   4. Calls navigator.clipboard.writeText with the value.
 *   5. description prop is rendered conditionally (description && ...).
 *   6. Registered in components/index.ts as CopyableValue.
 *   7. proxy_url property is visible on show page only (services.ts).
 *   8. proxy_url value is injected via recordTransform in services.ts.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const COMPONENT_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/properties/CopyableValue.tsx"
);

const INDEX_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/index.ts"
);

const SERVICES_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/services.ts"
);

const src = fs.readFileSync(COMPONENT_PATH, "utf-8");
const indexSrc = fs.readFileSync(INDEX_PATH, "utf-8");
const servicesSrc = fs.readFileSync(SERVICES_PATH, "utf-8");

describe("CopyableValue component (OPS-X)", () => {
  it("exports a default component", () => {
    expect(src).toContain("export default CopyableValue");
  });

  it('renders value via data-testid="copyable-value-text"', () => {
    expect(src).toContain('data-testid="copyable-value-text"');
  });

  it('renders copy button via data-testid="copyable-value-copy-btn"', () => {
    expect(src).toContain('data-testid="copyable-value-copy-btn"');
  });

  it("calls navigator.clipboard.writeText with the value", () => {
    expect(src).toContain("navigator.clipboard");
    expect(src).toContain("writeText(value)");
  });

  it("renders description conditionally ({description && ...)", () => {
    expect(src).toContain("{description && (");
  });

  it("shows Copied! feedback after clicking", () => {
    expect(src).toContain("Copied!");
  });

  it("uses useState for copied state", () => {
    expect(src).toContain("setCopied(true)");
    expect(src).toContain("setCopied(false)");
  });

  it("is registered in components/index.ts as CopyableValue", () => {
    expect(indexSrc).toContain("CopyableValue");
    expect(indexSrc).toContain("./properties/CopyableValue");
  });
});

describe("CopyableValue — services.ts integration (OPS-X)", () => {
  it("proxy_url is declared as a virtual property", () => {
    expect(servicesSrc).toContain('path: "proxy_url"');
  });

  it("proxy_url is visible only on show page", () => {
    expect(servicesSrc).toContain("show: true");
    // The visibility block lists list: false, edit: false, new: false, filter: false
    expect(servicesSrc).toContain("isVisible: { show: true, list: false, edit: false, new: false, filter: false }");
  });

  it("proxy_url uses CopyableValue component for show", () => {
    expect(servicesSrc).toContain("Components.CopyableValue");
  });

  it("proxy_url is included in showProperties array", () => {
    expect(servicesSrc).toContain('"proxy_url"');
    // showProperties line must include proxy_url
    const showPropLine = servicesSrc.split("\n").find((l) => l.includes("showProperties"));
    expect(showPropLine).toBeDefined();
    expect(showPropLine).toContain("proxy_url");
  });

  it("recordTransform injects proxy_url via resolveProxyPublicUrl (canonical: MINTKEY_PROXY_PUBLIC_URL, legacy: MINTKEY_PROXY_URL)", () => {
    // Canonical resolver imported from lib/public-urls
    expect(servicesSrc).toContain("resolveProxyPublicUrl");
    expect(servicesSrc).toContain("PROXY_PUBLIC_URL");
    expect(servicesSrc).toContain("proxy_url =");
    expect(servicesSrc).toContain("recordTransform");
  });

  it("resolveProxyPublicUrl in public-urls.ts falls back to http://localhost:8000", () => {
    const publicUrlsSrc = fs.readFileSync(
      path.resolve(new URL(".", import.meta.url).pathname, "../src/lib/public-urls.ts"),
      "utf-8",
    );
    expect(publicUrlsSrc).toContain("http://localhost:8000");
    // Legacy alias is still supported via fallback chain
    expect(publicUrlsSrc).toContain("MINTKEY_PROXY_URL");
    expect(publicUrlsSrc).toContain("MINTKEY_PROXY_PUBLIC_URL");
  });
});
