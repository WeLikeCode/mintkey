// Package server provides the gRPC server for the Vault Adapter.
//
// Source: design §8 gRPC service; vault.proto; T-1.0.4.
package server

import (
	"context"
	"fmt"
	"net"

	vaultv1 "github.com/mintkey/mintkey/internal/vault/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
)

// VaultServer is the gRPC server. It holds the KEK and VaultService.
type VaultServer struct {
	kek []byte
}

// New creates a VaultServer with the loaded KEK in memory.
// The KEK is held here for the lifetime of the process — never logged, never returned.
func New(kek []byte) *VaultServer {
	return &VaultServer{kek: kek}
}

// grpcVaultServer implements vaultv1.VaultAdapterServer by delegating to VaultService.
type grpcVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	svc *VaultService
}

// GetCredential translates the proto request to VaultService args and returns the result.
func (g *grpcVaultServer) GetCredential(ctx context.Context, req *vaultv1.GetCredentialRequest) (*vaultv1.GetCredentialResponse, error) {
	result, err := g.svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:      req.GetTenantId(),
		ServiceID:     req.GetServiceId(),
		KeyVersion:    req.GetKeyVersion(),
		CallerActorID: req.GetCallerActorId(),
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "GetCredential: %v", err)
	}
	return &vaultv1.GetCredentialResponse{
		AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
		Value:              result.Plaintext,
		ReturnedKeyVersion: result.ReturnedKeyVersion,
		CurrentKeyVersion:  result.CurrentKeyVersion,
	}, nil
}

// PutCredential is not yet implemented.
func (g *grpcVaultServer) PutCredential(_ context.Context, _ *vaultv1.PutCredentialRequest) (*vaultv1.PutCredentialResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented")
}

// RevokeCredential is not yet implemented.
func (g *grpcVaultServer) RevokeCredential(_ context.Context, _ *vaultv1.RevokeCredentialRequest) (*vaultv1.RevokeCredentialResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented")
}

// ListVersions is not yet implemented.
func (g *grpcVaultServer) ListVersions(_ context.Context, _ *vaultv1.ListVersionsRequest) (*vaultv1.ListVersionsResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented")
}

// ValidateServiceIdentity is not yet implemented.
func (g *grpcVaultServer) ValidateServiceIdentity(_ context.Context, _ *vaultv1.ValidateServiceIdentityRequest) (*vaultv1.ValidateServiceIdentityResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented")
}

// ListenAndServe starts the gRPC server on the given port, registering the VaultAdapter RPC.
func (s *VaultServer) ListenAndServe(ctx context.Context, port int, svc *VaultService) error {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		return fmt.Errorf("vault-adapter: listen :%d: %w", port, err)
	}

	grpcSrv := grpc.NewServer()

	healthSvc := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcSrv, healthSvc)
	healthSvc.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)

	vaultv1.RegisterVaultAdapterServer(grpcSrv, &grpcVaultServer{svc: svc})

	errCh := make(chan error, 1)
	go func() {
		errCh <- grpcSrv.Serve(lis)
	}()

	select {
	case <-ctx.Done():
		grpcSrv.GracefulStop()
		return nil
	case err := <-errCh:
		return err
	}
}
