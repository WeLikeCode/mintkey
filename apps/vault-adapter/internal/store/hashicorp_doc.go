// hashicorp_doc.go — pure path and document marshal/unmarshal helpers for the
// HashiCorp Vault KV v2 backend. No Vault client required; these functions are
// unit-testable in isolation.
package store

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
)

// dataPath returns the KV v2 data path for a single credential version doc.
// Layout: <prefix>/<tenantID>/<serviceID>/v<ver>
func dataPath(prefix, tenantID, serviceID string, ver uint32) string {
	return fmt.Sprintf("%s/%s/%s/v%d", prefix, tenantID, serviceID, ver)
}

// indexPath returns the KV v2 data path for the version index doc.
// Layout: <prefix>/<tenantID>/<serviceID>/_index
func indexPath(prefix, tenantID, serviceID string) string {
	return fmt.Sprintf("%s/%s/%s/_index", prefix, tenantID, serviceID)
}

// versionIndex is the in-memory representation of the _index doc stored in KV v2.
type versionIndex struct {
	Current  uint32   `json:"current"`
	Max      uint32   `json:"max"`
	Versions []uint32 `json:"versions"`
}

// marshalVersionDoc encodes a CredentialRecord into the flat JSON map written to
// KV v2. WrappedDEK and EncPayload are base64-std-encoded strings.
func marshalVersionDoc(rec CredentialRecord) (map[string]any, error) {
	m := map[string]any{
		"credential_id":  rec.CredentialID,
		"tenant_id":      rec.TenantID,
		"service_id":     rec.ServiceID,
		"key_version":    rec.KeyVersion,
		"auth_scheme":    rec.AuthScheme,
		"wrapped_dek":    base64.StdEncoding.EncodeToString(rec.WrappedDEK),
		"enc_payload":    base64.StdEncoding.EncodeToString(rec.EncPayload),
		"is_current":     rec.IsCurrent,
		"is_revoked":     rec.IsRevoked,
		"created_at":     rec.CreatedAt,
		"target_url":     rec.TargetURL,
		"header_name":    rec.HeaderName,
		"query_param":    rec.QueryParam,
		"target_address": rec.TargetAddress,
		"ssh_user":       rec.SSHUser,
	}
	return m, nil
}

// unmarshalVersionDoc decodes a KV v2 data map into a CredentialRecord.
// WrappedDEK and EncPayload are decoded from base64-std strings.
func unmarshalVersionDoc(m map[string]any) (CredentialRecord, error) {
	var rec CredentialRecord
	var err error

	rec.CredentialID, err = stringField(m, "credential_id")
	if err != nil {
		return rec, err
	}
	rec.TenantID, err = stringField(m, "tenant_id")
	if err != nil {
		return rec, err
	}
	rec.ServiceID, err = stringField(m, "service_id")
	if err != nil {
		return rec, err
	}
	rec.KeyVersion, err = uint32Field(m, "key_version")
	if err != nil {
		return rec, err
	}
	rec.AuthScheme, err = int32Field(m, "auth_scheme")
	if err != nil {
		return rec, err
	}
	rec.WrappedDEK, err = b64Field(m, "wrapped_dek")
	if err != nil {
		return rec, err
	}
	rec.EncPayload, err = b64Field(m, "enc_payload")
	if err != nil {
		return rec, err
	}
	rec.IsCurrent, err = boolField(m, "is_current")
	if err != nil {
		return rec, err
	}
	rec.IsRevoked, err = boolField(m, "is_revoked")
	if err != nil {
		return rec, err
	}
	rec.CreatedAt, err = int64Field(m, "created_at")
	if err != nil {
		return rec, err
	}
	rec.TargetURL, err = stringField(m, "target_url")
	if err != nil {
		return rec, err
	}
	rec.HeaderName, err = stringField(m, "header_name")
	if err != nil {
		return rec, err
	}
	rec.QueryParam, err = stringField(m, "query_param")
	if err != nil {
		return rec, err
	}
	rec.TargetAddress, err = stringField(m, "target_address")
	if err != nil {
		return rec, err
	}
	rec.SSHUser, err = stringField(m, "ssh_user")
	if err != nil {
		return rec, err
	}

	return rec, nil
}

// marshalIndex encodes a versionIndex into the flat JSON map written to KV v2.
func marshalIndex(idx versionIndex) map[string]any {
	versions := make([]any, len(idx.Versions))
	for i, v := range idx.Versions {
		versions[i] = v
	}
	return map[string]any{
		"current":  idx.Current,
		"max":      idx.Max,
		"versions": versions,
	}
}

// unmarshalIndex decodes a KV v2 data map into a versionIndex.
func unmarshalIndex(m map[string]any) (versionIndex, error) {
	var idx versionIndex
	var err error

	idx.Current, err = uint32Field(m, "current")
	if err != nil {
		return idx, err
	}
	idx.Max, err = uint32Field(m, "max")
	if err != nil {
		return idx, err
	}

	raw, ok := m["versions"]
	if !ok {
		return idx, fmt.Errorf("unmarshalIndex: missing field versions")
	}
	// The KV v2 API returns JSON numbers as json.Number or float64 depending
	// on how the map was produced. Handle both []any (from KV API) and
	// []uint32 (from round-trip via marshalIndex).
	switch v := raw.(type) {
	case []any:
		idx.Versions = make([]uint32, len(v))
		for i, elem := range v {
			n, err := toUint32(elem)
			if err != nil {
				return idx, fmt.Errorf("unmarshalIndex: versions[%d]: %w", i, err)
			}
			idx.Versions[i] = n
		}
	default:
		return idx, fmt.Errorf("unmarshalIndex: unexpected type for versions: %T", raw)
	}

	return idx, nil
}

// clampLimit enforces the 1–200 range for ListVersions, defaulting to 50 when
// the caller passes 0 or a value exceeding 200.
func clampLimit(limit uint32) uint32 {
	if limit == 0 || limit > 200 {
		return 50
	}
	return limit
}

// ---- field extraction helpers ----

func stringField(m map[string]any, key string) (string, error) {
	v, ok := m[key]
	if !ok {
		return "", nil // absent optional field → zero value
	}
	if v == nil {
		return "", nil
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("field %q: expected string, got %T", key, v)
	}
	return s, nil
}

func boolField(m map[string]any, key string) (bool, error) {
	v, ok := m[key]
	if !ok {
		return false, nil
	}
	b, ok := v.(bool)
	if !ok {
		return false, fmt.Errorf("field %q: expected bool, got %T", key, v)
	}
	return b, nil
}

func int64Field(m map[string]any, key string) (int64, error) {
	v, ok := m[key]
	if !ok {
		return 0, nil
	}
	return toInt64(v)
}

func uint32Field(m map[string]any, key string) (uint32, error) {
	v, ok := m[key]
	if !ok {
		return 0, nil
	}
	n, err := toUint32(v)
	if err != nil {
		return 0, fmt.Errorf("field %q: %w", key, err)
	}
	return n, nil
}

func int32Field(m map[string]any, key string) (int32, error) {
	v, ok := m[key]
	if !ok {
		return 0, nil
	}
	n, err := toInt64(v)
	if err != nil {
		return 0, fmt.Errorf("field %q: %w", key, err)
	}
	return int32(n), nil
}

func b64Field(m map[string]any, key string) ([]byte, error) {
	s, err := stringField(m, key)
	if err != nil {
		return nil, err
	}
	if s == "" {
		return nil, nil
	}
	b, err := base64.StdEncoding.DecodeString(s)
	if err != nil {
		return nil, fmt.Errorf("field %q: base64 decode: %w", key, err)
	}
	return b, nil
}

// toUint32 converts a value coming from a JSON-decoded map to uint32.
// json.Unmarshal produces float64 for numbers; the vault API may also give
// json.Number.
func toUint32(v any) (uint32, error) {
	switch n := v.(type) {
	case float64:
		return uint32(n), nil
	case json.Number:
		i, err := n.Int64()
		if err != nil {
			return 0, err
		}
		return uint32(i), nil
	case uint32:
		return n, nil
	case int32:
		return uint32(n), nil
	case int:
		return uint32(n), nil
	case int64:
		return uint32(n), nil
	default:
		return 0, fmt.Errorf("expected number, got %T", v)
	}
}

func toInt64(v any) (int64, error) {
	switch n := v.(type) {
	case float64:
		return int64(n), nil
	case json.Number:
		return n.Int64()
	case int64:
		return n, nil
	case int32:
		return int64(n), nil
	case int:
		return int64(n), nil
	default:
		return 0, fmt.Errorf("expected number, got %T", v)
	}
}
