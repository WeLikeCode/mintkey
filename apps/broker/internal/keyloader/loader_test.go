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

func writeSeedFile(t *testing.T, seed []byte) string {
	t.Helper()
	p := t.TempDir() + "/signing-key"
	if err := os.WriteFile(p, seed, 0o400); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}
	return p
}

func TestLoadKey_SameFileSameKID(t *testing.T) {
	seed := make([]byte, ed25519.SeedSize)
	if _, err := rand.Read(seed); err != nil {
		t.Fatalf("rand.Read: %v", err)
	}
	p := writeSeedFile(t, seed)
	_, kid1, err := keyloader.LoadKey("production", p)
	if err != nil {
		t.Fatalf("LoadKey #1: %v", err)
	}
	_, kid2, err := keyloader.LoadKey("production", p)
	if err != nil {
		t.Fatalf("LoadKey #2: %v", err)
	}
	if kid1 != kid2 {
		t.Fatalf("kid differs across loads of the same file: %q vs %q", kid1, kid2)
	}
	if len(kid1) != len("kid_")+26 || !strings.HasPrefix(kid1, "kid_") {
		t.Fatalf("kid %q is not kid_ + 26 chars", kid1)
	}
}

func TestLoadKey_DifferentFilesDifferentKID(t *testing.T) {
	a := make([]byte, ed25519.SeedSize)
	b := make([]byte, ed25519.SeedSize)
	b[0] = 1
	_, kidA, _ := keyloader.LoadKey("dev", writeSeedFile(t, a))
	_, kidB, _ := keyloader.LoadKey("dev", writeSeedFile(t, b))
	if kidA == kidB {
		t.Fatalf("different keys share kid %q", kidA)
	}
}

func TestLoadKey_FileSet_BadFile_FailsInEveryMode(t *testing.T) {
	for _, env := range []string{"dev", "production"} {
		t.Run(env+"/missing", func(t *testing.T) {
			_, _, err := keyloader.LoadKey(env, t.TempDir()+"/nope")
			if err == nil {
				t.Fatal("expected error for unreadable key file, got nil")
			}
		})
		t.Run(env+"/wrong-length", func(t *testing.T) {
			_, _, err := keyloader.LoadKey(env, writeSeedFile(t, []byte("short")))
			if err == nil {
				t.Fatal("expected error for wrong-length key file, got nil")
			}
			if !strings.Contains(err.Error(), "MINTKEY_BROKER_SIGNING_KEY_FILE") {
				t.Fatalf("error should name the variable: %v", err)
			}
		})
	}
}
