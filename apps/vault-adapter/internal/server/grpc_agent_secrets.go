// grpc_agent_secrets.go — AgentSecretsVault gRPC service (ADR-0025).
//
// This file registers the AgentSecretsVault service alongside VaultAdapter
// on the same gRPC server.  It exposes three RPCs:
//
//	/mintkey.vault.v1.AgentSecretsVault/PutAgentSecret
//	/mintkey.vault.v1.AgentSecretsVault/GetAgentSecret
//	/mintkey.vault.v1.AgentSecretsVault/DeleteAgentSecret
//
// Auth: each call requires x-mintkey-service-identity and
// x-mintkey-service-token metadata.  Required scopes are:
//   - PutAgentSecret   → vault.secret.put
//   - GetAgentSecret   → vault.secret.read
//   - DeleteAgentSecret → vault.secret.delete
//
// Crypto: crypto.Seal (fresh AES-256-GCM DEK per put) and crypto.Open.
// Storage: store.AgentSecretStore (implemented by *store.PostgresStore).
// SQLite: not implemented — returns codes.Unimplemented with a clear message.
//
// Source: ADR-0025; design.md D1; vault.proto AgentSecretsVault.
package server

import (
	"context"
	"errors"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/crypto"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// agentSecretsServer implements vaultv1.AgentSecretsVaultServer.
type agentSecretsServer struct {
	vaultv1.UnimplementedAgentSecretsVaultServer
	svc         *VaultService
	secretStore store.AgentSecretStore
}

// RegisterAgentSecretsVaultServer registers the AgentSecretsVault service on
// grpcSrv.  Must be called after VaultAdapter is registered.
// secretStore must be a *store.PostgresStore or a test double implementing
// store.AgentSecretStore.
func RegisterAgentSecretsVaultServer(grpcSrv *grpc.Server, svc *VaultService, secretStore store.AgentSecretStore) {
	vaultv1.RegisterAgentSecretsVaultServer(grpcSrv, &agentSecretsServer{
		svc:         svc,
		secretStore: secretStore,
	})

	// Extend methodScopes so the existing scopeInterceptor enforces scopes on
	// the new RPCs automatically.
	methodScopes[vaultv1.AgentSecretsVault_PutAgentSecret_FullMethodName] = "vault.secret.put"
	methodScopes[vaultv1.AgentSecretsVault_GetAgentSecret_FullMethodName] = "vault.secret.read"
	methodScopes[vaultv1.AgentSecretsVault_DeleteAgentSecret_FullMethodName] = "vault.secret.delete"
}

// PutAgentSecret seals and stores (or replaces) the encrypted blob for
// (tenant_id, secret_id).  The plaintext is discarded after sealing.
func (s *agentSecretsServer) PutAgentSecret(ctx context.Context, req *vaultv1.PutAgentSecretRequest) (*vaultv1.PutAgentSecretResponse, error) {
	if req.GetTenantId() == "" || req.GetSecretId() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "tenant_id and secret_id are required")
	}
	if len(req.GetValue()) == 0 {
		return nil, status.Errorf(codes.InvalidArgument, "value must not be empty")
	}
	if len(req.GetValue()) > 64*1024 {
		return nil, status.Errorf(codes.InvalidArgument, "value exceeds 65536 byte limit")
	}

	wrappedDEK, encPayload, err := crypto.Seal(s.svc.kek, req.GetValue())
	if err != nil {
		return nil, status.Errorf(codes.Internal, "PutAgentSecret: seal: %v", err)
	}

	// key_version: use 1 for new secrets; on overwrite the MCP server bumps the
	// public-facing version counter in public.agent_secrets.  The vault layer
	// always writes a fresh DEK so every put is cryptographically independent.
	// We use the proto kek_version hint (0 = use current KEK) for the record.
	kekVersion := req.GetKekVersion()
	if kekVersion == 0 {
		kekVersion = 1 // current KEK is always version 1 in this phase
	}

	rec := store.AgentSecretRecord{
		SecretID:   req.GetSecretId(),
		TenantID:   req.GetTenantId(),
		KeyVersion: int32(kekVersion),
		WrappedDEK: wrappedDEK,
		EncPayload: encPayload,
	}

	if err := s.secretStore.PutAgentSecret(ctx, rec); err != nil {
		return nil, status.Errorf(codes.Unavailable, "PutAgentSecret: store: %v", err)
	}

	return &vaultv1.PutAgentSecretResponse{
		KekVersion: kekVersion,
		WrittenAt:  timestamppb.Now(),
	}, nil
}

// GetAgentSecret unseals and returns the plaintext for (tenant_id, secret_id).
// Returns NOT_FOUND when no blob exists (callers must not distinguish not-found
// from no-access — the MCP server enforces that at the application layer).
func (s *agentSecretsServer) GetAgentSecret(ctx context.Context, req *vaultv1.GetAgentSecretRequest) (*vaultv1.GetAgentSecretResponse, error) {
	if req.GetTenantId() == "" || req.GetSecretId() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "tenant_id and secret_id are required")
	}

	rec, err := s.secretStore.GetAgentSecret(ctx, req.GetTenantId(), req.GetSecretId())
	if err != nil {
		if errors.Is(err, store.ErrAgentSecretNotFound) {
			return nil, status.Errorf(codes.NotFound, "agent secret not found")
		}
		return nil, status.Errorf(codes.Unavailable, "GetAgentSecret: store: %v", err)
	}

	plaintext, err := crypto.Open(s.svc.kek, rec.WrappedDEK, rec.EncPayload)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "GetAgentSecret: open: %v", err)
	}

	return &vaultv1.GetAgentSecretResponse{
		Value:      plaintext,
		KekVersion: uint32(rec.KeyVersion),
	}, nil
}

// DeleteAgentSecret removes the encrypted blob for (tenant_id, secret_id).
// Idempotent: returns OK when the row is already absent.
func (s *agentSecretsServer) DeleteAgentSecret(ctx context.Context, req *vaultv1.DeleteAgentSecretRequest) (*vaultv1.DeleteAgentSecretResponse, error) {
	if req.GetTenantId() == "" || req.GetSecretId() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "tenant_id and secret_id are required")
	}

	// GetAgentSecret to check existence (for the deleted bool in response).
	// We do a get first so we can report whether a row was actually deleted.
	_, getErr := s.secretStore.GetAgentSecret(ctx, req.GetTenantId(), req.GetSecretId())
	existed := getErr == nil

	if err := s.secretStore.DeleteAgentSecret(ctx, req.GetTenantId(), req.GetSecretId()); err != nil {
		return nil, status.Errorf(codes.Unavailable, "DeleteAgentSecret: store: %v", err)
	}

	return &vaultv1.DeleteAgentSecretResponse{Deleted: existed}, nil
}
