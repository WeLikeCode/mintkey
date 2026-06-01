// Package vault provides the SSH Proxy's gRPC client to the Vault Adapter.
//
// Design:
//   - Matches the shape of apps/proxy-plugin/internal/vault/client.go (ADR-0014.4).
//   - GetCredential is wired to the real vault proto.
//   - GetAgentByFingerprint, GetHostKeyFingerprint, StoreHostKeyFingerprint call
//     the SSHVaultAdapter service on the vault-adapter using JSON-over-gRPC
//     (no protoc required — see apps/vault-adapter/internal/sshvault/).
//
// Source: ADR-0021 (SSH Proxy Support); chunk C7.
package vault

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/encoding"
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

// sshVaultServiceName is the fully-qualified gRPC service name for the SSH vault
// RPCs registered by vault-adapter's SSHVaultAdapter service.
const sshVaultServiceName = "mintkey.vault.v1.SSHVaultAdapter"

// sshJSONCodec is the JSON codec registered under the name "json" so that
// grpc.ForceCodec(sshJSONCodec{}) selects it for SSH vault calls.
// The codec must be registered once before any gRPC calls using it.
func init() {
	encoding.RegisterCodec(sshJSONCodec{})
}

// sshJSONCodec implements encoding.Codec for JSON messages.
type sshJSONCodec struct{}

func (sshJSONCodec) Name() string { return "json" }

func (sshJSONCodec) Marshal(v any) ([]byte, error) {
	return json.Marshal(v)
}

func (sshJSONCodec) Unmarshal(data []byte, v any) error {
	return json.Unmarshal(data, v)
}

// sshGetAgentByFingerprintRequest is the JSON wire type for GetAgentByFingerprint.
type sshGetAgentByFingerprintRequest struct {
	Fingerprint string `json:"fingerprint"`
}

// sshGetAgentByFingerprintResponse is the JSON wire response.
type sshGetAgentByFingerprintResponse struct {
	AgentID   string `json:"agent_id"`
	TenantID  string `json:"tenant_id"`
	Name      string `json:"name"`
	SSHPubKey string `json:"ssh_pubkey"`
	Status    string `json:"status"`
}

// sshHostKeyFingerprintRequest is the JSON wire type for GetHostKeyFingerprint.
type sshHostKeyFingerprintRequest struct {
	TenantID  string `json:"tenant_id"`
	ServiceID string `json:"service_id"`
}

// sshHostKeyFingerprintResponse is the JSON wire response.
type sshHostKeyFingerprintResponse struct {
	Fingerprint string `json:"fingerprint"`
}

// sshStoreHostKeyFingerprintRequest is the JSON wire type for StoreHostKeyFingerprint.
type sshStoreHostKeyFingerprintRequest struct {
	TenantID    string `json:"tenant_id"`
	ServiceID   string `json:"service_id"`
	Fingerprint string `json:"fingerprint"`
}

// sshStoreHostKeyFingerprintResponse is the JSON wire response (empty).
type sshStoreHostKeyFingerprintResponse struct{}

// dialSSH dials the vault-adapter and attaches the service-identity metadata.
// Returns the connection and a cancel func; caller must close both.
func (c *Client) dialSSH(ctx context.Context) (*grpc.ClientConn, context.Context, error) {
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
		return nil, nil, fmt.Errorf("vault: dialSSH %s: %w", c.address, err)
	}
	return conn, outCtx, nil
}

// GetAgentByFingerprint looks up an agent by SSH public key fingerprint.
// Calls /mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint.
func (c *Client) GetAgentByFingerprint(ctx context.Context, fingerprint string) (*Agent, error) {
	conn, outCtx, err := c.dialSSH(ctx)
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	callCtx, cancel := context.WithTimeout(outCtx, 5*time.Second)
	defer cancel()

	req := &sshGetAgentByFingerprintRequest{Fingerprint: fingerprint}
	resp := &sshGetAgentByFingerprintResponse{}

	if err = conn.Invoke(
		callCtx,
		"/"+sshVaultServiceName+"/GetAgentByFingerprint",
		req, resp,
		grpc.ForceCodec(sshJSONCodec{}),
		grpc.WaitForReady(false),
	); err != nil {
		return nil, fmt.Errorf("vault: GetAgentByFingerprint: %w", err)
	}

	return &Agent{
		ID:        resp.AgentID,
		TenantID:  resp.TenantID,
		Name:      resp.Name,
		SSHPubKey: resp.SSHPubKey,
		Status:    resp.Status,
	}, nil
}

// GetHostKeyFingerprint retrieves the stored SSH host key fingerprint for a
// (tenantID, serviceID) pair. Returns ("", nil) when no fingerprint is stored yet
// (TOFU first-use path).
func (c *Client) GetHostKeyFingerprint(ctx context.Context, tenantID, serviceID string) (string, error) {
	conn, outCtx, err := c.dialSSH(ctx)
	if err != nil {
		return "", err
	}
	defer conn.Close()

	callCtx, cancel := context.WithTimeout(outCtx, 5*time.Second)
	defer cancel()

	req := &sshHostKeyFingerprintRequest{TenantID: tenantID, ServiceID: serviceID}
	resp := &sshHostKeyFingerprintResponse{}

	if err = conn.Invoke(
		callCtx,
		"/"+sshVaultServiceName+"/GetHostKeyFingerprint",
		req, resp,
		grpc.ForceCodec(sshJSONCodec{}),
		grpc.WaitForReady(false),
	); err != nil {
		return "", fmt.Errorf("vault: GetHostKeyFingerprint: %w", err)
	}

	return resp.Fingerprint, nil
}

// StoreHostKeyFingerprint persists an SSH host key fingerprint for a service.
// On conflict (same tuple) it updates last_seen.
func (c *Client) StoreHostKeyFingerprint(ctx context.Context, tenantID, serviceID, fingerprint string) error {
	conn, outCtx, err := c.dialSSH(ctx)
	if err != nil {
		return err
	}
	defer conn.Close()

	callCtx, cancel := context.WithTimeout(outCtx, 5*time.Second)
	defer cancel()

	req := &sshStoreHostKeyFingerprintRequest{
		TenantID:    tenantID,
		ServiceID:   serviceID,
		Fingerprint: fingerprint,
	}
	resp := &sshStoreHostKeyFingerprintResponse{}

	if err = conn.Invoke(
		callCtx,
		"/"+sshVaultServiceName+"/StoreHostKeyFingerprint",
		req, resp,
		grpc.ForceCodec(sshJSONCodec{}),
		grpc.WaitForReady(false),
	); err != nil {
		return fmt.Errorf("vault: StoreHostKeyFingerprint: %w", err)
	}

	return nil
}

// ErrNotImplemented is retained for callers that may check for it during
// migration. None of the three methods return it now; the constant is kept
// to avoid breaking any import that references vault.ErrNotImplemented.
var ErrNotImplemented = errors.New("not implemented")
