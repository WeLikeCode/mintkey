package crypto

import (
	"bytes"
	"testing"
)

// kek32 returns a deterministic 32-byte KEK for tests.
func kek32() []byte {
	k := make([]byte, 32)
	for i := range k {
		k[i] = byte(i + 1)
	}
	return k
}

func TestSealOpenRoundtrip(t *testing.T) {
	kek := kek32()
	plaintext := []byte("super-secret-api-key-value")

	wrappedDEK, encPayload, err := Seal(kek, plaintext)
	if err != nil {
		t.Fatalf("Seal: %v", err)
	}

	got, err := Open(kek, wrappedDEK, encPayload)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}

	if !bytes.Equal(got, plaintext) {
		t.Errorf("Open returned %q; want %q", got, plaintext)
	}
}

func TestSealProducesUniqueCiphertexts(t *testing.T) {
	kek := kek32()
	plaintext := []byte("same plaintext")

	wDEK1, payload1, err := Seal(kek, plaintext)
	if err != nil {
		t.Fatalf("Seal 1: %v", err)
	}
	wDEK2, payload2, err := Seal(kek, plaintext)
	if err != nil {
		t.Fatalf("Seal 2: %v", err)
	}

	if bytes.Equal(wDEK1, wDEK2) {
		t.Error("two Seal calls produced identical wrappedDEK; expected unique DEKs")
	}
	if bytes.Equal(payload1, payload2) {
		t.Error("two Seal calls produced identical encryptedPayload; expected unique ciphertexts")
	}
}

func TestOpenTamperedPayloadFails(t *testing.T) {
	kek := kek32()
	plaintext := []byte("sensitive")

	wrappedDEK, encPayload, err := Seal(kek, plaintext)
	if err != nil {
		t.Fatalf("Seal: %v", err)
	}

	// Flip one byte in the ciphertext body (after the 12-byte nonce).
	tampered := make([]byte, len(encPayload))
	copy(tampered, encPayload)
	tampered[12] ^= 0xFF

	_, err = Open(kek, wrappedDEK, tampered)
	if err == nil {
		t.Error("Open with tampered payload should have returned an error")
	}
}

func TestOpenTamperedDEKFails(t *testing.T) {
	kek := kek32()
	plaintext := []byte("sensitive")

	wrappedDEK, encPayload, err := Seal(kek, plaintext)
	if err != nil {
		t.Fatalf("Seal: %v", err)
	}

	// Flip one byte in the wrapped DEK body (after the 12-byte nonce).
	tamperedDEK := make([]byte, len(wrappedDEK))
	copy(tamperedDEK, wrappedDEK)
	tamperedDEK[12] ^= 0xFF

	_, err = Open(kek, tamperedDEK, encPayload)
	if err == nil {
		t.Error("Open with tampered wrappedDEK should have returned an error")
	}
}
