/**
 * EmailServiceOAuth2Setup — OAuth2 authorize/callback component (C-10).
 *
 * Rendered on the email service show page when auth_scheme = email_oauth2.
 * Hides itself silently for other auth schemes.
 *
 * Flow:
 *   1. POST /admin/email-services/{tid}/{sid}/oauth2/{provider}/authorize  (BFF — same-origin)
 *      → admin-ui forwards server-side to admin-api → returns { auth_url: string }
 *   2. Opens auth_url in a new window (popup) or falls back to top-level redirect.
 *   3. On redirect-back the operator lands on a callback URL that includes
 *      `code` and `state` query params; those are forwarded server-side by C-9.
 *
 * CSRF state is enforced server-side (oauth2_state table, 10-min TTL, C-9).
 * This component only drives step 1 (get auth URL) + opens the browser window.
 *
 * Error states handled:
 *   - Non-ok response from /authorize endpoint.
 *   - Network / fetch failure.
 *   - Provider returns error= in redirect (shown if component remounts with
 *     ?oauth2_error= in the URL, set by the C-9 callback view).
 *   - State expired (oauth2_error=state_expired).
 *   - Token refresh failure (oauth2_error=refresh_failed).
 *
 * Source: C-10; C-9 oauth2_state table; email-proxy contracts.
 */

import React, { useState, useEffect } from "react";
import { Box, Button, Text, H3 } from "@adminjs/design-system";
import { useSearchParams } from "react-router-dom";

// ── types ────────────────────────────────────────────────────────────────────

// Props injected by AdminJS for show-page property components
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

interface AuthorizeResponse {
  // admin-api returns "authorize_url"; accept "auth_url" as legacy fallback
  authorize_url?: string;
  auth_url?: string;
  title?: string;
  detail?: string;
}

// ── helpers ──────────────────────────────────────────────────────────────────

// BFF base: the authorize call is forwarded server-side by admin-ui so the
// browser only talks to admin-ui (same origin — no CORS needed). The old
// ADMIN_API_PUBLIC_URL fallback caused NetworkErrors when the operator's
// browser was on a different host than localhost:8080.
const BFF_BASE = "";

const ERROR_MESSAGES: Record<string, string> = {
  state_expired: "The OAuth2 session timed out (state expired). Please try again.",
  refresh_failed: "Token refresh failed. Please re-authorize.",
  access_denied: "Access was denied by the provider. Please try again.",
  state_mismatch: "OAuth2 state mismatch — possible CSRF attempt. Please try again.",
};

function humanizeOAuth2Error(code: string): string {
  return ERROR_MESSAGES[code] ?? `OAuth2 error: ${code}`;
}

// ── EmailServiceOAuth2Setup ───────────────────────────────────────────────────

const EmailServiceOAuth2Setup = (props: Props): React.ReactElement | null => {
  const [searchParams] = useSearchParams();

  // Read record context — AdminJS show-page passes the record in props
  // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
  const record = props.record as {
    id?: string;
    params?: Record<string, unknown>;
  } | undefined;

  const serviceId = record?.id ?? "";
  const params = record?.params ?? {};

  const authScheme = params["auth_scheme"] as string | undefined;
  const provider = params["provider"] as string | undefined;
  const oauth2Authorized = params["oauth2_authorized"] as boolean | undefined;

  // Detect tenant_id from the record params (BFF-set field)
  const tenantId = params["tenant_id"] as string | undefined;

  // ── component state ───────────────────────────────────────────────────────
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // ── read oauth2_error from URL on mount (set by C-9 callback view) ────────
  useEffect(() => {
    const oauth2Error = searchParams.get("oauth2_error");
    if (oauth2Error) {
      setError(humanizeOAuth2Error(oauth2Error));
    }
    const oauth2Success = searchParams.get("oauth2_success");
    if (oauth2Success === "1") {
      setSuccess(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Only render for email_oauth2 scheme
  if (authScheme !== "email_oauth2") {
    return null;
  }

  // Normalize provider for the endpoint path — gmail / outlook only
  const normalizedProvider =
    provider === "gmail" || provider === "outlook" ? provider : "generic";

  // ── authorize handler ─────────────────────────────────────────────────────
  const handleAuthorize = async (): Promise<void> => {
    if (!tenantId || !serviceId) {
      setError("Missing tenant or service ID — cannot start OAuth2 flow.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const resp = await fetch(
        `${BFF_BASE}/admin/email-services/${tenantId}/${serviceId}/oauth2/${normalizedProvider}/authorize`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
        }
      );

      const body = (await resp.json().catch(() => ({}))) as AuthorizeResponse;
      // admin-api returns "authorize_url"; fall back to legacy "auth_url"
      const authUrl = body.authorize_url ?? body.auth_url;

      if (!resp.ok || !authUrl) {
        setError(body.title ?? body.detail ?? "Failed to start OAuth2 authorization.");
        setLoading(false);
        return;
      }

      // Open auth URL — try popup first, fall back to top-level navigation
      const popup = window.open(
        authUrl,
        "oauth2_authorize",
        "width=600,height=700,menubar=no,toolbar=no,location=yes"
      );

      if (!popup || popup.closed) {
        // Popup blocked — redirect the current window
        window.location.href = authUrl;
      }
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Network error — cannot reach the authorization endpoint."
      );
    } finally {
      setLoading(false);
    }
  };

  // ── render ────────────────────────────────────────────────────────────────

  const providerLabel =
    provider === "gmail"
      ? "Gmail"
      : provider === "outlook"
      ? "Outlook / Microsoft 365"
      : "email provider";

  return (
    <Box
      mb="xl"
      p="lg"
      style={{
        background: oauth2Authorized ? "#d4edda" : "#fff3cd",
        border: `1px solid ${oauth2Authorized ? "#c3e6cb" : "#ffc107"}`,
        borderRadius: 4,
      }}
      data-testid="email-service-oauth2-setup"
    >
      <H3 mb="default" style={{ fontSize: 16 }}>
        OAuth2 Authorization
      </H3>

      {/* Success banner */}
      {success && (
        <Box
          mb="default"
          p="default"
          style={{
            background: "#d4edda",
            border: "1px solid #c3e6cb",
            borderRadius: 4,
          }}
          data-testid="oauth2-success-banner"
        >
          <Text style={{ color: "#155724", fontWeight: 600 }}>
            Authorization successful! This email service is now connected to {providerLabel}.
          </Text>
        </Box>
      )}

      {/* Current authorization status */}
      {oauth2Authorized ? (
        <Box mb="default" data-testid="oauth2-authorized-status">
          <Text style={{ color: "#155724" }}>
            Connected to {providerLabel}. OAuth2 token is active.
          </Text>
        </Box>
      ) : (
        <Box mb="default" data-testid="oauth2-unauthorized-status">
          <Text style={{ color: "#856404" }}>
            Not yet authorized. Click the button below to connect to {providerLabel}.
          </Text>
        </Box>
      )}

      {/* Error display */}
      {error && (
        <Box
          mb="default"
          p="default"
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            borderRadius: 4,
          }}
          data-testid="oauth2-error"
        >
          <Text style={{ color: "#721c24" }}>{error}</Text>
        </Box>
      )}

      {/* Authorize / Re-authorize button */}
      <Box>
        <Button
          variant={oauth2Authorized ? "light" : "primary"}
          disabled={loading}
          onClick={handleAuthorize}
          data-testid="oauth2-authorize-button"
        >
          {loading
            ? "Starting authorization…"
            : oauth2Authorized
            ? `Re-authorize with ${providerLabel} →`
            : `Authorize with ${providerLabel} →`}
        </Button>
      </Box>

      <Box mt="default">
        <Text style={{ fontSize: 12, color: "#6c757d" }}>
          CSRF state is enforced server-side. The OAuth2 session expires in 10
          minutes if not completed.
        </Text>
      </Box>
    </Box>
  );
};

export default EmailServiceOAuth2Setup;
