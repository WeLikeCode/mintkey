/**
 * AdminJS OAuth2Providers resource — feat/oauth2-providers-per-tenant-vault.
 *
 * Per-tenant OAuth2 client configuration for Gmail / Outlook.
 * Operators configure their own GCP / Azure OAuth2 client via this form.
 *
 * READ: lists configured providers (no client_secret ever shown).
 * WRITE: POST to admin-api (client_id + client_secret, type=password).
 * DELETE: removes config + revokes vault credential.
 *
 * client_secret is type=password in the new form; NEVER shown on the show page.
 *
 * Nav group: Email (same as Email Services).
 *
 * Sources: feat/oauth2-providers-per-tenant-vault §Layer 5; ADR-0024.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";

const OAUTH2_PROVIDERS = [
  { value: "gmail", label: "Gmail (Google)" },
  { value: "outlook", label: "Outlook / Microsoft 365" },
];

const _oauth2ProvidersResource = new RestResource({
  id: "oauth2_providers",
  name: "OAuth2 Providers",
  listPath: "/v1/tenants/{tenantId}/oauth2-providers",
  listKey: "providers",
  idField: "provider",
  filterKeys: [],
  properties: [
    { path: "provider", type: "string", isId: true, availableValues: OAUTH2_PROVIDERS },
    { path: "client_id_last4", type: "string" },
    { path: "configured_at", type: "datetime" },
    // Write-only fields (new/edit only — NEVER shown on show page)
    { path: "client_id", type: "string" },
    { path: "client_secret", type: "string" },
  ],
});

export const OAuth2ProvidersResource: ResourceWithOptions & {
  adminResource: typeof _oauth2ProvidersResource;
} = {
  resource: _oauth2ProvidersResource.resource,
  adminResource: _oauth2ProvidersResource,
  options: {
    navigation: { name: "Email", icon: "Mail" },
    listProperties: ["provider", "client_id_last4", "configured_at"],
    showProperties: ["provider", "client_id_last4", "configured_at"],
    // client_id + client_secret are new-only (NEVER in show/list)
    // AdminJS uses editProperties for BOTH new AND edit forms; per-property
    // isVisible.{new,edit} below scope each field to the right action.
    // (newProperties is not a recognized AdminJS key, so the previous form
    // rendered with no client_id/client_secret inputs.) The edit ACTION
    // itself is disabled in the actions block below — only the `new` form
    // ever renders these fields.
    editProperties: ["provider", "client_id", "client_secret"],
    filterProperties: [],
    properties: {
      provider: {
        availableValues: OAUTH2_PROVIDERS,
        label: "Provider",
        description: "OAuth2 provider: Gmail (Google) or Outlook (Microsoft 365).",
      },
      client_id_last4: {
        label: "Client ID (last 4)",
        description: "Last 4 characters of the configured OAuth2 client ID.",
        isVisible: { show: true, list: true, edit: false, new: false, filter: false },
      },
      configured_at: {
        label: "Configured At",
        description: "When this provider was last configured.",
        isVisible: { show: true, list: true, edit: false, new: false, filter: false },
      },
      client_id: {
        label: "Client ID",
        description:
          "Your OAuth2 client ID from the Google Cloud Console or Azure portal. " +
          "This is public information and stored in cleartext.",
        isVisible: { show: false, list: false, edit: false, new: true, filter: false },
      },
      client_secret: {
        label: "Client Secret",
        description:
          "Your OAuth2 client secret. Stored encrypted in vault. NEVER shown after saving.",
        isVisible: { show: false, list: false, edit: false, new: true, filter: false },
        type: "password",
      },
    },
    actions: {
      show: {
        isVisible: true,
        handler: async (_request, _response, context) => ({
          record: await recordJSON(context),
        }),
      },

      // Override list to hide the default 'new' button on list page
      list: {
        isVisible: true,
      },

      new: {
        isVisible: true,
        handler: async (request, _response, context) => {
          const { currentAdmin } = context;

          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const provider = (request.payload as Record<string, string>)?.["provider"] ?? "";
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/oauth2-providers/${provider}`,
            "POST",
            {
              client_id: (request.payload as Record<string, string>)?.["client_id"] ?? "",
              client_secret: (request.payload as Record<string, string>)?.["client_secret"] ?? "",
            },
            operatorOpts
          );

          const body = (await resp.json().catch(() => ({}))) as {
            provider?: string;
            client_id_last4?: string;
            configured_at?: string;
            title?: string;
          };

          if (!resp.ok) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: {
                message: body.title ?? "Failed to configure OAuth2 provider",
                type: "error",
              },
            };
          }

          return {
            record: await recordJSON(context, {
              provider: body.provider,
              client_id_last4: body.client_id_last4,
              configured_at: body.configured_at,
            }),
            notice: {
              message: `OAuth2 provider '${body.provider}' configured successfully.`,
              type: "success",
            },
            redirectUrl: `/admin/resources/oauth2_providers/records/${body.provider}/show`,
          };
        },
      },

      // Disable the built-in edit action — credentials are replaced via 'new'
      edit: {
        isVisible: false,
        isAccessible: false,
      },

      delete: {
        isVisible: true,
        handler: async (request, _response, context) => {
          const { currentAdmin, h, resource } = context;

          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }

          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const provider = request.params.recordId ?? "";
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/oauth2-providers/${provider}`,
            "DELETE",
            undefined,
            operatorOpts
          );

          if (!resp.ok) {
            const err = (await resp.json().catch(() => ({}))) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: {
                message: err.title ?? "Failed to delete OAuth2 provider config",
                type: "error",
              },
            };
          }

          return {
            record: await recordJSON(context),
            redirectUrl: h.resourceUrl({
              resourceId:
                resource._decorated?.id() ?? resource.id(),
            }),
            notice: { message: "OAuth2 provider config deleted", type: "success" },
          };
        },
      },
    },
  },
};
