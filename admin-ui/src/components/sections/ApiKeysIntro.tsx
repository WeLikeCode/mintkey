/**
 * ApiKeysIntro — list-action override for the Service API Keys resource.
 * Source: admin-ui-ux-uplift chunk.
 */

import React from "react";
import ResourceIntroList from "./ResourceIntroList.js";

const INTRO =
  "Service API Keys (`mk_svckey_…`) are the classical long-lived key flavour for non-agent clients — scripts, CI jobs, integrations that can't run the JWT-broker flow themselves. See ADR-0018. Each key is bound to one Agent, one Service, and a subset of the Agent's Permission Grants (with optional expiry and Constraints). Keys are Argon2id-hashed at rest, fingerprint-indexed, and instantly revocable. Mintkey resolves the key server-side and proxies the call.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ApiKeysIntro = (props: Record<string, any>): React.ReactElement => (
  <ResourceIntroList introText={INTRO} {...props} />
);

export default ApiKeysIntro;
