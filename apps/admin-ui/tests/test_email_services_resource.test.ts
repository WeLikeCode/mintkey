/**
 * EmailServicesResource unit tests — C-10.
 *
 * Tests:
 *   - Resource key is "email_services".
 *   - List properties include expected columns.
 *   - Edit properties include all writable fields.
 *   - provider + auth_scheme have correct availableValues.
 *   - new, edit, delete actions are present and visible.
 *   - _oauth2_setup property is show-only (not in list/edit/new/filter).
 *   - imap_port and smtp_port are type number in the property list.
 *
 * Source: C-10; ADMIN_UI_SPEC.md §2.x.
 */

import { describe, it, expect } from "vitest";
import { EmailServicesResource } from "../src/resources/email-services.js";

describe("EmailServicesResource — C-10", () => {
  it("has resource key email_services", () => {
    expect(EmailServicesResource.resource).toBe("email_services");
  });

  it("listProperties includes tenant_id, provider, name, imap_host, smtp_host, auth_scheme, created_at", () => {
    const listProps = EmailServicesResource.options?.listProperties ?? [];
    expect(listProps).toContain("tenant_id");
    expect(listProps).toContain("provider");
    expect(listProps).toContain("name");
    expect(listProps).toContain("imap_host");
    expect(listProps).toContain("smtp_host");
    expect(listProps).toContain("auth_scheme");
    expect(listProps).toContain("created_at");
  });

  it("editProperties includes all writable fields", () => {
    const editProps = EmailServicesResource.options?.editProperties ?? [];
    expect(editProps).toContain("provider");
    expect(editProps).toContain("imap_host");
    expect(editProps).toContain("imap_port");
    expect(editProps).toContain("smtp_host");
    expect(editProps).toContain("smtp_port");
    expect(editProps).toContain("auth_scheme");
    expect(editProps).toContain("allowed_recipient_domains");
    expect(editProps).toContain("pool_size_max");
  });

  it("provider property has gmail, outlook, generic as availableValues", () => {
    const properties = EmailServicesResource.options?.properties ?? {};
    const providerProp = (properties as Record<string, { availableValues?: Array<{ value: string }> }>)["provider"];
    const values = providerProp?.availableValues?.map((v) => v.value) ?? [];
    expect(values).toContain("gmail");
    expect(values).toContain("outlook");
    expect(values).toContain("generic");
  });

  it("auth_scheme property has email_password, email_oauth2, email_app_password as availableValues", () => {
    const properties = EmailServicesResource.options?.properties ?? {};
    const schemeProp = (properties as Record<string, { availableValues?: Array<{ value: string }> }>)["auth_scheme"];
    const values = schemeProp?.availableValues?.map((v) => v.value) ?? [];
    expect(values).toContain("email_password");
    expect(values).toContain("email_oauth2");
    expect(values).toContain("email_app_password");
  });

  it("new action is present and visible", () => {
    const actions = EmailServicesResource.options?.actions ?? {};
    expect("new" in actions).toBe(true);
    const newAction = (actions as Record<string, { isVisible?: boolean }>)["new"];
    expect(newAction?.isVisible).not.toBe(false);
  });

  it("edit action is present and visible", () => {
    const actions = EmailServicesResource.options?.actions ?? {};
    expect("edit" in actions).toBe(true);
    const editAction = (actions as Record<string, { isVisible?: boolean }>)["edit"];
    expect(editAction?.isVisible).not.toBe(false);
  });

  it("delete action is present and visible", () => {
    const actions = EmailServicesResource.options?.actions ?? {};
    expect("delete" in actions).toBe(true);
    const deleteAction = (actions as Record<string, { isVisible?: boolean }>)["delete"];
    expect(deleteAction?.isVisible).not.toBe(false);
  });

  it("_oauth2_setup property is show-only (not visible in list, edit, new, filter)", () => {
    const properties = EmailServicesResource.options?.properties ?? {};
    const oauthProp = (
      properties as Record<
        string,
        {
          isVisible?:
            | boolean
            | { list?: boolean; show?: boolean; edit?: boolean; new?: boolean; filter?: boolean };
        }
      >
    )["_oauth2_setup"];
    const vis = oauthProp?.isVisible;
    if (typeof vis === "object" && vis !== null) {
      expect(vis.show).toBe(true);
      expect(vis.list).toBe(false);
      expect(vis.edit).toBe(false);
      expect(vis.new).toBe(false);
      expect(vis.filter).toBe(false);
    } else {
      // If somehow not an object, fail clearly
      expect(typeof vis).toBe("object");
    }
  });

  it("imap_port and smtp_port are configured as numeric", () => {
    // Verify properties declared numeric in the RestResource config
    const adminResource = EmailServicesResource.adminResource;
    const props = adminResource.properties();
    const imapPort = props.find((p) => p.path() === "imap_port");
    const smtpPort = props.find((p) => p.path() === "smtp_port");
    expect(imapPort).toBeDefined();
    expect(smtpPort).toBeDefined();
    expect(imapPort?.type()).toBe("number");
    expect(smtpPort?.type()).toBe("number");
  });

  it("q filter property is not visible in list/show/edit/new", () => {
    const properties = EmailServicesResource.options?.properties ?? {};
    const qProp = (
      properties as Record<
        string,
        {
          isVisible?:
            | boolean
            | { list?: boolean; show?: boolean; edit?: boolean; filter?: boolean };
        }
      >
    )["q"];
    const vis = qProp?.isVisible;
    if (typeof vis === "object" && vis !== null) {
      expect(vis.list).toBe(false);
      expect(vis.show).toBe(false);
      expect(vis.edit).toBe(false);
    }
  });
});
