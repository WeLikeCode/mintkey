package main

import (
	"log/slog"
	"testing"
)

// TestParseLogLevel verifies LOG_LEVEL parsing maps each accepted value to the
// correct slog.Level, is case-insensitive and whitespace-tolerant, and falls
// back to Info for empty or unknown input.
func TestParseLogLevel(t *testing.T) {
	tests := []struct {
		in   string
		want slog.Level
	}{
		{"debug", slog.LevelDebug},
		{"DEBUG", slog.LevelDebug},
		{"  Debug ", slog.LevelDebug},
		{"info", slog.LevelInfo},
		{"INFO", slog.LevelInfo},
		{"warn", slog.LevelWarn},
		{"WARN", slog.LevelWarn},
		{"warning", slog.LevelWarn},
		{"error", slog.LevelError},
		{"ERROR", slog.LevelError},
		{"", slog.LevelInfo},          // default on empty
		{"verbose", slog.LevelInfo},   // default on unknown
		{"trace", slog.LevelInfo},     // default on unknown
	}

	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			if got := parseLogLevel(tt.in); got != tt.want {
				t.Errorf("parseLogLevel(%q) = %v, want %v", tt.in, got, tt.want)
			}
		})
	}
}
