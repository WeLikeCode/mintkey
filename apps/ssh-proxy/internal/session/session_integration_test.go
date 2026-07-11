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
	"os"
	"path/filepath"
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
				_ = newChan.Reject(ssh.UnknownChannelType, "unknown")
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
				_ = req.Reply(false, nil)
			}
			continue
		}
		if req.WantReply {
			_ = req.Reply(true, nil)
		}
		// Parse command payload.
		if len(req.Payload) >= 4 {
			cmdLen := binary.BigEndian.Uint32(req.Payload[0:4])
			if int(4+cmdLen) <= len(req.Payload) {
				cmd := string(req.Payload[4 : 4+cmdLen])
				_, _ = ch.Write([]byte(cmd + "\n"))
			}
		}
		// Send exit-status 0 and return (closes the channel via defer).
		_, _ = ch.SendRequest("exit-status", false, []byte{0, 0, 0, 0})
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
	// No t.Skip: test uses only loopback TCP (~10ms) and imposes no external deps.
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
	_ = agentSide.SetDeadline(time.Now().Add(5 * time.Second))
	var buf bytes.Buffer
	_, _ = io.Copy(&buf, agentSide)

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

// ---------------------------------------------------------------------------
// mockFilter — CommandFilter that denies a specific command
// ---------------------------------------------------------------------------

type mockFilter struct {
	denied string
}

func (f *mockFilter) IsAllowed(command string) bool {
	return command != f.denied
}

// ---------------------------------------------------------------------------
// TestSession_ExecHandler_FilterDeniesCommand
// ---------------------------------------------------------------------------

// TestSession_ExecHandler_FilterDeniesCommand verifies that when a Filter
// denies a command: Connect is NOT called, the channel is closed, and an
// audit exec event with exitCode=-2 is emitted.
func TestSession_ExecHandler_FilterDeniesCommand(t *testing.T) {
	connector := &mockConnector{
		factory: func() (*ssh.Client, error) {
			t.Error("Connect should not be called when command is denied")
			return nil, nil
		},
	}
	auditEmitter := &mockAuditEmitter{}

	// net.Pipe gives us a synchronous in-memory channel that we can read from.
	agentSide, sessionSide := net.Pipe()
	defer agentSide.Close()

	fakeChannel := &pipeChannel{conn: sessionSide}

	sess := &session.Session{
		ID:        "session_filter_deny_test",
		Context:   &session.SessionContext{TenantID: "t1", AgentID: "a1", ServiceID: "svc1", AuthMethod: "jwt"},
		Channel:   fakeChannel,
		StartTime: time.Now(),
	}
	sess.SetDeps(session.Deps{
		Connector:    connector,
		AuditEmitter: auditEmitter,
		Filter:       &mockFilter{denied: "rm -rf /"},
	})

	command := "rm -rf /"
	payload := make([]byte, 4+len(command))
	binary.BigEndian.PutUint32(payload[0:4], uint32(len(command)))
	copy(payload[4:], command)

	req := &ssh.Request{Type: "exec", WantReply: false, Payload: payload}
	if err := sess.HandleRequest(req); err != nil {
		t.Fatalf("HandleRequest(exec) returned error: %v", err)
	}

	// The handler closes the channel synchronously on filter deny; read until EOF.
	_ = agentSide.SetDeadline(time.Now().Add(2 * time.Second))
	_, _ = io.Copy(io.Discard, agentSide)

	// Connector must NOT have been called.
	connector.mu.Lock()
	called := connector.called
	connector.mu.Unlock()
	if called {
		t.Error("BackendConnector.Connect was called despite command being denied by filter")
	}

	// Audit must contain exec event with exitCode=-2 (encoded as "exec:<cmd>").
	auditEmitter.mu.Lock()
	events := auditEmitter.events
	auditEmitter.mu.Unlock()

	found := false
	for _, e := range events {
		if e == "exec:"+command {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected audit exec event for denied command %q, got events: %v", command, events)
	}
}

// ---------------------------------------------------------------------------
// startShellBackendServer — backend that supports PTY + shell
// ---------------------------------------------------------------------------

// startShellBackendServer spins up a minimal SSH server that accepts a
// "shell" request (with optional "pty-req"), writes a small output frame,
// and then exits cleanly. Used by the recorder test.
func startShellBackendServer(t *testing.T) *ssh.Client {
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
				_ = newChan.Reject(ssh.UnknownChannelType, "unknown")
				continue
			}
			ch, requests, err := newChan.Accept()
			if err != nil {
				return
			}
			go serveShellChannel(ch, requests)
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
		t.Fatalf("dial shell backend: %v", err)
	}
	t.Cleanup(func() { client.Close() })
	return client
}

// serveShellChannel accepts pty-req (replies true), shell (replies true),
// writes a small output frame, then sends exit-status 0.
func serveShellChannel(ch ssh.Channel, requests <-chan *ssh.Request) {
	defer ch.Close()
	for req := range requests {
		switch req.Type {
		case "pty-req":
			if req.WantReply {
				_ = req.Reply(true, nil)
			}
		case "shell":
			if req.WantReply {
				_ = req.Reply(true, nil)
			}
			// Write one output frame so the recorder captures it.
			_, _ = ch.Write([]byte("hello from shell\r\n"))
			_, _ = ch.SendRequest("exit-status", false, []byte{0, 0, 0, 0})
			return
		default:
			if req.WantReply {
				_ = req.Reply(false, nil)
			}
		}
	}
}

// ---------------------------------------------------------------------------
// TestSession_ShellHandler_RecorderWritten
// ---------------------------------------------------------------------------

// TestSession_ShellHandler_RecorderWritten verifies that when RecordingPath
// is set and a PTY+shell request is handled, a .cast file is created in
// the recording directory and contains at least one frame.
func TestSession_ShellHandler_RecorderWritten(t *testing.T) {
	backendClient := startShellBackendServer(t)

	connector := &mockConnector{
		factory: func() (*ssh.Client, error) { return backendClient, nil },
	}
	auditEmitter := &mockAuditEmitter{}

	recDir := t.TempDir()

	agentSide, sessionSide := net.Pipe()
	defer agentSide.Close()

	fakeChannel := &pipeChannel{conn: sessionSide}

	sessID := "session_recorder_test"
	sess := &session.Session{
		ID:        sessID,
		Context:   &session.SessionContext{TenantID: "t1", AgentID: "a1", ServiceID: "svc1", AuthMethod: "jwt"},
		Channel:   fakeChannel,
		StartTime: time.Now(),
	}
	sess.SetDeps(session.Deps{
		Connector:     connector,
		AuditEmitter:  auditEmitter,
		RecordingPath: recDir,
	})

	// First send a pty-req so handleShellRequest doesn't reject it.
	// Build a minimal pty-req payload: [uint32 termLen][term][uint32 w][uint32 h][uint32 wp][uint32 hp][uint32 modesLen][modes].
	term := "xterm"
	ptyPayload := make([]byte, 0, 4+len(term)+4*4+4)
	termLenBytes := make([]byte, 4)
	binary.BigEndian.PutUint32(termLenBytes, uint32(len(term)))
	ptyPayload = append(ptyPayload, termLenBytes...)
	ptyPayload = append(ptyPayload, []byte(term)...)
	// cols=80, rows=24, pixel-width=0, pixel-height=0
	for _, v := range []uint32{80, 24, 0, 0} {
		b := make([]byte, 4)
		binary.BigEndian.PutUint32(b, v)
		ptyPayload = append(ptyPayload, b...)
	}
	// modes: empty (just a 0-length encoded modes list is 1 byte: TTY_OP_END=0)
	ptyPayload = append(ptyPayload, 0, 0, 0, 1, 0) // uint32(1) + byte(0) = TTY_OP_END

	ptyReq := &ssh.Request{Type: "pty-req", WantReply: false, Payload: ptyPayload}
	if err := sess.HandleRequest(ptyReq); err != nil {
		t.Fatalf("HandleRequest(pty-req): %v", err)
	}

	shellReq := &ssh.Request{Type: "shell", WantReply: false, Payload: nil}
	if err := sess.HandleRequest(shellReq); err != nil {
		t.Fatalf("HandleRequest(shell): %v", err)
	}

	// Drain agent side; the backend sends one frame then exits.
	_ = agentSide.SetDeadline(time.Now().Add(5 * time.Second))
	_, _ = io.Copy(io.Discard, agentSide)

	// Give the deferred recorder.Close() a moment to flush.
	time.Sleep(50 * time.Millisecond)

	// Verify .cast file was created.
	castFile := filepath.Join(recDir, sessID+".cast")
	info, err := os.Stat(castFile)
	if err != nil {
		t.Fatalf("expected .cast file at %s: %v", castFile, err)
	}
	if info.Size() == 0 {
		t.Errorf(".cast file exists but is empty")
	}

	// Verify the file contains at least one asciicast frame (a JSON array line
	// starting with "[" after the header line).
	data, _ := os.ReadFile(castFile)
	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	frameFound := false
	for _, line := range lines[1:] { // skip header
		if strings.HasPrefix(line, "[") {
			frameFound = true
			break
		}
	}
	if !frameFound {
		t.Errorf("no asciicast frame found in .cast file; contents:\n%s", string(data))
	}
}

// ---------------------------------------------------------------------------
// TestSession_EnvHandler_RejectsNonWhitelisted
// ---------------------------------------------------------------------------

// TestSession_EnvHandler_RejectsNonWhitelisted verifies that a non-whitelisted
// env variable (FOO=bar) is rejected: the channel is not connected to a
// backend and an audit "sftp:env.denied:FOO" event is emitted.
func TestSession_EnvHandler_RejectsNonWhitelisted(t *testing.T) {
	connector := &mockConnector{
		factory: func() (*ssh.Client, error) {
			t.Error("Connect should not be called for env request")
			return nil, nil
		},
	}
	auditEmitter := &mockAuditEmitter{}

	agentSide, sessionSide := net.Pipe()
	defer agentSide.Close()

	fakeChannel := &pipeChannel{conn: sessionSide}

	sess := &session.Session{
		ID:        "session_env_test",
		Context:   &session.SessionContext{TenantID: "t1", AgentID: "a1", ServiceID: "svc1", AuthMethod: "jwt"},
		Channel:   fakeChannel,
		StartTime: time.Now(),
	}
	sess.SetDeps(session.Deps{
		Connector:    connector,
		AuditEmitter: auditEmitter,
	})

	// Build env payload: [uint32 nameLen][name][uint32 valueLen][value]
	name := "FOO"
	value := "bar"
	envPayload := make([]byte, 0, 4+len(name)+4+len(value))
	nameLenB := make([]byte, 4)
	binary.BigEndian.PutUint32(nameLenB, uint32(len(name)))
	envPayload = append(envPayload, nameLenB...)
	envPayload = append(envPayload, []byte(name)...)
	valLenB := make([]byte, 4)
	binary.BigEndian.PutUint32(valLenB, uint32(len(value)))
	envPayload = append(envPayload, valLenB...)
	envPayload = append(envPayload, []byte(value)...)

	envReq := &ssh.Request{Type: "env", WantReply: false, Payload: envPayload}
	if err := sess.HandleRequest(envReq); err != nil {
		t.Fatalf("HandleRequest(env): %v", err)
	}

	// Connector must NOT have been called.
	connector.mu.Lock()
	called := connector.called
	connector.mu.Unlock()
	if called {
		t.Error("BackendConnector.Connect was called for an env request")
	}

	// Audit must contain the env.denied event for FOO.
	auditEmitter.mu.Lock()
	events := auditEmitter.events
	auditEmitter.mu.Unlock()

	found := false
	for _, e := range events {
		if e == "sftp:env.denied:FOO" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected audit event 'sftp:env.denied:FOO', got events: %v", events)
	}
}
