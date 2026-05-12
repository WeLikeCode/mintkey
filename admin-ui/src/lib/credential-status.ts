/**
 * Credential status badge utilities.
 *
 * Used by the Service detail "Credential" panel to display the current
 * credential state as a status badge.
 *
 * Source: ADMIN_UI_SPEC.md §2.3; T-1.3.4; ADR-0014.4.
 */

export type CredentialStatusType = "none" | "no_credential" | "configured" | "revoked";

export interface CredentialStatusBadge {
  type: CredentialStatusType;
  label: string;
  version?: number;
}

export interface ServiceForCredentialStatus {
  auth_scheme: string;
  current_key_version: number;
  status?: string;
}

/**
 * Returns the credential status badge for a service.
 *
 * Logic:
 *   - auth_scheme=none → "n/a (no auth)"
 *   - status=revoked   → "✗ revoked"
 *   - key_version=0    → "⚠ no credential"
 *   - key_version>0    → "✓ configured vN"
 */
export function getCredentialStatus(service: ServiceForCredentialStatus): CredentialStatusBadge {
  if (service.auth_scheme === "none") {
    return { type: "none", label: "n/a (no auth)" };
  }

  if (service.status === "revoked") {
    return { type: "revoked", label: "✗ revoked" };
  }

  if (!service.current_key_version || service.current_key_version === 0) {
    return { type: "no_credential", label: "⚠ no credential" };
  }

  return {
    type: "configured",
    label: `✓ configured v${service.current_key_version}`,
    version: service.current_key_version,
  };
}
