/**
 * SSH Test Panel — source-level assertions.
 *
 * Verifies that TestServiceForm.tsx:
 *   1. Does NOT render HTTP method/path/headers/body fields for SSH services.
 *   2. Does NOT render the curl preview section for SSH services.
 *   3. DOES render an SSH-specific panel with a "Run Test" button.
 *   4. Uses auth_scheme (not base_url) to detect SSH services.
 *
 * We use source inspection (matching the pattern in tests/unit/components/intros.test.ts)
 * because the render project (jsdom) requires a separate .render.test.tsx file; these
 * structural assertions don't need a DOM.  Browser-level interaction is covered by the
 * Playwright e2e suite.
 *
 * Source: ADR-0021; UX-CLARITY P0; objective Part B §5.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const SOURCE_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/TestServiceForm.tsx"
);

function readSource(): string {
  return fs.readFileSync(SOURCE_PATH, "utf-8");
}

describe("TestServiceForm SSH panel — source assertions", () => {
  it("source file exists", () => {
    expect(fs.existsSync(SOURCE_PATH)).toBe(true);
  });

  it("defines SSH_AUTH_SCHEMES set covering ssh_private_key, ssh_password, ssh_ca", () => {
    const src = readSource();
    expect(src).toContain("ssh_private_key");
    expect(src).toContain("ssh_password");
    expect(src).toContain("ssh_ca");
    expect(src).toContain("SSH_AUTH_SCHEMES");
  });

  it("branches on SSH_AUTH_SCHEMES before rendering the HTTP form", () => {
    const src = readSource();
    // The SSH branch must appear before the HTTP method select
    const sshBranchIdx = src.indexOf("SSH_AUTH_SCHEMES.has(authScheme)");
    const httpMethodIdx = src.indexOf("field-select-method");
    expect(sshBranchIdx).toBeGreaterThan(-1);
    expect(httpMethodIdx).toBeGreaterThan(-1);
    expect(sshBranchIdx).toBeLessThan(httpMethodIdx);
  });

  it("SSHTestPanel does NOT contain HTTP method/path/headers/body field test-ids", () => {
    const src = readSource();
    // Locate the SSHTestPanel component body
    const panelStart = src.indexOf("const SSHTestPanel");
    const panelEnd = src.indexOf("// ── TestServiceForm (main component)");
    expect(panelStart).toBeGreaterThan(-1);
    expect(panelEnd).toBeGreaterThan(panelStart);
    const panelSrc = src.slice(panelStart, panelEnd);

    // These HTTP-specific test-ids must NOT appear inside SSHTestPanel
    expect(panelSrc).not.toContain("field-select-method");
    expect(panelSrc).not.toContain("field-input-path");
    expect(panelSrc).not.toContain("field-input-headers");
    expect(panelSrc).not.toContain("field-input-body");
    expect(panelSrc).not.toContain("curl-preview");
  });

  it("SSHTestPanel contains a 'Run Test' button with data-testid=test-service-submit", () => {
    const src = readSource();
    const panelStart = src.indexOf("const SSHTestPanel");
    const panelEnd = src.indexOf("// ── TestServiceForm (main component)");
    const panelSrc = src.slice(panelStart, panelEnd);

    expect(panelSrc).toContain("Run Test");
    expect(panelSrc).toContain("test-service-submit");
  });

  it("SSHTestPanel shows ssh-command-preview block (never exposes credentials)", () => {
    const src = readSource();
    const panelStart = src.indexOf("const SSHTestPanel");
    const panelEnd = src.indexOf("// ── TestServiceForm (main component)");
    const panelSrc = src.slice(panelStart, panelEnd);

    expect(panelSrc).toContain("ssh-command-preview");
    // The command block must NOT reference any credential field
    expect(panelSrc).not.toContain("private_key_pem");
    expect(panelSrc).not.toContain("password");
  });

  it("SSHTestPanel is rendered from TestServiceForm when auth_scheme is SSH", () => {
    const src = readSource();
    // TestServiceForm must return SSHTestPanel for SSH schemes
    expect(src).toContain("<SSHTestPanel");
  });

  it("uses auth_scheme field (not base_url) as the SSH detection signal", () => {
    const src = readSource();
    // Detection is via SSH_AUTH_SCHEMES.has(authScheme), NOT startsWith("ssh://")
    expect(src).toContain("SSH_AUTH_SCHEMES.has(authScheme)");
    // base_url startsWith check should NOT be the detection mechanism
    const sshDetectIdx = src.indexOf("SSH_AUTH_SCHEMES.has(authScheme)");
    const startswithIdx = src.indexOf("startsWith(\"ssh://\")");
    // Either no startsWith("ssh://") at all, or it appears after the scheme check
    if (startswithIdx !== -1) {
      expect(startswithIdx).toBeGreaterThan(sshDetectIdx);
    }
  });
});
