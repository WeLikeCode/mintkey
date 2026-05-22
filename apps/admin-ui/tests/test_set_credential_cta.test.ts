/**
 * Unit tests for OPS-DDEE DD-1: Set Credential CTA + CredentialNewForm.
 *
 * vitest environment is `node` (no jsdom), so tests use source-file inspection.
 * Playwright e2e specs cover real-browser flow.
 *
 * Assertions:
 *   1. services.ts has setCredential record action.
 *   2. setCredential has actionType: "record".
 *   3. setCredential label is "Set Credential".
 *   4. setCredential icon is "Key".
 *   5. setCredential redirects to credentials/new?service_id=<recordId>.
 *   6. CredentialNewForm component exists and exports default.
 *   7. CredentialNewForm reads service_id from useSearchParams.
 *   8. CredentialNewForm disables service_id field when pre-filled.
 *   9. CredentialNewForm renders credential-prefill-banner when pre-filled.
 *  10. CredentialNewForm submits to credentials/new action.
 *  11. CredentialNewForm is registered in components/index.ts.
 *  12. credentials.ts new action uses CredentialNewForm component.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const SERVICES_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/services.ts"
);

const CREDENTIALS_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/credentials.ts"
);

const FORM_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/CredentialNewForm.tsx"
);

const INDEX_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/index.ts"
);

const servicesSrc = fs.readFileSync(SERVICES_PATH, "utf-8");
const credentialsSrc = fs.readFileSync(CREDENTIALS_PATH, "utf-8");
const formSrc = fs.readFileSync(FORM_PATH, "utf-8");
const indexSrc = fs.readFileSync(INDEX_PATH, "utf-8");

describe("services.ts — Set Credential CTA (OPS-DDEE DD-1)", () => {
  it("setCredential record action exists", () => {
    expect(servicesSrc).toContain("setCredential:");
  });

  it("setCredential has actionType: \"record\"", () => {
    const credIdx = servicesSrc.indexOf("setCredential:");
    expect(credIdx).toBeGreaterThan(-1);
    const snippet = servicesSrc.slice(credIdx, credIdx + 300);
    expect(snippet).toContain('actionType: "record"');
  });

  it('setCredential label is "Set Credential"', () => {
    const credIdx = servicesSrc.indexOf("setCredential:");
    const snippet = servicesSrc.slice(credIdx, credIdx + 300);
    expect(snippet).toContain('label: "Set Credential"');
  });

  it('setCredential icon is "Key"', () => {
    const credIdx = servicesSrc.indexOf("setCredential:");
    const snippet = servicesSrc.slice(credIdx, credIdx + 300);
    expect(snippet).toContain('icon: "Key"');
  });

  it("setCredential handler stores redirect URL in record.params.redirectTo", () => {
    const credIdx = servicesSrc.indexOf("setCredential:");
    const snippet = servicesSrc.slice(credIdx, credIdx + 700);
    // The RedirectAction component reads record.params.redirectTo on mount
    expect(snippet).toContain("credentials/actions/new?service_id=");
    expect(snippet).toContain("request.params.recordId");
    expect(snippet).toContain("redirectTo:");
  });

  it("setCredential has showInDrawer: false", () => {
    const credIdx = servicesSrc.indexOf("setCredential:");
    const snippet = servicesSrc.slice(credIdx, credIdx + 300);
    expect(snippet).toContain("showInDrawer: false");
  });
});

describe("CredentialNewForm component (OPS-DDEE DD-1)", () => {
  it("exports a default component", () => {
    expect(formSrc).toContain("export default CredentialNewForm");
  });

  it("imports useSearchParams from react-router-dom", () => {
    expect(formSrc).toContain("useSearchParams");
    expect(formSrc).toContain("react-router-dom");
  });

  it("reads service_id from URL query params", () => {
    expect(formSrc).toContain('searchParams.get("service_id")');
  });

  it("sets serviceIdLocked when service_id is in URL", () => {
    expect(formSrc).toContain("setServiceIdLocked(true)");
  });

  it("disables service_id field when pre-filled (serviceIdLocked)", () => {
    expect(formSrc).toContain("serviceIdLocked");
    // Locked field shows as a non-editable display box
    expect(formSrc).toContain('data-testid="field-service-id-locked"');
  });

  it('renders credential-prefill-banner when service_id is pre-filled', () => {
    expect(formSrc).toContain('data-testid="credential-prefill-banner"');
  });

  it("pre-fill banner shows service ID", () => {
    expect(formSrc).toContain("Adding credential for service:");
  });

  it("submits to credentials new action via ApiClient", () => {
    expect(formSrc).toContain('resourceId: "credentials"');
    expect(formSrc).toContain('actionName: "new"');
  });

  it('renders submit button data-testid="credential-new-submit"', () => {
    expect(formSrc).toContain('data-testid="credential-new-submit"');
  });

  it('renders cancel button data-testid="credential-new-cancel"', () => {
    expect(formSrc).toContain('data-testid="credential-new-cancel"');
  });

  it("uses AUTH_SCHEMES for auth_scheme dropdown", () => {
    expect(formSrc).toContain("AUTH_SCHEMES");
  });

  it("uses getCredentialFields for dynamic credential fields", () => {
    expect(formSrc).toContain("getCredentialFields");
  });
});

describe("CredentialNewForm — components/index.ts registration", () => {
  it("is registered in components/index.ts as CredentialNewForm", () => {
    expect(indexSrc).toContain("CredentialNewForm");
    expect(indexSrc).toContain("./actions/CredentialNewForm");
  });
});

describe("credentials.ts — new action uses CredentialNewForm", () => {
  it("new action has component: Components.CredentialNewForm", () => {
    // Find the `new:` action block
    const newIdx = credentialsSrc.search(/new:\s*\{/);
    expect(newIdx).toBeGreaterThan(-1);
    const snippet = credentialsSrc.slice(newIdx, newIdx + 300);
    expect(snippet).toContain("CredentialNewForm");
  });
});
