/**
 * Labels reach AdminJS through its locale, and the new forms take AdminJS's own keys.
 *
 * AdminJS 7 reads a property's or an action's display name only from `options.translations` (it ignores a `label`
 * in the options), renders an action's `layout` (else `editProperties`) on the new form, and has no `newProperties`
 * key. Source: src/lib/labels.ts; AdminJS 7.8 PropertyDecorator.label(), getLocales() and actions/new.tsx.
 */

import { describe, it, expect } from "vitest";
import { withLabelTranslations, type LabeledResourceOptions } from "../src/lib/labels.js";
import { tenantIdOf } from "../src/lib/api-client.js";
import { AgentsResource } from "../src/resources/agents.js";
import { OperatorsResource } from "../src/resources/operators.js";
import { TenantsResource } from "../src/resources/tenants.js";

describe("withLabelTranslations", () => {
  it("copies property and action labels into options.translations.en", () => {
    const options: LabeledResourceOptions = {
      properties: { grants_count: { label: "Grants" }, name: {} },
      actions: { rotateKey: { actionType: "record", label: "Rotate Key" }, list: {} },
    };
    const out = withLabelTranslations(options);
    expect(out.translations?.["en"]).toEqual({
      properties: { grants_count: "Grants" },
      actions: { rotateKey: "Rotate Key" },
    });
  });

  it("keeps a translation the resource declares for the same key", () => {
    const options: LabeledResourceOptions = {
      properties: { status: { label: "Status label" } },
      translations: { en: { properties: { status: "Declared" }, messages: { saved: "Saved" } } },
    };
    const out = withLabelTranslations(options);
    expect(out.translations?.["en"]).toEqual({
      properties: { status: "Declared" },
      actions: {},
      messages: { saved: "Saved" },
    });
  });

  it("leaves options without labels as they are", () => {
    const options: LabeledResourceOptions = { properties: { name: {} } };
    expect(withLabelTranslations(options)).toBe(options);
  });

  it("puts a resource's labels where AdminJS reads them", () => {
    const out = withLabelTranslations(AgentsResource.options);
    const en = out.translations?.["en"] as { properties: Record<string, string>; actions: Record<string, string> };
    expect(en.properties["api_key_fingerprint"]).toBe("API Key Fingerprint (SHA-256 prefix)");
    expect(en.actions["rotateAgentKey"]).toBe("Rotate Key");
  });
});

describe("new forms use AdminJS's keys", () => {
  it("the promote-operator form has the fields to create one (an action layout)", () => {
    const options = OperatorsResource.options as Record<string, unknown>;
    expect(options["newProperties"]).toBeUndefined();
    const newAction = OperatorsResource.options?.actions?.["new"] as { layout?: unknown };
    expect(newAction?.layout).toEqual(["email", "tenant_id", "display_name", "oidc_sub", "is_platform_admin"]);
    // the edit form keeps its own, smaller field list
    expect(OperatorsResource.options?.editProperties).toEqual(["display_name", "is_platform_admin", "status"]);
  });

  it("the new-tenant form is editProperties", () => {
    const options = TenantsResource.options as Record<string, unknown>;
    expect(options["newProperties"]).toBeUndefined();
    expect(TenantsResource.options?.editProperties).toEqual(["slug", "display_name", "isolation_mode"]);
  });
});

describe("tenantIdOf", () => {
  it("is the session's tenantId", () => {
    expect(tenantIdOf({ email: "a@b.c", tenantId: "tenant_abc" })).toBe("tenant_abc");
  });

  it("names a missing session instead of failing on undefined", () => {
    expect(() => tenantIdOf(undefined)).toThrow(/no signed-in operator/);
  });
});
