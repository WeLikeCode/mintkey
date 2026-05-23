/**
 * AgentCombobox — AdminJS edit-property component wrapper for agent_id fields.
 *
 * Satisfies the AdminJS `editComponent` interface (props: property, record, onChange)
 * and delegates to AsyncCombobox with resourceId="agents".
 *
 * Registered in components/index.ts and wired into permissions.ts via:
 *   properties.agent_id.components.edit = Components.AgentCombobox
 *
 * Source: UX-A; admin-ui-ux-uplift Wave 2.
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

const AgentCombobox: React.FC<EditProps> = ({ property, record, onChange }) => {
  const path = property?.path ?? "agent_id";
  const currentValue = String(record?.params?.[path] ?? "");

  const handleChange = (wireId: string) => {
    if (!onChange) return;
    // AdminJS convention: onChange(propertyPath, newValue)
    onChange(path, wireId);
  };

  return (
    <AsyncCombobox
      resourceId="agents"
      value={currentValue}
      onChange={handleChange}
      placeholder="Search agents by name or ID"
      testId="agent-combobox"
    />
  );
};

export default AgentCombobox;
