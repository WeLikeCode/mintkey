package filter

import (
	"strings"
	"unicode"
)

// Parser parses shell commands with proper handling of quotes and escapes.
type Parser struct{}

// NewParser creates a new command parser.
func NewParser() *Parser {
	return &Parser{}
}

// Parse parses a command string into tokens, respecting quotes and escapes.
func (p *Parser) Parse(command string) ([]string, error) {
	var tokens []string
	var current strings.Builder
	inSingleQuote := false
	inDoubleQuote := false
	escaped := false

	for i := 0; i < len(command); i++ {
		ch := command[i]

		if escaped {
			current.WriteByte(ch)
			escaped = false
			continue
		}

		if ch == '\\' && !inSingleQuote {
			escaped = true
			continue
		}

		if ch == '\'' && !inDoubleQuote {
			inSingleQuote = !inSingleQuote
			continue
		}

		if ch == '"' && !inSingleQuote {
			inDoubleQuote = !inDoubleQuote
			continue
		}

		if unicode.IsSpace(rune(ch)) && !inSingleQuote && !inDoubleQuote {
			if current.Len() > 0 {
				tokens = append(tokens, current.String())
				current.Reset()
			}
			continue
		}

		current.WriteByte(ch)
	}

	// Add final token
	if current.Len() > 0 {
		tokens = append(tokens, current.String())
	}

	return tokens, nil
}

// ExtractCommand extracts the command name from a parsed command.
func (p *Parser) ExtractCommand(tokens []string) string {
	if len(tokens) == 0 {
		return ""
	}

	// Skip environment variable assignments (VAR=value)
	for _, token := range tokens {
		if !strings.Contains(token, "=") {
			return token
		}
	}

	return ""
}

// HasPipe checks if the command contains a pipe.
func (p *Parser) HasPipe(command string) bool {
	return strings.Contains(command, "|")
}

// HasRedirect checks if the command contains redirection.
func (p *Parser) HasRedirect(command string) bool {
	return strings.Contains(command, ">") || strings.Contains(command, "<")
}

// HasBackground checks if the command runs in the background.
func (p *Parser) HasBackground(command string) bool {
	return strings.HasSuffix(strings.TrimSpace(command), "&")
}

// SplitPipeline splits a command pipeline into individual commands.
func (p *Parser) SplitPipeline(command string) []string {
	// Simple split by pipe (doesn't handle pipes inside quotes)
	parts := strings.Split(command, "|")
	result := make([]string, 0, len(parts))

	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			result = append(result, trimmed)
		}
	}

	return result
}

// IsShellBuiltin checks if a command is a shell builtin.
func IsShellBuiltin(command string) bool {
	builtins := map[string]bool{
		"cd":       true,
		"echo":     true,
		"exit":     true,
		"export":   true,
		"source":   true,
		"alias":    true,
		"unalias":  true,
		"set":      true,
		"unset":    true,
		"readonly": true,
		"shift":    true,
		"test":     true,
		"[":        true,
		"exec":     true,
		"eval":     true,
		"trap":     true,
		"wait":     true,
		"kill":     true,
		"jobs":     true,
		"fg":       true,
		"bg":       true,
		"type":     true,
		"hash":     true,
		"ulimit":   true,
		"umask":    true,
		"pwd":      true,
		"read":     true,
		"return":   true,
		"break":    true,
		"continue": true,
	}

	return builtins[command]
}

// IsDangerousCommand checks if a command is potentially dangerous.
func IsDangerousCommand(command string) bool {
	dangerous := map[string]bool{
		"rm":       true,
		"rmdir":    true,
		"mkfs":     true,
		"dd":       true,
		"chmod":    true,
		"chown":    true,
		"chgrp":    true,
		"mount":    true,
		"umount":   true,
		"shutdown": true,
		"reboot":   true,
		"halt":     true,
		"poweroff": true,
		"init":     true,
		"kill":     true,
		"killall":  true,
		"pkill":    true,
	}

	return dangerous[command]
}
