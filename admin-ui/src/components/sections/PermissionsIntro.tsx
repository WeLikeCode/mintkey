/**
 * PermissionsIntro — list-action override for the Permission Grants resource.
 * Renders the Permissions intro paragraph and an inline search input above
 * the AdminJS list table (UX-B).
 * Source: admin-ui-ux-uplift chunk; UX-B.
 */

import React from "react";
import InlineSearchList from "../list/InlineSearchList.js";

const INTRO =
  "Permission Grants tie an Agent to a Service: 'this Agent may call this Service' — optionally with Constraints (rate limit, time window, allowed path prefixes, source-IP allowlist). Without an active Grant, the Agent cannot reach the Service through the Egress Proxy. Grants are the unit of access control: to give an Agent access to a new Service, create a new Grant; to revoke, delete or revoke the Grant.\n\nPermission grants bind an agent to a service with a specific action scope (and optional constraints). The agent must request a token with `action` matching one of its grants. The action format is either `call` (unrestricted) or `<verb>:<resource>` (e.g., `read:contacts`). Constraints can further restrict by rate limit, time window, request path prefix, or source IP.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const PermissionsIntro = (props: Record<string, any>): React.ReactElement => (
  <InlineSearchList
    introText={INTRO}
    placeholder="Search by action"
    {...props}
  />
);

export default PermissionsIntro;
