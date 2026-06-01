package recording

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"
)

// StorageBackend defines the interface for recording storage.
type StorageBackend interface {
	// Store stores a recording and returns its path/identifier.
	Store(ctx context.Context, sessionID string, data io.Reader) (string, error)

	// Retrieve retrieves a recording by its path/identifier.
	Retrieve(ctx context.Context, path string) (io.ReadCloser, error)

	// Delete deletes a recording by its path/identifier.
	Delete(ctx context.Context, path string) error

	// List lists all recordings.
	List(ctx context.Context) ([]string, error)
}

// LocalStorage implements StorageBackend using local filesystem.
type LocalStorage struct {
	basePath string
}

// NewLocalStorage creates a new local storage backend.
func NewLocalStorage(basePath string) (*LocalStorage, error) {
	// Create base directory if it doesn't exist
	if err := os.MkdirAll(basePath, 0755); err != nil {
		return nil, fmt.Errorf("failed to create base directory: %w", err)
	}

	return &LocalStorage{
		basePath: basePath,
	}, nil
}

// Store stores a recording to the local filesystem.
func (s *LocalStorage) Store(ctx context.Context, sessionID string, data io.Reader) (string, error) {
	filename := sessionID + ".cast"
	filepath := filepath.Join(s.basePath, filename)

	file, err := os.Create(filepath)
	if err != nil {
		return "", fmt.Errorf("failed to create file: %w", err)
	}
	defer file.Close()

	if _, err := io.Copy(file, data); err != nil {
		os.Remove(filepath)
		return "", fmt.Errorf("failed to write file: %w", err)
	}

	return filepath, nil
}

// Retrieve retrieves a recording from the local filesystem.
func (s *LocalStorage) Retrieve(ctx context.Context, path string) (io.ReadCloser, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("failed to open file: %w", err)
	}

	return file, nil
}

// Delete deletes a recording from the local filesystem.
func (s *LocalStorage) Delete(ctx context.Context, path string) error {
	if err := os.Remove(path); err != nil {
		return fmt.Errorf("failed to delete file: %w", err)
	}

	return nil
}

// List lists all recordings in the local filesystem.
func (s *LocalStorage) List(ctx context.Context) ([]string, error) {
	entries, err := os.ReadDir(s.basePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read directory: %w", err)
	}

	var paths []string
	for _, entry := range entries {
		if !entry.IsDir() && filepath.Ext(entry.Name()) == ".cast" {
			paths = append(paths, filepath.Join(s.basePath, entry.Name()))
		}
	}

	return paths, nil
}

// Cleanup removes recordings older than the retention period.
func (s *LocalStorage) Cleanup(ctx context.Context, retention time.Duration) (int, error) {
	paths, err := s.List(ctx)
	if err != nil {
		return 0, err
	}

	cutoff := time.Now().Add(-retention)
	deleted := 0

	for _, path := range paths {
		info, err := os.Stat(path)
		if err != nil {
			continue
		}

		if info.ModTime().Before(cutoff) {
			if err := s.Delete(ctx, path); err == nil {
				deleted++
			}
		}
	}

	return deleted, nil
}
