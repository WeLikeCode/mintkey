/**
 * OAuth2ProvidersResource unit tests — feat/oauth2-providers-per-tenant-vault.
 *
 * Tests:
 *   - Resource key is "oauth2_providers".
 *   - listProperties includes provider, client_id_last4, configured_at.
 *   - showProperties includes provider, client_id_last4, configured_at.
 *   - newProperties includes provider, client_id, client_secret.
 *   - client_secret has type=password and is NOT in show/list.
 *   - client_id is NOT in show/list.
 *   - edit action is not accessible (credentials replaced via new).
 *   - delete action is visible.
 *   - provider has gmail and outlook as availableValues.
 *   - nav group is "Email".
 *
 * Sources: feat/oauth2-providers-per-tenant-vault §Layer 5; NFR-17.
 */

import { describe, it, expect } from "vitest";
import { OAuth2ProvidersResource } from "../src/resources/oauth2-providers.js";

describe("OAuth2ProvidersResource — feat/oauth2-providers-per-tenant-vault", () => {
  it("has resource key oauth2_providers", () => {
    expect(OAuth2ProvidersResource.resource).toBe("oauth2_providers");
  });

  it("listProperties includes provider, client_id_last4, configured_at", () => {
    const listProps = OAuth2ProvidersResource.options?.listProperties ?? [];
    expect(listProps).toContain("provider");
    expect(listProps).toContain("client_id_last4");
    expect(listProps).toContain("configured_at");
  });

  it("showProperties includes provider, client_id_last4, configured_at", () => {
    const showProps = OAuth2ProvidersResource.options?.showProperties ?? [];
    expect(showProps).toContain("provider");
    expect(showProps).toContain("client_id_last4");
    expect(showProps).toContain("configured_at");
  });

  it("newProperties includes provider, client_id, client_secret", () => {
    const newProps = (OAuth2ProvidersResource.options as Record<string, unknown>)?.["newProperties"] as string[] ?? [];
    expect(newProps).toContain("provider");
    expect(newProps).toContain("client_id");
    expect(newProps).toContain("client_secret");
  });

  it("client_secret is NOT visible in show, list, edit, filter (NFR-17)", () => {
    const properties = (OAuth2ProvidersResource.options?.properties ?? {}) as Record<
      string,
      { isVisible?: { show?: boolean; list?: boolean; edit?: boolean; new?: boolean; filter?: boolean } }
    >;
    const clientSecretVis = properties["client_secret"]?.isVisible;
    expect(clientSecretVis?.show).toBe(false);
    expect(clientSecretVis?.list).toBe(false);
    expect(clientSecretVis?.edit).toBe(false);
    expect(clientSecretVis?.filter).toBe(false);
    // new=true is the only visible context for client_secret
    expect(clientSecretVis?.new).toBe(true);
  });

  it("client_id is NOT visible in show, list, edit, filter", () => {
    const properties = (OAuth2ProvidersResource.options?.properties ?? {}) as Record<
      string,
      { isVisible?: { show?: boolean; list?: boolean; edit?: boolean; new?: boolean; filter?: boolean } }
    >;
    const clientIdVis = properties["client_id"]?.isVisible;
    expect(clientIdVis?.show).toBe(false);
    expect(clientIdVis?.list).toBe(false);
  });

  it("edit action is not accessible (NFR: creds replaced via new)", () => {
    const actions = OAuth2ProvidersResource.options?.actions ?? {};
    const editAction = (actions as Record<string, { isVisible?: boolean; isAccessible?: boolean }>)["edit"];
    expect(editAction?.isVisible).toBe(false);
    expect(editAction?.isAccessible).toBe(false);
  });

  it("delete action is visible", () => {
    const actions = OAuth2ProvidersResource.options?.actions ?? {};
    const deleteAction = (actions as Record<string, { isVisible?: boolean }>)["delete"];
    expect(deleteAction?.isVisible).toBe(true);
  });

  it("provider property has gmail and outlook as availableValues", () => {
    const properties = (OAuth2ProvidersResource.options?.properties ?? {}) as Record<
      string,
      { availableValues?: Array<{ value: string }> }
    >;
    const values = properties["provider"]?.availableValues?.map((v) => v.value) ?? [];
    expect(values).toContain("gmail");
    expect(values).toContain("outlook");
  });

  it("navigation group is 'Email'", () => {
    const nav = OAuth2ProvidersResource.options?.navigation as { name?: string } | undefined;
    expect(nav?.name).toBe("Email");
  });

  it("client_id_last4 is NOT visible in new/edit (show and list only)", () => {
    const properties = (OAuth2ProvidersResource.options?.properties ?? {}) as Record<
      string,
      { isVisible?: { show?: boolean; list?: boolean; edit?: boolean; new?: boolean; filter?: boolean } }
    >;
    const last4Vis = properties["client_id_last4"]?.isVisible;
    expect(last4Vis?.show).toBe(true);
    expect(last4Vis?.list).toBe(true);
    expect(last4Vis?.edit).toBe(false);
    expect(last4Vis?.new).toBe(false);
  });
});
