package server

import (
	"context"
	"fmt"
	"net"
	"reflect"
	"sort"
	"testing"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/types/known/emptypb"
)

const methodScopesBufSize = 1024 * 1024

type grpcServerBuilder interface {
	buildGRPCServer(svc *VaultService) *grpc.Server
}

func allVaultMethods() []string {
	return []string{
		vaultv1.VaultAdapter_GetCredential_FullMethodName,
		vaultv1.VaultAdapter_PutCredential_FullMethodName,
		vaultv1.VaultAdapter_RevokeCredential_FullMethodName,
		vaultv1.VaultAdapter_ListVersions_FullMethodName,
		vaultv1.VaultAdapter_ValidateServiceIdentity_FullMethodName,
		vaultv1.AgentSecretsVault_PutAgentSecret_FullMethodName,
		vaultv1.AgentSecretsVault_GetAgentSecret_FullMethodName,
		vaultv1.AgentSecretsVault_DeleteAgentSecret_FullMethodName,
		"/mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint",
		"/mintkey.vault.v1.SSHVaultAdapter/GetHostKeyFingerprint",
		"/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint",
	}
}

func newMethodScopesService(t *testing.T) (*VaultService, func()) {
	t.Helper()
	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}
	st, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}
	return NewVaultService(kek, st), func() { _ = st.Close() }
}

func newMethodScopesVault(t *testing.T) (*VaultServer, *VaultService, func()) {
	t.Helper()
	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}
	st, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}
	return New(kek), NewVaultService(kek, st), func() { _ = st.Close() }
}

func buildMethodScopesServer(t *testing.T, s *VaultServer, svc *VaultService) *grpc.Server {
	t.Helper()
	builder, ok := interface{}(s).(grpcServerBuilder)
	if !ok {
		t.Fatalf("%T does not implement grpcServerBuilder", s)
	}
	return builder.buildGRPCServer(svc)
}

func serveMethodScopesServer(t *testing.T, srv *grpc.Server) (*grpc.ClientConn, func()) {
	t.Helper()
	lis := bufconn.Listen(methodScopesBufSize)
	go func() { _ = srv.Serve(lis) }()
	conn, err := grpc.NewClient(
		"passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}
	return conn, func() {
		_ = conn.Close()
		srv.Stop()
	}
}

func registerMethodScopesIdentity(t *testing.T, svc *VaultService, id string, token []byte, scopes []string) {
	t.Helper()
	if err := svc.RegisterServiceIdentity(id, token, scopes); err != nil {
		t.Fatalf("RegisterServiceIdentity(%s): %v", id, err)
	}
}

func incomingMetadata(ctx context.Context, identity, token string) context.Context {
	return metadata.NewIncomingContext(ctx, metadata.Pairs(
		"x-mintkey-service-identity", identity,
		"x-mintkey-service-token", token,
	))
}

func outgoingMetadata(ctx context.Context, identity, token string) context.Context {
	return metadata.NewOutgoingContext(ctx, metadata.Pairs(
		"x-mintkey-service-identity", identity,
		"x-mintkey-service-token", token,
	))
}

func callUnaryInterceptor(t *testing.T, interceptor grpc.UnaryServerInterceptor, ctx context.Context, method string) (interface{}, error, bool) {
	t.Helper()
	called := false
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		called = true
		return "handler-result", nil
	}
	resp, err := interceptor(ctx, nil, &grpc.UnaryServerInfo{FullMethod: method}, handler)
	return resp, err, called
}

func requirePermissionDenied(t *testing.T, label string, err error) *status.Status {
	t.Helper()
	if err == nil {
		t.Fatalf("%s: expected PERMISSION_DENIED, got nil", label)
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("%s: expected a gRPC status error, got %T: %v", label, err, err)
	}
	if st.Code() != codes.PermissionDenied {
		t.Fatalf("%s: expected PERMISSION_DENIED, got %v: %s", label, st.Code(), st.Message())
	}
	return st
}

func scopesOtherThanAnyIdentity() []string {
	seen := make(map[string]bool)
	var scopes []string
	for _, scope := range methodScopes {
		if scope == "*" || seen[scope] {
			continue
		}
		seen[scope] = true
		scopes = append(scopes, scope)
	}
	sort.Strings(scopes)
	return scopes
}

func TestScopeInterceptor_NoIdentityRefusedOnEveryListedMethod_C_c547eb9c(t *testing.T) {
	svc, cleanup := newMethodScopesService(t)
	defer cleanup()

	token := []byte("all-scopes-token-for-no-identity-test")
	registerMethodScopesIdentity(t, svc, "svcid_all_scopes", token, scopesOtherThanAnyIdentity())
	interceptor := scopeInterceptor(svc)

	for _, method := range allVaultMethods() {
		_, err, called := callUnaryInterceptor(t, interceptor, context.Background(), method)
		if called {
			t.Errorf("%s with no metadata: handler was called", method)
		}
		requirePermissionDenied(t, method+" with no metadata", err)

		ctx := incomingMetadata(context.Background(), "svcid_all_scopes", "")
		_, err, called = callUnaryInterceptor(t, interceptor, ctx, method)
		if called {
			t.Errorf("%s with an empty token: handler was called", method)
		}
		requirePermissionDenied(t, method+" with an empty token", err)
	}
}

func TestScopeInterceptor_WrongTokenRefusedOnEveryListedMethod_C_e4e95bdb(t *testing.T) {
	svc, cleanup := newMethodScopesService(t)
	defer cleanup()

	token := []byte("correct-token-for-wrong-token-test")
	registerMethodScopesIdentity(t, svc, "svcid_wrong_token", token, scopesOtherThanAnyIdentity())
	interceptor := scopeInterceptor(svc)

	for _, method := range allVaultMethods() {
		ctx := incomingMetadata(context.Background(), "svcid_wrong_token", "not-the-identity-token")
		_, err, called := callUnaryInterceptor(t, interceptor, ctx, method)
		if called {
			t.Errorf("%s with a wrong token: handler was called", method)
		}
		requirePermissionDenied(t, method+" with a wrong token", err)
	}
}

func TestScopeInterceptor_UnlistedMethodRefused_C_377bc9e7(t *testing.T) {
	svc, cleanup := newMethodScopesService(t)
	defer cleanup()

	token := []byte("all-scopes-token-for-unlisted-test")
	registerMethodScopesIdentity(t, svc, "svcid_all_scopes", token, scopesOtherThanAnyIdentity())
	interceptor := scopeInterceptor(svc)

	method := "/mintkey.vault.v1.VaultAdapter/NotAMethod"
	ctx := incomingMetadata(context.Background(), "svcid_all_scopes", string(token))
	_, err, called := callUnaryInterceptor(t, interceptor, ctx, method)
	if called {
		t.Fatalf("%s: handler was called", method)
	}
	st := requirePermissionDenied(t, method, err)
	want := "method not allowed: " + method
	if st.Message() != want {
		t.Fatalf("%s: message = %q, want %q", method, st.Message(), want)
	}
}

func TestMethodTable_NotWrittenByRegistration_C_56f4739c(t *testing.T) {
	before := make(map[string]string, len(methodScopes))
	for method, scope := range methodScopes {
		before[method] = scope
	}

	svc, cleanup := newMethodScopesService(t)
	defer cleanup()

	srv := grpc.NewServer()
	RegisterAgentSecretsVaultServer(srv, svc, newFakeAgentSecretStore())
	RegisterSSHVaultServer(srv, svc, &fakeSSHStore{
		agents:   map[string]*store.AgentSSHRecord{},
		hostKeys: map[string]string{},
	})

	if len(methodScopes) != 11 {
		t.Fatalf("methodScopes has %d keys after registration, want 11", len(methodScopes))
	}
	if !reflect.DeepEqual(before, methodScopes) {
		t.Fatalf("methodScopes changed during registration:\nbefore: %v\nafter:  %v", before, methodScopes)
	}
}

func TestScopeInterceptor_HealthMethodsNeedNoIdentity_C_ac51d472_C_377bc9e7(t *testing.T) {
	svc, cleanup := newMethodScopesService(t)
	defer cleanup()

	interceptor := scopeInterceptor(svc)
	for _, method := range []string{
		grpc_health_v1.Health_Check_FullMethodName,
		grpc_health_v1.Health_List_FullMethodName,
	} {
		resp, err, called := callUnaryInterceptor(t, interceptor, context.Background(), method)
		if err != nil {
			t.Fatalf("%s without identity: %v", method, err)
		}
		if !called {
			t.Errorf("%s without identity: handler was not called", method)
		}
		if resp != "handler-result" {
			t.Errorf("%s without identity: result = %v, want handler-result", method, resp)
		}
	}

	method := "/mintkey.vault.v1.VaultAdapter/NotAMethod"
	_, err, called := callUnaryInterceptor(t, interceptor, context.Background(), method)
	if called {
		t.Fatalf("%s: handler was called", method)
	}
	st := requirePermissionDenied(t, method, err)
	want := "method not allowed: " + method
	if st.Message() != want {
		t.Fatalf("%s: message = %q, want %q", method, st.Message(), want)
	}
}

func TestListVersions_RequiresIdentity_C_2d4f1ec1(t *testing.T) {
	srv, svc, cleanup := newMethodScopesVault(t)
	defer cleanup()

	grpcSrv := buildMethodScopesServer(t, srv, svc)
	conn, stop := serveMethodScopesServer(t, grpcSrv)
	defer stop()
	client := vaultv1.NewVaultAdapterClient(conn)

	req := &vaultv1.ListVersionsRequest{
		TenantId:  "tenant_list_versions_auth",
		ServiceId: "service_list_versions_auth",
	}
	_, err := client.ListVersions(context.Background(), req)
	requirePermissionDenied(t, "ListVersions without identity", err)

	token := []byte("vault-read-token-for-listversions")
	registerMethodScopesIdentity(t, svc, "svcid_list_versions_reader", token, []string{"vault.read"})

	ctx := outgoingMetadata(context.Background(), "svcid_list_versions_reader", string(token))
	resp, err := client.ListVersions(ctx, req)
	if err != nil {
		t.Fatalf("ListVersions as a vault.read identity: %v", err)
	}
	if resp == nil {
		t.Fatal("ListVersions as a vault.read identity: nil response")
	}
}

func TestValidateServiceIdentity_RequiresIdentityButNoScope_C_08b38088(t *testing.T) {
	srv, svc, cleanup := newMethodScopesVault(t)
	defer cleanup()

	grpcSrv := buildMethodScopesServer(t, srv, svc)
	conn, stop := serveMethodScopesServer(t, grpcSrv)
	defer stop()
	client := vaultv1.NewVaultAdapterClient(conn)

	_, err := client.ValidateServiceIdentity(context.Background(), &vaultv1.ValidateServiceIdentityRequest{})
	requirePermissionDenied(t, "ValidateServiceIdentity without identity", err)

	token := []byte("no-scope-token-for-validate-service-identity")
	registerMethodScopesIdentity(t, svc, "svcid_no_scope", token, []string{})

	ctx := outgoingMetadata(context.Background(), "svcid_no_scope", string(token))
	resp, err := client.ValidateServiceIdentity(ctx, &vaultv1.ValidateServiceIdentityRequest{})
	if err != nil {
		t.Fatalf("ValidateServiceIdentity as a no-scope identity: %v", err)
	}
	if !resp.GetOk() {
		t.Fatal("ValidateServiceIdentity as a no-scope identity: ok = false, want true")
	}
}

func TestMethodTable_ScopePerMethod_C_8c1bdc49(t *testing.T) {
	want := map[string]string{
		vaultv1.VaultAdapter_GetCredential_FullMethodName:           "vault.read",
		vaultv1.VaultAdapter_PutCredential_FullMethodName:           "vault.put",
		vaultv1.VaultAdapter_RevokeCredential_FullMethodName:        "vault.put",
		vaultv1.VaultAdapter_ListVersions_FullMethodName:            "vault.read",
		vaultv1.VaultAdapter_ValidateServiceIdentity_FullMethodName: "*",
		vaultv1.AgentSecretsVault_PutAgentSecret_FullMethodName:     "vault.secret.put",
		vaultv1.AgentSecretsVault_GetAgentSecret_FullMethodName:     "vault.secret.read",
		vaultv1.AgentSecretsVault_DeleteAgentSecret_FullMethodName:  "vault.secret.delete",
		"/mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint":   "vault.read",
		"/mintkey.vault.v1.SSHVaultAdapter/GetHostKeyFingerprint":   "vault.read",
		"/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint": "vault.hostkey.put",
	}

	if len(methodScopes) != 11 {
		t.Errorf("methodScopes has %d keys, want 11", len(methodScopes))
	}
	for method, scope := range want {
		got, ok := methodScopes[method]
		if !ok {
			t.Errorf("methodScopes misses %s", method)
			continue
		}
		if got != scope {
			t.Errorf("methodScopes[%s] = %q, want %q", method, got, scope)
		}
	}
	for method := range methodScopes {
		if _, ok := want[method]; !ok {
			t.Errorf("methodScopes has unexpected method %s", method)
		}
	}
}

func TestScopeInterceptor_ReadOnlyIdentityCannotWrite_C_78d436a5(t *testing.T) {
	svc, cleanup := newMethodScopesService(t)
	defer cleanup()

	token := []byte("read-only-token-for-write-test")
	registerMethodScopesIdentity(t, svc, "svcid_read_only", token, []string{"vault.read"})
	interceptor := scopeInterceptor(svc)
	ctx := incomingMetadata(context.Background(), "svcid_read_only", string(token))

	cases := []struct {
		method string
		scope  string
	}{
		{vaultv1.VaultAdapter_PutCredential_FullMethodName, "vault.put"},
		{vaultv1.VaultAdapter_RevokeCredential_FullMethodName, "vault.put"},
		{"/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint", "vault.hostkey.put"},
		{vaultv1.AgentSecretsVault_PutAgentSecret_FullMethodName, "vault.secret.put"},
	}
	for _, tc := range cases {
		_, err, called := callUnaryInterceptor(t, interceptor, ctx, tc.method)
		if called {
			t.Errorf("%s with a read-only identity: handler was called", tc.method)
		}
		st := requirePermissionDenied(t, tc.method+" with a read-only identity", err)
		want := fmt.Sprintf("caller lacks required scope %q", tc.scope)
		if st.Message() != want {
			t.Errorf("%s: message = %q, want %q", tc.method, st.Message(), want)
		}
	}
}

func TestScopeInterceptor_FullIdentityServedEverywhere_C_70816534(t *testing.T) {
	svc, cleanup := newMethodScopesService(t)
	defer cleanup()

	scopes := scopesOtherThanAnyIdentity()
	want := []string{
		"vault.hostkey.put",
		"vault.put",
		"vault.read",
		"vault.secret.delete",
		"vault.secret.put",
		"vault.secret.read",
	}
	if !reflect.DeepEqual(scopes, want) {
		t.Fatalf("methodScopes scopes other than anyIdentity are %v, want %v", scopes, want)
	}

	token := []byte("every-scope-token-for-full-identity-test")
	registerMethodScopesIdentity(t, svc, "svcid_every_scope", token, scopes)
	interceptor := scopeInterceptor(svc)
	ctx := incomingMetadata(context.Background(), "svcid_every_scope", string(token))

	for method := range methodScopes {
		_, err, called := callUnaryInterceptor(t, interceptor, ctx, method)
		if err != nil {
			t.Errorf("%s with every scope: %v", method, err)
		}
		if !called {
			t.Errorf("%s with every scope: handler was not called", method)
		}
	}
}

func TestMethodTable_CoversEveryServedMethod_C_8bf69f2c(t *testing.T) {
	srv, svc, cleanup := newMethodScopesVault(t)
	defer cleanup()
	srv = srv.WithSSHStore(&fakeSSHStore{
		agents:   map[string]*store.AgentSSHRecord{},
		hostKeys: map[string]string{},
	}).WithAgentSecretStore(newFakeAgentSecretStore())

	grpcSrv := buildMethodScopesServer(t, srv, svc)
	info := grpcSrv.GetServiceInfo()

	for _, name := range []string{
		"mintkey.vault.v1.VaultAdapter",
		"mintkey.vault.v1.AgentSecretsVault",
		"mintkey.vault.v1.SSHVaultAdapter",
		"grpc.health.v1.Health",
	} {
		if _, ok := info[name]; !ok {
			t.Errorf("served services miss %s", name)
		}
	}

	open := map[string]bool{
		grpc_health_v1.Health_Check_FullMethodName: true,
		grpc_health_v1.Health_List_FullMethodName:  true,
	}
	servedUnary := make(map[string]bool)
	for name, service := range info {
		for _, method := range service.Methods {
			full := "/" + name + "/" + method.Name
			if method.IsClientStream || method.IsServerStream {
				if full != grpc_health_v1.Health_Watch_FullMethodName {
					t.Errorf("served streaming method %s, want only %s", full, grpc_health_v1.Health_Watch_FullMethodName)
				}
				continue
			}
			servedUnary[full] = true
			_, listed := methodScopes[full]
			_, isOpen := open[full]
			if listed && isOpen {
				t.Errorf("%s is both in methodScopes and an open health method", full)
			}
			if !listed && !isOpen {
				t.Errorf("%s is neither in methodScopes nor an open health method", full)
			}
		}
	}

	for method := range methodScopes {
		if !servedUnary[method] {
			t.Errorf("methodScopes lists %s but the server does not serve it", method)
		}
	}
}

func TestBuiltServer_OnlyHealthWatchStreams_C_6484c16c(t *testing.T) {
	srv, svc, cleanup := newMethodScopesVault(t)
	defer cleanup()

	grpcSrv := buildMethodScopesServer(t, srv, svc)

	echoRan := false
	echoDesc := grpc.StreamDesc{
		StreamName: "Echo",
		Handler: func(srv interface{}, stream grpc.ServerStream) error {
			echoRan = true
			return nil
		},
		ServerStreams: true,
	}
	grpcSrv.RegisterService(&grpc.ServiceDesc{
		ServiceName: "mintkey.test.v1.Streams",
		HandlerType: (*interface{})(nil),
		Methods:     []grpc.MethodDesc{},
		Streams:     []grpc.StreamDesc{echoDesc},
	}, struct{}{})

	conn, stop := serveMethodScopesServer(t, grpcSrv)
	defer stop()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	watch, err := grpc_health_v1.NewHealthClient(conn).Watch(ctx, &grpc_health_v1.HealthCheckRequest{})
	if err != nil {
		t.Fatalf("Health.Watch: %v", err)
	}
	healthResp, err := watch.Recv()
	if err != nil {
		t.Fatalf("Health.Watch Recv: %v", err)
	}
	if healthResp.GetStatus() != grpc_health_v1.HealthCheckResponse_SERVING {
		t.Errorf("Health.Watch status = %v, want SERVING", healthResp.GetStatus())
	}

	stream, err := conn.NewStream(ctx, &grpc.StreamDesc{
		StreamName:    "Echo",
		ServerStreams: true,
	}, "/mintkey.test.v1.Streams/Echo")
	if err == nil {
		err = stream.RecvMsg(new(emptypb.Empty))
	}
	if err == nil {
		t.Fatal("Streams/Echo: expected PERMISSION_DENIED, got nil")
	}
	st, ok := status.FromError(err)
	if !ok || st.Code() != codes.PermissionDenied {
		t.Fatalf("Streams/Echo: expected PERMISSION_DENIED, got %v", err)
	}
	want := "method not allowed: /mintkey.test.v1.Streams/Echo"
	if st.Message() != want {
		t.Errorf("Streams/Echo: message = %q, want %q", st.Message(), want)
	}
	if echoRan {
		t.Error("Streams/Echo: handler ran")
	}
}
