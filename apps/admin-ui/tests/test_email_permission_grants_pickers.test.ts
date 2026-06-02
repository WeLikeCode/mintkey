/**
 * EmailPermissionGrantsResource — searchable pickers (feat/email-perm-grants-pickers).
 *
 * Tests verify that agent_id and email_service_id properties are wired to
 * combobox components (not left as plain text inputs).
 *
 * Source: feat/email-perm-grants-pickers.
 */

import { describe, it, expect } from "vitest";
import { EmailPermissionGrantsResource } from "../src/resources/email-permission-grants.js";

describe("EmailPermissionGrantsResource — pickers wired", () => {
  it("has resource id email_permission_grants", () => {
    expect(EmailPermissionGrantsResource.resource).toBe("email_permission_grants");
  });

  it("edit action is not visible", () => {
    const actions = EmailPermissionGrantsResource.options?.actions ?? {};
    expect(
      (actions as Record<string, { isVisible?: boolean }>).edit?.isVisible
    ).toBe(false);
  });

  it("editProperties contains agent_id and email_service_id", () => {
    const editProps = EmailPermissionGrantsResource.options?.editProperties ?? [];
    expect(editProps).toContain("agent_id");
    expect(editProps).toContain("email_service_id");
  });

  it("agent_id property has edit component (AgentCombobox) wired", () => {
    const props = (
      EmailPermissionGrantsResource.options?.properties ?? {}
    ) as Record<string, { components?: { edit?: unknown; filter?: unknown } }>;
    expect(props.agent_id?.components?.edit).toBeTruthy();
  });

  it("email_service_id property has edit component (EmailServiceCombobox) wired", () => {
    const props = (
      EmailPermissionGrantsResource.options?.properties ?? {}
    ) as Record<string, { components?: { edit?: unknown; filter?: unknown } }>;
    expect(props.email_service_id?.components?.edit).toBeTruthy();
  });

  it("agent_id property has filter component wired", () => {
    const props = (
      EmailPermissionGrantsResource.options?.properties ?? {}
    ) as Record<string, { components?: { edit?: unknown; filter?: unknown } }>;
    expect(props.agent_id?.components?.filter).toBeTruthy();
  });

  it("email_service_id property has filter component wired", () => {
    const props = (
      EmailPermissionGrantsResource.options?.properties ?? {}
    ) as Record<string, { components?: { edit?: unknown; filter?: unknown } }>;
    expect(props.email_service_id?.components?.filter).toBeTruthy();
  });

  it("agent_id edit component differs from email_service_id edit component", () => {
    // Ensures both are registered distinctly (not swapped)
    const props = (
      EmailPermissionGrantsResource.options?.properties ?? {}
    ) as Record<string, { components?: { edit?: unknown } }>;
    expect(props.agent_id?.components?.edit).not.toBe(
      props.email_service_id?.components?.edit
    );
  });
});
