/**
 * Helpers for parsing admin-api error responses into per-field error maps.
 *
 * Admin-api returns RFC-7807-ish bodies on 4xx.  When pydantic raises a
 * ValidationError the `detail` field carries the structured error array
 * (pydantic v2 format).  Other 4xx paths return `detail` as a plain string.
 *
 * This module normalises both shapes so CredentialNewForm can render
 * inline per-field messages without duplicating parsing logic.
 *
 * Source: C-2 chunk; ADR-0021; apps/admin-api/src/admin_api/api/credentials.py.
 */

/**
 * Single entry in a pydantic v2 error array.
 * `loc` is the field path (e.g. ["username"] or ["body", "value", "password"]).
 */
export interface PydanticErrorDetail {
  loc: (string | number)[];
  msg: string;
  type?: string;
  input?: unknown;
}

/**
 * Admin-api 4xx response body shape.
 * `detail` is either a plain string (legacy/simple paths) or a pydantic v2
 * error array (ValidationError paths in ssh_password, ssh_private_key, etc.).
 */
export interface AdminApiErrorResponse {
  type?: string;
  title?: string;
  detail?: string | PydanticErrorDetail[];
}

/**
 * Extract per-field errors from an admin-api error response body.
 *
 * Returns a map from field name → human-readable message.  Empty map means
 * no structured field errors were found (caller should render title/detail
 * as a single string instead).
 *
 * The field name is derived from the LAST string segment of pydantic's `loc`
 * array.  This handles both shallow (`["username"]`) and deep
 * (`["body", "value", "username"]`) paths that pydantic v2 emits.
 *
 * Only the first error per field is kept (pydantic can produce multiple
 * constraints per field; the first is the most actionable).
 */
export function extractFieldErrors(
  body: AdminApiErrorResponse | undefined
): Record<string, string> {
  if (!body || !Array.isArray(body.detail)) return {};
  const out: Record<string, string> = {};
  for (const e of body.detail) {
    // Find the last string in loc — that is the field name.
    const fieldName = [...e.loc].reverse().find((x): x is string => typeof x === "string");
    if (fieldName && !(fieldName in out)) {
      out[fieldName] = e.msg;
    }
  }
  return out;
}
