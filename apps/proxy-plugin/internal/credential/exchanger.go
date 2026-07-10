// Package credential provides credential injection for the Mintkey Egress Proxy plugin.
//
// This file implements the TokenExchanger which performs OAuth2 password-grant
// token exchanges by POSTing credential_fields to a token_url and extracting
// the access token from the JSON response using a JSONPath expression.
//
// Design constraints (Requirements 20.1–20.7):
//   - POST to token_url with credential_fields as JSON body.
//   - Apply token_request_headers on the outgoing request.
//   - Extract token using token_response_path (JSONPath).
//   - Enforce 10-second HTTP client timeout + 3-second response-header timeout.
//   - Return typed errors for non-2xx, unreachable, and parse failures.
//   - NEVER log credential_fields values or token values (P-1, S-SEC-1).
//
// Security constraints (hardened per security review):
//   - SSRF guard: dial-time IP check blocks loopback, link-local (169.254/16),
//     private ranges (RFC 1918), ULA, multicast and unspecified addresses —
//     checked AFTER DNS resolution to defeat DNS-rebind (BUG-3).
//   - CheckRedirect: redirect destinations undergo the same IP check (BUG-3).
//   - JSONPath: numeric token values are rejected, not silently coerced;
//     path depth is capped at maxJSONPathSegments (BUG-6).
//   - ResponseHeaderTimeout: 3s cap prevents slow-header goroutine hold (BUG-12).
//   - Error bodies: status code only, no attacker-controlled response data (BUG-17).
//
// Source: design.md §TokenExchanger; Requirements 20.1–20.7.
package credential

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// maxJSONPathSegments caps the number of dot-notation segments in a JSONPath
// expression.  Prevents both O(n) traversal attacks and accidental mis-configs.
// Value 16 is generous for any realistic token structure.
const maxJSONPathSegments = 16

// Sentinel errors for token exchange failures.
var (
	// ErrTokenExchangeFailed indicates the token endpoint returned a non-2xx response.
	ErrTokenExchangeFailed = errors.New("token_exchange_failed")

	// ErrTokenEndpointUnreachable indicates the token endpoint could not be reached
	// (connection timeout, DNS failure, or other network error).
	ErrTokenEndpointUnreachable = errors.New("token_endpoint_unreachable")

	// ErrTokenParseFailed indicates the token could not be extracted from the
	// response body using the configured token_response_path.
	ErrTokenParseFailed = errors.New("token_parse_failed")
)

// defaultExchangeTimeout is used when ExchangeRequest.Timeout is zero.
const defaultExchangeTimeout = 10 * time.Second

// maxExchangeTimeout is the upper bound on any per-credential timeout.
const maxExchangeTimeout = 120 * time.Second

// TokenExchanger performs OAuth2 password-grant token exchanges.
type TokenExchanger struct {
	// httpClient is the shared transport carrier — contains the SSRF dial guard
	// and redirect guard. Its Timeout is set to maxExchangeTimeout as a hard
	// ceiling; per-call context deadlines govern the effective timeout.
	httpClient   *http.Client
	allowPrivate bool // bypass SSRF guard for tests/dev
}

// ExchangeRequest holds the parsed credential payload for a token exchange.
type ExchangeRequest struct {
	TokenURL            string            // HTTPS endpoint
	CredentialFields    map[string]string // POST body fields
	TokenResponsePath   string            // JSONPath, e.g. "$.token"
	TokenRequestHeaders map[string]string // extra headers
	// Timeout is the per-credential whole-request timeout for the token exchange.
	// Zero means use the default (10s).  The exchanger clamps ≤0 → 10s, >120s → 120s.
	Timeout time.Duration
}

// ExchangeResult holds the outcome of a successful token exchange.
type ExchangeResult struct {
	Token     string
	ExpiresIn int64           // seconds, 0 if unknown
	RawBody   json.RawMessage // for JWT exp parsing
}

// newHTTPClient builds the hardened http.Client used by TokenExchanger.
//
// Security properties:
//   - Transport.DialContext: SSRF guard — blocks loopback, link-local, private
//     ranges, ULA, multicast, and unspecified after DNS resolution.
//   - Client.CheckRedirect: SSRF guard on redirect destinations (BUG-3).
//   - Client.Timeout: maxExchangeTimeout (120s) hard ceiling — prevents goroutine
//     hold if a per-call context deadline is somehow not set.
//   - Per-call timeout: Exchange wraps the caller's context with a
//     context.WithTimeout(ctx, perCredTimeout) deadline so each call is bounded
//     by the credential's exchange_timeout_seconds (default 10s, max 120s).
//     ResponseHeaderTimeout is intentionally NOT set on the transport so that
//     a slow-but-within-timeout header response (e.g. cold Azure app) is not
//     prematurely killed.
//
// allowPrivate bypasses the SSRF guard; use only in test helpers.
func newHTTPClient(allowPrivate bool) *http.Client {
	transport := &http.Transport{
		DialContext: ssrfSafeDialContext(allowPrivate),
		// ResponseHeaderTimeout deliberately omitted — per-call context deadline
		// governs the effective timeout; a fixed 3s cap here would prevent cold
		// token endpoints from being reached within their per-credential window.
		MaxIdleConns:    10,
		IdleConnTimeout: 30 * time.Second,
	}

	checkRedirect := func(req *http.Request, via []*http.Request) error {
		if allowPrivate {
			return nil
		}
		// Inspect the redirect destination.
		dest := req.URL
		host := dest.Hostname()
		addrs, err := net.DefaultResolver.LookupHost(req.Context(), host)
		if err != nil {
			return fmt.Errorf("%w: redirect DNS lookup failed for %q: %v",
				ErrTokenEndpointUnreachable, host, err)
		}
		for _, a := range addrs {
			ip := net.ParseIP(a)
			if ip == nil {
				return fmt.Errorf("%w: redirect: unparseable IP %q for host %q",
					ErrTokenEndpointUnreachable, a, host)
			}
			if isBlockedIP(ip) {
				return fmt.Errorf("%w: redirect to blocked address %s for host %q",
					ErrTokenEndpointUnreachable, ip, host)
			}
		}
		return nil
	}

	return &http.Client{
		// Hard ceiling: if per-call context deadline fires first (as expected),
		// this Timeout is never reached. It is a last-resort safety net.
		Timeout:       maxExchangeTimeout,
		Transport:     transport,
		CheckRedirect: checkRedirect,
	}
}

// NewTokenExchanger creates a TokenExchanger with a hardened HTTP client:
// SSRF dial-time guard, response-header timeout, and redirect SSRF check.
func NewTokenExchanger() *TokenExchanger {
	return &TokenExchanger{
		httpClient:   newHTTPClient(false),
		allowPrivate: false,
	}
}

// NewTokenExchangerAllowPrivate creates a TokenExchanger that bypasses the
// SSRF guard for private/loopback targets.  Use ONLY in tests or controlled
// internal environments; never expose this as a service default.
func NewTokenExchangerAllowPrivate() *TokenExchanger {
	return &TokenExchanger{
		httpClient:   newHTTPClient(true),
		allowPrivate: true,
	}
}

// NewTokenExchangerWithClient creates a TokenExchanger with a custom HTTP client.
// Used for testing.  SSRF pre-flight is bypassed because the caller controls
// the transport; the dial-level guard is assumed to be handled externally or
// intentionally absent (e.g. httptest.Server with a custom TLS client).
func NewTokenExchangerWithClient(client *http.Client) *TokenExchanger {
	return &TokenExchanger{
		httpClient:   client,
		allowPrivate: true,
	}
}

// validateTokenURL performs a pre-flight check on the token URL before dialling.
// It rejects URLs whose host is a literal IP in a blocked range, providing an
// early error path that doesn't even attempt DNS resolution.
func validateTokenURL(rawURL string) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("%w: invalid token_url: %v", ErrTokenEndpointUnreachable, err)
	}
	host := u.Hostname()
	if ip := net.ParseIP(host); ip != nil {
		if isBlockedIP(ip) {
			return fmt.Errorf("%w: token_url resolves to blocked address %s", ErrTokenEndpointUnreachable, ip)
		}
	}
	return nil
}

// effectiveTimeout returns the clamped per-call timeout duration from req.Timeout.
// ≤0 → defaultExchangeTimeout (10s); >maxExchangeTimeout → maxExchangeTimeout (120s).
func effectiveTimeout(d time.Duration) time.Duration {
	if d <= 0 {
		return defaultExchangeTimeout
	}
	if d > maxExchangeTimeout {
		return maxExchangeTimeout
	}
	return d
}

// Exchange performs the HTTP POST to the token endpoint and extracts the token.
//
// The per-call timeout is taken from req.Timeout (defaulted/clamped via
// effectiveTimeout).  A context.WithTimeout wraps the caller's ctx so that
// slow-but-within-timeout endpoints succeed while endpoints that exceed the
// per-credential window fail with ErrTokenEndpointUnreachable.
//
// Returns ExchangeResult on success, or a typed error:
//   - ErrTokenExchangeFailed (non-2xx)
//   - ErrTokenEndpointUnreachable (network error or SSRF block)
//   - ErrTokenParseFailed (JSONPath extraction failure)
func (te *TokenExchanger) Exchange(ctx context.Context, req ExchangeRequest) (*ExchangeResult, error) {
	// Apply per-credential timeout via context deadline.
	timeout := effectiveTimeout(req.Timeout)
	var cancel context.CancelFunc
	ctx, cancel = context.WithTimeout(ctx, timeout)
	defer cancel()

	// BUG-3 pre-flight: reject literal-IP blocked addresses before dialling.
	// Skipped when allowPrivate is true (test/dev mode only).
	if !te.allowPrivate {
		if err := validateTokenURL(req.TokenURL); err != nil {
			return nil, err
		}
	}

	// Determine the effective Content-Type. Default is application/json, but
	// token_request_headers may override it (case-insensitive header match).
	// The body encoding MUST match the declared Content-Type — an OAuth2
	// password-grant endpoint (e.g. Contabo/Keycloak) requires the fields to be
	// form-encoded, in which case a JSON body with a form Content-Type is
	// rejected with token_exchange_failed.
	contentType := "application/json"
	for name, value := range req.TokenRequestHeaders {
		if strings.EqualFold(name, "Content-Type") {
			contentType = value
			break
		}
	}

	// Encode credential_fields to match the declared Content-Type.
	var body []byte
	if mediaType := strings.TrimSpace(strings.SplitN(contentType, ";", 2)[0]); strings.EqualFold(mediaType, "application/x-www-form-urlencoded") {
		form := url.Values{}
		for k, v := range req.CredentialFields {
			form.Set(k, v)
		}
		body = []byte(form.Encode())
	} else {
		b, err := json.Marshal(req.CredentialFields)
		if err != nil {
			return nil, fmt.Errorf("%w: marshal credential fields: %v", ErrTokenParseFailed, err)
		}
		body = b
	}

	// Build the HTTP request.
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, req.TokenURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("%w: create request: %v", ErrTokenEndpointUnreachable, err)
	}

	// Set Content-Type default; can be overridden by token_request_headers.
	httpReq.Header.Set("Content-Type", "application/json")

	// Apply configured token_request_headers.
	for name, value := range req.TokenRequestHeaders {
		httpReq.Header.Set(name, value)
	}

	// Execute the request.
	resp, err := te.httpClient.Do(httpReq)
	if err != nil {
		// BUG-3 / BUG-17: classify all network/SSRF errors as unreachable;
		// err.Error() may contain SSRF guard messages — that is intentional and safe
		// (it describes our own guard output, not attacker-controlled data).
		return nil, fmt.Errorf("%w: %v", ErrTokenEndpointUnreachable, err)
	}
	defer resp.Body.Close()

	// Read the response body (limit to 64KB to prevent abuse; 1MB was excessive).
	rawBody, err := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if err != nil {
		return nil, fmt.Errorf("%w: read response body: %v", ErrTokenExchangeFailed, err)
	}

	// BUG-17: Check for non-2xx status BEFORE touching rawBody in error messages.
	// Only include the status code — NOT the response body — to avoid leaking
	// attacker-controlled data into error messages / logs.
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("%w: token endpoint returned HTTP %d", ErrTokenExchangeFailed, resp.StatusCode)
	}

	// Extract the token using the configured JSONPath.
	token, err := extractJSONPath(rawBody, req.TokenResponsePath)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrTokenParseFailed, err)
	}

	// Attempt to read expires_in from the response body.
	expiresIn := extractExpiresIn(rawBody)

	return &ExchangeResult{
		Token:     token,
		ExpiresIn: expiresIn,
		RawBody:   json.RawMessage(rawBody),
	}, nil
}

// defaultClientCredentialsTokenPath is the JSONPath applied to a
// client-credentials token response when the credential omits token_response_path.
const defaultClientCredentialsTokenPath = "$.access_token"

// ClientCredentialsRequest holds the parsed payload for an OAuth 2.0
// client-credentials token exchange.
type ClientCredentialsRequest struct {
	TokenURL          string // HTTPS endpoint
	ClientID          string // HTTP Basic username
	ClientSecret      string // HTTP Basic password
	Scope             string // optional space-delimited scopes
	Audience          string // optional token-request audience; omitted when empty
	TokenResponsePath string // JSONPath, default "$.access_token"
	// Timeout is the per-credential whole-request timeout. Zero → default (10s);
	// clamped ≤0 → 10s, >120s → 120s (via effectiveTimeout).
	Timeout time.Duration
}

// ExchangeClientCredentials performs an OAuth 2.0 client-credentials token
// exchange. It is a sibling of Exchange (password grant): it reuses te.httpClient
// (the SSRF-hardened dial/redirect guard), validateTokenURL, extractJSONPath, and
// extractExpiresIn, but builds the request per the client-credentials grant:
//   - Content-Type: application/x-www-form-urlencoded
//   - Body: grant_type=client_credentials (+ scope when set), form-encoded
//   - Authorization: Basic base64(client_id:client_secret)
//
// The token is extracted via TokenResponsePath (default "$.access_token").
// The password-grant Exchange path is left untouched.
//
// Returns ExchangeResult on success, or a typed error:
//   - ErrTokenExchangeFailed (non-2xx)
//   - ErrTokenEndpointUnreachable (network error or SSRF block)
//   - ErrTokenParseFailed (JSONPath extraction failure)
func (te *TokenExchanger) ExchangeClientCredentials(ctx context.Context, req ClientCredentialsRequest) (*ExchangeResult, error) {
	// Apply per-credential timeout via context deadline.
	timeout := effectiveTimeout(req.Timeout)
	var cancel context.CancelFunc
	ctx, cancel = context.WithTimeout(ctx, timeout)
	defer cancel()

	// Pre-flight: reject literal-IP blocked addresses before dialling.
	// Skipped when allowPrivate is true (test/dev mode only).
	if !te.allowPrivate {
		if err := validateTokenURL(req.TokenURL); err != nil {
			return nil, err
		}
	}

	// Build the form-encoded body: grant_type=client_credentials (+ scope + audience).
	vals := url.Values{}
	vals.Set("grant_type", "client_credentials")
	if req.Scope != "" {
		vals.Set("scope", req.Scope)
	}
	if req.Audience != "" {
		vals.Set("audience", req.Audience)
	}
	body := []byte(vals.Encode())

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, req.TokenURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("%w: create request: %v", ErrTokenEndpointUnreachable, err)
	}
	httpReq.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	// Authorization: Basic base64(client_id:client_secret) — MongoDB's documented method.
	httpReq.SetBasicAuth(req.ClientID, req.ClientSecret)

	resp, err := te.httpClient.Do(httpReq)
	if err != nil {
		// Classify all network/SSRF errors as unreachable (see Exchange BUG-3/BUG-17).
		return nil, fmt.Errorf("%w: %v", ErrTokenEndpointUnreachable, err)
	}
	defer resp.Body.Close()

	rawBody, err := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if err != nil {
		return nil, fmt.Errorf("%w: read response body: %v", ErrTokenExchangeFailed, err)
	}

	// Non-2xx: status code only — never the attacker-controlled response body (BUG-17).
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("%w: token endpoint returned HTTP %d", ErrTokenExchangeFailed, resp.StatusCode)
	}

	path := req.TokenResponsePath
	if path == "" {
		path = defaultClientCredentialsTokenPath
	}
	token, err := extractJSONPath(rawBody, path)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrTokenParseFailed, err)
	}

	expiresIn := extractExpiresIn(rawBody)

	return &ExchangeResult{
		Token:     token,
		ExpiresIn: expiresIn,
		RawBody:   json.RawMessage(rawBody),
	}, nil
}

// extractJSONPath extracts a string value from a JSON body using a simple
// JSONPath expression. Supports paths like:
//   - "$.token"
//   - "$.access_token"
//   - "$.data.token"
//   - "$.response.access_token"
//
// Only dot-notation paths starting with "$." are supported.
//
// Security rules (BUG-6):
//   - Path depth is capped at maxJSONPathSegments (16).
//   - Numeric values at the token position are REJECTED; they are not coerced
//     via fmt.Sprintf("%v") which would produce scientific-notation / precision
//     loss for large integers.
//   - Non-string, non-navigable values return a clean typed error.
func extractJSONPath(body []byte, path string) (string, error) {
	if path == "" {
		return "", fmt.Errorf("empty token_response_path")
	}

	// Strip the "$." prefix.
	if !strings.HasPrefix(path, "$.") {
		return "", fmt.Errorf("invalid JSONPath %q: must start with '$.'", path)
	}
	segments := strings.Split(path[2:], ".")
	if len(segments) == 0 {
		return "", fmt.Errorf("invalid JSONPath %q: no field specified", path)
	}

	// BUG-6: cap path depth to prevent O(n) traversal attacks.
	if len(segments) > maxJSONPathSegments {
		return "", fmt.Errorf("invalid JSONPath %q: too many segments (%d > %d)",
			path, len(segments), maxJSONPathSegments)
	}

	// Navigate through the JSON structure.
	var current any
	if err := json.Unmarshal(body, &current); err != nil {
		return "", fmt.Errorf("invalid JSON response: %v", err)
	}

	for _, segment := range segments {
		obj, ok := current.(map[string]any)
		if !ok {
			return "", fmt.Errorf("path %q: expected object at segment %q, got %T", path, segment, current)
		}
		val, exists := obj[segment]
		if !exists {
			return "", fmt.Errorf("path %q: key %q not found in response", path, segment)
		}
		current = val
	}

	// The final value must be a string.
	// BUG-6: numeric values (float64 from encoding/json) are explicitly rejected.
	// Coercing via fmt.Sprintf("%v") silently corrupts large integers to scientific
	// notation (e.g. 1.23456789e+20) and causes precision loss — any numeric token
	// is a misconfigured endpoint and must fail loudly.
	switch v := current.(type) {
	case string:
		if v == "" {
			return "", fmt.Errorf("path %q: extracted empty token value", path)
		}
		return v, nil
	case float64:
		// BUG-6: do NOT include v in the error — fmt.Sprintf("%v", float64) produces
		// scientific notation for large values (e.g. 1.23e+19), which is the bug we're
		// fixing.  Just report the type.
		_ = v
		return "", fmt.Errorf("path %q: token value is numeric (float64); token must be a JSON string — numeric tokens are rejected to prevent scientific-notation coercion", path)
	case json.Number:
		return "", fmt.Errorf("path %q: token value is numeric (json.Number); token must be a JSON string", path)
	default:
		return "", fmt.Errorf("path %q: expected string value, got %T", path, current)
	}
}

// extractExpiresIn attempts to read an "expires_in" field from the response body.
// Returns 0 if not found or not a number.
func extractExpiresIn(body []byte) int64 {
	var obj map[string]any
	if err := json.Unmarshal(body, &obj); err != nil {
		return 0
	}
	val, ok := obj["expires_in"]
	if !ok {
		return 0
	}
	switch v := val.(type) {
	case float64:
		return int64(v)
	case json.Number:
		n, err := v.Int64()
		if err != nil {
			return 0
		}
		return n
	default:
		return 0
	}
}

// isNetworkError checks if an error is a network-level error (timeout, DNS, connection refused).
func isNetworkError(err error) bool {
	if err == nil {
		return false
	}
	// Check for net.Error (includes timeouts).
	var netErr net.Error
	if errors.As(err, &netErr) {
		return true
	}
	// Check for DNS errors.
	var dnsErr *net.DNSError
	if errors.As(err, &dnsErr) {
		return true
	}
	// Check for connection refused / reset.
	var opErr *net.OpError
	if errors.As(err, &opErr) {
		return true
	}
	return false
}
