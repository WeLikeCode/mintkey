package backend

import (
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
	// Create a mock store (without vault client)
	store := &HostKeyStore{
		cache: make(map[string]string),
	}

	hostname := "test.example.com"
	fingerprint := "SHA256:abc123"

	// Initially not in cache
	store.mu.RLock()
	_, ok := store.cache[hostname]
	store.mu.RUnlock()

	if ok {
		t.Error("hostname should not be in cache initially")
	}

	// Add to cache
	store.mu.Lock()
	store.cache[hostname] = fingerprint
	store.mu.Unlock()

	// Now should be in cache
	store.mu.RLock()
	fp, ok := store.cache[hostname]
	store.mu.RUnlock()

	if !ok {
		t.Error("hostname should be in cache after adding")
	}

	if fp != fingerprint {
		t.Errorf("cache fingerprint = %s, want %s", fp, fingerprint)
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
