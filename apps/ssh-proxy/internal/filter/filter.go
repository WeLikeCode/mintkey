// Package filter implements command filtering for SSH sessions.
package filter

import (
	"errors"
	"regexp"
	"strings"
)

// Mode represents the filtering mode.
type Mode string

const (
	ModeAllowlist Mode = "allowlist"
	ModeDenylist  Mode = "denylist"
)

// Filter filters commands based on allowlist or denylist patterns.
type Filter struct {
	mode     Mode
	patterns []*regexp.Regexp
}

// NewFilter creates a new command filter.
func NewFilter(mode Mode, patterns []string) (*Filter, error) {
	if mode != ModeAllowlist && mode != ModeDenylist {
		return nil, errors.New("invalid filter mode: must be 'allowlist' or 'denylist'")
	}

	compiled := make([]*regexp.Regexp, 0, len(patterns))
	for _, pattern := range patterns {
		re, err := regexp.Compile(pattern)
		if err != nil {
			return nil, err
		}
		compiled = append(compiled, re)
	}

	return &Filter{
		mode:     mode,
		patterns: compiled,
	}, nil
}

// IsAllowed checks if a command is allowed by the filter.
func (f *Filter) IsAllowed(command string) bool {
	if len(f.patterns) == 0 {
		// No patterns: allowlist denies all, denylist allows all
		return f.mode == ModeDenylist
	}

	// Check if command matches any pattern
	matched := false
	for _, pattern := range f.patterns {
		if pattern.MatchString(command) {
			matched = true
			break
		}
	}

	// Allowlist: allow if matched
	// Denylist: allow if NOT matched
	if f.mode == ModeAllowlist {
		return matched
	}
	return !matched
}

// Check checks if a command is allowed and returns an error if not.
func (f *Filter) Check(command string) error {
	if !f.IsAllowed(command) {
		return &CommandBlockedError{
			Command: command,
			Mode:    f.mode,
		}
	}
	return nil
}

// CommandBlockedError indicates a command was blocked by the filter.
type CommandBlockedError struct {
	Command string
	Mode    Mode
}

func (e *CommandBlockedError) Error() string {
	return "command blocked by filter"
}

// ParseCommand extracts the command name from a command string.
func ParseCommand(command string) string {
	// Trim whitespace
	command = strings.TrimSpace(command)

	// Split by whitespace
	parts := strings.Fields(command)
	if len(parts) == 0 {
		return ""
	}

	// Return the first part (command name)
	return parts[0]
}

// ParseCommandWithArgs extracts the command name and arguments.
func ParseCommandWithArgs(command string) (string, []string) {
	// Trim whitespace
	command = strings.TrimSpace(command)

	// Split by whitespace
	parts := strings.Fields(command)
	if len(parts) == 0 {
		return "", nil
	}

	// Return command name and arguments
	return parts[0], parts[1:]
}
