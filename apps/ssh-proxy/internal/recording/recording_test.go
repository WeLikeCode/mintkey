package recording

import (
	"bytes"
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
	defer recorder.Close()

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

func TestRecorder_Close(t *testing.T) {
	tmpDir := t.TempDir()

	recorder, err := NewRecorder(tmpDir, "test_close", 80, 24)
	if err != nil {
		t.Fatalf("NewRecorder() error = %v", err)
	}

	// Close once
	if err := recorder.Close(); err != nil {
		t.Errorf("Close() error = %v", err)
	}

	// Close again (should be idempotent)
	if err := recorder.Close(); err != nil {
		t.Errorf("second Close() error = %v", err)
	}

	// Try to write after close
	if err := recorder.WriteOutput([]byte("test")); err == nil {
		t.Error("WriteOutput() should fail after Close()")
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

	writer.WriteOutput([]byte("line 1"))
	writer.WriteOutput([]byte("line 2"))

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
	path, err := storage.Store(nil, "test_session", data)
	if err != nil {
		t.Fatalf("Store() error = %v", err)
	}

	if path == "" {
		t.Error("Store() returned empty path")
	}

	// Test List
	paths, err := storage.List(nil)
	if err != nil {
		t.Fatalf("List() error = %v", err)
	}

	if len(paths) != 1 {
		t.Errorf("List() returned %d paths, want 1", len(paths))
	}

	// Test Retrieve
	reader, err := storage.Retrieve(nil, path)
	if err != nil {
		t.Fatalf("Retrieve() error = %v", err)
	}
	defer reader.Close()

	// Test Delete
	if err := storage.Delete(nil, path); err != nil {
		t.Errorf("Delete() error = %v", err)
	}

	// Verify deleted
	paths, err = storage.List(nil)
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
	deleted, err := storage.Cleanup(nil, 24*time.Hour)
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
