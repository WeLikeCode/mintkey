/**
 * EmailServiceNewForm — custom new email-service action component (Bug-B fix).
 *
 * Replaces the default AdminJS new form for the Email Services resource.
 *
 * Features:
 *   1. Provider dropdown (gmail / outlook / generic).
 *   2. Auto-prefills IMAP/SMTP host+port and auth_scheme when provider is selected.
 *      Values come from well-known per-provider defaults (see PROVIDER_DEFAULTS below).
 *      Operator-typed values are NOT overwritten once the field has been manually edited.
 *   3. Selecting "generic" leaves all fields blank (operator must fill).
 *   4. Submit POSTs via AdminJS ApiClient → email_services new action → admin-api.
 *
 * Provider defaults match the YAML template catalog:
 *   - gmail:   imap.gmail.com:993, smtp.gmail.com:465, email_oauth2
 *   - outlook: outlook.office365.com:993, smtp.office365.com:587, email_oauth2
 *   - generic: blank
 *
 * Source: Bug-B; C-10; email-proxy contracts.
 */

import React, { useState } from "react";
import {
  Box,
  H3,
  Text,
  Button,
  Label,
  Input,
  Select,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";
import { useNavigate } from "react-router-dom";
import { PROVIDER_DEFAULTS } from "../../lib/email-provider-defaults.js";

// Re-export for consumers that import directly from this component
export { PROVIDER_DEFAULTS };

// ── types ────────────────────────────────────────────────────────────────────

// Props injected by AdminJS for resource-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

const EMAIL_PROVIDERS = [
  { value: "", label: "— select provider —" },
  { value: "gmail", label: "Gmail" },
  { value: "outlook", label: "Outlook / Microsoft 365" },
  { value: "generic", label: "Generic IMAP/SMTP" },
];

const EMAIL_AUTH_SCHEMES = [
  { value: "", label: "— select auth scheme —" },
  { value: "email_password", label: "Email + Password" },
  { value: "email_oauth2", label: "OAuth2 (Gmail / Outlook)" },
  { value: "email_app_password", label: "App Password" },
];

// ── styles ───────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #dee2e6",
  borderRadius: 4,
  fontSize: 14,
  lineHeight: "1.5",
  boxSizing: "border-box",
};

// ── EmailServiceNewForm ───────────────────────────────────────────────────────

const EmailServiceNewForm = (_props: Props): React.ReactElement => {
  const navigate = useNavigate();

  // Form state
  const [provider, setProvider] = useState("");
  const [name, setName] = useState("");
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState<number | "">("");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState<number | "">("");
  const [authScheme, setAuthScheme] = useState("");
  const [allowedRecipientDomains, setAllowedRecipientDomains] = useState("");
  const [poolSizeMax, setPoolSizeMax] = useState<number | "">("");
  const [tlsInsecureSkipVerify, setTlsInsecureSkipVerify] = useState(false);

  // Track which fields have been manually edited (so prefill doesn't overwrite)
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(new Set());

  const markDirty = (field: string) => {
    setDirtyFields((prev) => {
      const next = new Set(prev);
      next.add(field);
      return next;
    });
  };

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // ── Provider selection handler ────────────────────────────────────────────
  //
  // When the operator selects a provider, prefill all fields that have NOT been
  // manually edited yet. Once a field is dirty (operator typed in it), it is
  // never overwritten by a provider selection change.
  const handleProviderChange = (value: string) => {
    setProvider(value);

    const defaults = PROVIDER_DEFAULTS[value];
    if (!defaults) return; // unknown provider — leave blank

    if (!dirtyFields.has("imap_host")) {
      setImapHost(defaults.imap_host);
    }
    if (!dirtyFields.has("imap_port")) {
      setImapPort(defaults.imap_port);
    }
    if (!dirtyFields.has("smtp_host")) {
      setSmtpHost(defaults.smtp_host);
    }
    if (!dirtyFields.has("smtp_port")) {
      setSmtpPort(defaults.smtp_port);
    }
    if (!dirtyFields.has("auth_scheme")) {
      setAuthScheme(defaults.auth_scheme);
    }
  };

  // ── Submit ────────────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!provider) {
      setSubmitError("Please select a provider.");
      return;
    }
    if (!name.trim()) {
      setSubmitError("Name is required.");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const payload: Record<string, unknown> = {
      provider,
      name: name.trim(),
      auth_scheme: authScheme || undefined,
    };
    if (imapHost) payload.imap_host = imapHost;
    if (imapPort !== "") payload.imap_port = Number(imapPort);
    if (smtpHost) payload.smtp_host = smtpHost;
    if (smtpPort !== "") payload.smtp_port = Number(smtpPort);
    if (allowedRecipientDomains.trim()) {
      payload.allowed_recipient_domains = allowedRecipientDomains.trim();
    }
    if (poolSizeMax !== "") payload.pool_size_max = Number(poolSizeMax);
    if (tlsInsecureSkipVerify) {
      payload.tls_insecure_skip_verify = tlsInsecureSkipVerify;
    }

    const api = new ApiClient();
    try {
      const resp = await api.resourceAction({
        resourceId: "email_services",
        actionName: "new",
        method: "post",
        data: payload,
      });

      const data = resp.data as {
        record?: { params?: { id?: string }; id?: string };
        redirectUrl?: string;
        notice?: { message: string; type: string };
      };

      if (data?.notice?.type === "error") {
        setSubmitError(data.notice.message || "Failed to create email service.");
        return;
      }

      const serviceId =
        data?.record?.id ??
        data?.record?.params?.id ??
        "";

      if (serviceId) {
        navigate(`/admin/resources/email_services/records/${serviceId}/show`);
      } else if (data?.redirectUrl) {
        navigate(data.redirectUrl);
      } else {
        setSubmitError("Unexpected response from server. Please check the email services list.");
      }
    } catch (err: unknown) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to create email service."
      );
    } finally {
      setSubmitting(false);
    }
  };

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <Box variant="white" p="xxl" data-testid="email-service-new-form">
      <H3 mb="default">Create Email Service</H3>
      <Text mb="xl" style={{ color: "#6c757d" }}>
        Select a provider to auto-populate standard host, port and auth settings.
        You can edit any field after pre-fill.
      </Text>

      <form onSubmit={handleSubmit} noValidate>
        {/* ── Provider ─────────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-provider">Provider *</Label>
          <Select
            id="es-provider"
            value={EMAIL_PROVIDERS.find((o) => o.value === provider) ?? null}
            options={EMAIL_PROVIDERS}
            onChange={(opt: { value: string } | null) => {
              handleProviderChange(opt?.value ?? "");
            }}
            data-testid="es-provider-select"
          />
        </Box>

        {/* ── Name ─────────────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-name">Name *</Label>
          <Input
            id="es-name"
            value={name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setName(e.target.value);
              markDirty("name");
            }}
            placeholder="e.g. my-gmail-service"
            style={inputStyle}
            data-testid="es-name-input"
          />
        </Box>

        {/* ── IMAP host ────────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-imap-host">IMAP Host</Label>
          <Input
            id="es-imap-host"
            value={imapHost}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setImapHost(e.target.value);
              markDirty("imap_host");
            }}
            placeholder="e.g. imap.gmail.com"
            style={inputStyle}
            data-testid="es-imap-host-input"
          />
        </Box>

        {/* ── IMAP port ────────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-imap-port">IMAP Port</Label>
          <Input
            id="es-imap-port"
            type="number"
            value={imapPort === "" ? "" : String(imapPort)}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const v = e.target.value;
              setImapPort(v === "" ? "" : Number(v));
              markDirty("imap_port");
            }}
            placeholder="993"
            style={inputStyle}
            data-testid="es-imap-port-input"
          />
        </Box>

        {/* ── SMTP host ────────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-smtp-host">SMTP Host</Label>
          <Input
            id="es-smtp-host"
            value={smtpHost}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setSmtpHost(e.target.value);
              markDirty("smtp_host");
            }}
            placeholder="e.g. smtp.gmail.com"
            style={inputStyle}
            data-testid="es-smtp-host-input"
          />
        </Box>

        {/* ── SMTP port ────────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-smtp-port">SMTP Port</Label>
          <Input
            id="es-smtp-port"
            type="number"
            value={smtpPort === "" ? "" : String(smtpPort)}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const v = e.target.value;
              setSmtpPort(v === "" ? "" : Number(v));
              markDirty("smtp_port");
            }}
            placeholder="465"
            style={inputStyle}
            data-testid="es-smtp-port-input"
          />
        </Box>

        {/* ── Auth Scheme ───────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-auth-scheme">Auth Scheme</Label>
          <Select
            id="es-auth-scheme"
            value={EMAIL_AUTH_SCHEMES.find((o) => o.value === authScheme) ?? null}
            options={EMAIL_AUTH_SCHEMES}
            onChange={(opt: { value: string } | null) => {
              setAuthScheme(opt?.value ?? "");
              markDirty("auth_scheme");
            }}
            data-testid="es-auth-scheme-select"
          />
        </Box>

        {/* ── Allowed Recipient Domains ─────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-allowed-domains">Allowed Recipient Domains</Label>
          <Input
            id="es-allowed-domains"
            value={allowedRecipientDomains}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setAllowedRecipientDomains(e.target.value);
            }}
            placeholder="Comma-separated, leave blank to allow all"
            style={inputStyle}
            data-testid="es-allowed-domains-input"
          />
        </Box>

        {/* ── Max Pool Size ─────────────────────────────────────────────────── */}
        <Box mb="default">
          <Label htmlFor="es-pool-size">Max Pool Size</Label>
          <Input
            id="es-pool-size"
            type="number"
            value={poolSizeMax === "" ? "" : String(poolSizeMax)}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const v = e.target.value;
              setPoolSizeMax(v === "" ? "" : Number(v));
            }}
            placeholder="5"
            style={inputStyle}
            data-testid="es-pool-size-input"
          />
        </Box>

        {/* ── TLS insecure ─────────────────────────────────────────────────── */}
        <Box mb="xl">
          <label
            htmlFor="es-tls-insecure"
            style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, cursor: "pointer" }}
            data-testid="es-tls-insecure-label"
          >
            <input
              id="es-tls-insecure"
              type="checkbox"
              checked={tlsInsecureSkipVerify}
              onChange={(e) => setTlsInsecureSkipVerify(e.target.checked)}
              data-testid="es-tls-insecure-checkbox"
            />
            Disable TLS Certificate Verification (⚠ not recommended for public providers)
          </label>
        </Box>

        {/* ── Submit error ──────────────────────────────────────────────────── */}
        {submitError && (
          <Box
            mb="default"
            p="default"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
            }}
            data-testid="es-submit-error"
          >
            <Text style={{ color: "#721c24" }}>{submitError}</Text>
          </Box>
        )}

        {/* ── Buttons ───────────────────────────────────────────────────────── */}
        <Box style={{ display: "flex", gap: 12 }}>
          <Button
            type="submit"
            variant="primary"
            disabled={submitting}
            data-testid="es-submit-btn"
          >
            {submitting ? "Creating…" : "Create Email Service"}
          </Button>
          <Button
            type="button"
            variant="light"
            onClick={() => navigate("/admin/resources/email_services")}
            data-testid="es-cancel-btn"
          >
            Cancel
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default EmailServiceNewForm;
