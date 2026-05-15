// Package wireids encodes database UUIDs into the canonical Crockford-base32
// wire-form IDs used across Mintkey's external API surface.
//
// This is the Go port of the Python encoder in:
//   - admin-api/src/admin_api/utils/wire_ids.py
//   - mcp-server/src/mcp_server/utils/wire_ids.py
//
// The output MUST be bit-exact with those Python encoders: the same UUID input
// must always produce the same 26-char Crockford token on both sides.
//
// Source: ADR-0017.11; OPS-GG.
package wireids

import (
	"encoding/hex"
	"fmt"
	"strings"
)

// crockford is the standard Crockford base32 alphabet (no I, L, O, U).
// Index i maps to the character for digit value i (0–31).
const crockford = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// DBUUIDToWire encodes a database UUID string into the canonical Crockford
// wire-form ID with the given prefix.
//
// The uuid parameter must be a standard dashed UUID string
// (e.g. "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd") or the 32-hex form without
// dashes.
//
// The output format is "<prefix>_<26-char uppercase Crockford base32>", e.g.
// "svc_3C7JAGMBGR9EMRS2AVGXDHQXDX".
//
// This is a Go port of db_uuid_to_wire() from wire_ids.py (ADR-0017.11).
// The encoding is identical: 128-bit integer → 26 × 5-bit Crockford digits,
// big-endian (most-significant digit first).
func DBUUIDToWire(uuidStr string, prefix string) (string, error) {
	// Strip dashes to get the 32-char hex representation.
	hex32 := strings.ReplaceAll(uuidStr, "-", "")
	if len(hex32) != 32 {
		return "", fmt.Errorf("wireids: invalid UUID %q: expected 32 hex chars after dash removal, got %d", uuidStr, len(hex32))
	}

	// Decode the 16-byte UUID into two uint64 halves (big-endian).
	raw, err := hex.DecodeString(hex32)
	if err != nil {
		return "", fmt.Errorf("wireids: invalid UUID hex %q: %w", hex32, err)
	}

	// Build the 128-bit value as hi:lo pair of uint64s to avoid big.Int.
	// hi = bytes[0..7], lo = bytes[8..15].
	var hi, lo uint64
	for i := 0; i < 8; i++ {
		hi = (hi << 8) | uint64(raw[i])
	}
	for i := 8; i < 16; i++ {
		lo = (lo << 8) | uint64(raw[i])
	}

	// Encode 128 bits into 26 Crockford base32 characters, LSB first, then reverse.
	// This mirrors the Python loop:
	//   for _ in range(26):
	//       chars.append(_CROCKFORD[val & 0x1F])
	//       val >>= 5
	//   chars.reverse()
	//
	// We extract 5 bits at a time from the low end of the {hi, lo} pair.
	chars := make([]byte, 26)
	for i := 25; i >= 0; i-- {
		// The current low 5 bits of lo.
		digit := lo & 0x1F
		chars[i] = crockford[digit]
		// Right-shift the 128-bit value by 5: shift lo right, pull 5 bits from hi.
		lo = (lo >> 5) | ((hi & 0x1F) << 59)
		hi >>= 5
	}

	return prefix + "_" + string(chars), nil
}
