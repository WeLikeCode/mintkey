package otelinit

// emailAllowedAttrs is the set of email-proxy span attribute names (ADR-0024)
// that are explicitly safe to export and must NOT be redacted by the suffix
// filter.
//
// These attributes carry structural/reference data only — no credential
// material, no message body, no recipient addresses.
// Maintained in lockstep with docs/architecture/contracts/otel/span-attributes.md.
var emailAllowedAttrs = map[string]struct{}{
	"email.service_id":       {},
	"email.message_id":       {},
	"email.mailbox":          {},
	"email.provider":         {},
	"email.attachment_count": {},
	"email.body_size_bytes":  {},
}

// IsEmailAllowed reports whether the given span attribute name is on the
// email-proxy allowlist and must bypass the suffix-based redaction filter.
// Called from isSensitive so that e.g. "email.service_id" is NOT redacted
// even though the generic suffix rules might otherwise match in future.
func IsEmailAllowed(key string) bool {
	_, ok := emailAllowedAttrs[key]
	return ok
}
