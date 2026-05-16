# Action Grid Escalations

Cells that cannot be fixed in `admin-ui/` alone — each requires a backend change
(new admin-api endpoint or changed response shape).

---

## ESC-001 — Tenant-wide permission grants list endpoint missing

**Cell:** `permission_grants.list` (and `permission_grants.new` submit, `permission_grants.delete`)

**Symptom:**  
`permissions.ts` sets `listPath: "/v1/tenants/{tenantId}/permissions"`.  
`GET /v1/tenants/{tid}/permissions` → HTTP 404.  
`RestResource.find()` catches the error silently and returns `[]`, so the list
renders "No records" with no visible error.  
`new` handler POSTs to `/v1/tenants/${tenantId}/permissions` → also 404.  
`delete` handler DELETEs `/v1/tenants/${tenantId}/permissions/${permissionId}` → also 404 AND missing `agent_id` in path.

**Root cause:**  
The OpenAPI contract only defines agent-scoped permission endpoints:
- `GET /v1/tenants/{tid}/agents/{aid}/permissions`
- `POST /v1/tenants/{tid}/agents/{aid}/permissions`
- `DELETE /v1/tenants/{tid}/agents/{aid}/permissions/{pid}`

There is no tenant-level flat permissions list/create/delete endpoint.

**Options (needs decision):**

| Option | Admin-api change | Admin-ui change |
|---|---|---|
| A — Add tenant-wide flat endpoints | Add `GET /v1/tenants/{tid}/permissions`, `POST /v1/tenants/{tid}/permissions`, `DELETE /v1/tenants/{tid}/permissions/{pid}` to admin-api | Change `permissions.ts` listPath/handlers to these new paths |
| B — Re-scope UI to per-agent | None | Re-design `permission_grants` resource to require an agent ULID first, then call per-agent endpoints |

Option A is simpler for the UI but requires an ADR amendment or new ADR (adds
endpoints not in current OpenAPI). Option B is architecturally consistent but
degrades UX (two-step UI to create a grant).

**Recommended path:** Option A — add three flat tenant-scoped endpoints to admin-api. The permission table already has `tenant_id`; a flat list filtered by `tenant_id` (via RLS) is natural and follows the pattern used for services, agents, and audit.

**Blocking:** Phase 1 Playwright tests for `permission_grants` cannot be written until either option is implemented.

---

## ESC-002 — Tenant-wide service API keys list endpoint missing

**Cell:** `service_api_keys.list` (and all record-level actions: `revokeApiKey`, `rotateApiKey`)

**Symptom:**  
`api_keys.ts` sets `listPath: "/v1/tenants/{tenantId}/api-keys"`.  
`GET /v1/tenants/{tid}/api-keys` → HTTP 404.  
List renders "No records" with no visible error.  
Record-level actions (`revokeApiKey`, `rotateApiKey`) are untestable because no records appear.

**Root cause:**  
The OpenAPI contract only defines agent-scoped API key endpoints:
- `GET /v1/tenants/{tid}/agents/{aid}/api-keys`
- `POST /v1/tenants/{tid}/agents/{aid}/api-keys`
- `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/revoke`
- `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/rotate`

There is no tenant-level flat API key list endpoint.

**Options (needs decision):**

| Option | Admin-api change | Admin-ui change |
|---|---|---|
| A — Add tenant-wide flat endpoint | Add `GET /v1/tenants/{tid}/api-keys` returning all keys across all agents | Change `api_keys.ts` listPath to this new path |
| B — Re-scope UI to per-agent view | None | Re-design `service_api_keys` resource to require an agent ULID first, then list per-agent keys |

**Recommended path:** Option A — a flat tenant-scoped list with `agent_id` as a column is the most useful view for a platform admin ("show me all active API keys"). The underlying `service_api_keys` table has `tenant_id`; RLS handles isolation.

**Blocking:** Phase 1 tests for `service_api_keys` list, `revokeApiKey`, and `rotateApiKey` cannot be written until this is resolved. The `createApiKey` cell (missing component — a pure admin-ui fix) can be fixed independently once ESC-002 is escalated.

---

## Non-escalation notes

These cells are broken but fixable in admin-ui alone (no backend change):

| Cell | Fix needed |
|---|---|
| `services.testService` | Add `TestService` React component; register in `ComponentLoader` |
| `credentials.rotateCredential` | Add GET guard + React component for confirmation/result display |
| `agents.revokeAgent` | Add GET guard + React component for confirmation/result display |
| `service_api_keys.createApiKey` | Add `CreateApiKey` React component; register in `ComponentLoader` |
| `audit_events.list` | Change `listKey: "items"` → `listKey: "events"` in `audit.ts` |
| `audit_events.show` | Enable `show` action in `audit.ts` options; add `getPath` to `RestResource` config |
| `services.delete` / `agents.delete` | Investigate why `delete` action URL navigation returns "does not have action"; may need `component:` or capability flag on `RestResource` |
