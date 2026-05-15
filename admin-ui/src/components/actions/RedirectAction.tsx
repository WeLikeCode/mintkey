/**
 * RedirectAction — minimal component that immediately redirects to a URL
 * embedded in record.params.redirectUrl (OPS-DDEE DD-1).
 *
 * Used by the setCredential action to navigate the operator from the service
 * show page to the credentials/new form with service_id pre-filled.
 *
 * AdminJS record action GET requests render the action component, so a
 * server-side `redirectUrl` in the handler's GET response is not automatically
 * followed. This component reads the URL from record.params and calls
 * window.location.replace() on mount — transparent to the operator.
 *
 * Source: OPS-DDEE DD-1; AdminJS 7.x action component behaviour.
 */

import React, { useEffect } from "react";
import { Box, Text } from "@adminjs/design-system";
import { useNavigate } from "react-router-dom";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

const RedirectAction = (props: Props): React.ReactElement => {
  const navigate = useNavigate();

  useEffect(() => {
    const record = props.record as { params?: Record<string, unknown> } | undefined;
    const redirectUrl = record?.params?.["redirectTo"] as string | undefined;

    if (redirectUrl) {
      // Use navigate for SPA-style redirect (stays within React router)
      navigate(redirectUrl);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Box variant="white" p="xxl" data-testid="redirect-action">
      <Text style={{ color: "#6c757d" }}>Redirecting…</Text>
    </Box>
  );
};

export default RedirectAction;
