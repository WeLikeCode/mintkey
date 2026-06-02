/**
 * EmailServiceCredentialForm — username + password form for email_password /
 * email_app_password email services (feat/email-credentials-and-ui-fixes).
 *
 * Rendered as a "set-credential" record action on the email_services show page.
 * Only visible when auth_scheme ∈ {email_password, email_app_password}.
 *
 * Submits to:
 *   POST /v1/tenants/{tid}/email-services/{sid}/credentials
 *
 * NFR-17 compliance: the form POSTs via AdminJS's action handler (handleAction) so
 * the plaintext only travels over the internal server-to-server channel. The
 * component itself never stores passwords beyond the React form session.
 *
 * Source: feat/email-credentials-and-ui-fixes; ADR-0024; NFR-17.
 */

import React, { useState } from "react";
import { Box, Button, Label, Text, H3 } from "@adminjs/design-system";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

const EmailServiceCredentialForm = (props: Props): React.ReactElement => {
  // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
  const record = props.record as {
    id?: string;
    params?: Record<string, unknown>;
  } | undefined;

  const params = record?.params ?? {};
  const authScheme = params["auth_scheme"] as string | undefined;

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    if (!username.trim()) {
      setError("Username is required.");
      return;
    }
    if (!password) {
      setError("Password is required.");
      return;
    }

    setSubmitting(true);

    try {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-explicit-any
      const handleAction = (props as any).handleAction as ((
        payload: Record<string, unknown>
      ) => Promise<void>) | undefined;

      if (handleAction) {
        await handleAction({ username, password, auth_scheme: authScheme });
        setSuccess(true);
        setUsername("");
        setPassword("");
      }
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "An unexpected error occurred."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const schemeLabel =
    authScheme === "email_app_password" ? "App Password" : "Password";

  return (
    <Box
      p="lg"
      style={{
        maxWidth: 480,
        border: "1px solid #dee2e6",
        borderRadius: 4,
        background: "#fff",
      }}
      data-testid="email-service-credential-form"
    >
      <H3 mb="default" style={{ fontSize: 16 }}>
        Set Email Credential
      </H3>

      <Text mb="lg" style={{ fontSize: 13, color: "#6c757d" }}>
        Enter the username and {schemeLabel.toLowerCase()} for this email service.
        The credential is stored encrypted in vault — it will never be displayed again.
      </Text>

      {success && (
        <Box
          mb="default"
          p="default"
          style={{
            background: "#d4edda",
            border: "1px solid #c3e6cb",
            borderRadius: 4,
          }}
          data-testid="credential-success"
        >
          <Text style={{ color: "#155724" }}>Credential set successfully.</Text>
        </Box>
      )}

      {error && (
        <Box
          mb="default"
          p="default"
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            borderRadius: 4,
          }}
          data-testid="credential-error"
        >
          <Text style={{ color: "#721c24" }}>{error}</Text>
        </Box>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div style={{ marginBottom: 12 }}>
          <Label htmlFor="cred-username">
            Username
          </Label>
          <input
            id="cred-username"
            data-testid="credential-username-input"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="user@example.com"
            style={{
              width: "100%",
              padding: "6px 10px",
              border: "1px solid #ced4da",
              borderRadius: 4,
              fontSize: 14,
              boxSizing: "border-box",
            }}
            disabled={submitting}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <Label htmlFor="cred-password">
            {schemeLabel}
          </Label>
          <input
            id="cred-password"
            data-testid="credential-password-input"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={`Enter ${schemeLabel.toLowerCase()}`}
            style={{
              width: "100%",
              padding: "6px 10px",
              border: "1px solid #ced4da",
              borderRadius: 4,
              fontSize: 14,
              boxSizing: "border-box",
            }}
            disabled={submitting}
          />
        </div>

        <Box mt="default">
          <Button
            type="submit"
            variant="primary"
            disabled={submitting}
            data-testid="credential-submit-button"
          >
            {submitting ? "Saving…" : "Save credential"}
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default EmailServiceCredentialForm;
