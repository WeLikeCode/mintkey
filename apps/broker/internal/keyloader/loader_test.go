package keyloader_test

import (
	"crypto/ed25519"
	"crypto/rand"
	"os"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/keyloader"
)

func TestLoadKey_FromFile(t *testing.T) {
	seed := make([]byte, ed25519.SeedSize)
	if _, err := rand.Read(seed); err != nil {
		t.Fatalf("rand.Read: %v", err)
	}
	f, err := os.CreateTemp(t.TempDir(), "signing-key-*")
	if err != nil {
		t.Fatalf("CreateTemp: %v", err)
	}
	if _, err := f.Write(seed); err != nil {
		t.Fatalf("Write seed: %v", err)
	}
	f.Close()

	priv, kid, err := keyloader.LoadKey("dev", f.Name())
	if err != nil {
		t.Fatalf("LoadKey: %v", err)
	}
	if len(priv) != ed25519.PrivateKeySize {
		t.Fatalf("private key length %d, want %d", len(priv), ed25519.PrivateKeySize)
	}
	if !strings.HasPrefix(kid, "kid_") {
		t.Fatalf("kid %q does not start with 'kid_'", kid)
	}
}

func TestLoadKey_TwoInstancesSameFile(t *testing.T) {
	seed := make([]byte, ed25519.SeedSize)
	if _, err := rand.Read(seed); err != nil {
		t.Fatalf("rand.Read: %v", err)
	}
	f, err := os.CreateTemp(t.TempDir(), "signing-key-*")
	if err != nil {
		t.Fatalf("CreateTemp: %v", err)
	}
	if _, err := f.Write(seed); err != nil {
		t.Fatalf("Write seed: %v", err)
	}
	f.Close()

	priv1, _, err := keyloader.LoadKey("dev", f.Name())
	if err != nil {
		t.Fatalf("LoadKey #1: %v", err)
	}
	priv2, _, err := keyloader.LoadKey("dev", f.Name())
	if err != nil {
		t.Fatalf("LoadKey #2: %v", err)
	}

	msg := []byte("test message")

	sig1 := ed25519.Sign(priv1, msg)
	if !ed25519.Verify(priv2.Public().(ed25519.PublicKey), msg, sig1) {
		t.Fatal("sig from key1 failed to verify with key2 public key")
	}

	sig2 := ed25519.Sign(priv2, msg)
	if !ed25519.Verify(priv1.Public().(ed25519.PublicKey), msg, sig2) {
		t.Fatal("sig from key2 failed to verify with key1 public key")
	}
}

func TestLoadKey_MissingFile_DevReturnsEphemeral(t *testing.T) {
	priv, kid, err := keyloader.LoadKey("dev", "")
	if err != nil {
		t.Fatalf("LoadKey dev with no file: %v", err)
	}
	if len(priv) != ed25519.PrivateKeySize {
		t.Fatalf("private key length %d, want %d", len(priv), ed25519.PrivateKeySize)
	}
	if !strings.HasPrefix(kid, "kid_") {
		t.Fatalf("kid %q does not start with 'kid_'", kid)
	}
}

func TestLoadKey_MissingFile_ProductionFails(t *testing.T) {
	_, _, err := keyloader.LoadKey("production", "")
	if err == nil {
		t.Fatal("expected error for production with no file, got nil")
	}
}
