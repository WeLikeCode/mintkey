// Package googleserviceaccount handles Google service account credential
// exchange for the Vault Adapter.  It parses the encrypted blob, signs a
// short-lived RS256 JWT assertion, and exchanges it at the Google token
// endpoint for an OAuth2 access token.
//
// Source: feature spec §4.4 (google_service_account auth scheme).
package googleserviceaccount

import (
	"encoding/json"
	"fmt"
)

// KeyFile represents the Google service account JSON key file format.
// See https://cloud.google.com/iam/docs/creating-managing-service-account-keys
type KeyFile struct {
	Type        string `json:"type"`
	ProjectID   string `json:"project_id"`
	PrivateKeyID string `json:"private_key_id"`
	PrivateKey  string `json:"private_key"`
	ClientEmail string `json:"client_email"`
	TokenURI    string `json:"token_uri"`
}

// StoredBlob is the outer structure stored (encrypted) in the Vault for a
// google_service_account credential.  JSONKey is the raw Google JSON key file
// bytes; Scope is the OAuth2 scope string to request.
type StoredBlob struct {
	JSONKey json.RawMessage `json:"json_key"`
	Scope   string          `json:"scope"`
}

// ParseStoredBlob decodes the two-layer JSON structure:
//
//  1. Outer blob  → StoredBlob (extracts JSONKey bytes and Scope string).
//  2. JSONKey     → KeyFile (extracts the Google service account fields).
//
// Returns the parsed KeyFile, the scope string, and any parse error.
func ParseStoredBlob(raw []byte) (*KeyFile, string, error) {
	var blob StoredBlob
	if err := json.Unmarshal(raw, &blob); err != nil {
		return nil, "", fmt.Errorf("googleserviceaccount: unmarshal stored blob: %w", err)
	}
	if len(blob.JSONKey) == 0 {
		return nil, "", fmt.Errorf("googleserviceaccount: stored blob missing json_key field")
	}
	if blob.Scope == "" {
		return nil, "", fmt.Errorf("googleserviceaccount: stored blob missing scope field")
	}

	var kf KeyFile
	if err := json.Unmarshal(blob.JSONKey, &kf); err != nil {
		return nil, "", fmt.Errorf("googleserviceaccount: unmarshal json_key: %w", err)
	}
	if kf.ClientEmail == "" {
		return nil, "", fmt.Errorf("googleserviceaccount: json_key missing client_email")
	}
	if kf.TokenURI == "" {
		return nil, "", fmt.Errorf("googleserviceaccount: json_key missing token_uri")
	}
	if kf.PrivateKey == "" {
		return nil, "", fmt.Errorf("googleserviceaccount: json_key missing private_key")
	}

	return &kf, blob.Scope, nil
}
