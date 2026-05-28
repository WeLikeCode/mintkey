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
//   - Enforce 10-second HTTP client timeout.
//   - Return typed errors for non-2xx, unreachable, and parse failures.
//   - NEVER log credential_fields values or token values (P-1, S-SEC-1).
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
	"strings"
	"time"
)

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

// TokenExchanger performs OAuth2 password-grant token exchanges.
type TokenExchanger struct {
	httpClient *http.Client // 10s timeout
}

// ExchangeRequest holds the parsed credential payload for a token exchange.
type ExchangeRequest struct {
	TokenURL            string            // HTTPS endpoint
	CredentialFields    map[string]string // POST body fields
	TokenResponsePath   string            // JSONPath, e.g. "$.token"
	TokenRequestHeaders map[string]string // extra headers
}

// ExchangeResult holds the outcome of a successful token exchange.
type ExchangeResult struct {
	Token     string
	ExpiresIn int64           // seconds, 0 if unknown
	RawBody   json.RawMessage // for JWT exp parsing
}

// NewTokenExchanger creates a TokenExchanger with a 10-second HTTP client timeout.
func NewTokenExchanger() *TokenExchanger {
	return &TokenExchanger{
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// NewTokenExchangerWithClient creates a TokenExchanger with a custom HTTP client.
// Used for testing.
func NewTokenExchangerWithClient(client *http.Client) *TokenExchanger {
	return &TokenExchanger{
		httpClient: client,
	}
}

// Exchange performs the HTTP POST to the token endpoint and extracts the token.
//
// Returns ExchangeResult on success, or a typed error:
//   - ErrTokenExchangeFailed (non-2xx)
//   - ErrTokenEndpointUnreachable (network error)
//   - ErrTokenParseFailed (JSONPath extraction failure)
func (te *TokenExchanger) Exchange(ctx context.Context, req ExchangeRequest) (*ExchangeResult, error) {
	// Marshal credential_fields as JSON body.
	body, err := json.Marshal(req.CredentialFields)
	if err != nil {
		return nil, fmt.Errorf("%w: marshal credential fields: %s", ErrTokenParseFailed, err)
	}

	// Build the HTTP request.
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, req.TokenURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("%w: create request: %s", ErrTokenEndpointUnreachable, err)
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
		// Classify network errors as unreachable.
		if isNetworkError(err) {
			return nil, fmt.Errorf("%w: %s", ErrTokenEndpointUnreachable, err)
		}
		return nil, fmt.Errorf("%w: %s", ErrTokenEndpointUnreachable, err)
	}
	defer resp.Body.Close()

	// Read the response body (limit to 1MB to prevent abuse).
	rawBody, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("%w: read response body: %s", ErrTokenExchangeFailed, err)
	}

	// Check for non-2xx status.
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("%w: token endpoint returned HTTP %d", ErrTokenExchangeFailed, resp.StatusCode)
	}

	// Extract the token using the configured JSONPath.
	token, err := extractJSONPath(rawBody, req.TokenResponsePath)
	if err != nil {
		return nil, fmt.Errorf("%w: %s", ErrTokenParseFailed, err)
	}

	// Attempt to read expires_in from the response body.
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

	// Navigate through the JSON structure.
	var current any
	if err := json.Unmarshal(body, &current); err != nil {
		return "", fmt.Errorf("invalid JSON response: %s", err)
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
	switch v := current.(type) {
	case string:
		if v == "" {
			return "", fmt.Errorf("path %q: extracted empty token value", path)
		}
		return v, nil
	case float64:
		// Some APIs return tokens as numbers (unlikely but handle gracefully).
		return fmt.Sprintf("%v", v), nil
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
