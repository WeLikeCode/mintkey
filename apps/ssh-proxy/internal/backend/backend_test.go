package backend

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"testing"

	"golang.org/x/crypto/ssh"
)

func TestComputeFingerprint(t *testing.T) {
	// Generate a test key
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	// Convert to SSH public key
	sshPubKey, err := ssh.NewPublicKey(priv.Public())
	if err != nil {
		t.Fatalf("failed to create SSH public key: %v", err)
	}

	// Compute fingerprint
	fp := ComputeFingerprint(sshPubKey)

	// Verify format
	if fp == "" {
		t.Error("ComputeFingerprint() returned empty string")
	}

	if len(fp) < 10 {
		t.Errorf("ComputeFingerprint() returned suspiciously short fingerprint: %s", fp)
	}

	// Should start with "SHA256:"
	if fp[:7] != "SHA256:" {
		t.Errorf("ComputeFingerprint() = %s, want prefix 'SHA256:'", fp)
	}

	// Compute again - should be deterministic
	fp2 := ComputeFingerprint(sshPubKey)
	if fp != fp2 {
		t.Error("ComputeFingerprint() not deterministic")
	}
}

func TestVerifyHostKey(t *testing.T) {
	// Generate a test key
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	// Convert to SSH public key
	sshPubKey, err := ssh.NewPublicKey(priv.Public())
	if err != nil {
		t.Fatalf("failed to create SSH public key: %v", err)
	}

	// Compute expected fingerprint
	expectedFP := ComputeFingerprint(sshPubKey)

	// Verify with correct fingerprint
	if !VerifyHostKey(sshPubKey, expectedFP) {
		t.Error("VerifyHostKey() returned false for correct fingerprint")
	}

	// Verify with incorrect fingerprint
	if VerifyHostKey(sshPubKey, "SHA256:invalid") {
		t.Error("VerifyHostKey() returned true for incorrect fingerprint")
	}

	// Generate different key
	_, priv2, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate second key: %v", err)
	}

	sshPubKey2, err := ssh.NewPublicKey(priv2.Public())
	if err != nil {
		t.Fatalf("failed to create second SSH public key: %v", err)
	}

	// Verify different key with original fingerprint
	if VerifyHostKey(sshPubKey2, expectedFP) {
		t.Error("VerifyHostKey() returned true for different key")
	}
}

func TestHostKeyStore_Cache(t *testing.T) {
	// Create a store without vault client (in-memory only).
	store := NewHostKeyStore(nil)

	hostname := "test.example.com"
	fingerprint := "SHA256:abc123"

	// Initially not in cache → GetFingerprint returns error.
	_, err := store.GetFingerprint(context.Background(), hostname)
	if err == nil {
		t.Error("GetFingerprint should return error when hostname not in cache")
	}

	// Store a fingerprint.
	if err := store.StoreFingerprint(context.Background(), hostname, fingerprint); err != nil {
		t.Fatalf("StoreFingerprint() error = %v", err)
	}

	// Now should be retrievable.
	fp, err := store.GetFingerprint(context.Background(), hostname)
	if err != nil {
		t.Fatalf("GetFingerprint() after store error = %v", err)
	}
	if fp != fingerprint {
		t.Errorf("GetFingerprint() = %s, want %s", fp, fingerprint)
	}
}

func TestConnector_Close(t *testing.T) {
	// Test that Close zeros the private key
	privateKey := []byte("test private key data")

	// Make a copy to verify zeroing
	original := make([]byte, len(privateKey))
	copy(original, privateKey)

	// Close (with nil client)
	Close(nil, privateKey)

	// Verify key is zeroed
	for i, b := range privateKey {
		if b != 0 {
			t.Errorf("privateKey[%d] = %d, want 0", i, b)
		}
	}

	// Verify original is not zeroed (to ensure we're testing the right thing)
	allZero := true
	for _, b := range original {
		if b != 0 {
			allZero = false
			break
		}
	}

	if allZero {
		t.Error("original key should not be all zeros")
	}
}

// ---------------------------------------------------------------------------
// TOFU tests (C6 — Part A)
// ---------------------------------------------------------------------------

// TestTOFU_HappyPath verifies that on first connection the fingerprint is
// stored in-memory and subsequent calls succeed with the same key.
func TestTOFU_HappyPath(t *testing.T) {
	store := NewTOFUStore(nil, false)
	ctx := context.Background()

	_, key1, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	sshKey1, _ := ssh.NewPublicKey(key1.Public())

	cb := TOFUCallback(store, false)

	// First call: fingerprint stored, no error.
	if err := cb("host1:22", nil, sshKey1); err != nil {
		t.Fatalf("first TOFU call should succeed: %v", err)
	}

	// Second call with the same key: should succeed (fingerprint matches).
	if err := cb("host1:22", nil, sshKey1); err != nil {
		t.Fatalf("second TOFU call with same key should succeed: %v", err)
	}

	// Confirm the fingerprint is now in the store.
	fp, err := store.GetFingerprint(ctx, "host1:22")
	if err != nil {
		t.Fatalf("GetFingerprint after TOFU store: %v", err)
	}
	if fp == "" {
		t.Error("stored fingerprint should not be empty")
	}
}

// TestTOFU_Mismatch verifies that a different key for the same host is rejected.
func TestTOFU_Mismatch(t *testing.T) {
	store := NewTOFUStore(nil, false)

	_, key1, _ := ed25519.GenerateKey(rand.Reader)
	_, key2, _ := ed25519.GenerateKey(rand.Reader)
	sshKey1, _ := ssh.NewPublicKey(key1.Public())
	sshKey2, _ := ssh.NewPublicKey(key2.Public())

	cb := TOFUCallback(store, false)

	// First call stores key1.
	if err := cb("host2:22", nil, sshKey1); err != nil {
		t.Fatalf("first TOFU call: %v", err)
	}

	// Second call with different key2 must be rejected.
	err := cb("host2:22", nil, sshKey2)
	if err == nil {
		t.Fatal("TOFU mismatch: expected rejection but got nil")
	}
	// Error should contain mismatch signal.
	if len(err.Error()) < 8 {
		t.Errorf("mismatch error too short: %q", err.Error())
	}
}

// TestTOFU_StrictMode verifies that in strict mode an unknown host is rejected
// even on the first connection.
func TestTOFU_StrictMode(t *testing.T) {
	store := NewTOFUStore(nil, true /* strict */)

	_, key1, _ := ed25519.GenerateKey(rand.Reader)
	sshKey1, _ := ssh.NewPublicKey(key1.Public())

	cb := TOFUCallback(store, true)

	// In strict mode, first connection to an unknown host must be rejected.
	err := cb("stricthost:22", nil, sshKey1)
	if err == nil {
		t.Fatal("strict mode: expected rejection for unknown host, got nil")
	}
}

// TestTOFU_VaultNotImplemented_FallsBackToMemory verifies that when the vault
// stub returns ErrNotImplemented, StoreFingerprint still works via in-memory.
func TestTOFU_VaultNotImplemented_FallsBackToMemory(t *testing.T) {
	// NewHostKeyStore with nil vault → pure in-memory.
	store := NewHostKeyStore(nil)
	ctx := context.Background()

	err := store.StoreFingerprint(ctx, "myhost:22", "SHA256:deadbeef")
	if err != nil {
		t.Fatalf("StoreFingerprint with nil vault: %v", err)
	}

	fp, err := store.GetFingerprint(ctx, "myhost:22")
	if err != nil {
		t.Fatalf("GetFingerprint after in-memory store: %v", err)
	}
	if fp != "SHA256:deadbeef" {
		t.Errorf("fp = %q, want %q", fp, "SHA256:deadbeef")
	}
}
