/**
 * AdminJS Operators resource — operator-management.
 *
 * Visible ONLY to PlatformAdmin operators. Operator management is a
 * platform-level action: it mints and revokes the humans who hold
 * `is_platform_admin` and tenant-admin roles, so the resource mirrors the
 * platform-only Tenants resource (flat `/v1/operators`, platform-admin gate).
 *
 * READ: list operators via RestResource (GET /v1/operators → `{ data: [...] }`).
 * WRITE: promote (POST) / edit (PATCH) / deactivate (DELETE) via apiWrite
 * (session + signed-request + CSRF, ADR-0019).
 *
 * admin-api makes NO Keycloak call at promotion time: `oidc_sub` is optional and
 * binds lazily on the operator's first OIDC login (ADR-0020 / ADR-0031 D3).
 * `internal_password_hash` is never serialized (S-SEC-1).
 *
 * Source: operator-management OpenSpec change; ADR-0031; ADR-0019; ADR-0017.10.
 */

import type { ResourceWithOptions, ActionContext } from "adminjs";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { RestResource } from "../lib/rest-resource.js";
import { recordJSON } from "../lib/record-helpers.js";

function assertPlatformAdmin(context: ActionContext): void {
  const admin = context.currentAdmin as { isPlatformAdmin?: boolean };
  if (!admin.isPlatformAdmin) {
    throw new Error("PlatformAdmin required");
  }
}

// Property set reconciled with what admin-api returns for GET /v1/operators
// (`{ data: [...] }`, _operator_row_to_dict): id, tenant_id, email, display_name,
// oidc_sub, is_platform_admin, status, created_at. IDs are op_/tenant_ Crockford
// ULID wire-form (ADR-0017.10 / ADR-0031 D2). `internal_password_hash` is never
// returned by admin-api and is therefore never declared here (S-SEC-1).
//
// `q` is a virtual filter-only property (free-text search on email / display_name).
const _operatorsResource = new RestResource({
  id: "operators", name: "Operators",
  listPath: "/v1/operators",
  listKey: "data",
  idField: "id",
  filterKeys: ["q", "tenant_id", "status"],
  properties: [
    { path: "id", type: "uuid", isId: true },
    { path: "email", type: "string" },
    { path: "display_name", type: "string" },
    { path: "tenant_id", type: "string" },
    { path: "oidc_sub", type: "string" },
    { path: "is_platform_admin", type: "boolean" },
    { path: "status", type: "string" },
    { path: "created_at", type: "datetime" },
    // Virtual filter-only: free-text search on email / display_name
    { path: "q", type: "string" },
  ],
});

export const OperatorsResource: ResourceWithOptions & { adminResource: typeof _operatorsResource } = {
  resource: _operatorsResource.resource,
  adminResource: _operatorsResource,
  options: {
    navigation: { name: "Operators", icon: "Users" },
    listProperties: ["id", "email", "display_name", "is_platform_admin", "status", "created_at"],
    showProperties: ["id", "email", "display_name", "tenant_id", "oidc_sub", "is_platform_admin", "status", "created_at"],
    newProperties: ["email", "tenant_id", "display_name", "oidc_sub", "is_platform_admin"],
    editProperties: ["display_name", "is_platform_admin", "status"],
    filterProperties: ["q", "tenant_id", "status"],
    properties: {
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (email / name)",
        description: "Case-insensitive substring match on operator email and display_name.",
      },
      email: {
        description: "The operator's login email. Must match the Keycloak realm-mintkey user you are promoting. Unique within the home tenant.",
      },
      tenant_id: {
        label: "Home tenant (tenant_ ID)",
        description: "The operator's home tenant. Paste a tenant_… wire ID or a bare tenant UUID. The operator is granted an Admin membership in this tenant on creation.",
      },
      oidc_sub: {
        description: "Keycloak subject claim. Optional — leave blank and it binds lazily on the operator's first 'Sign in with Keycloak' (ADR-0020). Supply it only if you already know the sub; it must be unique.",
      },
      is_platform_admin: {
        label: "Platform admin",
        description: "Grants cross-tenant platform-admin powers (manage tenants and operators). Grant sparingly — this is the highest-privilege flag in Mintkey.",
      },
      status: {
        availableValues: [
          { value: "active", label: "active" },
          { value: "disabled", label: "disabled" },
        ],
        description: "`active` operators can establish a session. `disabled` (soft-deactivated) operators cannot log in; deactivation never hard-deletes the row.",
      },
    },

    // Resource is visible only to PlatformAdmin (mirrors Tenants).
    // Non-PlatformAdmin sessions get an empty list and blocked writes.
    actions: {
      list: {
        isVisible: ({ currentAdmin }: { currentAdmin?: { isPlatformAdmin?: boolean } }) =>
          currentAdmin?.isPlatformAdmin === true,
        before: [
          async (request, context) => {
            assertPlatformAdmin(context);
            return request;
          },
        ],
      },
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          assertPlatformAdmin(context);
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }
          const { currentAdmin } = context;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite("/v1/operators", "POST", request.payload, operatorOpts);

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to promote operator", type: "error" },
            };
          }

          const body = await resp.json().catch(() => ({})) as { email?: string };
          const who = body.email ?? (request.payload?.email as string | undefined) ?? "operator";
          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: { message: `Operator promoted — ${who}`, type: "success" },
            redirectUrl: "/admin/resources/operators",
          };
        },
      },
      edit: {
        isVisible: true,
        handler: async (request, response, context) => {
          assertPlatformAdmin(context);
          if (request.method === "get") {
            return { record: await recordJSON(context, request.payload ?? {}) };
          }
          const { currentAdmin } = context;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);
          const targetOperatorId = request.params.recordId;

          // Only the mutable columns (ADR-0031 D5: no updated_at). is_platform_admin
          // arrives from the AdminJS boolean control as a boolean or a "true"/"false"
          // string — normalise to a real boolean so pydantic accepts it.
          const payload = request.payload ?? {};
          const rawFlag = payload.is_platform_admin as boolean | string | undefined;
          const isPlatformAdmin =
            rawFlag === undefined ? undefined : rawFlag === true || rawFlag === "true";

          const resp = await apiWrite(
            `/v1/operators/${targetOperatorId}`,
            "PATCH",
            {
              display_name: payload.display_name,
              is_platform_admin: isPlatformAdmin,
              status: payload.status,
            },
            operatorOpts
          );

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to update operator", type: "error" },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: { message: "Operator updated", type: "success" },
          };
        },
      },
      delete: {
        isVisible: true,
        handler: async (request, response, context) => {
          assertPlatformAdmin(context);
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }
          const { currentAdmin } = context;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);
          const targetOperatorId = request.params.recordId ?? "";

          const resp = await apiWrite(
            `/v1/operators/${targetOperatorId}`,
            "DELETE",
            undefined,
            operatorOpts
          );

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: { message: err.title ?? "Failed to deactivate operator", type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
            notice: { message: "Operator deactivated (status=disabled)", type: "success" },
            redirectUrl: "/admin/resources/operators",
          };
        },
      },
    },
  },
};
