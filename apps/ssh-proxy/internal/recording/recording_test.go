package recording

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestNewRecorder(t *testing.T) {
	tmpDir := t.TempDir()

	recorder, err := NewRecorder(tmpDir, "test_session", 80, 24)
	if err != nil {
		t.Fatalf("NewRecorder() error = %v", err)
	}
	recorder.Close()

	// Verify file was created
	filename := filepath.Join(tmpDir, "test_session.cast")
	if _, err := os.Stat(filename); os.IsNotExist(err) {
		t.Error("recording file was not created")
	}

	// Read and verify header
	data, err := os.ReadFile(filename)
	if err != nil {
		t.Fatalf("failed to read recording file: %v", err)
	}

	lines := bytes.Split(data, []byte{'\n'})
	if len(lines) < 2 {
		t.Fatal("recording file has no content")
	}

	var header AsciicastHeader
	if err := json.Unmarshal(lines[0], &header); err != nil {
		t.Fatalf("failed to parse header: %v", err)
	}

	if header.Version != 2 {
		t.Errorf("header version = %d, want 2", header.Version)
	}

	if header.Width != 80 {
		t.Errorf("header width = %d, want 80", header.Width)
	}

	if header.Height != 24 {
		t.Errorf("header height = %d, want 24", header.Height)
	}
}

func TestRecorder_WriteOutput(t *testing.T) {
	tmpDir := t.TempDir()

	recorder, err := NewRecorder(tmpDir, "test_output", 80, 24)
	if err != nil {
		t.Fatalf("NewRecorder() error = %v", err)
	}

	// Write some output
	if err := recorder.WriteOutput([]byte("Hello, World!")); err != nil {
		t.Errorf("WriteOutput() error = %v", err)
	}

	recorder.Close()

	// Read and verify
	filename := filepath.Join(tmpDir, "test_output.cast")
	data, err := os.ReadFile(filename)
	if err != nil {
		t.Fatalf("failed to read recording file: %v", err)
	}

	lines := bytes.Split(data, []byte{'\n'})
	if len(lines) < 3 {
		t.Fatal("recording file missing output event")
	}

	// Parse output event
	var event []interface{}
	if err := json.Unmarshal(lines[1], &event); err != nil {
		t.Fatalf("failed to parse output event: %v", err)
	}

	if len(event) != 3 {
		t.Errorf("event has %d elements, want 3", len(event))
	}

	if event[1] != "o" {
		t.Errorf("event type = %v, want 'o'", event[1])
	}

	if event[2] != "Hello, World!" {
		t.Errorf("event data = %v, want 'Hello, World!'", event[2])
	}
}

func TestRecorder_WriteInput(t *testing.T) {
	tmpDir := t.TempDir()

	recorder, err := NewRecorder(tmpDir, "test_input", 80, 24)
	if err != nil {
		t.Fatalf("NewRecorder() error = %v", err)
	}

	// Write some input
	if err := recorder.WriteInput([]byte("ls -la")); err != nil {
		t.Errorf("WriteInput() error = %v", err)
	}

	recorder.Close()

	// Read and verify
	filename := filepath.Join(tmpDir, "test_input.cast")
	data, err := os.ReadFile(filename)
	if err != nil {
		t.Fatalf("failed to read recording file: %v", err)
	}

	lines := bytes.Split(data, []byte{'\n'})
	if len(lines) < 3 {
		t.Fatal("recording file missing input event")
	}

	// Parse input event
	var event []interface{}
	if err := json.Unmarshal(lines[1], &event); err != nil {
		t.Fatalf("failed to parse input event: %v", err)
	}

	if event[1] != "i" {
		t.Errorf("event type = %v, want 'i'", event[1])
	}

	if event[2] != "ls -la" {
		t.Errorf("event data = %v, want 'ls -la'", event[2])
	}
}

func TestRecorder_Close_Idempotent(t *testing.T) {
	tmpDir := t.TempDir()

	recorder, err := NewRecorder(tmpDir, "test_close", 80, 24)
	if err != nil {
		t.Fatalf("NewRecorder() error = %v", err)
	}

	// Close once — should return a non-empty digest
	digest, err := recorder.Close()
	if err != nil {
		t.Errorf("Close() error = %v", err)
	}
	if digest == "" {
		t.Error("Close() should return a non-empty digest")
	}

	// Close again (should be idempotent, return empty digest with nil error)
	digest2, err := recorder.Close()
	if err != nil {
		t.Errorf("second Close() error = %v", err)
	}
	if digest2 != "" {
		t.Errorf("second Close() should return empty digest, got %q", digest2)
	}

	// Try to write after close
	if err := recorder.WriteOutput([]byte("test")); err == nil {
		t.Error("WriteOutput() should fail after Close()")
	}
}

// TestRecorder_IntegrityDigest verifies that Close() returns a SHA-256 digest
// that matches sha256sum of the .cast file content.
func TestRecorder_IntegrityDigest(t *testing.T) {
	tmpDir := t.TempDir()

	recorder, err := NewRecorder(tmpDir, "test_integrity", 80, 24)
	if err != nil {
		t.Fatalf("NewRecorder() error = %v", err)
	}

	// Write some frames
	if err := recorder.WriteOutput([]byte("hello")); err != nil {
		t.Fatalf("WriteOutput: %v", err)
	}
	if err := recorder.WriteInput([]byte("world")); err != nil {
		t.Fatalf("WriteInput: %v", err)
	}
	if err := recorder.WriteOutput([]byte("more output")); err != nil {
		t.Fatalf("WriteOutput: %v", err)
	}

	digest, err := recorder.Close()
	if err != nil {
		t.Fatalf("Close() error = %v", err)
	}

	if digest == "" {
		t.Fatal("Close() returned empty digest")
	}

	// Verify digest prefix
	if len(digest) < 7 || digest[:7] != "sha256:" {
		t.Errorf("digest should start with 'sha256:', got %q", digest)
	}

	// Compare against sha256 of the file content
	castPath := filepath.Join(tmpDir, "test_integrity.cast")
	fileData, err := os.ReadFile(castPath)
	if err != nil {
		t.Fatalf("failed to read cast file: %v", err)
	}

	h := sha256.Sum256(fileData)
	expectedDigest := "sha256:" + hex.EncodeToString(h[:])

	if digest != expectedDigest {
		t.Errorf("digest mismatch:\n  got      %s\n  expected %s", digest, expectedDigest)
	}
}

// TestRecorder_SidecarFile verifies that Close() writes a sidecar .cast.sha256 file.
func TestRecorder_SidecarFile(t *testing.T) {
	tmpDir := t.TempDir()

	recorder, err := NewRecorder(tmpDir, "test_sidecar", 80, 24)
	if err != nil {
		t.Fatalf("NewRecorder() error = %v", err)
	}

	if err := recorder.WriteOutput([]byte("some output")); err != nil {
		t.Fatalf("WriteOutput: %v", err)
	}

	digest, err := recorder.Close()
	if err != nil {
		t.Fatalf("Close() error = %v", err)
	}

	sidecarPath := filepath.Join(tmpDir, "test_sidecar.cast.sha256")
	sidecarData, err := os.ReadFile(sidecarPath)
	if err != nil {
		t.Fatalf("sidecar file not created at %s: %v", sidecarPath, err)
	}

	sidecarContent := string(sidecarData)
	if len(sidecarContent) < len(digest) || sidecarContent[:len(digest)] != digest {
		t.Errorf("sidecar content does not start with digest:\n  sidecar: %q\n  digest:  %q",
			sidecarContent, digest)
	}
}

func TestAsciicastWriter(t *testing.T) {
	var buf bytes.Buffer

	writer, err := NewAsciicastWriter(&buf, 80, 24)
	if err != nil {
		t.Fatalf("NewAsciicastWriter() error = %v", err)
	}

	// Write output
	if err := writer.WriteOutput([]byte("test output")); err != nil {
		t.Errorf("WriteOutput() error = %v", err)
	}

	// Write input
	if err := writer.WriteInput([]byte("test input")); err != nil {
		t.Errorf("WriteInput() error = %v", err)
	}

	// Write resize
	if err := writer.WriteResize(120, 40); err != nil {
		t.Errorf("WriteResize() error = %v", err)
	}

	// Verify output
	lines := bytes.Split(buf.Bytes(), []byte{'\n'})
	if len(lines) < 5 {
		t.Errorf("expected at least 5 lines, got %d", len(lines))
	}
}

func TestAsciicastReader(t *testing.T) {
	// Create a test asciicast
	var buf bytes.Buffer
	writer, err := NewAsciicastWriter(&buf, 80, 24)
	if err != nil {
		t.Fatalf("NewAsciicastWriter() error = %v", err)
	}

	if err := writer.WriteOutput([]byte("line 1")); err != nil {
		t.Fatalf("WriteOutput: %v", err)
	}
	if err := writer.WriteOutput([]byte("line 2")); err != nil {
		t.Fatalf("WriteOutput: %v", err)
	}

	// Read it back
	reader, err := NewAsciicastReader(&buf)
	if err != nil {
		t.Fatalf("NewAsciicastReader() error = %v", err)
	}

	header := reader.Header()
	if header.Version != 2 {
		t.Errorf("header version = %d, want 2", header.Version)
	}

	if header.Width != 80 {
		t.Errorf("header width = %d, want 80", header.Width)
	}

	// Read events
	event1, err := reader.ReadEvent()
	if err != nil {
		t.Fatalf("ReadEvent() error = %v", err)
	}

	if event1.Type != "o" {
		t.Errorf("event1 type = %s, want 'o'", event1.Type)
	}

	event2, err := reader.ReadEvent()
	if err != nil {
		t.Fatalf("ReadEvent() error = %v", err)
	}

	if event2.Type != "o" {
		t.Errorf("event2 type = %s, want 'o'", event2.Type)
	}

	// Time should be monotonically increasing
	if event2.Time < event1.Time {
		t.Error("event times are not monotonically increasing")
	}
}

func TestLocalStorage(t *testing.T) {
	tmpDir := t.TempDir()

	storage, err := NewLocalStorage(tmpDir)
	if err != nil {
		t.Fatalf("NewLocalStorage() error = %v", err)
	}

	// Test Store
	data := bytes.NewBufferString("test recording data")
	path, err := storage.Store(context.TODO(), "test_session", data)
	if err != nil {
		t.Fatalf("Store() error = %v", err)
	}

	if path == "" {
		t.Error("Store() returned empty path")
	}

	// Test List
	paths, err := storage.List(context.TODO())
	if err != nil {
		t.Fatalf("List() error = %v", err)
	}

	if len(paths) != 1 {
		t.Errorf("List() returned %d paths, want 1", len(paths))
	}

	// Test Retrieve
	reader, err := storage.Retrieve(context.TODO(), path)
	if err != nil {
		t.Fatalf("Retrieve() error = %v", err)
	}
	defer reader.Close()

	// Test Delete
	if err := storage.Delete(context.TODO(), path); err != nil {
		t.Errorf("Delete() error = %v", err)
	}

	// Verify deleted
	paths, err = storage.List(context.TODO())
	if err != nil {
		t.Fatalf("List() after delete error = %v", err)
	}

	if len(paths) != 0 {
		t.Errorf("List() after delete returned %d paths, want 0", len(paths))
	}
}

func TestLocalStorage_Cleanup(t *testing.T) {
	tmpDir := t.TempDir()

	storage, err := NewLocalStorage(tmpDir)
	if err != nil {
		t.Fatalf("NewLocalStorage() error = %v", err)
	}

	// Create old recording
	oldPath := filepath.Join(tmpDir, "old_session.cast")
	if err := os.WriteFile(oldPath, []byte("old data"), 0644); err != nil {
		t.Fatalf("failed to create old recording: %v", err)
	}

	// Set modification time to 2 days ago
	oldTime := time.Now().Add(-48 * time.Hour)
	if err := os.Chtimes(oldPath, oldTime, oldTime); err != nil {
		t.Fatalf("failed to set modification time: %v", err)
	}

	// Create new recording
	newPath := filepath.Join(tmpDir, "new_session.cast")
	if err := os.WriteFile(newPath, []byte("new data"), 0644); err != nil {
		t.Fatalf("failed to create new recording: %v", err)
	}

	// Cleanup recordings older than 24 hours
	deleted, err := storage.Cleanup(context.TODO(), 24*time.Hour)
	if err != nil {
		t.Fatalf("Cleanup() error = %v", err)
	}

	if deleted != 1 {
		t.Errorf("Cleanup() deleted %d recordings, want 1", deleted)
	}

	// Verify old recording was deleted
	if _, err := os.Stat(oldPath); !os.IsNotExist(err) {
		t.Error("old recording was not deleted")
	}

	// Verify new recording still exists
	if _, err := os.Stat(newPath); os.IsNotExist(err) {
		t.Error("new recording was deleted")
	}
}

// TestLocalStorage_PathTraversal verifies that Retrieve and Delete reject paths
// that escape the recording directory. ADR-0021 / CodeQL go/path-injection.
func TestLocalStorage_PathTraversal(t *testing.T) {
	tmpDir := t.TempDir()

	storage, err := NewLocalStorage(tmpDir)
	if err != nil {
		t.Fatalf("NewLocalStorage() error = %v", err)
	}

	traversalPaths := []string{
		tmpDir + "/../etc/passwd",
		"/etc/passwd",
		tmpDir + "/../../secret",
	}

	for _, p := range traversalPaths {
		_, err := storage.Retrieve(context.TODO(), p)
		if err == nil {
			t.Errorf("Retrieve(%q) should have rejected path traversal, got nil error", p)
		}

		if err := storage.Delete(context.TODO(), p); err == nil {
			t.Errorf("Delete(%q) should have rejected path traversal, got nil error", p)
		}
	}
}
