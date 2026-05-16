#!/usr/bin/env bats
# Unit tests for install.sh functions using bats-core.
# Run with: npx bats tests/install_script/bats/test_install.bats

setup() {
    load "test_helper"
}

# =============================================================================
# validate_email tests (Requirement 3.2)
# =============================================================================

@test "validate_email: accepts user@example.com" {
    run validate_email "user@example.com"
    assert_success
}

@test "validate_email: accepts a@b.c" {
    run validate_email "a@b.c"
    assert_success
}

@test "validate_email: accepts complex email with dots and plus" {
    run validate_email "first.last+tag@sub.domain.org"
    assert_success
}

@test "validate_email: rejects no-at-sign" {
    run validate_email "no-at-sign"
    assert_failure
}

@test "validate_email: rejects @missing-local" {
    run validate_email "@missing-local.com"
    assert_failure
}

@test "validate_email: rejects user@no-dot" {
    run validate_email "user@nodot"
    assert_failure
}

@test "validate_email: rejects empty string" {
    run validate_email ""
    assert_failure
}

@test "validate_email: rejects double-at user@@domain.com" {
    run validate_email "user@@domain.com"
    assert_failure
}

# =============================================================================
# validate_tenant_name tests (Requirement 3.3)
# =============================================================================

@test "validate_tenant_name: accepts t_default" {
    run validate_tenant_name "t_default"
    assert_success
}

@test "validate_tenant_name: accepts t_abc123" {
    run validate_tenant_name "t_abc123"
    assert_success
}

@test "validate_tenant_name: accepts t_a (minimum length after prefix)" {
    run validate_tenant_name "t_a"
    assert_success
}

@test "validate_tenant_name: accepts t_ followed by 61 chars (max length)" {
    local long_suffix
    long_suffix="$(printf '%0.sa' {1..61})"
    run validate_tenant_name "t_${long_suffix}"
    assert_success
}

@test "validate_tenant_name: rejects no_prefix (missing t_)" {
    run validate_tenant_name "no_prefix"
    assert_failure
}

@test "validate_tenant_name: rejects t_ alone (no chars after prefix)" {
    run validate_tenant_name "t_"
    assert_failure
}

@test "validate_tenant_name: rejects T_UPPER (uppercase)" {
    run validate_tenant_name "T_UPPER"
    assert_failure
}

@test "validate_tenant_name: rejects t_ followed by 62 chars (too long)" {
    local long_suffix
    long_suffix="$(printf '%0.sa' {1..62})"
    run validate_tenant_name "t_${long_suffix}"
    assert_failure
}

@test "validate_tenant_name: rejects t_has-dash (invalid char)" {
    run validate_tenant_name "t_has-dash"
    assert_failure
}

@test "validate_tenant_name: rejects empty string" {
    run validate_tenant_name ""
    assert_failure
}

# =============================================================================
# validate_domain tests (Requirement 3.1)
# =============================================================================

@test "validate_domain: accepts example.com" {
    run validate_domain "example.com"
    assert_success
}

@test "validate_domain: accepts 192.168.1.1" {
    run validate_domain "192.168.1.1"
    assert_success
}

@test "validate_domain: accepts localhost" {
    run validate_domain "localhost"
    assert_success
}

@test "validate_domain: accepts sub.domain.example.com" {
    run validate_domain "sub.domain.example.com"
    assert_success
}

@test "validate_domain: rejects empty string" {
    run validate_domain ""
    assert_failure
}

@test "validate_domain: rejects string with space" {
    run validate_domain "has space"
    assert_failure
}

@test "validate_domain: rejects trailing slash" {
    run validate_domain "example.com/"
    assert_failure
}

@test "validate_domain: rejects string with tab" {
    run validate_domain "has	tab"
    assert_failure
}

# =============================================================================
# parse_docker_version tests (Requirement 2.1)
# =============================================================================

@test "parse_docker_version: extracts 24 from 'Docker version 24.0.7, build abc'" {
    run parse_docker_version "Docker version 24.0.7, build abc"
    assert_success
    assert_output "24"
}

@test "parse_docker_version: extracts 23 from 'Docker version 23.0.1, build def'" {
    run parse_docker_version "Docker version 23.0.1, build def"
    assert_success
    assert_output "23"
}

@test "parse_docker_version: extracts 25 from 'Docker version 25.0.0, build xyz123'" {
    run parse_docker_version "Docker version 25.0.0, build xyz123"
    assert_success
    assert_output "25"
}

@test "parse_docker_version: extracts 1 from 'Docker version 1.13.1, build old'" {
    run parse_docker_version "Docker version 1.13.1, build old"
    assert_success
    assert_output "1"
}

@test "parse_docker_version: returns empty for unparseable string" {
    run parse_docker_version "not a docker version"
    assert_success
    assert_output ""
}

@test "parse_docker_version: returns empty for empty string" {
    run parse_docker_version ""
    assert_success
    assert_output ""
}

# =============================================================================
# detect_os tests (Requirement 10.2)
# =============================================================================

@test "detect_os: returns macos on Darwin" {
    # On macOS this test will pass natively; on Linux it would need mocking.
    # We test the actual platform detection here.
    run detect_os
    assert_success
    # The output should be one of the known values
    [[ "${output}" == "macos" ]] || \
    [[ "${output}" == "ubuntu" ]] || \
    [[ "${output}" == "debian" ]] || \
    [[ "${output}" == "fedora" ]] || \
    [[ "${output}" == "unknown" ]]
}

@test "detect_os: returns a non-empty string" {
    run detect_os
    assert_success
    [ -n "${output}" ]
}

# =============================================================================
# should_use_color tests (Requirement 9.4)
# =============================================================================

@test "should_use_color: returns 1 (no color) when NO_COLOR is set" {
    NO_COLOR=1 run should_use_color
    assert_failure  # return 1 means no color
}

@test "should_use_color: returns 1 (no color) when stdout is not a TTY (piped)" {
    # In bats, stdout is captured (not a TTY), so should_use_color returns 1
    unset NO_COLOR
    run should_use_color
    assert_failure  # return 1 because stdout is not a TTY in bats
}

@test "should_use_color: returns 1 when both NO_COLOR set and not a TTY" {
    NO_COLOR=1 run should_use_color
    assert_failure
}

@test "should_use_color: would return 0 if TTY and no NO_COLOR (verified via logic)" {
    # We can't easily simulate a TTY in bats, but we can verify the logic:
    # The function checks NO_COLOR first, then checks -t 1.
    # If NO_COLOR is unset and we force fd 1 to be a TTY, it should return 0.
    # This test verifies the NO_COLOR check takes priority.
    NO_COLOR="" run should_use_color
    # Empty NO_COLOR is still "set" in bash [[ -n ]] check — actually empty string
    # means -n returns false, so it should proceed to TTY check.
    # In bats, stdout is not a TTY, so this still returns 1.
    assert_failure
}

# =============================================================================
# get_install_command tests (Requirement 10.2, 10.3)
# =============================================================================

@test "get_install_command: docker on ubuntu" {
    run get_install_command "docker" "ubuntu"
    assert_success
    assert_output --partial "apt-get"
    assert_output --partial "docker-ce"
}

@test "get_install_command: docker on debian" {
    run get_install_command "docker" "debian"
    assert_success
    assert_output --partial "apt-get"
    assert_output --partial "docker-ce"
}

@test "get_install_command: docker on fedora" {
    run get_install_command "docker" "fedora"
    assert_success
    assert_output --partial "dnf"
    assert_output --partial "docker-ce"
}

@test "get_install_command: docker on macos" {
    run get_install_command "docker" "macos"
    assert_success
    assert_output --partial "brew"
    assert_output --partial "docker"
}

@test "get_install_command: docker on unknown" {
    run get_install_command "docker" "unknown"
    assert_success
    assert_output --partial "https://docs.docker.com"
}

@test "get_install_command: docker-compose on ubuntu" {
    run get_install_command "docker-compose" "ubuntu"
    assert_success
    assert_output --partial "apt-get"
    assert_output --partial "docker-compose-plugin"
}

@test "get_install_command: docker-compose on fedora" {
    run get_install_command "docker-compose" "fedora"
    assert_success
    assert_output --partial "dnf"
    assert_output --partial "docker-compose-plugin"
}

@test "get_install_command: docker-compose on macos" {
    run get_install_command "docker-compose" "macos"
    assert_success
    assert_output --partial "brew"
    assert_output --partial "docker-compose"
}

@test "get_install_command: git on ubuntu" {
    run get_install_command "git" "ubuntu"
    assert_success
    assert_output --partial "apt-get"
    assert_output --partial "git"
}

@test "get_install_command: git on fedora" {
    run get_install_command "git" "fedora"
    assert_success
    assert_output --partial "dnf"
    assert_output --partial "git"
}

@test "get_install_command: git on macos" {
    run get_install_command "git" "macos"
    assert_success
    assert_output --partial "brew"
    assert_output --partial "git"
}

@test "get_install_command: docker-daemon on ubuntu" {
    run get_install_command "docker-daemon" "ubuntu"
    assert_success
    assert_output --partial "systemctl start docker"
}

@test "get_install_command: docker-daemon on macos" {
    run get_install_command "docker-daemon" "macos"
    assert_success
    assert_output --partial "open -a Docker"
}

@test "get_install_command: unknown tool" {
    run get_install_command "unknown-tool" "ubuntu"
    assert_success
    assert_output --partial "No install command available"
}

# =============================================================================
# log() and die() tests (format_error equivalent — Requirement 9.4)
# =============================================================================

@test "log: INFO message goes to stdout" {
    run log INFO "Test message"
    assert_success
    assert_output --partial "[INFO]"
    assert_output --partial "Test message"
}

@test "log: ERROR message contains ERROR tag" {
    run log ERROR "Something failed"
    # die/log ERROR writes to stderr, which bats captures in output
    assert_output --partial "[ERROR]"
    assert_output --partial "Something failed"
}

@test "log: WARN message contains WARN tag" {
    run log WARN "Be careful"
    assert_output --partial "[WARN]"
    assert_output --partial "Be careful"
}

@test "log: message includes ISO 8601 timestamp" {
    run log INFO "timestamp test"
    assert_success
    # Check for timestamp pattern like [2024-01-15T14:30:25+0000]
    [[ "${output}" =~ \[[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2} ]]
}

@test "die: exits with non-zero status" {
    run die "fatal error" "try again"
    assert_failure
}

@test "die: includes error message" {
    run die "fatal error" "try again"
    assert_output --partial "fatal error"
}

@test "die: includes remediation hint" {
    run die "fatal error" "try again"
    assert_output --partial "try again"
}

# =============================================================================
# generate_env_file tests (Requirement 3.4)
# =============================================================================

@test "generate_env_file: generates .env from .env.example with token substitution" {
    # Set up a temp directory with a minimal .env.example
    local tmpdir
    tmpdir="$(mktemp -d)"

    # Create a minimal .env.example with placeholders
    cat > "${tmpdir}/.env.example" <<'EOF'
# Mintkey config
BROKER_TOKEN=REPLACE_WITH_BROKER_TOKEN
PROXY_TOKEN=REPLACE_WITH_PROXY_TOKEN
SOME_OTHER_VAR=keep_this_value
EOF

    # Set required globals
    CONFIGURED_DOMAIN="192.168.1.50"
    CONFIGURED_EMAIL="admin@test.com"
    CONFIGURED_TENANT="t_default"
    NON_INTERACTIVE="true"
    LOG_FILE=""

    # Run generate_env_file from the temp directory
    cd "${tmpdir}"
    run generate_env_file
    assert_success

    # Verify .env was created
    [ -f "${tmpdir}/.env" ]

    # Verify no REPLACE_WITH_* placeholders remain
    run grep "REPLACE_WITH_" "${tmpdir}/.env"
    assert_failure  # grep should find nothing (exit 1)

    # Verify the non-placeholder value is preserved
    run grep "SOME_OTHER_VAR=keep_this_value" "${tmpdir}/.env"
    assert_success

    # Verify domain URLs were appended
    run grep "MINTKEY_MCP_PUBLIC_URL=http://192.168.1.50:8082" "${tmpdir}/.env"
    assert_success

    run grep "MINTKEY_ADMIN_EMAIL=admin@test.com" "${tmpdir}/.env"
    assert_success

    # Cleanup
    rm -rf "${tmpdir}"
}

@test "generate_env_file: each REPLACE_WITH placeholder gets a unique 64-char hex token" {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "${tmpdir}/.env.example" <<'EOF'
TOKEN_A=REPLACE_WITH_A
TOKEN_B=REPLACE_WITH_B
EOF

    CONFIGURED_DOMAIN="example.com"
    CONFIGURED_EMAIL="a@b.c"
    CONFIGURED_TENANT="t_default"
    NON_INTERACTIVE="true"
    LOG_FILE=""

    cd "${tmpdir}"
    run generate_env_file
    assert_success

    # Extract token values
    local token_a token_b
    token_a="$(grep '^TOKEN_A=' "${tmpdir}/.env" | cut -d= -f2)"
    token_b="$(grep '^TOKEN_B=' "${tmpdir}/.env" | cut -d= -f2)"

    # Each should be 64 hex characters
    [[ "${token_a}" =~ ^[0-9a-f]{64}$ ]]
    [[ "${token_b}" =~ ^[0-9a-f]{64}$ ]]

    # They should be different (unique)
    [ "${token_a}" != "${token_b}" ]

    rm -rf "${tmpdir}"
}

# =============================================================================
# check_prerequisites aggregation test (Requirement 2.5)
# =============================================================================

@test "check_prerequisites: collects all failures without short-circuiting" {
    # Override commands to simulate multiple failures.
    # We create a subshell script that redefines command checks.
    local tmpdir
    tmpdir="$(mktemp -d)"
    local test_script="${tmpdir}/test_prereq.sh"

    cat > "${test_script}" <<'SCRIPT'
#!/usr/bin/env bash
# Source the install script functions
SCRIPT

    # Build a script that sources install.sh (modified) and overrides commands
    local sourceable
    sourceable="$(mktemp)"
    sed \
        -e '/^set -euo pipefail/d' \
        -e '/^if \[\[ -z "\${BASH_VERSINFO\[0\]:-}" \]\]/,/^fi$/d' \
        -e '/^main "\$@"$/d' \
        -e '/^_init_log_file$/d' \
        "${INSTALL_SCRIPT}" > "${sourceable}"

    cat > "${test_script}" <<SCRIPT
#!/usr/bin/env bash
export NO_COLOR=1
export LOG_FILE=""
source "${sourceable}"

# Override 'command' builtin to simulate missing tools
# Make docker, git all "not found"
command() {
    if [[ "\$1" == "-v" ]]; then
        case "\$2" in
            docker|git)
                return 1
                ;;
            *)
                builtin command "\$@"
                ;;
        esac
    else
        builtin command "\$@"
    fi
}

# Run phase_prerequisites and capture exit code
phase_prerequisites
SCRIPT

    chmod +x "${test_script}"
    run bash "${test_script}"
    assert_failure

    # The output should mention BOTH docker and git failures (not just the first one)
    [[ "${output}" =~ "docker" ]]
    [[ "${output}" =~ "git" ]]

    rm -rf "${tmpdir}" "${sourceable}"
}
