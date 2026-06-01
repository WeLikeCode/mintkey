// Package backend handles SSH connections to backend servers.
package backend

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"time"

	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/session"
	"github.com/WeLikeCode/mintkey/internal/vault"
	"golang.org/x/crypto/ssh"
)

// Connector manages SSH connections to backend servers.
type Connector struct {
	vaultClient *vault.Client
}

// NewConnector creates a new backend connector.
func NewConnector(vaultClient *vault.Client) *Connector {
	return &Connector{
		vaultClient: vaultClient,
	}
}

// Connect establishes an SSH connection to a backend server.
func (c *Connector) Connect(ctx context.Context, sessCtx *session.SessionContext, targetAddr string) (*ssh.Client, []byte, error) {
	// Fetch SSH private key from vault
	cred, err := c.vaultClient.GetCredential(ctx, sessCtx.TenantID, sessCtx.ServiceID)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to fetch credential: %w", err)
	}

	// Verify auth scheme is SSH private key
	if cred.AuthScheme != vault.AuthSchemeSSHPrivateKey {
		return nil, nil, fmt.Errorf("invalid auth scheme: expected SSH_PRIVATE_KEY, got %v", cred.AuthScheme)
	}

	// Parse SSH private key
	signer, err := ssh.ParsePrivateKey(cred.Value)
	if err != nil {
		// Try parsing as OpenSSH format
		signer, err = ssh.ParsePrivateKeyWithPassphrase(cred.Value, nil)
		if err != nil {
			return nil, nil, fmt.Errorf("failed to parse SSH private key: %w", err)
		}
	}

	// Determine target address
	// If targetAddr is empty, use the service's default address from vault
	if targetAddr == "" {
		targetAddr = cred.TargetAddress
		if targetAddr == "" {
			return nil, nil, fmt.Errorf("no target address specified and service has no default")
		}
	}

	// Determine SSH user
	user := cred.SSHUser
	if user == "" {
		user = "root" // Default to root if not specified
	}

	// Create SSH client config
	config := &ssh.ClientConfig{
		User: user,
		Auth: []ssh.AuthMethod{
			ssh.PublicKeys(signer),
		},
		HostKeyCallback: c.hostKeyCallback(sessCtx),
		Timeout:         10 * time.Second,
	}

	// Connect to backend
	slog.Info("connecting to backend",
		"session_id", sessCtx.AgentID, // Use agent_id as session identifier for now
		"target", targetAddr,
		"user", user,
	)

	client, err := ssh.Dial("tcp", targetAddr, config)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to connect to backend %s: %w", targetAddr, err)
	}

	slog.Info("backend connection established",
		"session_id", sessCtx.AgentID,
		"target", targetAddr,
	)

	return client, cred.Value, nil
}

// hostKeyCallback returns a host key callback that implements TOFU (Trust On First Use).
func (c *Connector) hostKeyCallback(sessCtx *session.SessionContext) ssh.HostKeyCallback {
	return func(hostname string, remote net.Addr, key ssh.PublicKey) error {
		// For now, accept all host keys (TOFU will be implemented later)
		// TODO: Implement proper TOFU with database storage
		slog.Debug("accepting host key",
			"hostname", hostname,
			"remote", remote.String(),
			"fingerprint", ssh.FingerprintSHA256(key),
		)
		return nil
	}
}

// Close closes the backend connection and zeros the private key.
func Close(client *ssh.Client, privateKey []byte) {
	// Zero the private key
	for i := range privateKey {
		privateKey[i] = 0
	}

	// Close the connection
	if client != nil {
		client.Close()
	}
}
