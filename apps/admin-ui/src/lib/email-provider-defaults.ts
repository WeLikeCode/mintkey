/**
 * Provider defaults for email service IMAP/SMTP configuration (Bug-B fix).
 *
 * Used by EmailServiceNewForm to prefill IMAP/SMTP host+port and auth_scheme
 * when the operator selects a provider. Extracted as a standalone module so
 * it can be imported by node-env tests without pulling in React/adminjs-design-system.
 *
 * Values match the YAML template catalog (email_gmail_oauth2 / email_outlook_oauth2).
 *
 * Source: Bug-B; C-10; email-proxy contracts.
 */

export interface EmailProviderDefaults {
  imap_host: string;
  imap_port: number | "";
  smtp_host: string;
  smtp_port: number | "";
  auth_scheme: string;
}

/**
 * Per-provider prefill defaults.
 *
 * - gmail:   imap.gmail.com:993, smtp.gmail.com:465,       email_oauth2
 * - outlook: outlook.office365.com:993, smtp.office365.com:587, email_oauth2
 * - generic: all blank — operator must fill
 */
export const PROVIDER_DEFAULTS: Record<string, EmailProviderDefaults> = {
  gmail: {
    imap_host: "imap.gmail.com",
    imap_port: 993,
    smtp_host: "smtp.gmail.com",
    smtp_port: 465,
    auth_scheme: "email_oauth2",
  },
  outlook: {
    imap_host: "outlook.office365.com",
    imap_port: 993,
    smtp_host: "smtp.office365.com",
    smtp_port: 587,
    auth_scheme: "email_oauth2",
  },
  generic: {
    imap_host: "",
    imap_port: "",
    smtp_host: "",
    smtp_port: "",
    auth_scheme: "",
  },
};
