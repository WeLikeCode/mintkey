package crypto

// Seal encrypts plaintext with a fresh DEK, then wraps that DEK with the KEK.
//
// Returns:
//   - wrappedDEK: the DEK encrypted with the KEK (nonce||ciphertext||tag).
//   - encryptedPayload: the plaintext encrypted with the DEK (nonce||ciphertext||tag).
//
// Every call generates a new DEK and new nonces, so the same plaintext sealed
// twice always produces different ciphertexts.  This is the property required
// by ADR-0003 ("unique ciphertext per store operation").
func Seal(kek, plaintext []byte) (wrappedDEK []byte, encryptedPayload []byte, err error) {
	dek, err := GenerateDEK()
	if err != nil {
		return nil, nil, err
	}

	wrappedDEK, err = WrapDEK(kek, dek)
	if err != nil {
		return nil, nil, err
	}

	encryptedPayload, err = WrapDEK(dek, plaintext)
	if err != nil {
		return nil, nil, err
	}

	return wrappedDEK, encryptedPayload, nil
}

// Open decrypts an encrypted payload using the wrapped DEK and KEK.
// Returns an error if authentication fails (tampered DEK or payload).
// The plaintext is NEVER persisted; callers must handle it as ephemeral.
func Open(kek, wrappedDEK, encryptedPayload []byte) ([]byte, error) {
	dek, err := UnwrapDEK(kek, wrappedDEK)
	if err != nil {
		return nil, err
	}

	return UnwrapDEK(dek, encryptedPayload)
}
