/**
 * PermissionsIntro — list-action override for the Permission Grants resource.
 * Renders the Permissions intro paragraph and an inline search input above
 * the AdminJS list table (UX-B).
 * Source: admin-ui-ux-uplift chunk; UX-B.
 */

import React from "react";
import InlineSearchList from "../list/InlineSearchList.js";

const INTRO =
  "Permission Grants tie an Agent to a Service: 'this Agent may call this Service' — optionally with Constraints (rate limit, time window, allowed path prefixes, source-IP allowlist). Without an active Grant, the Agent cannot reach the Service through the Egress Proxy. Grants are the unit of access control: to give an Agent access to a new Service, create a new Grant; to revoke, delete or revoke the Grant.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const PermissionsIntro = (props: Record<string, any>): React.ReactElement => (
  <InlineSearchList
    introText={INTRO}
    placeholder="Search by action"
    {...props}
  />
);

export default PermissionsIntro;
