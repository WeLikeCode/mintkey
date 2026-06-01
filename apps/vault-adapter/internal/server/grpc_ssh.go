// grpc_ssh.go — SSH-proxy-specific gRPC handlers for the vault-adapter.
//
// This file registers the SSHVaultAdapter service — a separate gRPC service
// that lives alongside VaultAdapter on the same port. It exposes three RPCs:
//
//	/mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint
//	/mintkey.vault.v1.SSHVaultAdapter/GetHostKeyFingerprint
//	/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint
//
// Messages are JSON-encoded structs (defined in sshvault/messages.go) carried
// inside standard gRPC length-prefixed frames. The codec is selected per-call
// by both sides via grpc.ForceCodec(sshvault.JSONCodec{}).
//
// Auth: every call must supply x-mintkey-service-identity and
// x-mintkey-service-token metadata. The required scope is "vault.read" for
// the two read RPCs and "vault.put" for StoreHostKeyFingerprint.
//
// Source: ADR-0021; chunk C7.
package server

import (
	"context"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/sshvault"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// sshVaultServiceName is the fully-qualified gRPC service name.
const sshVaultServiceName = "mintkey.vault.v1.SSHVaultAdapter"

// sshVaultServer implements the three SSH vault RPCs.
type sshVaultServer struct {
	svc   *VaultService
	store store.SSHStore
}

// RegisterSSHVaultServer registers the SSHVaultAdapter service on grpcSrv.
// It must be called after the VaultAdapter service is registered.
// sshStore must be a *store.PostgresStore or a test double.
func RegisterSSHVaultServer(grpcSrv *grpc.Server, svc *VaultService, sshStore store.SSHStore) {
	s := &sshVaultServer{svc: svc, store: sshStore}
	grpcSrv.RegisterService(&sshVaultServiceDesc, s)
}

// sshVaultServiceDesc is the hand-written gRPC ServiceDesc (no protoc required).
var sshVaultServiceDesc = grpc.ServiceDesc{
	ServiceName: sshVaultServiceName,
	HandlerType: (*interface{})(nil), // unused for manual dispatch
	Methods: []grpc.MethodDesc{
		{
			MethodName: "GetAgentByFingerprint",
			Handler:    _SSHVault_GetAgentByFingerprint_Handler,
		},
		{
			MethodName: "GetHostKeyFingerprint",
			Handler:    _SSHVault_GetHostKeyFingerprint_Handler,
		},
		{
			MethodName: "StoreHostKeyFingerprint",
			Handler:    _SSHVault_StoreHostKeyFingerprint_Handler,
		},
	},
	Streams: []grpc.StreamDesc{},
}

// --------------------------------------------------------------------------
// gRPC handler functions — called by the gRPC framework via ServiceDesc.
// Each handler:
//   1. Validates scope via the VaultService identity store.
//   2. Decodes the JSON-encoded request bytes.
//   3. Calls the appropriate store method.
//   4. Returns a JSON-encoded response or a gRPC status error.
// --------------------------------------------------------------------------

func _SSHVault_GetAgentByFingerprint_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(sshvault.GetAgentByFingerprintRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	h := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(*sshVaultServer).GetAgentByFingerprint(ctx, req.(*sshvault.GetAgentByFingerprintRequest))
	}
	if interceptor == nil {
		return h(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/" + sshVaultServiceName + "/GetAgentByFingerprint",
	}
	return interceptor(ctx, in, info, h)
}

func _SSHVault_GetHostKeyFingerprint_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(sshvault.HostKeyFingerprintRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	h := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(*sshVaultServer).GetHostKeyFingerprint(ctx, req.(*sshvault.HostKeyFingerprintRequest))
	}
	if interceptor == nil {
		return h(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/" + sshVaultServiceName + "/GetHostKeyFingerprint",
	}
	return interceptor(ctx, in, info, h)
}

func _SSHVault_StoreHostKeyFingerprint_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(sshvault.StoreHostKeyFingerprintRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	h := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(*sshVaultServer).StoreHostKeyFingerprint(ctx, req.(*sshvault.StoreHostKeyFingerprintRequest))
	}
	if interceptor == nil {
		return h(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/" + sshVaultServiceName + "/StoreHostKeyFingerprint",
	}
	return interceptor(ctx, in, info, h)
}

// --------------------------------------------------------------------------
// Method implementations
// --------------------------------------------------------------------------

// GetAgentByFingerprint looks up the agent whose ssh_pubkey fingerprint matches
// the one in the request. Requires scope "vault.read".
func (s *sshVaultServer) GetAgentByFingerprint(ctx context.Context, req *sshvault.GetAgentByFingerprintRequest) (*sshvault.GetAgentByFingerprintResponse, error) {
	if err := s.requireScope(ctx, "vault.read"); err != nil {
		return nil, err
	}
	if req.Fingerprint == "" {
		return nil, status.Errorf(codes.InvalidArgument, "fingerprint is required")
	}

	// GetAgentBySSHPubKey requires a tenantID for RLS. The SSH proxy does not
	// know the tenantID at this stage — it's determined by the fingerprint
	// lookup itself.  We scan all tenants: set app.platform_admin_view=on
	// so that RLS allows the cross-tenant scan, then filter by fingerprint.
	// The query itself sets a per-connection GUC; we must pass a synthetic
	// tenantID that enables the platform_admin_view bypass path.
	//
	// Implementation: use the superuser DSN path by passing a sentinel
	// tenantID of "00000000-0000-0000-0000-000000000000" and relying on
	// the platform_admin_view GUC that the Postgres store can set.
	//
	// For the current implementation we delegate to a global scan method
	// on the postgres store.
	rec, err := s.store.GetAgentBySSHPubKeyGlobal(ctx, req.Fingerprint)
	if err != nil {
		if store.IsNotFound(err) {
			return nil, status.Errorf(codes.NotFound, "no agent found for fingerprint")
		}
		return nil, status.Errorf(codes.Internal, "GetAgentByFingerprint: %v", err)
	}

	return &sshvault.GetAgentByFingerprintResponse{
		AgentID:   rec.ID,
		TenantID:  rec.TenantID,
		Name:      rec.Name,
		SSHPubKey: rec.SSHPubKey,
		Status:    rec.Status,
	}, nil
}

// GetHostKeyFingerprint retrieves the stored SSH host key fingerprint for a
// (tenant, service) pair. Requires scope "vault.read".
func (s *sshVaultServer) GetHostKeyFingerprint(ctx context.Context, req *sshvault.HostKeyFingerprintRequest) (*sshvault.HostKeyFingerprintResponse, error) {
	if err := s.requireScope(ctx, "vault.read"); err != nil {
		return nil, err
	}
	if req.TenantID == "" || req.ServiceID == "" {
		return nil, status.Errorf(codes.InvalidArgument, "tenant_id and service_id are required")
	}

	fp, err := s.store.GetHostKeyFingerprint(ctx, req.TenantID, req.ServiceID)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "GetHostKeyFingerprint: %v", err)
	}

	return &sshvault.HostKeyFingerprintResponse{Fingerprint: fp}, nil
}

// StoreHostKeyFingerprint persists a TOFU host-key fingerprint.
// Requires scope "vault.put".
func (s *sshVaultServer) StoreHostKeyFingerprint(ctx context.Context, req *sshvault.StoreHostKeyFingerprintRequest) (*sshvault.StoreHostKeyFingerprintResponse, error) {
	if err := s.requireScope(ctx, "vault.put"); err != nil {
		return nil, err
	}
	if req.TenantID == "" || req.ServiceID == "" || req.Fingerprint == "" {
		return nil, status.Errorf(codes.InvalidArgument, "tenant_id, service_id, and fingerprint are required")
	}

	if err := s.store.StoreHostKeyFingerprint(ctx, req.TenantID, req.ServiceID, req.Fingerprint); err != nil {
		return nil, status.Errorf(codes.Internal, "StoreHostKeyFingerprint: %v", err)
	}

	return &sshvault.StoreHostKeyFingerprintResponse{}, nil
}

// --------------------------------------------------------------------------
// Auth helper
// --------------------------------------------------------------------------

// requireScope validates the caller's service token and checks the required scope.
func (s *sshVaultServer) requireScope(ctx context.Context, required string) error {
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return status.Errorf(codes.PermissionDenied, "missing metadata")
	}
	tokens := md.Get("x-mintkey-service-token")
	if len(tokens) == 0 || tokens[0] == "" {
		return status.Errorf(codes.PermissionDenied, "missing service token")
	}
	scopes, valid := s.svc.ValidateServiceIdentity(ctx, extractIdentityID(md), []byte(tokens[0]))
	if !valid {
		return status.Errorf(codes.PermissionDenied, "invalid service token")
	}
	if !hasScope(scopes, required) {
		return status.Errorf(codes.PermissionDenied, "caller lacks required scope %q", required)
	}
	return nil
}

// Ensure sshVaultServer satisfies the compiler (no interface defined — manual dispatch).
var _ = (*sshVaultServer)(nil)
