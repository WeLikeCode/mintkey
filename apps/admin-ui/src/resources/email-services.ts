/**
 * AdminJS EmailServices resource — C-10.
 *
 * READ via RestResource (calls admin-api HTTP).
 * WRITE via apiWrite (session + CSRF double-submit, ADR-0014.5).
 *
 * Mirrors the services/credentials resource pattern.
 *
 * List: tenant_id, provider, name, imap_host, smtp_host, auth_scheme, created_at.
 * Edit: provider (gmail/outlook/generic), imap_host/port, smtp_host/port,
 *       auth_scheme (email_password/email_oauth2/email_app_password),
 *       allowed_recipient_domains (csv), pool_size_max (number).
 *
 * For auth_scheme = email_oauth2: show Authorize button via EmailServiceOAuth2Setup.
 *
 * Source: C-10; email-proxy contracts.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

const EMAIL_PROVIDERS = [
  { value: "gmail", label: "Gmail" },
  { value: "outlook", label: "Outlook / Microsoft 365" },
  { value: "generic", label: "Generic IMAP/SMTP" },
];

const EMAIL_AUTH_SCHEMES = [
  { value: "email_password", label: "Email + Password" },
  { value: "email_oauth2", label: "OAuth2 (Gmail / Outlook)" },
  { value: "email_app_password", label: "App Password" },
];

const _emailServicesResource = new RestResource({
  id: "email_services",
  name: "Email Services",
  listPath: "/v1/tenants/{tenantId}/email-services",
  getPath: "/v1/tenants/{tenantId}/email-services/{id}",
  listKey: "email_services",
  idField: "id",
  filterKeys: ["q"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "tenant_id", type: "string" },
    { path: "provider", type: "string", availableValues: EMAIL_PROVIDERS },
    { path: "name", type: "string" },
    { path: "imap_host", type: "string" },
    { path: "imap_port", type: "number" },
    { path: "smtp_host", type: "string" },
    { path: "smtp_port", type: "number" },
    { path: "auth_scheme", type: "string", availableValues: EMAIL_AUTH_SCHEMES },
    { path: "allowed_recipient_domains", type: "string" },
    { path: "pool_size_max", type: "number" },
    { path: "oauth2_authorized", type: "boolean" },
    { path: "tls_insecure_skip_verify", type: "boolean" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
    // Virtual filter-only: free-text search on name
    { path: "q", type: "string" },
    // Virtual: OAuth2 setup widget (shown when auth_scheme = email_oauth2)
    { path: "_oauth2_setup", type: "string" },
  ],
});

export const EmailServicesResource: ResourceWithOptions & {
  adminResource: typeof _emailServicesResource;
} = {
  resource: _emailServicesResource.resource,
  adminResource: _emailServicesResource,
  options: {
    navigation: { name: "Email", icon: "Mail" },
    listProperties: [
      "tenant_id",
      "provider",
      "name",
      "imap_host",
      "smtp_host",
      "auth_scheme",
      "created_at",
    ],
    editProperties: [
      "provider",
      "name",
      "imap_host",
      "imap_port",
      "smtp_host",
      "smtp_port",
      "auth_scheme",
      "allowed_recipient_domains",
      "pool_size_max",
      "tls_insecure_skip_verify",
    ],
    showProperties: [
      "_oauth2_setup",
      "id",
      "tenant_id",
      "provider",
      "name",
      "imap_host",
      "imap_port",
      "smtp_host",
      "smtp_port",
      "auth_scheme",
      "allowed_recipient_domains",
      "pool_size_max",
      "tls_insecure_skip_verify",
      "oauth2_authorized",
      "created_at",
      "updated_at",
    ],
    filterProperties: ["q", "provider", "auth_scheme"],
    properties: {
      provider: {
        availableValues: EMAIL_PROVIDERS,
      },
      auth_scheme: {
        availableValues: EMAIL_AUTH_SCHEMES,
      },
      imap_port: {
        type: "number",
        description: "IMAP port (typical: 993 for TLS, 143 for STARTTLS).",
      },
      smtp_port: {
        type: "number",
        description: "SMTP port (typical: 587 for STARTTLS, 465 for TLS).",
      },
      allowed_recipient_domains: {
        label: "Allowed Recipient Domains",
        description:
          "Comma-separated list of domains agents are allowed to send to. Leave blank to allow all.",
      },
      pool_size_max: {
        type: "number",
        label: "Max Pool Size",
        description: "Maximum number of concurrent IMAP/SMTP connections. Default: 5.",
      },
      tls_insecure_skip_verify: {
        type: "boolean",
        label: "Disable TLS Certificate Verification",
        description:
          "⚠ TLS certificate verification DISABLED for this service. Connections to\n" +
          "the IMAP/SMTP server will not validate the server's TLS certificate.\n" +
          "Only enable this for trusted internal servers with self-signed or\n" +
          "private-CA certificates. NEVER enable this on a public mail provider\n" +
          "(Gmail, Outlook, iCloud, etc.).",
      },
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (name)",
        description: "Case-insensitive substring match on email service name.",
      },
      // Virtual OAuth2 setup widget — show only
      _oauth2_setup: {
        isVisible: {
          show: true,
          list: false,
          edit: false,
          new: false,
          filter: false,
        },
        label: "OAuth2 Authorization",
        description:
          "Authorize this email service with Gmail or Outlook via OAuth2.",
        components: {
          show: Components.EmailServiceOAuth2Setup,
        },
      },
    },
    actions: {
      // Explicit show action — AdminJS 7.x will not auto-generate show when other
      // actions are declared. Without this the show page 404s with:
      // "Resource ... does not have an action with name: show or you are not authorized to use it!"
      show: {
        isVisible: true,
        handler: async (_request, _response, context) => ({
          record: await recordJSON(context),
        }),
      },

      // set-credential: record action for email_password / email_app_password services
      "set-credential": {
        actionType: "record",
        icon: "Key",
        label: "Set credential",
        isVisible: (context) => {
          const scheme = context.record?.params?.["auth_scheme"] as string | undefined;
          return scheme === "email_password" || scheme === "email_app_password";
        },
        component: Components.EmailServiceCredentialForm,
        handler: async (request, _response, context) => {
          const { currentAdmin } = context;

          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }

          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/email-services/${serviceId}/credentials`,
            "POST",
            request.payload,
            operatorOpts
          );

          const body = (await resp.json().catch(() => ({}))) as {
            id?: string;
            title?: string;
            status?: string;
          };

          if (!resp.ok) {
            return {
              record: await recordJSON(context),
              notice: {
                message: body.title ?? "Failed to set credential",
                type: "error",
              },
            };
          }

          return {
            record: await recordJSON(context),
            notice: {
              message: "Credential set successfully.",
              type: "success",
            },
          };
        },
      },

      new: {
        isVisible: true,
        handler: async (request, _response, context) => {
          const { currentAdmin } = context;

          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/email-services`,
            "POST",
            request.payload,
            operatorOpts
          );

          const body = (await resp.json().catch(() => ({}))) as {
            id?: string;
            title?: string;
          };

          if (!resp.ok) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: {
                message: body.title ?? "Failed to create email service",
                type: "error",
              },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            redirectUrl: `/admin/resources/email_services/records/${body.id}/show`,
          };
        },
      },
      edit: {
        isVisible: true,
        handler: async (request, _response, context) => {
          const { currentAdmin } = context;

          if (request.method === "get") {
            return {
              record: await recordJSON(context, request.payload ?? {}),
            };
          }

          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/email-services/${serviceId}`,
            "PATCH",
            request.payload,
            operatorOpts
          );

          if (!resp.ok) {
            const err = (await resp.json()) as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: {
                message: err.title ?? "Failed to update email service",
                type: "error",
              },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
          };
        },
      },
      delete: {
        isVisible: true,
        handler: async (request, _response, context) => {
          const { currentAdmin, h, resource } = context;

          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }

          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/email-services/${serviceId}`,
            "DELETE",
            undefined,
            operatorOpts
          );

          if (!resp.ok) {
            const err = (await resp.json()) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: {
                message: err.title ?? "Failed to delete email service",
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
            notice: { message: "Email service deleted", type: "success" },
          };
        },
      },

      // ── BFF passthrough: POST /v1/tenants/{tid}/email-services/from-template
      // Called by ServiceTemplatePicker when kind=email_service is selected.
      // Takes {template_id, name?} and creates the email_services row.
      "from-template": {
        actionType: "resource",
        isVisible: false,
        handler: async (request, _response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/email-services/from-template`,
            "POST",
            request.payload,
            operatorOpts
          );

          let body: {
            id?: string;
            title?: string;
            detail?: string;
          } = {};
          try {
            body = (await resp.json()) as typeof body;
          } catch {
            // unparseable body — treat as empty
          }

          if (!resp.ok) {
            const baseRecord = await recordJSON(context, {});
            return {
              record: baseRecord,
              notice: {
                message:
                  body.title ??
                  body.detail ??
                  "Failed to create email service from template",
                type: "error",
              },
            };
          }

          if (!body.id) {
            const baseRecord = await recordJSON(context, {});
            return {
              record: baseRecord,
              notice: {
                message:
                  "Email service creation returned an unexpected response (no service id). Please retry.",
                type: "error",
              },
            };
          }

          const baseRecord = await recordJSON(context, {});
          return {
            record: {
              ...baseRecord,
              params: {
                ...baseRecord.params,
                service_id: body.id,
              },
            },
            email_service: body,
            redirectUrl: `/admin/resources/email_services/records/${body.id}/show`,
          };
        },
      },
    },
  },
};
