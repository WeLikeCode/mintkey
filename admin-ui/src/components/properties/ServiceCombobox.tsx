/**
 * ServiceCombobox — AdminJS edit-property component wrapper for service_id fields.
 *
 * Satisfies the AdminJS `editComponent` interface (props: property, record, onChange)
 * and delegates to AsyncCombobox with resourceId="services".
 *
 * Registered in components/index.ts and wired into permissions.ts via:
 *   properties.service_id.components.edit = Components.ServiceCombobox
 *
 * UX-FB-B: passes a custom labelFor that appends " ⚠ no credential" when the
 * service has auth_scheme !== 'none' and current_key_version === 0, so the
 * operator sees the gap at grant-creation time.
 *
 * Source: UX-A; admin-ui-ux-uplift Wave 2; UX-FB-B.
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

// Label formatter: appends "⚠ no credential" when service lacks an active credential.
const labelFor = (params: Record<string, unknown>): string => {
  const name = (params.name as string) ?? "";
  const id = (params.id as string) ?? "";
  const ver = Number(params.current_key_version ?? 0);
  const scheme = (params.auth_scheme as string) ?? "";
  const suffix = scheme !== "none" && ver === 0 ? " ⚠ no credential" : "";
  return name ? `${name} (${id})${suffix}` : id;
};

const ServiceCombobox: React.FC<EditProps> = ({ property, record, onChange }) => {
  const path = property?.path ?? "service_id";
  const currentValue = String(record?.params?.[path] ?? "");

  const handleChange = (wireId: string) => {
    if (!onChange) return;
    // AdminJS convention: onChange(propertyPath, newValue)
    onChange(path, wireId);
  };

  return (
    <AsyncCombobox
      resourceId="services"
      value={currentValue}
      onChange={handleChange}
      placeholder="Search services by name or ID"
      labelFor={labelFor}
      testId="service-combobox"
    />
  );
};

export default ServiceCombobox;
