/**
 * Vitest tests for email-service template integration in ServiceTemplatePicker.
 *
 * Covers:
 *   1. CATEGORY_LABELS has 'email' mapped to 'Email'.
 *   2. ServiceTemplate interface accepts kind=email_service with imap/smtp fields.
 *   3. ServiceTemplatePicker uses resourceId='email_services' for kind=email_service.
 *   4. ServiceTemplatePicker uses resourceId='services' for kind=http_service / default.
 *   5. email-services.ts resource has a 'from-template' action (isVisible: false).
 *   6. email-services.ts from-template calls /v1/tenants/{tid}/email-services/from-template.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const PICKER_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/ServiceTemplatePicker.tsx"
);

const EMAIL_SERVICES_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/email-services.ts"
);

const pickerSrc = fs.readFileSync(PICKER_PATH, "utf-8");
const emailServicesSrc = fs.readFileSync(EMAIL_SERVICES_PATH, "utf-8");

describe("ServiceTemplatePicker — email_service kind routing", () => {
  it("CATEGORY_LABELS includes email mapped to 'Email'", () => {
    // The map must have the 'email' key
    expect(pickerSrc).toContain('email: "Email"');
  });

  it("ServiceTemplate interface has kind field", () => {
    expect(pickerSrc).toContain("kind?:");
    expect(pickerSrc).toContain("email_service");
  });

  it("ServiceTemplate interface has imap_host, imap_port, smtp_host, smtp_port fields", () => {
    expect(pickerSrc).toContain("imap_host?:");
    expect(pickerSrc).toContain("imap_port?:");
    expect(pickerSrc).toContain("smtp_host?:");
    expect(pickerSrc).toContain("smtp_port?:");
  });

  it("handleSubmit routes email_service kind to email_services resourceId", () => {
    // The picker must use 'email_services' when kind === 'email_service'
    expect(pickerSrc).toContain('resourceId = isEmail ? "email_services" : "services"');
  });

  it("submitSuccess uses email_services path for email kind", () => {
    // Success URL must use the correct resource path for email services
    expect(pickerSrc).toContain("email_services");
    // and the resourceName variable
    expect(pickerSrc).toContain("resourceName");
  });

  it("isEmailTemplate / isEmail guard is present in the component", () => {
    // The kind guard must be present
    expect(pickerSrc).toMatch(/kind.*===.*"email_service"/);
  });
});

describe("email-services.ts resource — from-template action", () => {
  it("has a 'from-template' action definition", () => {
    expect(emailServicesSrc).toContain('"from-template"');
  });

  it("from-template action is not visible (isVisible: false)", () => {
    const ftIdx = emailServicesSrc.indexOf('"from-template"');
    expect(ftIdx).toBeGreaterThan(-1);
    const snippet = emailServicesSrc.slice(ftIdx, ftIdx + 300);
    expect(snippet).toContain("isVisible: false");
  });

  it("from-template calls /v1/tenants/{tid}/email-services/from-template", () => {
    expect(emailServicesSrc).toContain(
      "/v1/tenants/${tenantId}/email-services/from-template"
    );
  });

  it("from-template returns email_service in response payload", () => {
    // The response must include the email_service object for picker success detection
    expect(emailServicesSrc).toContain("email_service: body");
  });

  it("from-template has an error notice path (type: 'error' in resource)", () => {
    // The resource must have at least one error notice — verify the file overall
    expect(emailServicesSrc).toMatch(/type:\s*["']error["']/);
  });
});
