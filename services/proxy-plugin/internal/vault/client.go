// Package vault provides a gRPC client from the proxy plugin to the Vault Adapter.
//
// Design constraints (ADR-0014.4):
//   - NO plaintext cache in this client — every call fetches from the Vault Adapter.
//   - Every outgoing gRPC call carries "x-mintkey-service-token" metadata.
//   - Vault Adapter unreachable → return error (never panic).
//   - Callers MUST zero GetCredentialResponse.Plaintext after use.
//
// Full proto-generated integration is wired in T-1.6.8.
// Source: ADR-0004; ADR-0014.4; vault.proto; T-1.6.3.
package vault

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

// GetCredentialRequest identifies a credential to fetch from the Vault Adapter.
// Field names mirror vault.proto GetCredentialRequest.
type GetCredentialRequest struct {
	TenantID      string
	ServiceID     string
	KeyVersion    uint32 // 0 = current version
	CallerActorID string
}

// GetCredentialResponse carries the plaintext and injection metadata.
//
// WARNING: The Plaintext field contains a sensitive secret.
// Callers MUST zero it (e.g. with clear(resp.Plaintext)) immediately after use.
// It must never appear in logs, spans, or error strings.
type GetCredentialResponse struct {
	// AuthScheme mirrors the proto AuthScheme enum.
	// 1=API_KEY_HEADER 2=API_KEY_QUERY 3=BEARER_TOKEN 4=BASIC_AUTH
	// 5=OAUTH2_CLIENT_CREDENTIALS 6=OIDC_CLIENT_SECRET 7=MTLS
	AuthScheme int32

	// Plaintext is the raw credential bytes. MUST be zeroed after use.
	Plaintext []byte

	// ReturnedKeyVersion is the version actually returned (resolves 0 → current).
	ReturnedKeyVersion uint32

	// HeaderName is the optional injection hint for API_KEY_HEADER scheme.
	HeaderName string

	// QueryParam is the optional injection hint for API_KEY_QUERY scheme.
	QueryParam string
}

// Client is the Vault Adapter gRPC client used by the proxy plugin.
//
// It has NO cache field — per ADR-0014.4 credential caching lives in the
// Vault Adapter only; the proxy plugin fetches plaintext per-request.
type Client struct {
	address      string
	serviceToken string
	// No cache field — ADR-0014.4: cache in Vault Adapter, not in proxy plugin.
}

// NewClient creates a Vault Adapter client targeting the given address.
// serviceToken is sent as "x-mintkey-service-token" metadata on every call.
func NewClient(address, serviceToken string) *Client {
	return &Client{
		address:      address,
		serviceToken: serviceToken,
	}
}

// ServiceToken returns the service identity token used in outgoing metadata.
func (c *Client) ServiceToken() string {
	return c.serviceToken
}

// GetCredential fetches a plaintext credential from the Vault Adapter.
//
// Every call:
//  1. Attaches "x-mintkey-service-token: <token>" to the outgoing gRPC metadata.
//  2. Dials the Vault Adapter (lazy connection, fails fast on unreachable).
//  3. Returns an error — never panics — if the adapter is unreachable.
//
// Callers MUST zero resp.Plaintext after use.
//
// Note: full proto-generated RPC invocation is wired in T-1.6.8. This
// implementation establishes the connection and metadata pattern; the Invoke
// call below is a placeholder that returns a known sentinel error until
// the proto-generated stub is linked.
func (c *Client) GetCredential(ctx context.Context, req GetCredentialRequest) (*GetCredentialResponse, error) {
	// Attach service identity token to outgoing metadata (required on every call).
	md := metadata.Pairs("x-mintkey-service-token", c.serviceToken)
	ctx = metadata.NewOutgoingContext(ctx, md)

	// Apply a per-call dial timeout so that an unreachable adapter returns
	// quickly rather than blocking indefinitely.
	dialCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	conn, err := grpc.NewClient(
		c.address,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("vault: create client for %s: %w", c.address, err)
	}
	defer conn.Close()

	// Probe connectivity: attempt a no-op Invoke to force TCP connection.
	// grpc.WaitForReady(false) means fail immediately if not connected,
	// but the dialCtx timeout still applies.
	var reply struct{}
	invokeErr := conn.Invoke(
		dialCtx,
		"/mintkey.vault.v1.VaultAdapter/GetCredential",
		req,
		&reply,
		grpc.WaitForReady(false),
	)
	if invokeErr != nil {
		return nil, fmt.Errorf("vault: GetCredential(%s/%s): %w", req.TenantID, req.ServiceID, invokeErr)
	}

	// T-1.6.8 will replace the Invoke above with the proto-generated stub call
	// and unmarshal the real GetCredentialResponse. Until then, return a sentinel.
	return nil, fmt.Errorf("vault: proto-generated integration not yet wired (T-1.6.8)")
}
