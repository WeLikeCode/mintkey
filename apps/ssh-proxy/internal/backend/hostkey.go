package backend

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"net"
	"sync"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/vault"
	"golang.org/x/crypto/ssh"
)

// HostKeyStore stores and retrieves host key fingerprints.
type HostKeyStore struct {
	vaultClient *vault.Client
	cache       map[string]string // hostname -> fingerprint
	mu          sync.RWMutex
}

// NewHostKeyStore creates a new host key store.
func NewHostKeyStore(vaultClient *vault.Client) *HostKeyStore {
	return &HostKeyStore{
		vaultClient: vaultClient,
		cache:       make(map[string]string),
	}
}

// GetFingerprint retrieves the stored fingerprint for a hostname.
func (s *HostKeyStore) GetFingerprint(ctx context.Context, hostname string) (string, error) {
	// Check cache first
	s.mu.RLock()
	if fp, ok := s.cache[hostname]; ok {
		s.mu.RUnlock()
		return fp, nil
	}
	s.mu.RUnlock()

	// Query vault for stored fingerprint.
	// hostname is used as a stand-in for tenantID/serviceID until C6 wires
	// the proper identifiers from the session context.
	fp, err := s.vaultClient.GetHostKeyFingerprint(ctx, hostname, "")
	if err != nil {
		return "", err
	}

	// Update cache
	s.mu.Lock()
	s.cache[hostname] = fp
	s.mu.Unlock()

	return fp, nil
}

// StoreFingerprint stores a fingerprint for a hostname.
func (s *HostKeyStore) StoreFingerprint(ctx context.Context, hostname, fingerprint string) error {
	// Store in vault.
	// hostname is used as a stand-in for tenantID/serviceID until C6 wires
	// the proper identifiers from the session context.
	if err := s.vaultClient.StoreHostKeyFingerprint(ctx, hostname, "", fingerprint); err != nil {
		return err
	}

	// Update cache
	s.mu.Lock()
	s.cache[hostname] = fingerprint
	s.mu.Unlock()

	return nil
}

// TOFUCallback creates a host key callback that implements Trust On First Use.
func TOFUCallback(store *HostKeyStore, strict bool) ssh.HostKeyCallback {
	return func(hostname string, remote net.Addr, key ssh.PublicKey) error {
		// Compute fingerprint
		fingerprint := ComputeFingerprint(key)

		// Try to get stored fingerprint
		ctx := context.Background()
		storedFP, err := store.GetFingerprint(ctx, hostname)

		if err != nil {
			// No stored fingerprint - first connection
			slog.Info("first connection to host, storing fingerprint",
				"hostname", hostname,
				"fingerprint", fingerprint,
			)

			if err := store.StoreFingerprint(ctx, hostname, fingerprint); err != nil {
				return fmt.Errorf("failed to store host key fingerprint: %w", err)
			}

			return nil
		}

		// Compare fingerprints
		if storedFP != fingerprint {
			slog.Error("host key changed",
				"hostname", hostname,
				"stored_fingerprint", storedFP,
				"current_fingerprint", fingerprint,
			)

			if strict {
				return fmt.Errorf("host key verification failed: key changed for %s (stored: %s, current: %s)", hostname, storedFP, fingerprint)
			}

			// In non-strict mode, log warning but allow connection
			slog.Warn("host key changed but strict mode disabled, allowing connection",
				"hostname", hostname,
			)
		}

		return nil
	}
}

// ComputeFingerprint computes the SHA256 fingerprint of an SSH public key.
func ComputeFingerprint(key ssh.PublicKey) string {
	hash := sha256.Sum256(key.Marshal())
	return "SHA256:" + hex.EncodeToString(hash[:])
}

// VerifyHostKey verifies a host key against a known fingerprint.
func VerifyHostKey(key ssh.PublicKey, expectedFingerprint string) bool {
	actual := ComputeFingerprint(key)
	return actual == expectedFingerprint
}
