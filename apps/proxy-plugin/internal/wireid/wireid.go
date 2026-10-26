// Package wireid decodes the wire-form IDs of ADR-0017.11 to their database
// UUID form. Both the canonical 26-character Crockford base32 form and the
// legacy 32-hex form are accepted.
//
// Source: ADR-0017.11.
package wireid

import (
	"math/big"
	"strings"
)

// crockford is the Crockford base32 alphabet of ADR-0017.11 (no I, L, O, U).
const crockford = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// ToUUID returns the lowercase dashed UUID that id denotes, and true; or
// "", false when id is not decodable.
// prefix includes the underscore ("agent_", "svc_", "tenant_").
//
//	prefix + 26 Crockford characters (either case) -> the 130-bit big-endian
//	  base-32 value masked to its low 128 bits
//	prefix + 32 hex digits (either case) -> those digits, dashed
//	a dashed UUID (36 characters) -> lowercased
//	32 hex digits, no prefix -> dashed, lowercased
//	anything else (including "") -> "", false
func ToUUID(id, prefix string) (string, bool) {
	if id == "" {
		return "", false
	}

	if prefix != "" && strings.HasPrefix(id, prefix) {
		tail := id[len(prefix):]
		switch len(tail) {
		case 26:
			return decodeCrockford(tail)
		case 32:
			return decodeHex(tail)
		default:
			return "", false
		}
	}

	if len(id) == 36 {
		return decodeDashedUUID(id)
	}
	if len(id) == 32 {
		return decodeHex(id)
	}
	return "", false
}

// Canonical returns ToUUID(id, prefix) when it succeeds, else id unchanged.
func Canonical(id, prefix string) string {
	if u, ok := ToUUID(id, prefix); ok {
		return u
	}
	return id
}

func decodeCrockford(s string) (string, bool) {
	v := new(big.Int)
	for _, c := range strings.ToUpper(s) {
		idx := strings.IndexRune(crockford, c)
		if idx < 0 {
			return "", false
		}
		v.Lsh(v, 5)
		v.Or(v, big.NewInt(int64(idx)))
	}

	mask := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1))
	v.And(v, mask)

	h := v.Text(16)
	if len(h) < 32 {
		h = strings.Repeat("0", 32-len(h)) + h
	}
	return dash(h), true
}

func decodeHex(s string) (string, bool) {
	if !isHex(s) {
		return "", false
	}
	return dash(strings.ToLower(s)), true
}

func decodeDashedUUID(s string) (string, bool) {
	if s[8] != '-' || s[13] != '-' || s[18] != '-' || s[23] != '-' {
		return "", false
	}
	h := s[:8] + s[9:13] + s[14:18] + s[19:23] + s[24:]
	if len(h) != 32 || !isHex(h) {
		return "", false
	}
	return dash(strings.ToLower(h)), true
}

func dash(h string) string {
	return h[:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}

func isHex(s string) bool {
	for _, c := range s {
		switch {
		case c >= '0' && c <= '9':
		case c >= 'a' && c <= 'f':
		case c >= 'A' && c <= 'F':
		default:
			return false
		}
	}
	return true
}
