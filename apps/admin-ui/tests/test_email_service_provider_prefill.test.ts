/**
 * Tests for the EmailServiceNewForm provider-driven prefill (Bug-B fix).
 *
 * These are source-file inspection + PROVIDER_DEFAULTS logic tests
 * (node environment, no jsdom).
 *
 * Assertions:
 *   1. PROVIDER_DEFAULTS exported from EmailServiceNewForm has gmail entry.
 *   2. gmail defaults: imap.gmail.com:993, smtp.gmail.com:465, email_oauth2.
 *   3. outlook defaults: outlook.office365.com:993, smtp.office365.com:587, email_oauth2.
 *   4. generic defaults: all blank / empty string.
 *   5. EmailServiceNewForm component source has data-testid="email-service-new-form".
 *   6. handleProviderChange only prefills fields not in dirtyFields.
 *   7. The new action in email-services.ts wires EmailServiceNewForm component.
 *   8. EmailServiceNewForm is registered in components/index.ts.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";
// Import PROVIDER_DEFAULTS from the pure-TS lib module (no adminjs/React deps → works in node env)
import { PROVIDER_DEFAULTS } from "../src/lib/email-provider-defaults.js";

const COMPONENT_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/EmailServiceNewForm.tsx"
);

const EMAIL_SERVICES_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/email-services.ts"
);

const COMPONENTS_INDEX_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/index.ts"
);

const componentSrc = fs.readFileSync(COMPONENT_PATH, "utf-8");
const emailServicesSrc = fs.readFileSync(EMAIL_SERVICES_PATH, "utf-8");
const componentsIndexSrc = fs.readFileSync(COMPONENTS_INDEX_PATH, "utf-8");

describe("PROVIDER_DEFAULTS — exported values (Bug-B fix)", () => {
  it("has gmail entry", () => {
    expect(PROVIDER_DEFAULTS).toHaveProperty("gmail");
  });

  it("gmail: imap_host = imap.gmail.com", () => {
    expect(PROVIDER_DEFAULTS.gmail.imap_host).toBe("imap.gmail.com");
  });

  it("gmail: imap_port = 993", () => {
    expect(PROVIDER_DEFAULTS.gmail.imap_port).toBe(993);
  });

  it("gmail: smtp_host = smtp.gmail.com", () => {
    expect(PROVIDER_DEFAULTS.gmail.smtp_host).toBe("smtp.gmail.com");
  });

  it("gmail: smtp_port = 465", () => {
    expect(PROVIDER_DEFAULTS.gmail.smtp_port).toBe(465);
  });

  it("gmail: auth_scheme = email_oauth2", () => {
    expect(PROVIDER_DEFAULTS.gmail.auth_scheme).toBe("email_oauth2");
  });

  it("has outlook entry", () => {
    expect(PROVIDER_DEFAULTS).toHaveProperty("outlook");
  });

  it("outlook: imap_host = outlook.office365.com", () => {
    expect(PROVIDER_DEFAULTS.outlook.imap_host).toBe("outlook.office365.com");
  });

  it("outlook: imap_port = 993", () => {
    expect(PROVIDER_DEFAULTS.outlook.imap_port).toBe(993);
  });

  it("outlook: smtp_host = smtp.office365.com", () => {
    expect(PROVIDER_DEFAULTS.outlook.smtp_host).toBe("smtp.office365.com");
  });

  it("outlook: smtp_port = 587", () => {
    expect(PROVIDER_DEFAULTS.outlook.smtp_port).toBe(587);
  });

  it("outlook: auth_scheme = email_oauth2", () => {
    expect(PROVIDER_DEFAULTS.outlook.auth_scheme).toBe("email_oauth2");
  });

  it("has generic entry", () => {
    expect(PROVIDER_DEFAULTS).toHaveProperty("generic");
  });

  it("generic: all fields are blank (empty string)", () => {
    const g = PROVIDER_DEFAULTS.generic;
    expect(g.imap_host).toBe("");
    expect(g.imap_port).toBe("");
    expect(g.smtp_host).toBe("");
    expect(g.smtp_port).toBe("");
    expect(g.auth_scheme).toBe("");
  });
});

describe("EmailServiceNewForm component source (Bug-B fix)", () => {
  it("exports a default component named EmailServiceNewForm", () => {
    expect(componentSrc).toContain("export default EmailServiceNewForm");
  });

  it("has data-testid='email-service-new-form' on root element", () => {
    expect(componentSrc).toContain('data-testid="email-service-new-form"');
  });

  it("has data-testid for provider select", () => {
    expect(componentSrc).toContain('data-testid="es-provider-select"');
  });

  it("has data-testid for imap-host input", () => {
    expect(componentSrc).toContain('data-testid="es-imap-host-input"');
  });

  it("has data-testid for imap-port input", () => {
    expect(componentSrc).toContain('data-testid="es-imap-port-input"');
  });

  it("has data-testid for smtp-host input", () => {
    expect(componentSrc).toContain('data-testid="es-smtp-host-input"');
  });

  it("has data-testid for smtp-port input", () => {
    expect(componentSrc).toContain('data-testid="es-smtp-port-input"');
  });

  it("has data-testid for auth-scheme select", () => {
    expect(componentSrc).toContain('data-testid="es-auth-scheme-select"');
  });

  it("has data-testid for submit button", () => {
    expect(componentSrc).toContain('data-testid="es-submit-btn"');
  });

  it("tracks dirty fields to avoid overwriting operator-typed values", () => {
    expect(componentSrc).toContain("dirtyFields");
    expect(componentSrc).toContain("markDirty");
  });

  it("handleProviderChange skips prefill for dirty fields", () => {
    expect(componentSrc).toContain("dirtyFields.has(");
  });

  it("uses PROVIDER_DEFAULTS for prefill values (not hardcoded strings in handler)", () => {
    expect(componentSrc).toContain("PROVIDER_DEFAULTS");
    expect(componentSrc).toContain("PROVIDER_DEFAULTS[value]");
  });
});

describe("email-services.ts wires EmailServiceNewForm (Bug-B fix)", () => {
  it("new action references EmailServiceNewForm component", () => {
    expect(emailServicesSrc).toContain("EmailServiceNewForm");
  });

  it("new action has component: Components.EmailServiceNewForm", () => {
    expect(emailServicesSrc).toContain("Components.EmailServiceNewForm");
  });
});

describe("components/index.ts registers EmailServiceNewForm", () => {
  it("registers EmailServiceNewForm with componentLoader.add", () => {
    expect(componentsIndexSrc).toContain("EmailServiceNewForm");
    expect(componentsIndexSrc).toContain("./actions/EmailServiceNewForm");
  });
});
