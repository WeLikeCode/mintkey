// Package vault provides a gRPC client from the proxy plugin to the Vault Adapter.
//
// Design constraints (ADR-0014.4):
//   - NO plaintext cache in this client — every call fetches from the Vault Adapter.
//   - Every outgoing gRPC call carries "x-mintkey-service-token" metadata.
//   - Vault Adapter unreachable → return error (never panic).
//   - Callers MUST zero GetCredentialResponse.Plaintext after use.
//
// Source: ADR-0004; ADR-0014.4; vault.proto; T-1.6.3; T-1.6.8.
package vault

import (
	"context"
	"fmt"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
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

	// TargetURL is the service's registered base_url stored at credential registration time.
	// When non-empty the proxy should prefer this over the X-Mintkey-Target header.
	TargetURL string
}

// Client is the Vault Adapter gRPC client used by the proxy plugin.
//
// It has NO cache field — per ADR-0014.4 credential caching lives in the
// Vault Adapter only; the proxy plugin fetches plaintext per-request.
type Client struct {
	address           string
	serviceToken      string
	serviceIdentityID string
	// No cache field — ADR-0014.4: cache in Vault Adapter, not in proxy plugin.
}

// NewClient creates a Vault Adapter client targeting the given address.
// serviceToken is sent as "x-mintkey-service-token" metadata on every call.
// serviceIdentityID is sent as "x-mintkey-service-identity" metadata on every
// call so the vault-adapter's scopeInterceptor can validate the caller against
// its registered identities (Requirement 22.5 / BUG-1 fix).
//
// serviceIdentityID is required; an empty string will cause every call to fail
// with PERMISSION_DENIED from the scopeInterceptor (the exact failure mode of BUG-1).
func NewClient(address, serviceToken, serviceIdentityID string) *Client {
	return &Client{
		address:           address,
		serviceToken:      serviceToken,
		serviceIdentityID: serviceIdentityID,
	}
}

// ServiceToken returns the service identity token used in outgoing metadata.
func (c *Client) ServiceToken() string {
	return c.serviceToken
}

// ServiceIdentityID returns the service identity ID sent as
// "x-mintkey-service-identity" metadata on every vault call.
func (c *Client) ServiceIdentityID() string {
	return c.serviceIdentityID
}

// GetCredential fetches a plaintext credential from the Vault Adapter.
//
// Every call:
//  1. Attaches "x-mintkey-service-token: <token>" to the outgoing gRPC metadata.
//  2. Dials the Vault Adapter (per-call, fails fast on unreachable).
//  3. Returns an error — never panics — if the adapter is unreachable.
//
// Callers MUST zero resp.Plaintext after use.
func (c *Client) GetCredential(ctx context.Context, req GetCredentialRequest) (*GetCredentialResponse, error) {
	// Attach service identity headers to outgoing metadata (required on every
	// call so the vault-adapter's scopeInterceptor can grant vault.read scope).
	// Both x-mintkey-service-token and x-mintkey-service-identity must be present
	// and match a registered identity — see Requirement 22.5 / BUG-1 fix.
	md := metadata.Pairs(
		"x-mintkey-service-token", c.serviceToken,
		"x-mintkey-service-identity", c.serviceIdentityID,
	)
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

	stub := vaultv1.NewVaultAdapterClient(conn)
	resp, err := stub.GetCredential(dialCtx, &vaultv1.GetCredentialRequest{
		TenantId:      req.TenantID,
		ServiceId:     req.ServiceID,
		KeyVersion:    req.KeyVersion,
		CallerActorId: req.CallerActorID,
	}, grpc.WaitForReady(false))
	if err != nil {
		return nil, fmt.Errorf("vault: GetCredential(%s/%s): %w", req.TenantID, req.ServiceID, err)
	}

	return &GetCredentialResponse{
		AuthScheme:         int32(resp.GetAuthScheme()),
		Plaintext:          resp.GetValue(),
		ReturnedKeyVersion: resp.GetReturnedKeyVersion(),
		HeaderName:         resp.GetHeaderName(),
		QueryParam:         resp.GetQueryParam(),
		TargetURL:          resp.GetTargetUrl(),
	}, nil
}
