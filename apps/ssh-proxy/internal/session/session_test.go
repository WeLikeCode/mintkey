package session

import (
	"testing"
	"time"
)

func TestNewManager(t *testing.T) {
	mgr := NewManager(5)

	if mgr == nil {
		t.Fatal("NewManager() returned nil")
	}

	if mgr.maxPerAgent != 5 {
		t.Errorf("maxPerAgent = %d, want 5", mgr.maxPerAgent)
	}

	if mgr.sessions == nil {
		t.Error("sessions map not initialized")
	}

	if mgr.agentSessions == nil {
		t.Error("agentSessions map not initialized")
	}
}

func TestManager_ActiveCount(t *testing.T) {
	mgr := NewManager(5)

	if count := mgr.ActiveCount(); count != 0 {
		t.Errorf("ActiveCount() = %d, want 0", count)
	}
}

func TestSessionContext_Serialize(t *testing.T) {
	ctx := &SessionContext{
		TenantID:   "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
		AgentID:    "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
		ServiceID:  "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
		AuthMethod: "jwt",
	}

	serialized := ctx.Serialize()
	expected := "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9|agent_01HX5J9F8V8H8V0CG3F2Y5J6A1|svc_01HX5J9F8V8H8V0CG3F2Y5J6S1|jwt"

	if serialized != expected {
		t.Errorf("Serialize() = %q, want %q", serialized, expected)
	}
}

func TestParseSessionContext(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    *SessionContext
		wantErr bool
	}{
		{
			name:  "valid context",
			input: "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9|agent_01HX5J9F8V8H8V0CG3F2Y5J6A1|svc_01HX5J9F8V8H8V0CG3F2Y5J6S1|jwt",
			want: &SessionContext{
				TenantID:   "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
				AgentID:    "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
				ServiceID:  "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
				AuthMethod: "jwt",
			},
			wantErr: false,
		},
		{
			name:    "invalid format - missing fields",
			input:   "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9|agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
			wantErr: true,
		},
		{
			name:    "invalid format - empty string",
			input:   "",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseSessionContext(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseSessionContext() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if got.TenantID != tt.want.TenantID {
					t.Errorf("TenantID = %q, want %q", got.TenantID, tt.want.TenantID)
				}
				if got.AgentID != tt.want.AgentID {
					t.Errorf("AgentID = %q, want %q", got.AgentID, tt.want.AgentID)
				}
				if got.ServiceID != tt.want.ServiceID {
					t.Errorf("ServiceID = %q, want %q", got.ServiceID, tt.want.ServiceID)
				}
				if got.AuthMethod != tt.want.AuthMethod {
					t.Errorf("AuthMethod = %q, want %q", got.AuthMethod, tt.want.AuthMethod)
				}
			}
		})
	}
}

func TestSession_Terminate(t *testing.T) {
	sess := &Session{
		ID:        "session_01HX5J9F8V8H8V0CG3F2Y5J6X1",
		StartTime: time.Now(),
	}

	// Initially not terminated
	if sess.terminated {
		t.Error("session should not be terminated initially")
	}

	// Terminate
	sess.Terminate()

	if !sess.terminated {
		t.Error("session should be terminated after Terminate()")
	}

	// Terminate again (should be idempotent)
	sess.Terminate()

	if !sess.terminated {
		t.Error("session should still be terminated after second Terminate()")
	}
}

func TestSession_BytesTracking(t *testing.T) {
	sess := &Session{
		ID:        "session_01HX5J9F8V8H8V0CG3F2Y5J6X2",
		StartTime: time.Now(),
	}

	// Initially zero
	if sent := sess.BytesSent.Load(); sent != 0 {
		t.Errorf("BytesSent = %d, want 0", sent)
	}
	if recv := sess.BytesRecv.Load(); recv != 0 {
		t.Errorf("BytesRecv = %d, want 0", recv)
	}

	// Add bytes
	sess.BytesSent.Add(100)
	sess.BytesRecv.Add(200)

	if sent := sess.BytesSent.Load(); sent != 100 {
		t.Errorf("BytesSent = %d, want 100", sent)
	}
	if recv := sess.BytesRecv.Load(); recv != 200 {
		t.Errorf("BytesRecv = %d, want 200", recv)
	}
}
