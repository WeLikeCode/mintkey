/**
 * EmailServiceCombobox — AdminJS edit-property component wrapper for email_service_id fields.
 *
 * Satisfies the AdminJS `editComponent` interface (props: property, record, onChange)
 * and delegates to AsyncCombobox with resourceId="email_services".
 *
 * Registered in components/index.ts and wired into email-permission-grants.ts via:
 *   properties.email_service_id.components.edit = Components.EmailServiceCombobox
 *
 * Display: "{name} ({imap_host}:{imap_port})" so the operator can identify the
 * email service at a glance without needing to know the UUID.
 *
 * Source: feat/email-perm-grants-pickers.
 */

import React from "react";
import AsyncCombobox from "./AsyncCombobox.js";

// AdminJS edit-component props interface
interface EditProps {
  property?: { path?: string; label?: string };
  record?: { params?: Record<string, unknown> };
  // AdminJS onChange receives (propertyOrEvent, value?)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onChange?: (propertyOrEvent: any, value?: any) => void;
}

// Label formatter: shows "{name} ({imap_host}:{imap_port})" for identification.
const labelFor = (params: Record<string, unknown>): string => {
  const name = (params.name as string) ?? "";
  const imapHost = (params.imap_host as string) ?? "";
  const imapPort = params.imap_port != null ? String(params.imap_port) : "";
  const id = (params.id as string) ?? "";

  if (name && imapHost && imapPort) {
    return `${name} (${imapHost}:${imapPort})`;
  }
  if (name && imapHost) {
    return `${name} (${imapHost})`;
  }
  return name || id;
};

const EmailServiceCombobox: React.FC<EditProps> = ({ property, record, onChange }) => {
  const path = property?.path ?? "email_service_id";
  const currentValue = String(record?.params?.[path] ?? "");

  const handleChange = (wireId: string) => {
    if (!onChange) return;
    // AdminJS convention: onChange(propertyPath, newValue)
    onChange(path, wireId);
  };

  return (
    <AsyncCombobox
      resourceId="email_services"
      value={currentValue}
      onChange={handleChange}
      placeholder="Search email services by name or host"
      labelFor={labelFor}
      testId="email-service-combobox"
    />
  );
};

export default EmailServiceCombobox;
