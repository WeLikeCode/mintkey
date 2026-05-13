/**
 * AuditIntro — list-action override for the Audit Events resource.
 * Source: admin-ui-ux-uplift chunk.
 */

import React from "react";
import ResourceIntroList from "./ResourceIntroList.js";

const INTRO =
  "Audit Events are the immutable, hash-chained record of every state change and security-relevant action in Mintkey: credential rotations, agent revocations, permission grants/revokes, settings updates, PlatformAdmin cross-tenant reads, and sampled proxy hits. The hash chain prevents tampering; retention is configurable per event class. Search and filter here when investigating an incident — search across all fields, not just the default filter.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const AuditIntro = (props: Record<string, any>): React.ReactElement => (
  <ResourceIntroList introText={INTRO} {...props} />
);

export default AuditIntro;
