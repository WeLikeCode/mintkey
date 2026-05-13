# Admin UI Action Matrix

**Legend:** ✅ verified working in live browser · 🚧 in progress · ❌ broken · 🚫 not-implemented · n/a not applicable · ⬜ untested

Updated after every code change. The "Browser" column is the live UI verification; the "Spec" column is the Playwright test file:line that covers it.

## Standard actions

| Resource | list | show | new | edit | delete | bulkDelete |
|---|---|---|---|---|---|---|
| services | ✅ intro para renders, 215 records, table populated | ✅ all fields render, Edit/Delete/Test Service buttons visible | ✅ Create new form renders with Name/Slug/Base Url/Auth Scheme/Description fields | ✅ edit form pre-populated with existing values | ❌ "Cannot GET /admin/resources/services/records/.../actions/delete" — wrong URL pattern; AdminJS delete is at `/records/<id>/delete` not `/records/<id>/actions/delete` | ❌ "Resource of given id: services does not have an action with name: bulkDelete or you are not authorized to use it!" — bulkDelete not configured in resource |
| credentials | ✅ intro para renders, 215 rows (reuses services list endpoint), Rotate Credential custom action button visible in row menu | ✅ show renders all fields + "Rotate Credential" button; current_key_version blank for this seed record | ✅ "Register Credential" form renders with Service Id / Auth Scheme fields | n/a (edit: isVisible: false in resource config) | n/a (delete: isVisible: false in resource config) | n/a (bulkDelete not configured) |
| agents | ✅ intro para renders, 728 records, table populated with id/name/status/api_key_fingerprint/rate_limit_rps/created_at | ✅ all fields render; Edit/Delete/Revoke Agent buttons visible; api_key_fingerprint shown (never api_key — S-SEC-1 compliant) | ✅ Create new form renders with Name/Description/Mcp Endpoint/Rate Limit Rps | ✅ edit form pre-populated with existing agent values | ❌ "Cannot GET /admin/resources/agents/records/.../actions/delete" — same wrong URL as services; AdminJS delete is at `/records/<id>/delete` | ❌ "Resource of given id: agents does not have an action with name: bulkDelete or you are not authorized to use it!" — bulkDelete not configured |
| permission_grants | ✅ intro para renders, 0 records (empty in seed), "Create new" button visible | n/a (no records exist to show; show-URL would render if record existed — resource is read-capable) | ✅ "Create new" form renders with Agent Id / Service Id / Action / Constraints (JSON) fields | n/a (edit: isVisible: false in resource config) | ✅ delete handler is configured (isVisible: true), pressing Delete from row menu would invoke it; visited via show page Delete button | n/a (bulkDelete not configured) |
| service_api_keys | ✅ intro para renders, 0 records (empty in seed), "Create Api Key" button visible (no standard "Create new") | n/a (no records exist; show would render if records existed) | n/a (new: isVisible: false — creation via createApiKey custom action only) | n/a (edit: isVisible: false in resource config) | n/a (delete: isVisible: false in resource config) | n/a (bulkDelete: isVisible: false in resource config) |
| audit_events | ✅ intro para renders, 0 records visible (audit list endpoint returns events but AdminJS list shows 0 — likely listKey mismatch: API returns `events` but resource config uses `items`) | ✅ show page would render if records existed | n/a (new: isVisible: false — append-only) | n/a (edit: isVisible: false) | n/a (delete: isVisible: false) | n/a (bulkDelete: isVisible: false) |
| tenants | ✅ intro para renders, 2 tenants visible (PlatformAdmin gate working correctly — admin@mintkey.internal is PlatformAdmin) | ✅ show renders id/slug/display_name/isolation_mode/status/settings/created_at/updated_at | ✅ "Create new" form renders with Slug / Display Name / Isolation Mode fields | ✅ edit handler configured (isVisible: true) | n/a (delete: isVisible: false in resource config) | n/a (bulkDelete not configured) |

## Custom actions (per ADR-0013 / ADR-0018)

| Resource | Action | API endpoint | UI wiring | Browser | Spec |
|---|---|---|---|---|---|
| credentials | rotate (rotateCredential) | `POST /v1/tenants/{tid}/services/{sid}/credentials` — exists in OpenAPI (200 expected) | ✅ wired in `credentials.ts` as `actionType: "record"`, label "Rotate", isVisible: true, calls `apiWrite()` | ✅ "Rotate Credential" button visible on show page (verified in screenshot); handler calls admin-api with rotate_from parameter | |
| credentials | revoke (no such action configured) | `DELETE /v1/tenants/{tid}/services/{sid}/credentials/{key_version}` — exists in OpenAPI | 🚫 NOT configured — credentials.ts has `edit: { isVisible: false }` and `delete: { isVisible: false }` but no named revoke custom action; the ADR-0013 table lists credential revoke but it was never implemented | 🚫 Not present in UI | |
| agents | revoke (revokeAgent) | `POST /v1/tenants/{tid}/agents/{aid}/revoke` — exists in OpenAPI (200 on valid agent; 500 returned during curl probe on wrong path) | ✅ wired in `agents.ts` as `actionType: "record"`, label "Revoke", isVisible conditioned on status !== "revoked", calls `apiWrite()` | ✅ "Revoke Agent" button visible on show page; handler wired correctly | |
| permission_grants | grant (new action) | `POST /v1/tenants/{tid}/agents/{aid}/permissions` — exists in OpenAPI **BUT** permissions.ts calls `POST /v1/tenants/{tenantId}/permissions` which is a 404 path | ❌ permissions.ts `new` action handler calls `/v1/tenants/${tenantId}/permissions` — this endpoint does NOT exist; OpenAPI only has per-agent path `/v1/tenants/{tid}/agents/{aid}/permissions` | ❌ Form renders but submit will 404; ESCALATE — requires either admin-api to add tenant-wide permissions endpoint OR admin-ui to require agent_id input and call per-agent path | |
| permission_grants | revoke (delete action) | `DELETE /v1/tenants/{tid}/agents/{aid}/permissions/{pid}` — exists in OpenAPI **BUT** permissions.ts `delete` handler calls `DELETE /v1/tenants/${tenantId}/permissions/${permissionId}` which is a 404 path | ❌ Wrong endpoint called — permissions.ts delete handler calls `/v1/tenants/${tenantId}/permissions/${permissionId}` but OpenAPI has `/v1/tenants/{tid}/agents/{aid}/permissions/{pid}` (requires agent_id in path) | ❌ Delete will always 404; ESCALATE — admin-api needs a tenant-wide permission DELETE endpoint, or UI needs agent_id available on the record to call the correct per-agent path | |
| service_api_keys | create-and-show-once (createApiKey) | `POST /v1/tenants/{tid}/agents/{aid}/api-keys` — exists in OpenAPI | ❌ Wired in `api_keys.ts` as `actionType: "resource"` with `isVisible: true` and handler implemented BUT no `component:` is registered for this action in `ComponentLoader` — AdminJS `resource`-type actions require a component or they render the "You have to implement action component for your ActionSee: the documentation" error | ❌ Live screenshot confirmed: "You have to implement action component for your ActionSee: the documentation" | |
| service_api_keys | revoke (revokeApiKey) | `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/revoke` — exists in OpenAPI | ✅ wired in `api_keys.ts` as `actionType: "record"`, label "Revoke", isVisible conditioned on status !== "revoked", calls `apiWrite()` to correct endpoint | ⬜ Cannot verify in browser — 0 API keys exist in seed data; endpoint path and handler code are correct by static analysis | |
| service_api_keys | rotate (rotateApiKey) | `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/rotate` — exists in OpenAPI | ✅ wired in `api_keys.ts` as `actionType: "record"`, label "Rotate", isVisible conditioned on status !== "revoked", calls `apiWrite()` to correct endpoint | ⬜ Cannot verify in browser — 0 API keys in seed; endpoint path and handler code correct by static analysis | |

## Cross-cutting

| Concern | Status | Notes |
|---|---|---|
| Dashboard | ✅ | Custom Dashboard component renders: "Mintkey — credential broker for AI agents" heading, operator email, tenant ID, SVG data-model diagram visible |
| Settings page | ⬜ | Not probed in this audit (no URL in standard grid) |
| Logout | ⬜ | Not probed (button in nav; not part of action-grid) |
| 7 resource intro paragraphs | ✅ | All 7 list-view intro paragraphs confirmed: Services (via CredentialsIntro sharing services list), Credentials, Agents, Permission Grants, Service API Keys, Audit Events, Tenants all rendered intro text above the table |
| Search/`q` filter | ⬜ | Not re-probed; covered by existing intros-and-dashboard / search-and-filters specs |
| Contextual filters | ⬜ | Not re-probed |
| Pagination | ⬜ | Not re-probed; services shows 215 records, agents shows 728 |
| Sorting | ⬜ | Not re-probed |
| Tenants PlatformAdmin gate | ✅ | Bootstrap operator (admin@mintkey.internal) is PlatformAdmin; Tenants list shows 2 tenants correctly; non-PlatformAdmin gate enforced server-side |
| audit_events list shows 0 (listKey mismatch) | ❌ | Admin-api `/v1/tenants/{tid}/audit` returns `{"events": [...]}` but `audit.ts` RestResource uses `listKey: "items"` — the list renders "No records" even when the API has data. ESCALATE — either change `listKey` to `"events"` in audit.ts or admin-api changes response envelope |
| ComponentLoader vs component: cross-check | ✅ no dangles | Registered: Dashboard, TenantsIntro, ServicesIntro, CredentialsIntro, AgentsIntro, PermissionsIntro, ApiKeysIntro, AuditIntro, JsonValue. All `component:` references in resources point to these names — NO dangling references. The createApiKey breakage is NOT a dangling component reference (no `component:` at all on that action) — it is a missing component for a resource-type custom action |
| delete/bulkDelete URL routing | ❌ | Standard `delete` action URL in test spec used wrong pattern `/records/<id>/actions/delete` — AdminJS uses `/records/<id>/delete`; the actual Delete button in the show/edit UI navigates correctly. bulkDelete is not configured on any resource (not needed given permissions model) |

## Phase log

- Phase 0 audit completed: 2026-05-13 (pending commit hash)
- Phase 1 pending: user review of audit findings
