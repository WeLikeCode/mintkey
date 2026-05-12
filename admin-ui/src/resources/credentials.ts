/**
 * AdminJS Credentials resource — T-1.3.4 + T-1.8.4.
 *
 * READ: list credentials via RestResource.
 * WRITE: create/rotate via apiWrite (session + CSRF, ADR-0014.5).
 *
 * Plaintext credential never appears in the UI (ADR-0014.4, S-SEC-1).
 *
 * Source: T-1.3.4; T-1.8.4; Req 4; ADR-0013; ADR-0014.4; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { buildCredentialPayload } from "../lib/auth-scheme.js";
import { apiWrite } from "../lib/api-client.js";

const _credentialsResource = new RestResource({
  id: "credentials", name: "Credentials",
  listPath: "/v1/tenants/{tenantId}/services",
  listKey: "services",
  idField: "id",
  properties: [
    { path: "id", type: "uuid", isId: true },
    { path: "name", type: "string" },
    { path: "slug", type: "string" },
    { path: "auth_scheme", type: "string" },
    { path: "current_key_version", type: "number" },
    { path: "status", type: "string" },
  ],
});

export const CredentialsResource: ResourceWithOptions & { adminResource: typeof _credentialsResource } = {
  resource: _credentialsResource.resource,
  adminResource: _credentialsResource,
  options: {
    navigation: { name: "Credentials", icon: "Lock" },
    // Service is first column per ADMIN_UI_SPEC.md §2.4
    listProperties: ["name", "auth_scheme", "current_key_version", "status"],
    showProperties: ["id", "name", "slug", "auth_scheme", "current_key_version", "status"],
    // No editProperties — credentials cannot be edited directly
    filterProperties: ["auth_scheme", "status"],
    actions: {
      // Create via admin-api (plaintext only sent once, never stored in AdminJS)
      new: {
        isVisible: true,
        label: "Register Credential",
        component: false,
        handler: async (request, response, context) => {
          const { resource, currentAdmin, record } = context;
          if (request.method === "get") {
            const emptyRecord = await resource.build({});
            return { record: emptyRecord.toJSON(currentAdmin) };
          }
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.payload?.service_id as string;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}/credentials`,
            "POST",
            buildCredentialPayload(
              request.payload?.auth_scheme as string ?? "none",
              request.payload as Record<string, string> ?? {}
            )
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to register credential", type: "error" },
            };
          }

          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: { message: "Credential registered", type: "success" },
          };
        },
      },
      edit: { isVisible: false },
      delete: { isVisible: false },

      // T-1.8.4: Rotate action
      rotateCredential: {
        actionType: "record",
        label: "Rotate",
        icon: "RotateCw",
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const credentialId = request.params.recordId;
          const serviceId = record?.get("id") as string;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}/credentials`,
            "POST",
            {
              auth_scheme: record?.get("auth_scheme"),
              rotate_from: credentialId,
            }
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Rotation failed", type: "error" },
            };
          }

          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: { message: "Credential rotated — old version deprecated, new version active", type: "success" },
          };
        },
      },
    },
  },
};
