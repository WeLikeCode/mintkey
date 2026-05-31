package googleserviceaccount

import (
	"encoding/json"
	"testing"
)

func TestParseStoredBlob_HappyPath(t *testing.T) {
	keyFile := KeyFile{
		Type:         "service_account",
		ProjectID:    "my-project",
		PrivateKeyID: "key123",
		PrivateKey:   "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
		ClientEmail:  "sa@my-project.iam.gserviceaccount.com",
		TokenURI:     "https://oauth2.googleapis.com/token",
	}
	keyBytes, _ := json.Marshal(keyFile)
	blob, _ := json.Marshal(map[string]interface{}{
		"json_key": json.RawMessage(keyBytes),
		"scope":    "https://www.googleapis.com/auth/cloud-platform",
	})

	kf, scope, err := ParseStoredBlob(blob)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if kf.ClientEmail != keyFile.ClientEmail {
		t.Errorf("ClientEmail: got %q, want %q", kf.ClientEmail, keyFile.ClientEmail)
	}
	if kf.TokenURI != keyFile.TokenURI {
		t.Errorf("TokenURI: got %q, want %q", kf.TokenURI, keyFile.TokenURI)
	}
	if scope != "https://www.googleapis.com/auth/cloud-platform" {
		t.Errorf("scope: got %q", scope)
	}
}

func TestParseStoredBlob_MissingScope(t *testing.T) {
	keyFile := KeyFile{
		ClientEmail: "sa@proj.iam.gserviceaccount.com",
		TokenURI:    "https://oauth2.googleapis.com/token",
		PrivateKey:  "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
	}
	keyBytes, _ := json.Marshal(keyFile)
	blob, _ := json.Marshal(map[string]interface{}{
		"json_key": json.RawMessage(keyBytes),
		// scope intentionally omitted
	})
	_, _, err := ParseStoredBlob(blob)
	if err == nil {
		t.Fatal("expected error for missing scope, got nil")
	}
}

func TestParseStoredBlob_MissingJSONKey(t *testing.T) {
	blob, _ := json.Marshal(map[string]interface{}{
		"scope": "https://www.googleapis.com/auth/cloud-platform",
	})
	_, _, err := ParseStoredBlob(blob)
	if err == nil {
		t.Fatal("expected error for missing json_key, got nil")
	}
}

func TestParseStoredBlob_InvalidOuterJSON(t *testing.T) {
	_, _, err := ParseStoredBlob([]byte("not json"))
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

func TestParseStoredBlob_InvalidInnerJSON(t *testing.T) {
	blob, _ := json.Marshal(map[string]interface{}{
		"json_key": "not json at all",
		"scope":    "some-scope",
	})
	_, _, err := ParseStoredBlob(blob)
	if err == nil {
		t.Fatal("expected error for invalid inner JSON, got nil")
	}
}
