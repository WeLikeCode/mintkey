// Package crypto provides AES-256-GCM envelope encryption primitives for the
// Vault Adapter.  All key material stays in memory; nothing is ever logged.
//
// Source: design §8 security invariants; ADR-0003; T-1.3.1.
package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"errors"
	"io"
)

const (
	dekLen   = 32 // AES-256
	nonceLen = 12 // GCM standard nonce
)

// GenerateDEK returns a fresh 32-byte AES-256 key suitable for use as a DEK.
func GenerateDEK() ([]byte, error) {
	dek := make([]byte, dekLen)
	if _, err := io.ReadFull(rand.Reader, dek); err != nil {
		return nil, err
	}
	return dek, nil
}

// WrapDEK encrypts dek with kek using AES-256-GCM.
// The returned blob is: nonce (12 bytes) || ciphertext+tag (len(dek)+16 bytes).
func WrapDEK(kek, dek []byte) ([]byte, error) {
	gcm, err := newGCM(kek)
	if err != nil {
		return nil, err
	}

	nonce := make([]byte, nonceLen)
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}

	// Seal appends ciphertext+tag to nonce in one allocation.
	return gcm.Seal(nonce, nonce, dek, nil), nil
}

// UnwrapDEK decrypts a wrapped DEK produced by WrapDEK.
// Returns an error if the blob is malformed or the ciphertext is tampered.
func UnwrapDEK(kek, wrapped []byte) ([]byte, error) {
	gcm, err := newGCM(kek)
	if err != nil {
		return nil, err
	}

	if len(wrapped) < nonceLen {
		return nil, errors.New("wrapped DEK too short")
	}

	nonce := wrapped[:nonceLen]
	ciphertext := wrapped[nonceLen:]
	return gcm.Open(nil, nonce, ciphertext, nil)
}

// newGCM constructs an AES-256-GCM AEAD from a 32-byte key.
func newGCM(key []byte) (cipher.AEAD, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	return cipher.NewGCM(block)
}
