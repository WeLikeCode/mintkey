// Package vault provides the SSH Proxy's gRPC client to the Vault Adapter.
//
// Design:
//   - Matches the shape of apps/proxy-plugin/internal/vault/client.go (ADR-0014.4).
//   - GetCredential is wired to the real vault proto. TargetAddress/SSHUser
//     are zero until C3 adds the proto extensions.
//   - GetAgentByFingerprint, GetHostKeyFingerprint, StoreHostKeyFingerprint are
//     stubbed — they return ErrNotImplemented so callers fail loudly rather than
//     silently succeeding with stale data.
//
// Source: ADR-0021 (SSH Proxy Support).
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

// AuthScheme mirrors the proto AuthScheme enum plus SSH-specific values added
// in this PR.
type AuthScheme int32

const (
	AuthSchemeUnspecified          AuthScheme = 0
	AuthSchemeBearerToken          AuthScheme = 4  // existing
	AuthSchemeAppleJWT             AuthScheme = 9  // existing
	AuthSchemeGoogleServiceAccount AuthScheme = 10 // existing
	AuthSchemeSSHPrivateKey        AuthScheme = 11 // this PR
	AuthSchemeSSHCA                AuthScheme = 12 // Phase 2
)

// Credential carries the decrypted credential and SSH-specific metadata.
//
// WARNING: Value contains a sensitive secret (e.g. PEM-encoded private key).
// Callers MUST zero Value immediately after use.
type Credential struct {
	// Value is the raw decrypted plaintext (e.g. PEM bytes for SSH).
	Value []byte

	// AuthScheme indicates how the credential should be used.
	AuthScheme AuthScheme

	// KeyVersion is the version actually returned (resolves 0 → current).
	KeyVersion uint32

	// TargetAddress is the SSH backend "host:port". Zero until C3 wires proto
	// extensions.
	TargetAddress string

	// SSHUser is the SSH username for the backend. Zero until C3 wires proto
	// extensions.
	SSHUser string
}

// Agent represents a Mintkey agent entity as returned by the vault.
// Status and APIKeyHash are consumed by auth.go (ValidateAPIKey).
type Agent struct {
	ID         string
	TenantID   string
	Name       string
	SSHPubKey  string // OpenSSH-format public key (wired in a later chunk)
	Status     string // "active" | "revoked" | etc.
	APIKeyHash string // SHA-256 hex of the agent's API key
}

// Client is the Vault Adapter gRPC client used by the SSH Proxy.
//
// It has NO cache — per ADR-0014.4 caching lives in the Vault Adapter only.
type Client struct {
	address    string
	identityID string
	token      string
}

// NewClient creates a Vault Adapter client targeting the given address.
// identityID and token are sent as gRPC metadata on every call.
// Both may be empty strings during development; an empty identityID will cause
// vault-adapter's scopeInterceptor to reject the call (same failure mode as
// proxy-plugin BUG-1).
func NewClient(address, identityID, token string) (*Client, error) {
	return &Client{
		address:    address,
		identityID: identityID,
		token:      token,
	}, nil
}

// Close is a no-op: connections are per-call (same pattern as proxy-plugin).
func (c *Client) Close() error { return nil }

// GetCredential fetches a plaintext credential from the Vault Adapter.
//
// Every call dials the adapter (per-call, fails fast on unreachable) and
// attaches x-mintkey-service-identity / x-mintkey-service-token metadata.
//
// Callers MUST zero Credential.Value after use.
func (c *Client) GetCredential(ctx context.Context, tenantID, serviceID string) (*Credential, error) {
	md := metadata.Pairs(
		"x-mintkey-service-identity", c.identityID,
		"x-mintkey-service-token", c.token,
	)
	ctx = metadata.NewOutgoingContext(ctx, md)

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
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0, // 0 = current version
	}, grpc.WaitForReady(false))
	if err != nil {
		return nil, fmt.Errorf("vault: GetCredential(%s/%s): %w", tenantID, serviceID, err)
	}

	return &Credential{
		Value:      resp.GetValue(),
		AuthScheme: AuthScheme(resp.GetAuthScheme()),
		KeyVersion: resp.GetReturnedKeyVersion(),
		// TargetAddress and SSHUser are left "" until C3 adds proto extensions.
	}, nil
}

// ErrNotImplemented is returned by stub methods that are wired in later chunks.
var ErrNotImplemented = errors.New("not implemented")

// GetAgentByFingerprint looks up an agent by SSH public key fingerprint.
// STUB — returns ErrNotImplemented until C3 wires the vault-adapter handler.
func (c *Client) GetAgentByFingerprint(_ context.Context, _ string) (*Agent, error) {
	return nil, ErrNotImplemented
}

// GetHostKeyFingerprint retrieves the stored SSH host key fingerprint for a
// service.
// STUB — returns ErrNotImplemented until C6 wires persistent TOFU storage.
func (c *Client) GetHostKeyFingerprint(_ context.Context, _, _ string) (string, error) {
	return "", ErrNotImplemented
}

// StoreHostKeyFingerprint persists an SSH host key fingerprint for a service.
// STUB — returns ErrNotImplemented until C6 wires persistent TOFU storage.
func (c *Client) StoreHostKeyFingerprint(_ context.Context, _, _, _ string) error {
	return ErrNotImplemented
}
