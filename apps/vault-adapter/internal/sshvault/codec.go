// Package sshvault — JSON codec registration for the SSHVaultAdapter service.
//
// gRPC uses "proto" as its default codec. Registering a JSON codec named
// "json" and selecting it per-call (via grpc.ForceCodec / grpc.CallContentSubtype)
// lets us pass our plain-Go structs over gRPC without generating protobuf code.
//
// The ssh-proxy client selects this codec via grpc.ForceCodec(JSONCodec{}).
// The vault-adapter server registers the codec via init() so that incoming
// requests with Content-Type: application/grpc+json are routed correctly.
//
// Source: ADR-0021; chunk C7.
package sshvault

import (
	"encoding/json"
	"fmt"

	"google.golang.org/grpc/encoding"
)

func init() {
	// Register the JSON codec so both client and server can use it by name.
	// This must run before any gRPC calls; the init() function guarantees this.
	encoding.RegisterCodec(JSONCodec{})
}

// JSONCodec is a gRPC codec that marshals/unmarshals messages as JSON.
// Register it once at startup via grpc.RegisterCodec (server) and select it
// per-call via grpc.ForceCodec (client).
type JSONCodec struct{}

// Name returns the codec name; must match the grpc Content-Type subtype.
func (JSONCodec) Name() string { return "json" }

// Marshal encodes v as JSON.
func (JSONCodec) Marshal(v any) ([]byte, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("sshvault json codec: marshal: %w", err)
	}
	return b, nil
}

// Unmarshal decodes JSON bytes into v.
func (JSONCodec) Unmarshal(data []byte, v any) error {
	if err := json.Unmarshal(data, v); err != nil {
		return fmt.Errorf("sshvault json codec: unmarshal: %w", err)
	}
	return nil
}
