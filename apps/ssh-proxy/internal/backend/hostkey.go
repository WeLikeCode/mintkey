package backend

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"sync"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/vault"
	"golang.org/x/crypto/ssh"
)

// TOFUStore stores and retrieves host key fingerprints using Trust On First Use
// semantics. It wraps a vault.Client for persistence and maintains an in-memory
// cache as a fallback when the vault stub returns ErrNotImplemented.
type TOFUStore struct {
	vaultClient *vault.Client
	cache       map[string]string // hostname -> fingerprint (in-memory fallback)
	mu          sync.RWMutex
	strict      bool // when true, never auto-accept unknown keys
}

// HostKeyStore is a type alias kept for backward compatibility.
type HostKeyStore = TOFUStore

// NewHostKeyStore creates a new TOFUStore (in non-strict mode by default).
func NewHostKeyStore(vaultClient *vault.Client) *TOFUStore {
	return &TOFUStore{
		vaultClient: vaultClient,
		cache:       make(map[string]string),
		strict:      false,
	}
}

// NewTOFUStore creates a TOFUStore with explicit strict-mode control.
func NewTOFUStore(vaultClient *vault.Client, strict bool) *TOFUStore {
	return &TOFUStore{
		vaultClient: vaultClient,
		cache:       make(map[string]string),
		strict:      strict,
	}
}

// GetFingerprint retrieves the stored fingerprint for a hostname.
// Returns an error (non-nil) if no fingerprint is stored — callers treat that
// as "first connection".
func (s *TOFUStore) GetFingerprint(ctx context.Context, hostname string) (string, error) {
	// Check in-memory cache first (covers both the ErrNotImplemented fallback
	// and entries promoted from vault).
	s.mu.RLock()
	if fp, ok := s.cache[hostname]; ok {
		s.mu.RUnlock()
		return fp, nil
	}
	s.mu.RUnlock()

	if s.vaultClient == nil {
		return "", fmt.Errorf("no fingerprint stored for %s", hostname)
	}

	fp, err := s.vaultClient.GetHostKeyFingerprint(ctx, hostname, "")
	if err != nil {
		if errors.Is(err, vault.ErrNotImplemented) {
			// Vault stub not wired — treat as "not found" (will trigger TOFU first-use path).
			return "", fmt.Errorf("no fingerprint stored for %s (vault persistence not wired)", hostname)
		}
		return "", err
	}

	// Promote to in-memory cache.
	s.mu.Lock()
	s.cache[hostname] = fp
	s.mu.Unlock()

	return fp, nil
}

// StoreFingerprint persists a fingerprint for a hostname.
// Always updates the in-memory cache; vault persistence failures are logged
// as warnings but do not fail the call (in-memory serves as fallback).
func (s *TOFUStore) StoreFingerprint(ctx context.Context, hostname, fingerprint string) error {
	// Always update in-memory cache first so subsequent GetFingerprint calls
	// don't hit vault again.
	s.mu.Lock()
	s.cache[hostname] = fingerprint
	s.mu.Unlock()

	if s.vaultClient == nil {
		return nil
	}

	if err := s.vaultClient.StoreHostKeyFingerprint(ctx, hostname, "", fingerprint); err != nil {
		if errors.Is(err, vault.ErrNotImplemented) {
			slog.Warn("TOFU: vault persistence not wired — fingerprint stored in memory only",
				"hostname", hostname,
				"fingerprint", fingerprint,
			)
			return nil // not an error; in-memory fallback is live
		}
		return err
	}

	return nil
}

// TOFUCallback creates a host key callback that implements Trust On First Use.
// Deprecated: use Connector.hostKeyCallback which uses TOFUStore directly.
// Kept for backward compatibility with tests.
func TOFUCallback(store *TOFUStore, strict bool) ssh.HostKeyCallback {
	return func(hostname string, remote net.Addr, key ssh.PublicKey) error {
		fingerprint := ComputeFingerprint(key)
		ctx := context.Background()

		storedFP, err := store.GetFingerprint(ctx, hostname)
		if err != nil {
			// First connection.
			slog.Info("TOFU: first connection to host, storing fingerprint",
				"hostname", hostname,
				"fingerprint", fingerprint,
			)

			if strict {
				return fmt.Errorf("strict mode: no pre-registered key for %s", hostname)
			}

			if storeErr := store.StoreFingerprint(ctx, hostname, fingerprint); storeErr != nil {
				return fmt.Errorf("failed to store host key fingerprint: %w", storeErr)
			}
			return nil
		}

		if storedFP != fingerprint {
			slog.Error("TOFU: host key changed",
				"hostname", hostname,
				"stored_fingerprint", storedFP,
				"current_fingerprint", fingerprint,
			)
			return fmt.Errorf("ssh.hostkey.mismatch: key changed for %s (stored: %s, current: %s)",
				hostname, storedFP, fingerprint)
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
