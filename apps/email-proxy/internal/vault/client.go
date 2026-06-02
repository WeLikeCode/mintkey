// Package vault provides the Email Proxy's gRPC client to the Vault Adapter.
//
// Mirrors apps/ssh-proxy/internal/vault/client.go minus SSH-specific
// operations (no host-key, no fingerprint storage). Adds support for the
// three email auth schemes introduced in C-1 (ADR-0024):
//   - AUTH_SCHEME_EMAIL_PASSWORD = 14
//   - AUTH_SCHEME_EMAIL_OAUTH2   = 15
//   - AUTH_SCHEME_EMAIL_APP_PASSWORD = 16
package vault

import (
	"context"
	"errors"
	"fmt"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

// AuthScheme mirrors the proto AuthScheme enum plus the three email-specific
// values added in C-1.
type AuthScheme int32

const (
	AuthSchemeUnspecified          AuthScheme = 0
	AuthSchemeBearerToken          AuthScheme = 3
	AuthSchemeBasicAuth            AuthScheme = 4
	AuthSchemeSSHPrivateKey        AuthScheme = 11
	AuthSchemeSSHCA                AuthScheme = 12
	AuthSchemeSSHPassword          AuthScheme = 13
	// Email auth schemes (C-1, ADR-0024).
	AuthSchemeEmailPassword    AuthScheme = 14
	AuthSchemeEmailOAuth2      AuthScheme = 15
	AuthSchemeEmailAppPassword AuthScheme = 16
)

// Credential holds the decrypted email credential and its auth scheme.
//
// WARNING: Value contains a sensitive secret. Callers MUST zero Value
// immediately after use.
type Credential struct {
	// Value is the raw decrypted plaintext (JSON payload for email schemes).
	Value []byte

	// AuthScheme indicates the credential type.
	AuthScheme AuthScheme

	// KeyVersion is the resolved key version (0 → current).
	KeyVersion uint32

	// BaseUrl is the canonical upstream address (if set on the service).
	BaseUrl string

	// AuthSchemeName is the string form of the auth scheme.
	AuthSchemeName string
}

// Client is the Vault Adapter gRPC client used by the Email Proxy.
// Per ADR-0014.4, there is NO cache — caching lives in the Vault Adapter.
type Client struct {
	address    string
	identityID string
	token      string
}

// NewClient creates a Vault Adapter client for the given address.
// identityID and token are sent as gRPC metadata on every call.
func NewClient(address, identityID, token string) (*Client, error) {
	if address == "" {
		return nil, errors.New("vault: address must not be empty")
	}
	return &Client{
		address:    address,
		identityID: identityID,
		token:      token,
	}, nil
}

// Close is a no-op: connections are per-call (same pattern as proxy-plugin/ssh-proxy).
func (c *Client) Close() error { return nil }

// dial creates a per-call gRPC connection with service-identity metadata attached.
func (c *Client) dial(ctx context.Context) (*grpc.ClientConn, context.Context, error) {
	md := metadata.Pairs(
		"x-mintkey-service-identity", c.identityID,
		"x-mintkey-service-token", c.token,
	)
	outCtx := metadata.NewOutgoingContext(ctx, md)

	conn, err := grpc.NewClient(
		c.address,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("vault: dial %s: %w", c.address, err)
	}
	return conn, outCtx, nil
}

// ValidateServiceIdentity calls ValidateServiceIdentity on the vault-adapter
// to confirm the email-proxy's service identity is known and active.
// Called at startup; a failure means the operator has not provisioned the
// identity yet (not a fatal crash by default — logged and monitored).
func (c *Client) ValidateServiceIdentity(ctx context.Context) error {
	conn, outCtx, err := c.dial(ctx)
	if err != nil {
		return err
	}
	defer conn.Close()

	callCtx, cancel := context.WithTimeout(outCtx, 5*time.Second)
	defer cancel()

	stub := vaultv1.NewVaultAdapterClient(conn)
	_, err = stub.ValidateServiceIdentity(callCtx, &vaultv1.ValidateServiceIdentityRequest{},
		grpc.WaitForReady(false))
	if err != nil {
		return fmt.Errorf("vault: ValidateServiceIdentity: %w", err)
	}
	return nil
}

// GetCredential fetches the plaintext credential for an (tenant_id, service_id) pair.
// authScheme is informational (used by callers to interpret Value); the vault-adapter
// selects the stored scheme from the database. Callers MUST zero Credential.Value after use.
func (c *Client) GetCredential(ctx context.Context, tenantID, serviceID string, authScheme AuthScheme) (*Credential, error) {
	conn, outCtx, err := c.dial(ctx)
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	callCtx, cancel := context.WithTimeout(outCtx, 5*time.Second)
	defer cancel()

	stub := vaultv1.NewVaultAdapterClient(conn)
	resp, err := stub.GetCredential(callCtx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0, // 0 = current version
	}, grpc.WaitForReady(false))
	if err != nil {
		return nil, fmt.Errorf("vault: GetCredential(%s/%s): %w", tenantID, serviceID, err)
	}

	// authScheme param is for the caller's benefit (e.g. to pre-select the decoder);
	// the actual scheme is authoritative from the vault response.
	_ = authScheme

	return &Credential{
		Value:          resp.GetValue(),
		AuthScheme:     AuthScheme(resp.GetAuthScheme()),
		KeyVersion:     resp.GetReturnedKeyVersion(),
		BaseUrl:        resp.GetBaseUrl(),
		AuthSchemeName: resp.GetAuthSchemeName(),
	}, nil
}
