"""
Injection hint table for all 17 Mintkey AuthScheme values.

Each entry describes exactly what the Mintkey proxy injects and where, so agents
can self-serve the call recipe from on-wire responses without reading source code.

Keys mirror vault.proto AuthScheme enum (lowercase underscore, no AUTH_SCHEME_ prefix):

    AUTH_SCHEME_API_KEY_HEADER = 1  → "api_key_header"
    AUTH_SCHEME_API_KEY_QUERY  = 2  → "api_key_query"
    ... (AUTH_SCHEME_UNSPECIFIED = 0 is omitted — not a real scheme)

Cross-reference: proxy-plugin/internal/credential/injector.go lines ~44-90.
Cross-reference: docs/architecture/contracts/vault-adapter/vault.proto lines ~84-117.

Field semantics
---------------
  injects       : What the proxy sets on the outbound request.
  location      : Where the injected value appears ("header", "query",
                  "connection", or "out_of_band").
  never_send    : What the AGENT must NOT send — the proxy strips/replaces it.
  handled_by    : Which Mintkey component handles this scheme
                  ("http-proxy" = Kong egress plugin,
                   "ssh-proxy"  = SSH bastion,
                   "email-proxy" = email proxy).
  status        : One of:
                    "injected_by_proxy"       — Kong plugin handles it, call works.
                    "not_implemented"          — proxy returns an error today.
                    "handled_by_other_proxy"   — use the named proxy surface, not Kong.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# The canonical injection-hint table.
# Any addition to vault.proto AuthScheme MUST add an entry here, or the
# enum-parity test (tests/test_auth_schemes.py) will fail CI.
# ---------------------------------------------------------------------------
INJECTION_HINTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------
    # AUTH_SCHEME_API_KEY_HEADER = 1
    # injector.go:49-54: sets cred.HeaderName (default "X-API-Key") on the request.
    # ------------------------------------------------------------------
    "api_key_header": {
        "injects": (
            "Proxy sets the API key in a request header. "
            "Default header name: X-API-Key. "
            "The operator may have configured a different header name (e.g. X-Auth-Key)."
        ),
        "location": "header",
        "never_send": (
            "Do not set your own Authorization header or X-API-Key — "
            "the proxy strips the agent's Authorization header and injects the real key."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_API_KEY_QUERY = 2
    # injector.go:56-63: sets cred.QueryParam (default "api_key") on the URL.
    # ------------------------------------------------------------------
    "api_key_query": {
        "injects": (
            "Proxy adds the API key as a URL query parameter. "
            "Default parameter name: api_key. "
            "The operator may have configured a different name."
        ),
        "location": "query",
        "never_send": (
            "Do not set your own Authorization header — the proxy strips it. "
            "Do not include the api_key query param yourself; the proxy appends it."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_BEARER_TOKEN = 3
    # injector.go:65-70: sets Authorization: Bearer <secret>.
    # ------------------------------------------------------------------
    "bearer_token": {
        "injects": (
            "Proxy sets Authorization: Bearer <secret> on the outbound request."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and replaces it "
            "with the real bearer token."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_BASIC_AUTH = 4
    # injector.go:72-74: sets Authorization: Basic base64(cred.Value).
    # cred.Value must be "user:pass" bytes — the vault adapter stores it that way.
    # ------------------------------------------------------------------
    "basic_auth": {
        "injects": (
            "Proxy sets Authorization: Basic <base64(user:pass)> on the outbound request. "
            "The credential stored in the vault is already in user:pass format; "
            "the proxy base64-encodes it before injection."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and replaces it "
            "with the correct Basic auth value."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_OAUTH2_CLIENT_CREDENTIALS = 5
    # The proxy's client-credentials handler POSTs grant_type=client_credentials
    # (HTTP Basic client_id:client_secret) to the token_url, caches the result,
    # and injects Authorization: Bearer <access_token>.
    # ------------------------------------------------------------------
    "oauth2_client_credentials": {
        "injects": (
            "Proxy exchanges the stored client_id/client_secret for a short-lived "
            "access token (OAuth2 client_credentials grant) and sets "
            "Authorization: Bearer <access_token> on the outbound request."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and replaces it "
            "with the exchanged access token."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_OIDC_CLIENT_SECRET = 6
    # injector.go:76-77: same branch as oauth2_client_credentials.
    # Vault Adapter handles OIDC token exchange; proxy treats value as bearer.
    # ------------------------------------------------------------------
    "oidc_client_secret": {
        "injects": (
            "Proxy sets Authorization: Bearer <id_or_access_token> on the outbound request. "
            "The Vault Adapter performs the OIDC token exchange using the client secret; "
            "the proxy receives the resulting token and injects it as a bearer."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and replaces it "
            "with the exchanged OIDC token."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_MTLS = 7
    # injector.go:83-85: returns an error "mtls: not implemented in session 1".
    # ------------------------------------------------------------------
    "mtls": {
        "injects": (
            "Nothing — mTLS is not implemented. "
            "Any call to an mTLS service will fail with an error from the proxy."
        ),
        "location": "connection",
        "never_send": (
            "mTLS is not implemented; the proxy will return an error rather than "
            "attempting TLS client certificate injection. "
            "Do not attempt to call this service via the HTTP proxy."
        ),
        "handled_by": "http-proxy",
        "status": "not_implemented",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_OAUTH2_PASSWORD_GRANT = 8
    # injector.go:79-81: sets Authorization: Bearer <value>.
    # Vault Adapter exchanges ROPC grant; proxy treats value as bearer.
    # ------------------------------------------------------------------
    "oauth2_password_grant": {
        "injects": (
            "Proxy sets Authorization: Bearer <access_token> on the outbound request. "
            "The Vault Adapter performs the OAuth2 Resource Owner Password Credentials grant; "
            "the proxy receives the resulting access token and injects it as a bearer."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and replaces it "
            "with the exchanged access token."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_APPLE_JWT = 9
    # injector.go:65-70 (same branch as bearer_token):
    #   "AuthSchemeAppleJWT: JWT is pre-generated by the Vault Adapter (ES256);
    #    proxy treats the returned Value opaquely — identical to bearer_token injection."
    # ------------------------------------------------------------------
    "apple_jwt": {
        "injects": (
            "Proxy sets Authorization: Bearer <apple_jwt> on the outbound request. "
            "The Vault Adapter generates a signed Apple JWT (ES256, p8 key) before "
            "each request; the proxy injects it opaquely as a bearer token."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and replaces it "
            "with the Vault-generated Apple JWT."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT = 10
    # injector.go:65-70 (same branch as bearer_token):
    #   "AuthSchemeGoogleServiceAccount: access_token is generated request-scoped by the
    #    Vault Adapter and is NOT cached in the proxy plugin (spec §4.5);
    #    proxy treats the returned Value opaquely — identical to bearer_token injection."
    # ------------------------------------------------------------------
    "google_service_account": {
        "injects": (
            "Proxy sets Authorization: Bearer <google_access_token> on the outbound request. "
            "The Vault Adapter exchanges the service account JSON key for a short-lived "
            "Google access token per request (not cached in the proxy); "
            "the proxy injects it opaquely as a bearer token."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and replaces it "
            "with the Vault-generated Google access token."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_SSH_PRIVATE_KEY = 11
    # vault.proto comment: "Used by the SSH proxy (ADR-0022)."
    # NOT handled by Kong HTTP proxy.
    # ------------------------------------------------------------------
    "ssh_private_key": {
        "injects": (
            "SSH private key authentication is handled by the Mintkey SSH bastion, "
            "not the HTTP proxy. "
            "The bastion uses the stored private key to authenticate to the backend SSH server."
        ),
        "location": "connection",
        "never_send": (
            "Do not route SSH services through the HTTP proxy (Kong) — it will not work. "
            "Use the SSH bastion endpoint instead. "
            "Do not send the private key yourself; the bastion holds it."
        ),
        "handled_by": "ssh-proxy",
        "status": "handled_by_other_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_SSH_CA = 12
    # vault.proto comment: "Used by the SSH proxy (ADR-0022, Phase 2)."
    # NOT handled by Kong HTTP proxy.
    # ------------------------------------------------------------------
    "ssh_ca": {
        "injects": (
            "SSH CA certificate signing is handled by the Mintkey SSH bastion, "
            "not the HTTP proxy. "
            "The bastion signs a short-lived SSH certificate for the agent "
            "and routes the connection to the backend."
        ),
        "location": "connection",
        "never_send": (
            "Do not route SSH CA services through the HTTP proxy (Kong). "
            "Use the SSH bastion endpoint. "
            "Do not present your own certificate; the bastion signs one for you."
        ),
        "handled_by": "ssh-proxy",
        "status": "handled_by_other_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_SSH_PASSWORD = 13
    # vault.proto comment: "Used by the SSH proxy (ADR-0022)."
    # NOT handled by Kong HTTP proxy.
    # ------------------------------------------------------------------
    "ssh_password": {
        "injects": (
            "SSH password authentication is handled by the Mintkey SSH bastion, "
            "not the HTTP proxy. "
            "The bastion presents the stored password to the backend SSH server."
        ),
        "location": "connection",
        "never_send": (
            "Do not route SSH services through the HTTP proxy (Kong). "
            "Use the SSH bastion endpoint. "
            "Do not send the password yourself; the bastion injects it."
        ),
        "handled_by": "ssh-proxy",
        "status": "handled_by_other_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_EMAIL_PASSWORD = 14
    # vault.proto comment: "Used by the email proxy (ADR-0024)."
    # Accessed via email_* MCP tools, not the HTTP proxy.
    # ------------------------------------------------------------------
    "email_password": {
        "injects": (
            "IMAP/SMTP password authentication is handled by the Mintkey email proxy, "
            "not the HTTP proxy. "
            "Use the email_* MCP tools (email_list_mailboxes, email_send, etc.); "
            "the email proxy handles authentication with the stored username and password."
        ),
        "location": "out_of_band",
        "never_send": (
            "Do not call email services through the HTTP proxy (Kong). "
            "Use the email_* MCP tools. "
            "Do not send the email password yourself."
        ),
        "handled_by": "email-proxy",
        "status": "handled_by_other_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_EMAIL_OAUTH2 = 15
    # vault.proto comment: "Used by the email proxy (ADR-0024), OAuth2 refresh token."
    # Accessed via email_* MCP tools, not the HTTP proxy.
    # ------------------------------------------------------------------
    "email_oauth2": {
        "injects": (
            "OAuth2 IMAP/SMTP authentication (Gmail, Outlook) is handled by the "
            "Mintkey email proxy, not the HTTP proxy. "
            "Use the email_* MCP tools; the email proxy exchanges the stored "
            "refresh token for an access token and authenticates to the mail server."
        ),
        "location": "out_of_band",
        "never_send": (
            "Do not call email services through the HTTP proxy (Kong). "
            "Use the email_* MCP tools. "
            "Do not send the OAuth2 token yourself."
        ),
        "handled_by": "email-proxy",
        "status": "handled_by_other_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_EMAIL_APP_PASSWORD = 16
    # vault.proto comment: "Used by the email proxy (ADR-0024), app-password credential."
    # Accessed via email_* MCP tools, not the HTTP proxy.
    # ------------------------------------------------------------------
    "email_app_password": {
        "injects": (
            "App-password IMAP/SMTP authentication (e.g. Google App Password) is "
            "handled by the Mintkey email proxy, not the HTTP proxy. "
            "Use the email_* MCP tools; the email proxy authenticates with the "
            "stored app password."
        ),
        "location": "out_of_band",
        "never_send": (
            "Do not call email services through the HTTP proxy (Kong). "
            "Use the email_* MCP tools. "
            "Do not send the app password yourself."
        ),
        "handled_by": "email-proxy",
        "status": "handled_by_other_proxy",
    },

    # ------------------------------------------------------------------
    # AUTH_SCHEME_HTTP_DIGEST = 18
    # digest.go: the proxy attaches an RFC 2617 Digest transport built from
    # the stored public_key (username) / private_key (password) and performs
    # the 401-challenge → response handshake per request; no static header.
    # ------------------------------------------------------------------
    "http_digest": {
        "injects": (
            "Proxy performs HTTP Digest authentication (RFC 2617) using the stored "
            "public/private key pair (public key = username, private key = password). "
            "The proxy answers the upstream's challenge and sets the resulting "
            "Authorization: Digest header on the outbound request per request."
        ),
        "location": "header",
        "never_send": (
            "Never send your own Authorization header to the upstream service. "
            "The proxy strips the agent's Authorization header and performs the "
            "Digest handshake with the stored key pair itself."
        ),
        "handled_by": "http-proxy",
        "status": "injected_by_proxy",
    },
}
