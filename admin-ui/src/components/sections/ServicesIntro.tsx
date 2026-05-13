/**
 * ServicesIntro — list-action override for the Services resource.
 * Source: admin-ui-ux-uplift chunk.
 */

import React from "react";
import ResourceIntroList from "./ResourceIntroList.js";

const INTRO =
  "Services are the backend APIs you've registered with Mintkey for an Agent to call. Each Service has a base URL, an auth scheme (API key, basic auth, OAuth, mTLS, none), and optional metadata. Mintkey never exposes the Service directly to Agents — Agents call it through the Egress Proxy, which injects the real Credential in-flight. Pair every Service with a Credential, then grant access to specific Agents via Permission Grants.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ServicesIntro = (props: Record<string, any>): React.ReactElement => (
  <ResourceIntroList introText={INTRO} {...props} />
);

export default ServicesIntro;
