/**
 * PermissionsIntro — list-action override for the Permission Grants resource.
 * Source: admin-ui-ux-uplift chunk.
 */

import React from "react";
import ResourceIntroList from "./ResourceIntroList.js";

const INTRO =
  "Permission Grants tie an Agent to a Service: 'this Agent may call this Service' — optionally with Constraints (rate limit, time window, allowed path prefixes, source-IP allowlist). Without an active Grant, the Agent cannot reach the Service through the Egress Proxy. Grants are the unit of access control: to give an Agent access to a new Service, create a new Grant; to revoke, delete or revoke the Grant.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const PermissionsIntro = (props: Record<string, any>): React.ReactElement => (
  <ResourceIntroList introText={INTRO} {...props} />
);

export default PermissionsIntro;
