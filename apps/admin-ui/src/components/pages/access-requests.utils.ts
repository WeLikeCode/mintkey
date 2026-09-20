/**
 * Pure utility functions + types for the Requests_Review_Area
 * (agent access requests).
 *
 * Kept free of any @adminjs/design-system / React import so the logic is
 * cleanly unit-testable in the node vitest project (same precedent as
 * budget-consumers.utils.ts).
 *
 * Source: agent-access-requests spec Task 8.2; design §Wire Contracts
 * (AccessRequest shape); Requirements 4.1, 4.2, 4.5, 4.6.
 */

import { getCredentialFields, type CredentialField } from "../../lib/auth-scheme.js";

/** Request kind discriminator (design §Data Models). */
export type RequestKind = "access" | "integration" | "share";

/** Request lifecycle status (design §Wire Contracts). */
export type RequestStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "cancelled";

/**
 * AccessRequest — the list-item / detail wire shape returned by
 * GET /admin/api/access-requests[/:requestId] (design §Wire Contracts,
 * OAS 3.1 AccessRequest schema). Nullable fields are `| null` on the wire.
 */
export interface AccessRequest {
  request_id: string;
  kind: RequestKind;
  status: RequestStatus;
  requesting_agent_id: string;
  service_id: string | null;
  action: string | null;
  target_agent_id: string | null;
  share_direction: "outbound" | "inbound" | null;
  /** Non-secret proposed config for integration proposals; never holds secrets. */
  proposed_config: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
  expires_at: string;
}

/** Selectable kinds for the kind filter control (Req 4.1). */
export const REQUEST_KINDS: RequestKind[] = ["access", "integration", "share"];

/** Selectable statuses for the status filter control (Req 4.1). */
export const REQUEST_STATUSES: RequestStatus[] = [
  "pending",
  "approved",
  "rejected",
  "expired",
  "cancelled",
];

export interface RequestFilterState {
  status: RequestStatus | "";
  kind: RequestKind | "";
}

/**
 * Client-side filter for the list table. Both filters apply as logical AND;
 * an empty string means "no filter on this field". The server also filters
 * (Req 4.1) — this mirrors that so the UI stays responsive when the operator
 * flips a control before the refetch lands.
 */
export function filterRequests(
  requests: AccessRequest[],
  filters: RequestFilterState,
): AccessRequest[] {
  return requests.filter((r) => {
    if (filters.status && r.status !== filters.status) return false;
    if (filters.kind && r.kind !== filters.kind) return false;
    return true;
  });
}

/**
 * Builds the human-readable "target summary" cell for the list table (Req 4.2):
 *   - access  → "service_id · action"
 *   - share   → "service_id · action → target_agent_id (direction)"
 *   - integration → proposed service name (proposed_config.name) or "(integration)"
 */
export function targetSummary(r: AccessRequest): string {
  if (r.kind === "integration") {
    const name =
      r.proposed_config && typeof r.proposed_config["name"] === "string"
        ? (r.proposed_config["name"] as string)
        : "";
    return name ? name : "(integration proposal)";
  }

  if (r.kind === "share") {
    const svc = r.service_id ?? "?";
    const action = r.action ?? "?";
    const target = r.target_agent_id ?? "?";
    const dir = r.share_direction ? ` (${r.share_direction})` : "";
    return `${svc} · ${action} → ${target}${dir}`;
  }

  // access
  const svc = r.service_id ?? "?";
  const action = r.action ?? "?";
  return `${svc} · ${action}`;
}

/**
 * Extracts the operator-supplied secret fields for an integration proposal's
 * detail view (Req 4.6). Derived from the proposed `auth_scheme` via the shared
 * auth-scheme registry; only fields flagged `secret` are returned so the detail
 * page renders them EMPTY and clearly labelled "operator-supplied". Non-secret
 * config is rendered separately from `proposed_config` and is NOT returned here.
 *
 * Returns [] when the request is not an integration proposal or the scheme is
 * unknown/has no secret fields (safe default).
 */
export function operatorSecretFields(r: AccessRequest): CredentialField[] {
  if (r.kind !== "integration" || !r.proposed_config) return [];
  const scheme = r.proposed_config["auth_scheme"];
  if (typeof scheme !== "string") return [];
  return getCredentialFields(scheme).filter((f) => f.secret);
}

/**
 * Non-secret proposed-config entries for the integration detail view (Req 4.6),
 * as ordered [key, displayValue] pairs. Any key matching the secret denylist is
 * defensively omitted so a stray secret value is never rendered even if one
 * somehow reached the row (belt-and-braces to the server-side create gate,
 * Req 2.4).
 */
const SECRET_KEY_DENYLIST = [
  // `*_secret` / bare `secret`, `*_password` / bare `password`,
  // `*_passphrase` / bare `passphrase` (Req 2.4 secret denylist).
  /(^|_)secret$/i,
  /(^|_)password$/i,
  /(^|_)passphrase$/i,
  /^private_key$/i,
  /^token$/i,
  /^api_key$/i,
];

export function nonSecretConfigEntries(
  r: AccessRequest,
): Array<[string, string]> {
  if (!r.proposed_config) return [];
  return Object.entries(r.proposed_config)
    .filter(([k]) => !SECRET_KEY_DENYLIST.some((re) => re.test(k)))
    .map(([k, v]) => {
      const display =
        v === null || v === undefined
          ? ""
          : typeof v === "string"
            ? v
            : JSON.stringify(v);
      return [k, display] as [string, string];
    });
}

/* ─────────────────────────────────────────────────────────────────────────
   Task 8.3 — pure guards + request-body builders for the action controls.

   Kept here (React-free) so the guards are unit-testable in the node vitest
   project (Task 8.4). The component wires these to the DOM; the guards
   themselves carry the Req 6.8 / Req 8.5 behavior.
   ───────────────────────────────────────────────────────────────────────── */

/**
 * Reject-reason guard (Req 8.5): a reason is valid for submission only when it
 * contains at least one non-whitespace character. Empty or whitespace-only
 * reasons MUST block submission client-side (the server also enforces
 * `reason_required`, Req 8.2).
 */
export function rejectReasonValid(reason: string): boolean {
  return reason.trim().length > 0;
}

/**
 * The names of the operator-supplied secret fields that MUST be filled before an
 * integration proposal can be finalized (Req 6.8). Derived from the same
 * auth-scheme registry the detail view renders (`operatorSecretFields`), so the
 * guard and the inputs stay in lock-step. Non-integration requests have none.
 */
export function requiredSecretFieldNames(r: AccessRequest): string[] {
  return operatorSecretFields(r)
    .filter((f) => f.required)
    .map((f) => f.name);
}

/**
 * Finalize guard (Req 6.8): the Finalize control is enabled ONLY once every
 * required operator secret field has a non-empty (non-whitespace) value.
 *
 * `secretValues` maps secret-field name → the operator-typed value. Missing keys
 * are treated as empty. For a request with no required secret fields this
 * returns false — an integration with no secret has nothing to finalize through
 * this path, and non-integration requests use Approve, not Finalize.
 */
export function finalizeEnabled(
  r: AccessRequest,
  secretValues: Record<string, string>,
): boolean {
  const required = requiredSecretFieldNames(r);
  if (required.length === 0) return false;
  return required.every((name) => (secretValues[name] ?? "").trim().length > 0);
}

/** Shape of the Connection_Test result rendered after a Test connection call. */
export interface ConnectionTestResult {
  ok: boolean;
  status_code?: number | null;
  latency_ms?: number | null;
  diagnostic?: string | null;
}

/**
 * Human-readable one-line summary of a Connection_Test result for display
 * (Req 6.8 / design §Connection_Test). Contains no secret material — it only
 * echoes the server-returned ok/status/latency/diagnostic, all of which are
 * guaranteed secret-free by the admin-api (Req 6.3).
 */
export function formatConnectionTestResult(res: ConnectionTestResult): string {
  const verdict = res.ok ? "OK" : "FAILED";
  const parts: string[] = [verdict];
  if (typeof res.status_code === "number") parts.push(`status ${res.status_code}`);
  if (typeof res.latency_ms === "number") parts.push(`${res.latency_ms}ms`);
  if (res.diagnostic) parts.push(res.diagnostic);
  return parts.join(" · ");
}

/**
 * Assembles the `{credential, config}` body for the Test connection
 * (`POST .../:requestId/test`) and Finalize (`POST .../:requestId/approve`)
 * calls (Req 6.2, 6.3, design §Wire Contracts).
 *
 *   - `credential`: the operator-typed secret field values (only non-empty ones
 *     are included) plus the `auth_scheme` copied from the proposal so the
 *     server knows how to interpret them. The secret is sent ONLY in this body;
 *     it is never persisted or echoed on the page (Req 6.1).
 *   - `config`: the non-secret config, seeded from `proposed_config` and
 *     overridden by any operator edits (`editedConfig`). Operator edits take
 *     precedence (Req 6.2).
 */
export function buildProposalActionBody(
  r: AccessRequest,
  secretValues: Record<string, string>,
  editedConfig: Record<string, string>,
): { credential: Record<string, string>; config: Record<string, string> } {
  const credential: Record<string, string> = {};

  const scheme =
    r.proposed_config && typeof r.proposed_config["auth_scheme"] === "string"
      ? (r.proposed_config["auth_scheme"] as string)
      : "";
  if (scheme) credential["auth_scheme"] = scheme;

  for (const name of operatorSecretFields(r).map((f) => f.name)) {
    const v = secretValues[name];
    if (v !== undefined && v !== "") credential[name] = v;
  }

  // Config: proposed non-secret entries as the base, operator edits override.
  const config: Record<string, string> = {};
  for (const [k, v] of nonSecretConfigEntries(r)) {
    config[k] = v;
  }
  for (const [k, v] of Object.entries(editedConfig)) {
    config[k] = v;
  }

  return { credential, config };
}
