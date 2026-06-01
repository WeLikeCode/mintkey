// Package backend handles SSH connections to backend servers.
package backend

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"time"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/session"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/vault"
	"golang.org/x/crypto/ssh"
)

// Connector manages SSH connections to backend servers.
type Connector struct {
	vaultClient *vault.Client
	tofu        *TOFUStore
}

// NewConnector creates a new backend connector.
// tofu may be nil; in that case an in-memory-only TOFUStore is created.
func NewConnector(vaultClient *vault.Client, tofu *TOFUStore) *Connector {
	if tofu == nil {
		tofu = NewHostKeyStore(vaultClient)
	}
	return &Connector{
		vaultClient: vaultClient,
		tofu:        tofu,
	}
}

// Connect establishes an SSH connection to a backend server.
func (c *Connector) Connect(ctx context.Context, sessCtx *session.SessionContext, targetAddr string) (*ssh.Client, []byte, error) {
	// Fetch SSH private key from vault
	cred, err := c.vaultClient.GetCredential(ctx, sessCtx.TenantID, sessCtx.ServiceID)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to fetch credential: %w", err)
	}

	// Verify auth scheme is SSH private key or SSH password
	if cred.AuthScheme != vault.AuthSchemeSSHPrivateKey && cred.AuthScheme != vault.AuthSchemeSSHPassword {
		return nil, nil, fmt.Errorf("invalid auth scheme: expected SSH_PRIVATE_KEY or SSH_PASSWORD, got %v", cred.AuthScheme)
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

	// Build the auth method based on the scheme.
	var authMethod ssh.AuthMethod
	if cred.AuthScheme == vault.AuthSchemeSSHPassword {
		// SSH password auth — copy password bytes into the method then zeroize.
		pwCopy := make([]byte, len(cred.Value))
		copy(pwCopy, cred.Value)
		authMethod = ssh.Password(string(pwCopy))
		// Zeroize our copy immediately; cred.Value is zeroed by Close() after session ends.
		for i := range pwCopy {
			pwCopy[i] = 0
		}
	} else {
		// SSH private key auth.
		signer, err := ssh.ParsePrivateKey(cred.Value)
		if err != nil {
			// Try parsing as OpenSSH format
			signer, err = ssh.ParsePrivateKeyWithPassphrase(cred.Value, nil)
			if err != nil {
				return nil, nil, fmt.Errorf("failed to parse SSH private key: %w", err)
			}
		}
		authMethod = ssh.PublicKeys(signer)
	}

	// Create SSH client config
	config := &ssh.ClientConfig{
		User: user,
		Auth: []ssh.AuthMethod{
			authMethod,
		},
		HostKeyCallback: c.hostKeyCallback(ctx, sessCtx),
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

// hostKeyCallback returns a host key callback that implements TOFU.
func (c *Connector) hostKeyCallback(ctx context.Context, sessCtx *session.SessionContext) ssh.HostKeyCallback {
	return func(hostname string, remote net.Addr, key ssh.PublicKey) error {
		fingerprint := ComputeFingerprint(key)

		storedFP, err := c.tofu.GetFingerprint(ctx, hostname)
		if err != nil {
			// No stored fingerprint — first connection.
			if c.tofu.strict {
				slog.Error("TOFU strict mode: rejecting unknown host key",
					"hostname", hostname,
					"fingerprint", fingerprint,
					"session_id", sessCtx.AgentID,
				)
				return fmt.Errorf("ssh.hostkey.mismatch: strict mode — no pre-registered key for %s (fingerprint %s)", hostname, fingerprint)
			}

			slog.Warn("TOFU: first connection to host — storing fingerprint (persistence may not be wired)",
				"hostname", hostname,
				"fingerprint", fingerprint,
				"session_id", sessCtx.AgentID,
			)
			if storeErr := c.tofu.StoreFingerprint(ctx, hostname, fingerprint); storeErr != nil {
				// Non-fatal: in-memory fallback already updated inside StoreFingerprint.
				slog.Warn("TOFU: failed to persist fingerprint (non-fatal)",
					"hostname", hostname,
					"error", storeErr,
				)
			}
			return nil
		}

		// Fingerprint on record — verify.
		if storedFP != fingerprint {
			slog.Error("ssh.hostkey.mismatch: host key changed",
				"hostname", hostname,
				"stored_fingerprint", storedFP,
				"current_fingerprint", fingerprint,
				"session_id", sessCtx.AgentID,
			)
			// Always reject mismatches regardless of strict mode — changed key = possible MITM.
			return fmt.Errorf("ssh.hostkey.mismatch: key changed for %s (stored: %s, current: %s)",
				hostname, storedFP, fingerprint)
		}

		slog.Debug("TOFU: host key verified",
			"hostname", hostname,
			"fingerprint", fingerprint,
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
