package vault

import (
	"context"
	"net"
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// mockVaultServer is an in-process gRPC server that implements VaultAdapterServer.
type mockVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	validateErr     error
	getCredResp     *vaultv1.GetCredentialResponse
	getCredErr      error
}

func (m *mockVaultServer) ValidateServiceIdentity(ctx context.Context, req *vaultv1.ValidateServiceIdentityRequest) (*vaultv1.ValidateServiceIdentityResponse, error) {
	if m.validateErr != nil {
		return nil, m.validateErr
	}
	return &vaultv1.ValidateServiceIdentityResponse{Ok: true}, nil
}

func (m *mockVaultServer) GetCredential(ctx context.Context, req *vaultv1.GetCredentialRequest) (*vaultv1.GetCredentialResponse, error) {
	if m.getCredErr != nil {
		return nil, m.getCredErr
	}
	if m.getCredResp != nil {
		return m.getCredResp, nil
	}
	return &vaultv1.GetCredentialResponse{
		Value:             []byte(`{"username":"user@example.com","password":"secret"}`),
		AuthScheme:        vaultv1.AuthScheme(14), // EMAIL_PASSWORD
		ReturnedKeyVersion: 1,
		AuthSchemeName:    "email_password",
	}, nil
}

// startMockServer starts an in-process gRPC server and returns a client connected to it.
func startMockServer(t *testing.T, mock *mockVaultServer) *Client {
	t.Helper()

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}

	srv := grpc.NewServer()
	vaultv1.RegisterVaultAdapterServer(srv, mock)

	go func() {
		if err := srv.Serve(lis); err != nil && err != grpc.ErrServerStopped {
			// ignore — test cleanup
		}
	}()
	t.Cleanup(srv.GracefulStop)

	addr := lis.Addr().String()

	// Build a Client pointing at the in-process server.
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}
	t.Cleanup(func() { conn.Close() })

	// Return a client with the mock server's address.
	c, err := NewClient(addr, "identity_test", "token_test")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	return c
}

func TestNewClient_EmptyAddress(t *testing.T) {
	_, err := NewClient("", "id", "tok")
	if err == nil {
		t.Error("NewClient should fail with empty address")
	}
}

func TestValidateServiceIdentity_Success(t *testing.T) {
	mock := &mockVaultServer{}
	c := startMockServer(t, mock)

	err := c.ValidateServiceIdentity(context.Background())
	if err != nil {
		t.Errorf("ValidateServiceIdentity: %v", err)
	}
}

func TestGetCredential_Success(t *testing.T) {
	mock := &mockVaultServer{}
	c := startMockServer(t, mock)

	cred, err := c.GetCredential(context.Background(), "tenant_01", "svc_01", AuthSchemeEmailPassword)
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}
	if len(cred.Value) == 0 {
		t.Error("expected non-empty Value")
	}
	if cred.AuthScheme != AuthSchemeEmailPassword {
		t.Errorf("AuthScheme = %d, want %d", cred.AuthScheme, AuthSchemeEmailPassword)
	}
	if cred.AuthSchemeName != "email_password" {
		t.Errorf("AuthSchemeName = %q", cred.AuthSchemeName)
	}
}

func TestAuthSchemeConstants(t *testing.T) {
	if AuthSchemeEmailPassword != 14 {
		t.Errorf("AuthSchemeEmailPassword = %d, want 14", AuthSchemeEmailPassword)
	}
	if AuthSchemeEmailOAuth2 != 15 {
		t.Errorf("AuthSchemeEmailOAuth2 = %d, want 15", AuthSchemeEmailOAuth2)
	}
	if AuthSchemeEmailAppPassword != 16 {
		t.Errorf("AuthSchemeEmailAppPassword = %d, want 16", AuthSchemeEmailAppPassword)
	}
}
