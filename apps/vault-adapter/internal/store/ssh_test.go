// Package store — unit tests for ValidateSSHPubKey and computeSSHFingerprint.
//
// These tests run without a live Postgres instance (no build tag required).
// They verify:
//   - ed25519 key parsed and fingerprint computed correctly.
//   - Multi-line key rejected.
//   - Empty key rejected.
//   - Unknown prefix rejected.
//   - Fingerprint format: "SHA256:<base64-no-padding>".
//   - Same key always yields the same fingerprint.
//
// Source: ADR-0021; chunk C7.
package store

import (
	"crypto/ed25519"
	"crypto/rand"
	"strings"
	"testing"

	"golang.org/x/crypto/ssh"
)

// generateTestED25519PubKey generates a fresh ED25519 SSH public key in
// authorized-keys format (single line: "ssh-ed25519 <base64> test").
func generateTestED25519PubKey(t *testing.T) string {
	t.Helper()
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	pub, err := ssh.NewPublicKey(priv.Public().(ed25519.PublicKey))
	if err != nil {
		t.Fatalf("ssh.NewPublicKey: %v", err)
	}
	// ssh.MarshalAuthorizedKey returns "ssh-ed25519 <base64>\n"
	return strings.TrimSpace(string(ssh.MarshalAuthorizedKey(pub)))
}

func TestValidateSSHPubKey_ED25519(t *testing.T) {
	key := generateTestED25519PubKey(t)
	fp, err := ValidateSSHPubKey(key)
	if err != nil {
		t.Fatalf("ValidateSSHPubKey(%q): unexpected error: %v", key[:20]+"...", err)
	}
	if !strings.HasPrefix(fp, "SHA256:") {
		t.Errorf("fingerprint %q does not start with SHA256:", fp)
	}
	// SHA-256 of 32-byte ED25519 key: base64 of 32 bytes = 43 chars without padding.
	suffix := strings.TrimPrefix(fp, "SHA256:")
	if len(suffix) == 0 {
		t.Errorf("fingerprint suffix is empty")
	}
	if strings.Contains(suffix, "=") {
		t.Errorf("fingerprint %q contains padding '='", fp)
	}
}

func TestValidateSSHPubKey_Deterministic(t *testing.T) {
	key := generateTestED25519PubKey(t)
	fp1, err1 := ValidateSSHPubKey(key)
	fp2, err2 := ValidateSSHPubKey(key)
	if err1 != nil || err2 != nil {
		t.Fatalf("unexpected errors: %v / %v", err1, err2)
	}
	if fp1 != fp2 {
		t.Errorf("fingerprints differ: %q vs %q", fp1, fp2)
	}
}

func TestValidateSSHPubKey_Empty(t *testing.T) {
	_, err := ValidateSSHPubKey("")
	if err == nil {
		t.Error("expected error for empty key, got nil")
	}
}

func TestValidateSSHPubKey_Multiline(t *testing.T) {
	key := generateTestED25519PubKey(t)
	multiline := key + "\nssh-rsa AAAA... malicious"
	_, err := ValidateSSHPubKey(multiline)
	if err == nil {
		t.Error("expected error for multiline key, got nil")
	}
}

func TestValidateSSHPubKey_UnknownPrefix(t *testing.T) {
	bad := "ecdh-sha2-nistp256 AAAAAAAAAA comment"
	_, err := ValidateSSHPubKey(bad)
	if err == nil {
		t.Error("expected error for unknown key type prefix, got nil")
	}
}

func TestValidateSSHPubKey_InvalidBase64Body(t *testing.T) {
	bad := "ssh-ed25519 NOT!!VALID!!BASE64 comment"
	_, err := ValidateSSHPubKey(bad)
	if err == nil {
		t.Error("expected error for invalid base64 body, got nil")
	}
}

func TestComputeSSHFingerprint_MatchesSSHPackage(t *testing.T) {
	key := generateTestED25519PubKey(t)
	fp, err := computeSSHFingerprint(key)
	if err != nil {
		t.Fatalf("computeSSHFingerprint: %v", err)
	}

	// Cross-check by parsing the key ourselves with ssh.ParseAuthorizedKey
	// and computing the fingerprint via the ssh package directly.
	pub, _, _, _, err := ssh.ParseAuthorizedKey([]byte(key))
	if err != nil {
		t.Fatalf("ssh.ParseAuthorizedKey: %v", err)
	}
	expected := ssh.FingerprintSHA256(pub)
	if fp != expected {
		t.Errorf("fingerprint mismatch: computeSSHFingerprint=%q ssh.FingerprintSHA256=%q", fp, expected)
	}
}
