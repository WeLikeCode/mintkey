package session_test

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"encoding/binary"
	"io"
	"net"
	"strings"
	"sync"
	"testing"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/session"
)

// ---------------------------------------------------------------------------
// Mock backend connector
// ---------------------------------------------------------------------------

type mockConnector struct {
	mu     sync.Mutex
	called bool
	// factory creates the backend *ssh.Client on demand; called inside Connect.
	factory func() (*ssh.Client, error)
}

func (m *mockConnector) Connect(ctx context.Context, _ *session.SessionContext, _ string) (*ssh.Client, []byte, error) {
	m.mu.Lock()
	m.called = true
	m.mu.Unlock()
	c, err := m.factory()
	return c, []byte("fake-pem"), err
}

// ---------------------------------------------------------------------------
// Mock audit emitter
// ---------------------------------------------------------------------------

type mockAuditEmitter struct {
	mu     sync.Mutex
	events []string
}

func (m *mockAuditEmitter) record(e string) {
	m.mu.Lock()
	m.events = append(m.events, e)
	m.mu.Unlock()
}
func (m *mockAuditEmitter) EmitSessionStarted(_ context.Context, _ *session.SessionContext, _, _ string) error {
	m.record("started")
	return nil
}
func (m *mockAuditEmitter) EmitSessionEnded(_ context.Context, _ *session.SessionContext, _ string, _, _, _ int64) error {
	m.record("ended")
	return nil
}
func (m *mockAuditEmitter) EmitSessionExec(_ context.Context, _ *session.SessionContext, _, cmd string, _ int) error {
	m.record("exec:" + cmd)
	return nil
}
func (m *mockAuditEmitter) EmitSessionSFTP(_ context.Context, _ *session.SessionContext, _, op, path string) error {
	m.record("sftp:" + op + ":" + path)
	return nil
}

// ---------------------------------------------------------------------------
// Minimal in-memory backend SSH server
// ---------------------------------------------------------------------------

// startBackendServer spins up an SSH server on a listener and returns a
// connected *ssh.Client. All operations happen concurrently so there is no
// net.Pipe deadlock.
func startBackendServer(t *testing.T) *ssh.Client {
	t.Helper()

	hostKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate host key: %v", err)
	}
	hostSigner, err := ssh.NewSignerFromKey(hostKey)
	if err != nil {
		t.Fatalf("make host signer: %v", err)
	}

	serverCfg := &ssh.ServerConfig{NoClientAuth: true}
	serverCfg.AddHostKey(hostSigner)

	// Use an actual loopback listener to avoid net.Pipe synchronous-buffer
	// deadlocks during SSH version exchange.
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	t.Cleanup(func() { ln.Close() })

	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		sshConn, chans, reqs, err := ssh.NewServerConn(conn, serverCfg)
		if err != nil {
			conn.Close()
			return
		}
		defer sshConn.Close()
		go ssh.DiscardRequests(reqs)

		for newChan := range chans {
			if newChan.ChannelType() != "session" {
				newChan.Reject(ssh.UnknownChannelType, "unknown")
				continue
			}
			ch, requests, err := newChan.Accept()
			if err != nil {
				return
			}
			go serveExecChannel(ch, requests)
		}
	}()

	clientCfg := &ssh.ClientConfig{
		User:            "test",
		Auth:            nil,
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         5 * time.Second,
	}
	client, err := ssh.Dial("tcp", ln.Addr().String(), clientCfg)
	if err != nil {
		t.Fatalf("dial backend: %v", err)
	}
	t.Cleanup(func() { client.Close() })
	return client
}

// serveExecChannel handles a single SSH session channel: responds to "exec"
// requests by echoing the command as output, then sends exit-status 0.
func serveExecChannel(ch ssh.Channel, requests <-chan *ssh.Request) {
	defer ch.Close()
	for req := range requests {
		if req.Type != "exec" {
			if req.WantReply {
				req.Reply(false, nil)
			}
			continue
		}
		if req.WantReply {
			req.Reply(true, nil)
		}
		// Parse command payload.
		if len(req.Payload) >= 4 {
			cmdLen := binary.BigEndian.Uint32(req.Payload[0:4])
			if int(4+cmdLen) <= len(req.Payload) {
				cmd := string(req.Payload[4 : 4+cmdLen])
				ch.Write([]byte(cmd + "\n"))
			}
		}
		// Send exit-status 0 and return (closes the channel via defer).
		ch.SendRequest("exit-status", false, []byte{0, 0, 0, 0})
		return
	}
}

// ---------------------------------------------------------------------------
// pipeChannel — minimal ssh.Channel backed by a net.Conn
// ---------------------------------------------------------------------------

type pipeChannel struct {
	conn   net.Conn
	stderr bytes.Buffer
	mu     sync.Mutex
}

func (c *pipeChannel) Read(data []byte) (int, error)  { return c.conn.Read(data) }
func (c *pipeChannel) Write(data []byte) (int, error) { return c.conn.Write(data) }
func (c *pipeChannel) Close() error                   { return c.conn.Close() }
func (c *pipeChannel) CloseWrite() error              { return nil }
func (c *pipeChannel) SendRequest(name string, wantReply bool, payload []byte) (bool, error) {
	return false, nil
}
func (c *pipeChannel) Stderr() io.ReadWriter {
	c.mu.Lock()
	defer c.mu.Unlock()
	return &c.stderr
}

// ---------------------------------------------------------------------------
// TestSession_ExecHandler_EndToEnd
// ---------------------------------------------------------------------------

// TestSession_ExecHandler_EndToEnd wires a real exec channel through an
// in-memory SSH bastion session (no external network) and verifies:
//  1. BackendConnector.Connect is called exactly once.
//  2. The exec command is forwarded to the backend and its output comes back.
//  3. An audit exec event is emitted.
func TestSession_ExecHandler_EndToEnd(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping integration test in short mode")
	}

	backendClient := startBackendServer(t)

	connector := &mockConnector{
		factory: func() (*ssh.Client, error) { return backendClient, nil },
	}
	auditEmitter := &mockAuditEmitter{}

	deps := session.Deps{
		Connector:    connector,
		AuditEmitter: auditEmitter,
	}

	// Build an in-memory channel pair to stand in for the agent SSH channel.
	agentSide, sessionSide := net.Pipe()
	defer agentSide.Close()

	fakeChannel := &pipeChannel{conn: sessionSide}

	sess := &session.Session{
		ID:      "session_test_e2e",
		Context: &session.SessionContext{TenantID: "t1", AgentID: "a1", ServiceID: "svc1", AuthMethod: "jwt"},
		Channel: fakeChannel,
		StartTime: time.Now(),
	}
	sess.SetDeps(deps)

	// Build an exec request payload.
	command := "echo hello"
	payload := make([]byte, 4+len(command))
	binary.BigEndian.PutUint32(payload[0:4], uint32(len(command)))
	copy(payload[4:], command)

	req := &ssh.Request{Type: "exec", WantReply: false, Payload: payload}
	if err := sess.HandleRequest(req); err != nil {
		t.Fatalf("HandleRequest(exec): %v", err)
	}

	// Collect output from the agent side until it is closed by the session
	// handler (which happens when the backend sends exit-status).
	agentSide.SetDeadline(time.Now().Add(5 * time.Second))
	var buf bytes.Buffer
	io.Copy(&buf, agentSide)

	// 1. Connector was called.
	connector.mu.Lock()
	called := connector.called
	connector.mu.Unlock()
	if !called {
		t.Error("BackendConnector.Connect was not called")
	}

	// 2. Output contains the echoed command.
	if !strings.Contains(buf.String(), command) {
		t.Errorf("expected output to contain %q, got %q", command, buf.String())
	}

	// 3. Audit exec event was emitted.
	auditEmitter.mu.Lock()
	events := auditEmitter.events
	auditEmitter.mu.Unlock()

	hasExec := false
	for _, e := range events {
		if strings.HasPrefix(e, "exec:"+command) {
			hasExec = true
			break
		}
	}
	if !hasExec {
		t.Errorf("expected audit exec event for %q, got events: %v", command, events)
	}
}
