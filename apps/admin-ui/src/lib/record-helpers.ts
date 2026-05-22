/**
 * Helpers for returning a well-formed RecordJSON from custom action handlers.
 *
 * AdminJS's frontend form renderer (New/Edit components) does
 * `record.params[path]` and `record.errors[path]` for every property. If a
 * handler returns `{ record: {} }` (e.g. from a `record?.toJSON() ?? {}`
 * fallback when `context.record` is undefined — which it always is for a `new`
 * action), the frontend throws `TypeError: Cannot read properties of undefined`
 * for each field. Every handler must therefore return a real RecordJSON: one
 * built via `resource.build(...)` (which carries `params`, `errors: {}`, etc.).
 *
 * Source: ADMIN_UI_SPEC.md §2.x; AdminJS 7.x New/Edit form renderer.
 */

import type { ActionContext, RecordJSON } from "adminjs";

/**
 * Return a RecordJSON for an action response.
 *
 * Prefers `context.record` (present for record-type actions: edit, testService,
 * revoke, rotate, …). For resource-type actions with no record (`new`), builds a
 * record from `fallbackParams` (typically `request.payload` so the form
 * repopulates after a validation error, or `{}` for a fresh form).
 */
export async function recordJSON(
  context: ActionContext,
  fallbackParams: Record<string, unknown> = {}
): Promise<RecordJSON> {
  const { record, resource, currentAdmin } = context;
  if (record) {
    return record.toJSON(currentAdmin);
  }
  const built = await resource.build(fallbackParams);
  return built.toJSON(currentAdmin);
}
