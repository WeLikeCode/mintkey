// Package server provides the gRPC server stub for the Vault Adapter.
//
// Full RPC implementations are added in T-1.3.x (credential storage).
// Source: design §8 gRPC service; vault.proto; T-1.0.4.
package server

import (
	"context"
	"fmt"
	"net"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
)

// VaultServer is the gRPC server stub. Methods are wired in later tasks.
type VaultServer struct {
	kek []byte
}

// New creates a VaultServer with the loaded KEK in memory.
// The KEK is held here for the lifetime of the process — never logged, never returned.
func New(kek []byte) *VaultServer {
	return &VaultServer{kek: kek}
}

// ListenAndServe starts the gRPC server on the given port.
func (s *VaultServer) ListenAndServe(ctx context.Context, port int) error {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		return fmt.Errorf("vault-adapter: listen :%d: %w", port, err)
	}

	grpcSrv := grpc.NewServer()

	healthSvc := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcSrv, healthSvc)
	healthSvc.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)

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
