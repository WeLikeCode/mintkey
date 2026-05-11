/**
 * AdminJS Credentials resource — T-1.3.4 + T-1.8.4.
 *
 * READ: list credentials via @adminjs/sql (read-only).
 * WRITE: create/rotate via signed admin-api requests (ADR-0014.5).
 *
 * Plaintext credential never appears in the UI (ADR-0014.4, S-SEC-1).
 * The create form collects the plaintext once, forwards it to admin-api,
 * which calls the Vault Adapter — the plaintext never reaches AdminJS's DB
 * adapter.
 *
 * Source: T-1.3.4; T-1.8.4; Req 4; ADR-0013; ADR-0014.4; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { buildSignedRequest } from "../lib/signed-request.js";
import { RestResource } from "../lib/rest-resource.js";

const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";

export const CredentialsResource: ResourceWithOptions = {
  resource: new RestResource({
    id: "credentials", name: "Credentials",
    listPath: "/v1/tenants/{tenantId}/services",
    listKey: "services",
    idField: "id",
    properties: [
      { path: "id", type: "uuid", isId: true },
      { path: "name", type: "string" },
      { path: "slug", type: "string" },
      { path: "auth_scheme", type: "string" },
    ],
  }),
  options: {
    navigation: { name: "Credentials", icon: "Lock" },
    listProperties: ["id", "service_id", "auth_scheme", "key_version", "status", "created_at"],
    showProperties: ["id", "service_id", "auth_scheme", "key_version", "status", "created_at", "revoked_at"],
    // No editProperties — credentials cannot be edited directly
    filterProperties: ["service_id", "auth_scheme", "status"],
    actions: {
      // Create via admin-api (plaintext only sent once, never stored in AdminJS)
      new: {
        isVisible: true,
        label: "Register Credential",
        component: false,
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.payload?.service_id as string;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/services/${serviceId}/credentials`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${jwt}`,
              },
              // Forward plaintext credential to admin-api; admin-api sends to Vault
              body: JSON.stringify({
                auth_scheme: request.payload?.auth_scheme,
                plaintext: request.payload?.plaintext,
              }),
            }
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
            notice: { message: "Credential registered — plaintext shown once in admin-api response", type: "success" },
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
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const credentialId = request.params.recordId;

          // Fetch current service_id from record
          const serviceId = record?.get("service_id") as string;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/services/${serviceId}/credentials`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${jwt}`,
              },
              body: JSON.stringify({
                auth_scheme: record?.get("auth_scheme"),
                plaintext: request.payload?.new_plaintext,
                rotate_from: credentialId,
              }),
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
