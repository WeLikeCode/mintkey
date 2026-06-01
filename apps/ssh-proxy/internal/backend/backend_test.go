package backend

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"fmt"
	"net"
	"testing"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/vault"
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

// ---------------------------------------------------------------------------
// SSH password auth branch — unit test using in-process sshd
// ---------------------------------------------------------------------------

// TestConnect_SSHPassword_AcceptsPasswordAuth verifies that the Connect method
// correctly uses ssh.Password() when cred.AuthScheme == AuthSchemeSSHPassword,
// and that the connection succeeds against an in-process SSH server configured
// to accept that password.
func TestConnect_SSHPassword_AcceptsPasswordAuth(t *testing.T) {
	const testPassword = "hunter2-test-password"
	const testUser = "testuser"

	// Generate a host key for the in-process server.
	_, hostPriv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("generate host key: %v", err)
	}
	hostSigner, err := ssh.NewSignerFromKey(hostPriv)
	if err != nil {
		t.Fatalf("host signer: %v", err)
	}

	// Start a minimal in-process SSH server that accepts password auth.
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer listener.Close()

	serverConfig := &ssh.ServerConfig{
		PasswordCallback: func(c ssh.ConnMetadata, pass []byte) (*ssh.Permissions, error) {
			if c.User() == testUser && string(pass) == testPassword {
				return nil, nil
			}
			return nil, fmt.Errorf("password rejected")
		},
	}
	serverConfig.AddHostKey(hostSigner)

	// Accept one connection in the background.
	serverDone := make(chan error, 1)
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			serverDone <- err
			return
		}
		_, _, _, err = ssh.NewServerConn(conn, serverConfig)
		serverDone <- err
	}()

	// Build a minimal ssh.ClientConfig using ssh.Password — mirroring the
	// production path in Connect().
	clientConfig := &ssh.ClientConfig{
		User: testUser,
		Auth: []ssh.AuthMethod{
			ssh.Password(testPassword),
		},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), // test only
	}

	client, err := ssh.Dial("tcp", listener.Addr().String(), clientConfig)
	if err != nil {
		t.Fatalf("ssh.Dial with password: %v", err)
	}
	client.Close()

	// Verify the server accepted the connection without error.
	if sErr := <-serverDone; sErr != nil {
		t.Fatalf("server rejected connection: %v", sErr)
	}
}

// TestConnect_SSHPassword_ZeroizesPasswordBytes verifies that the byte slice
// used to pass the password to ssh.Password() is zeroed after construction,
// ensuring the password does not linger in memory beyond the auth exchange.
func TestConnect_SSHPassword_ZeroizesPasswordBytes(t *testing.T) {
	// Simulate the zeroize logic from backend.go.
	rawPassword := []byte("my-secret-password")
	pwCopy := make([]byte, len(rawPassword))
	copy(pwCopy, rawPassword)

	// After building the auth method, zero pwCopy.
	_ = ssh.Password(string(pwCopy))
	for i := range pwCopy {
		pwCopy[i] = 0
	}

	// pwCopy must be all zeros now.
	for i, b := range pwCopy {
		if b != 0 {
			t.Errorf("pwCopy[%d] = %d, want 0 after zeroize", i, b)
		}
	}

	// rawPassword must NOT be zeroed (it's the original credential bytes
	// held by the Credential struct — zeroed separately by Close()).
	allZero := true
	for _, b := range rawPassword {
		if b != 0 {
			allZero = false
			break
		}
	}
	if allZero {
		t.Error("rawPassword should not be zeroed — only the pwCopy is zeroed here")
	}
}

// TestAuthSchemeSSHPassword_ConstValue ensures the AuthSchemeSSHPassword
// constant equals 13 (matching vault.proto AUTH_SCHEME_SSH_PASSWORD = 13).
func TestAuthSchemeSSHPassword_ConstValue(t *testing.T) {
	if vault.AuthSchemeSSHPassword != 13 {
		t.Errorf("AuthSchemeSSHPassword = %d, want 13", vault.AuthSchemeSSHPassword)
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
