/**
 * AdminJS EmailPermissionGrants resource — feat/email-permission-grants.
 *
 * READ: list email permission grants via RestResource.
 * WRITE: create/revoke via apiWrite (session + CSRF, ADR-0014.5).
 *
 * Mirrors the PermissionsResource pattern but targets email_services
 * instead of HTTP services. The picker for email_service_id fetches from
 * /v1/tenants/{tenantId}/email-services (NOT /v1/tenants/{tenantId}/services).
 *
 * Source: feat/email-permission-grants.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";

const _emailPermissionGrantsResource = new RestResource({
  id: "email_permission_grants",
  name: "Email Permission Grants",
  listPath: "/v1/tenants/{tenantId}/email-permission-grants",
  listKey: "grants",
  idField: "id",
  filterKeys: [],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "tenant_id", type: "string" },
    { path: "agent_id", type: "string" },
    { path: "email_service_id", type: "string" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
  ],
});

export const EmailPermissionGrantsResource: ResourceWithOptions & {
  adminResource: typeof _emailPermissionGrantsResource;
} = {
  resource: _emailPermissionGrantsResource.resource,
  adminResource: _emailPermissionGrantsResource,
  options: {
    navigation: { name: "Email", icon: "Mail" },
    listProperties: [
      "id",
      "agent_id",
      "email_service_id",
      "created_at",
    ],
    showProperties: [
      "id",
      "tenant_id",
      "agent_id",
      "email_service_id",
      "created_at",
      "updated_at",
    ],
    editProperties: ["agent_id", "email_service_id"],
    filterProperties: ["agent_id", "email_service_id"],
    properties: {
      agent_id: {
        label: "Agent",
        isVisible: { list: true, show: true, edit: true, filter: true },
        description: "The agent being granted access to the email service.",
      },
      email_service_id: {
        label: "Email Service",
        isVisible: { list: true, show: true, edit: true, filter: true },
        description: "The email service the agent is being granted access to.",
      },
    },
    actions: {
      list: {
        isVisible: true,
      },
      show: {
        isVisible: true,
        handler: async (_request, _response, context) => ({
          record: await recordJSON(context),
        }),
      },
      new: {
        isVisible: true,
        handler: async (request, _response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          const agentId = request.payload?.agent_id as string | undefined;
          if (!agentId) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: "agent_id is required", type: "error" },
            };
          }

          const emailServiceId = request.payload?.email_service_id as string | undefined;
          if (!emailServiceId) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: "email_service_id is required", type: "error" },
            };
          }

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/email-permission-grants`,
            "POST",
            {
              agent_id: agentId,
              email_service_id: emailServiceId,
            },
            operatorOpts
          );

          if (!resp.ok) {
            const err = (await resp.json().catch(() => ({}))) as {
              title?: string;
            };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: {
                message:
                  err.title ?? "Failed to create email permission grant",
                type: "error",
              },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: { message: "Email permission grant created", type: "success" },
            redirectUrl: "/admin/resources/email_permission_grants",
          };
        },
      },
      delete: {
        isVisible: true,
        handler: async (request, _response, context) => {
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const grantId = request.params.recordId;
          const operatorOpts = operatorOptsFromAdmin(
            currentAdmin as Record<string, unknown>
          );

          await apiWrite(
            `/v1/tenants/${tenantId}/email-permission-grants/${grantId}`,
            "DELETE",
            undefined,
            operatorOpts
          );

          return {
            record: await recordJSON(context),
            notice: {
              message: "Email permission grant revoked",
              type: "success",
            },
            redirectUrl: "/admin/resources/email_permission_grants",
          };
        },
      },
      edit: { isVisible: false },
    },
  },
};
