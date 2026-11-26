// Package store — egress-scope tests for the HashiCorp version document.
//
// Source: proxy-public-egress spec, requirement "The vault adapter stores and
// returns the scope"; design D1.
package store

import (
	"reflect"
	"testing"
)

// egressScopeField returns the EgressScope field of a CredentialRecord, failing
// the test when the record has no such string field.
func egressScopeField(t *testing.T, rec *CredentialRecord) reflect.Value {
	t.Helper()
	v := reflect.ValueOf(rec).Elem().FieldByName("EgressScope")
	if !v.IsValid() || v.Kind() != reflect.String {
		t.Fatalf("CredentialRecord has no string EgressScope field")
	}
	return v
}

// TestHashicorpDocEgressScope: marshalVersionDoc writes the scope under
// egress_scope and unmarshalVersionDoc reads it, defaulting a missing key to any.
func TestHashicorpDocEgressScope_C_adac8186(t *testing.T) {
	t.Run("C-adac8186", func(t *testing.T) {
		rec := CredentialRecord{
			CredentialID: "cred_egress_scope_doc",
			TenantID:     "t1",
			ServiceID:    "s1",
			KeyVersion:   1,
			AuthScheme:   1,
			WrappedDEK:   []byte{1, 2, 3},
			EncPayload:   []byte{4, 5, 6},
		}
		egressScopeField(t, &rec).SetString("public")

		doc, err := marshalVersionDoc(rec)
		if err != nil {
			t.Fatalf("marshalVersionDoc: %v", err)
		}

		raw, ok := doc["egress_scope"]
		if !ok {
			t.Fatalf("marshalVersionDoc did not write egress_scope: %v", doc)
		}
		if got, ok := raw.(string); !ok || got != "public" {
			t.Errorf("egress_scope = %v, want %q", raw, "public")
		}

		decoded, err := unmarshalVersionDoc(doc)
		if err != nil {
			t.Fatalf("unmarshalVersionDoc: %v", err)
		}
		if got := egressScopeField(t, &decoded).String(); got != "public" {
			t.Errorf("decoded scope = %q, want %q", got, "public")
		}

		delete(doc, "egress_scope")
		decoded, err = unmarshalVersionDoc(doc)
		if err != nil {
			t.Fatalf("unmarshalVersionDoc(no key): %v", err)
		}
		if got := egressScopeField(t, &decoded).String(); got != "any" {
			t.Errorf("decoded scope without key = %q, want %q", got, "any")
		}
	})
}
