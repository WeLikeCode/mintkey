#!/usr/bin/env bash
# Mintkey Developer Install Script
# Automates the full "clone to running stack" workflow.
# Requires Bash 4.0+, Docker 24+, Docker Compose v2, and Git.
#
# Usage: install.sh [OPTIONS]
#
# Options:
#   --non-interactive    Use defaults/env-vars for all prompts; abort if required values missing
#   --clean              Remove Docker volumes before rebuild (prompts for confirmation)
#   --force-destroy      Required with --clean --non-interactive; prevents silent volume removal
#                        (EvidenceRef: EV-DESTRUCTIVE-003, 2026-05-18-dev-settings-backup-recovery)
#   --help               Show this help message
#
# Note: Windows is not supported. Use WSL2 on Windows (future release).

set -euo pipefail

# --- Bash version guard (minimum 4.0) ---
if [[ -z "${BASH_VERSINFO[0]:-}" ]] || [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    printf "Error: Bash 4.0 or higher is required. Current version: %s\n" "${BASH_VERSION:-unknown}" >&2
    printf "On macOS, install a newer Bash via: brew install bash\n" >&2
    exit 1
fi

# --- Global flags ---
NON_INTERACTIVE=false
CLEAN=false
# --force-destroy: required when combining --clean with --non-interactive.
# Prevents silent data loss from CI/scripting invocations that bypass the interactive [y/N] prompt.
# EvidenceRef: EV-DESTRUCTIVE-003 (2026-05-18-dev-settings-backup-recovery)
FORCE_DESTROY=false

# --- Signal handling ---
cleanup() {
    local signal="${1:-}"
    printf "\n[INTERRUPTED] Received %s. Cleaning up...\n" "${signal}" >&2
    # Stop any in-progress docker compose operations
    if command -v docker >/dev/null 2>&1; then
        docker compose down --timeout 10 >/dev/null 2>&1 || true
    fi
    if [[ "${signal}" == "SIGINT" ]]; then
        exit 130
    elif [[ "${signal}" == "SIGTERM" ]]; then
        exit 143
    fi
    exit 1
}

trap 'cleanup SIGINT' SIGINT
trap 'cleanup SIGTERM' SIGTERM

# --- Color support ---
should_use_color() {
    # Returns 0 (true) if colors should be used
    if [[ -n "${NO_COLOR:-}" ]]; then
        return 1
    fi
    if [[ -t 1 ]]; then
        return 0
    fi
    return 1
}

GREEN=""
RED=""
YELLOW=""
RESET=""

if should_use_color; then
    GREEN=$'\033[0;32m'
    RED=$'\033[0;31m'
    YELLOW=$'\033[0;33m'
    RESET=$'\033[0m'
fi

# --- Log file setup ---
LOG_FILE=""
_init_log_file() {
    local log_name
    log_name="install-$(date '+%Y%m%d-%H%M%S').log"
    if touch "${log_name}" 2>/dev/null; then
        LOG_FILE="${log_name}"
    else
        printf "%sWarning: Could not create log file '%s'. Continuing without file logging.%s\n" \
            "${YELLOW}" "${log_name}" "${RESET}" >&2
        LOG_FILE=""
    fi
}
_init_log_file

# --- Logging and output utilities ---

log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date '+%Y-%m-%dT%H:%M:%S%z')"
    local formatted="[${timestamp}] [${level}] ${message}"

    # Write to log file if available
    if [[ -n "${LOG_FILE}" ]]; then
        printf "%s\n" "${formatted}" >> "${LOG_FILE}" 2>/dev/null || true
    fi

    # Write to stdout or stderr based on level
    case "${level}" in
        ERROR)
            printf "%s%s%s\n" "${RED}" "${formatted}" "${RESET}" >&2
            ;;
        WARN)
            printf "%s%s%s\n" "${YELLOW}" "${formatted}" "${RESET}" >&2
            ;;
        *)
            printf "%s%s%s\n" "${GREEN}" "${formatted}" "${RESET}"
            ;;
    esac
}

die() {
    local message="${1:-An error occurred}"
    local remediation="${2:-}"
    local timestamp
    timestamp="$(date '+%Y-%m-%dT%H:%M:%S%z')"
    local formatted="[${timestamp}] [ERROR] ${message}"

    # Write to log file if available
    if [[ -n "${LOG_FILE}" ]]; then
        printf "%s\n" "${formatted}" >> "${LOG_FILE}" 2>/dev/null || true
        if [[ -n "${remediation}" ]]; then
            printf "  Remediation: %s\n" "${remediation}" >> "${LOG_FILE}" 2>/dev/null || true
        fi
    fi

    # Write to stderr
    printf "%s%s%s\n" "${RED}" "${formatted}" "${RESET}" >&2
    if [[ -n "${remediation}" ]]; then
        printf "  Suggested fix: %s\n" "${remediation}" >&2
    fi
    exit 1
}

detect_os() {
    local os_id=""
    if [[ "$(uname -s)" == "Darwin" ]]; then
        printf "macos"
        return 0
    fi
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091 # /etc/os-release is a system file, not a project file
        os_id="$(. /etc/os-release && printf "%s" "${ID:-}")"
    fi
    case "${os_id}" in
        ubuntu)
            printf "ubuntu"
            ;;
        debian)
            printf "debian"
            ;;
        fedora)
            printf "fedora"
            ;;
        *)
            printf "unknown"
            ;;
    esac
    return 0
}

generate_token() {
    openssl rand -hex 32
}

prompt() {
    local message="${1:-Enter value}"
    local default_value="${2:-}"
    local validate_fn="${3:-}"
    local timeout="${4:-30}"
    local max_retries=3
    local attempt=0
    local input=""

    if [[ "${NON_INTERACTIVE}" == "true" ]]; then
        if [[ -n "${default_value}" ]]; then
            printf "%s" "${default_value}"
            return 0
        fi
        die "Cannot prompt in non-interactive mode and no default provided" \
            "Provide the required value via environment variable or command-line argument"
    fi

    while [[ ${attempt} -lt ${max_retries} ]]; do
        attempt=$((attempt + 1))
        if [[ -n "${default_value}" ]]; then
            printf "%s [%s]: " "${message}" "${default_value}" >&2
        else
            printf "%s: " "${message}" >&2
        fi

        input=""
        if ! read -r -t "${timeout}" input; then
            printf "\n" >&2
            log WARN "Input timed out after ${timeout} seconds"
            if [[ -n "${default_value}" ]]; then
                printf "%s" "${default_value}"
                return 0
            fi
            if [[ ${attempt} -ge ${max_retries} ]]; then
                die "No input received after ${max_retries} attempts" \
                    "Provide a valid value or use --non-interactive with environment variables"
            fi
            continue
        fi

        # Use default if input is empty
        if [[ -z "${input}" ]] && [[ -n "${default_value}" ]]; then
            input="${default_value}"
        fi

        # Validate if a validation function is provided
        if [[ -n "${validate_fn}" ]]; then
            if ${validate_fn} "${input}"; then
                printf "%s" "${input}"
                return 0
            else
                printf "%sInvalid input (attempt %d of %d).%s\n" \
                    "${YELLOW}" "${attempt}" "${max_retries}" "${RESET}" >&2
                if [[ ${attempt} -ge ${max_retries} ]]; then
                    die "Invalid input after ${max_retries} attempts" \
                        "Provide a valid value matching the required format"
                fi
            fi
        else
            printf "%s" "${input}"
            return 0
        fi
    done
}

# --- Argument parsing ---
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            --clean)
                CLEAN=true
                shift
                ;;
            --force-destroy)
                # Required when --clean and --non-interactive are both set.
                # EvidenceRef: EV-DESTRUCTIVE-003 (2026-05-18-dev-settings-backup-recovery)
                FORCE_DESTROY=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                printf "Error: Unknown option '%s'\n" "$1" >&2
                printf "Run 'install.sh --help' for usage information.\n" >&2
                exit 1
                ;;
        esac
    done
}

show_help() {
    cat <<'EOF'
Usage: install.sh [OPTIONS]

Automates the full Mintkey developer setup: clone, prerequisites, configure,
build, migrate, seed, start, and verify.

Options:
  --non-interactive    Use defaults/env-vars for all prompts; abort if required values missing
  --clean              Remove Docker volumes before rebuild (prompts for confirmation)
  --force-destroy      Required when combining --clean with --non-interactive. Bypasses the
                       interactive [y/N] confirmation for volume removal. Without this flag,
                       --clean --non-interactive exits 1 and prints the volume list so you
                       can run 'bash scripts/dev-backup.sh' first.
                       (EvidenceRef: EV-DESTRUCTIVE-003)
  --help               Show this help message

Environment variables (for --non-interactive):
  MINTKEY_DOMAIN                  Required. Public-facing domain or IP (e.g., 192.168.1.50)
  MINTKEY_ADMIN_EMAIL             Required. Platform admin email address
  MINTKEY_TENANT_NAME             Optional. Initial tenant name (default: t_default)
  MINTKEY_HEALTH_TIMEOUT_SECONDS  Optional. Health poll timeout (default: 120)

Note: Windows is not supported natively. Use WSL2 on Windows (future release).
EOF
}

# --- Phase stubs (to be implemented in later tasks) ---

phase_clone() {
    local target_dir="."
    local repo_url="https://github.com/WeLikeCode/mintkey.git"
    local clone_timeout=120

    # Skip if .git directory already exists
    if [[ -d "${target_dir}/.git" ]]; then
        log INFO "Repository already cloned (.git directory exists). Skipping clone."
        return 0
    fi

    # Check git availability
    if ! command -v git >/dev/null 2>&1; then
        die "git is not installed or not found on the system PATH" \
            "Install git: $(get_git_install_hint)"
    fi

    log INFO "Cloning repository from ${repo_url} (timeout: ${clone_timeout}s)..."

    # Determine timeout command (macOS may need gtimeout from coreutils)
    local timeout_cmd=""
    if command -v timeout >/dev/null 2>&1; then
        timeout_cmd="timeout"
    elif command -v gtimeout >/dev/null 2>&1; then
        timeout_cmd="gtimeout"
    fi

    local clone_output=""
    local clone_exit=0

    if [[ -n "${timeout_cmd}" ]]; then
        clone_output="$( ${timeout_cmd} "${clone_timeout}" git clone "${repo_url}" "${target_dir}" 2>&1 )" || clone_exit=$?
    else
        # Fallback: background process with kill for Bash 4.0 compatibility
        git clone "${repo_url}" "${target_dir}" >"${target_dir}/.clone_output.tmp" 2>&1 &
        local clone_pid=$!
        local elapsed=0
        while kill -0 "${clone_pid}" 2>/dev/null; do
            if [[ ${elapsed} -ge ${clone_timeout} ]]; then
                kill "${clone_pid}" 2>/dev/null || true
                wait "${clone_pid}" 2>/dev/null || true
                rm -f "${target_dir}/.clone_output.tmp"
                die "Clone operation timed out after ${clone_timeout} seconds" \
                    "Check network connectivity and try again"
            fi
            sleep 1
            elapsed=$((elapsed + 1))
        done
        wait "${clone_pid}" 2>/dev/null || clone_exit=$?
        clone_output="$(cat "${target_dir}/.clone_output.tmp" 2>/dev/null || true)"
        rm -f "${target_dir}/.clone_output.tmp"
    fi

    # Handle timeout exit code (124 for timeout/gtimeout)
    if [[ ${clone_exit} -eq 124 ]]; then
        die "Clone operation timed out after ${clone_timeout} seconds" \
            "Check network connectivity and try again"
    fi

    if [[ ${clone_exit} -ne 0 ]]; then
        local error_reason="${clone_output:-unknown error}"
        die "Failed to clone repository: ${error_reason}" \
            "Check network connectivity and that the URL is accessible: ${repo_url}"
    fi

    log INFO "Repository cloned successfully."
    return 0
}

get_git_install_hint() {
    local os
    os="$(detect_os)"
    case "${os}" in
        ubuntu|debian)
            printf "sudo apt-get install -y git"
            ;;
        fedora)
            printf "sudo dnf install -y git"
            ;;
        macos)
            printf "brew install git"
            ;;
        *)
            printf "Install git from https://git-scm.com/downloads"
            ;;
    esac
}

parse_docker_version() {
    # Extracts the major version number from docker --version output.
    # Input: string like "Docker version 24.0.7, build afdd53b"
    # Output: the major version integer (e.g., 24), or empty string on parse failure.
    local version_string="${1:-}"
    local major=""
    # Match "Docker version X.Y.Z" and extract X
    if [[ "${version_string}" =~ Docker\ version\ ([0-9]+)\. ]]; then
        major="${BASH_REMATCH[1]}"
    fi
    printf "%s" "${major}"
}

get_install_command() {
    # Returns a platform-appropriate install command for a given tool.
    # Arguments: $1 = tool name (docker, docker-compose, git)
    #            $2 = OS identifier from detect_os() (ubuntu, debian, fedora, macos, unknown)
    local tool="${1:-}"
    local os="${2:-}"

    case "${tool}" in
        docker)
            case "${os}" in
                ubuntu|debian)
                    printf "sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io"
                    ;;
                fedora)
                    printf "sudo dnf install -y docker-ce docker-ce-cli containerd.io"
                    ;;
                macos)
                    printf "brew install --cask docker"
                    ;;
                *)
                    printf "Install Docker from https://docs.docker.com/get-docker/"
                    ;;
            esac
            ;;
        docker-compose)
            case "${os}" in
                ubuntu|debian)
                    printf "sudo apt-get update && sudo apt-get install -y docker-compose-plugin"
                    ;;
                fedora)
                    printf "sudo dnf install -y docker-compose-plugin"
                    ;;
                macos)
                    printf "brew install docker-compose"
                    ;;
                *)
                    printf "Install Docker Compose from https://docs.docker.com/compose/install/"
                    ;;
            esac
            ;;
        git)
            case "${os}" in
                ubuntu|debian)
                    printf "sudo apt-get update && sudo apt-get install -y git"
                    ;;
                fedora)
                    printf "sudo dnf install -y git"
                    ;;
                macos)
                    printf "brew install git"
                    ;;
                *)
                    printf "Install Git from https://git-scm.com/downloads"
                    ;;
            esac
            ;;
        docker-daemon)
            case "${os}" in
                ubuntu|debian|fedora)
                    printf "sudo systemctl start docker"
                    ;;
                macos)
                    printf "open -a Docker"
                    ;;
                *)
                    printf "Start the Docker daemon manually"
                    ;;
            esac
            ;;
        *)
            printf "No install command available for '%s'" "${tool}"
            ;;
    esac
}

phase_prerequisites() {
    log INFO "Checking prerequisites..."
    local failures=0
    local os
    os="$(detect_os)"

    # --- Check 1: docker on PATH with major version >= 24 ---
    if ! command -v docker >/dev/null 2>&1; then
        failures=$((failures + 1))
        log ERROR "Prerequisite failed: docker not found on PATH"
        log ERROR "  Required: Docker >= 24"
        log ERROR "  Install:  $(get_install_command docker "${os}")"
    else
        local docker_version_output
        docker_version_output="$(docker --version 2>/dev/null || true)"
        local docker_major
        docker_major="$(parse_docker_version "${docker_version_output}")"
        if [[ -z "${docker_major}" ]]; then
            failures=$((failures + 1))
            log ERROR "Prerequisite failed: could not parse Docker version from: ${docker_version_output}"
            log ERROR "  Required: Docker >= 24"
            log ERROR "  Install:  $(get_install_command docker "${os}")"
        elif [[ "${docker_major}" -lt 24 ]]; then
            failures=$((failures + 1))
            log ERROR "Prerequisite failed: Docker version ${docker_major} is below minimum"
            log ERROR "  Required: Docker >= 24 (found: ${docker_version_output})"
            log ERROR "  Install:  $(get_install_command docker "${os}")"
        fi
    fi

    # --- Check 2: docker compose v2 plugin syntax ---
    if ! docker compose version >/dev/null 2>&1; then
        failures=$((failures + 1))
        log ERROR "Prerequisite failed: 'docker compose' (v2 plugin) not available"
        log ERROR "  Required: Docker Compose v2 plugin (docker compose version exits 0)"
        log ERROR "  Install:  $(get_install_command docker-compose "${os}")"
    fi

    # --- Check 3: git on PATH ---
    if ! command -v git >/dev/null 2>&1; then
        failures=$((failures + 1))
        log ERROR "Prerequisite failed: git not found on PATH"
        log ERROR "  Required: git (any version)"
        log ERROR "  Install:  $(get_install_command git "${os}")"
    else
        if ! git --version >/dev/null 2>&1; then
            failures=$((failures + 1))
            log ERROR "Prerequisite failed: 'git --version' did not exit successfully"
            log ERROR "  Required: git (any version)"
            log ERROR "  Install:  $(get_install_command git "${os}")"
        fi
    fi

    # --- Check 4: Docker daemon running (10-second timeout) ---
    local docker_info_exit=0
    if command -v docker >/dev/null 2>&1; then
        # Use a background process approach for timeout (works on macOS without coreutils timeout)
        docker info >/dev/null 2>&1 &
        local docker_info_pid=$!
        local elapsed=0
        while kill -0 "${docker_info_pid}" 2>/dev/null; do
            if [[ ${elapsed} -ge 10 ]]; then
                kill "${docker_info_pid}" 2>/dev/null || true
                wait "${docker_info_pid}" 2>/dev/null || true
                docker_info_exit=1
                break
            fi
            sleep 1
            elapsed=$((elapsed + 1))
        done
        if [[ ${docker_info_exit} -eq 0 ]]; then
            wait "${docker_info_pid}" 2>/dev/null
            docker_info_exit=$?
        fi

        if [[ ${docker_info_exit} -ne 0 ]]; then
            failures=$((failures + 1))
            log ERROR "Prerequisite failed: Docker daemon is not running (or did not respond within 10 seconds)"
            log ERROR "  Required: Docker daemon running (docker info exits 0 within 10s)"
            log ERROR "  Fix:      $(get_install_command docker-daemon "${os}")"
        fi
    fi

    # --- Report result ---
    if [[ ${failures} -gt 0 ]]; then
        log ERROR "${failures} prerequisite check(s) failed. Please fix the above issues and re-run."
        exit 1
    fi

    log INFO "All prerequisites satisfied."
}

# --- Validation functions ---

validate_domain() {
    local value="${1:-}"
    # Must be non-empty
    if [[ -z "${value}" ]]; then
        printf "Domain/IP must not be empty.\n" >&2
        return 1
    fi
    # Must not contain whitespace
    if [[ "${value}" =~ [[:space:]] ]]; then
        printf "Domain/IP must not contain whitespace.\n" >&2
        return 1
    fi
    # Must not have a trailing slash
    if [[ "${value}" == */ ]]; then
        printf "Domain/IP must not end with a trailing slash.\n" >&2
        return 1
    fi
    return 0
}

validate_email() {
    local value="${1:-}"
    # Must match ^[^@]+@[^@]+\.[^@]+$
    if [[ "${value}" =~ ^[^@]+@[^@]+\.[^@]+$ ]]; then
        return 0
    fi
    printf "Email must match format: local-part@domain (with at least one dot in domain).\n" >&2
    return 1
}

validate_tenant_name() {
    local value="${1:-}"
    # Must match ^t_[a-z0-9_]{1,61}$
    if [[ "${value}" =~ ^t_[a-z0-9_]{1,61}$ ]]; then
        return 0
    fi
    printf "Tenant name must match: t_ followed by 1-61 lowercase alphanumeric/underscore characters.\n" >&2
    return 1
}

# --- Configuration globals ---
CONFIGURED_DOMAIN=""
CONFIGURED_EMAIL=""
CONFIGURED_TENANT=""

phase_configure() {
    log INFO "Starting configuration phase..."

    # --- Non-interactive mode: validate required env vars and use defaults ---
    if [[ "${NON_INTERACTIVE}" == "true" ]]; then
        local missing=""

        if [[ -z "${MINTKEY_DOMAIN:-}" ]]; then
            missing="${missing}MINTKEY_DOMAIN, "
        fi
        if [[ -z "${MINTKEY_ADMIN_EMAIL:-}" ]]; then
            missing="${missing}MINTKEY_ADMIN_EMAIL, "
        fi

        if [[ -n "${missing}" ]]; then
            # Remove trailing ", "
            missing="${missing%, }"
            printf "Error: Non-interactive mode requires the following environment variables: %s\n" "${missing}" >&2
            exit 1
        fi

        # Validate the provided values
        if ! validate_domain "${MINTKEY_DOMAIN}"; then
            die "Invalid MINTKEY_DOMAIN value: '${MINTKEY_DOMAIN}'" \
                "Provide a non-empty value with no whitespace and no trailing slash"
        fi
        if ! validate_email "${MINTKEY_ADMIN_EMAIL}"; then
            die "Invalid MINTKEY_ADMIN_EMAIL value: '${MINTKEY_ADMIN_EMAIL}'" \
                "Provide a valid email matching: local-part@domain (with at least one dot in domain)"
        fi

        CONFIGURED_DOMAIN="${MINTKEY_DOMAIN}"
        CONFIGURED_EMAIL="${MINTKEY_ADMIN_EMAIL}"
        CONFIGURED_TENANT="${MINTKEY_TENANT_NAME:-t_default}"

        # Validate tenant name if explicitly provided
        if [[ -n "${MINTKEY_TENANT_NAME:-}" ]]; then
            if ! validate_tenant_name "${CONFIGURED_TENANT}"; then
                die "Invalid MINTKEY_TENANT_NAME value: '${CONFIGURED_TENANT}'" \
                    "Provide a value matching: t_ followed by 1-61 lowercase alphanumeric/underscore characters"
            fi
        fi

        log INFO "Configuration collected (non-interactive): domain=${CONFIGURED_DOMAIN}, email=${CONFIGURED_EMAIL}, tenant=${CONFIGURED_TENANT}"
        generate_env_file
        return 0
    fi

    # --- Interactive mode: prompt for values ---

    # Prompt for public-facing domain/IP
    CONFIGURED_DOMAIN="$(prompt \
        "Enter public-facing domain or IP (e.g., 192.168.1.50)" \
        "${MINTKEY_DOMAIN:-}" \
        validate_domain \
        30)"

    # Prompt for admin email
    CONFIGURED_EMAIL="$(prompt \
        "Enter platform admin email address" \
        "${MINTKEY_ADMIN_EMAIL:-}" \
        validate_email \
        30)"

    # Prompt for tenant name (default: t_default)
    CONFIGURED_TENANT="$(prompt \
        "Enter initial tenant name" \
        "${MINTKEY_TENANT_NAME:-t_default}" \
        validate_tenant_name \
        30)"

    log INFO "Configuration collected: domain=${CONFIGURED_DOMAIN}, email=${CONFIGURED_EMAIL}, tenant=${CONFIGURED_TENANT}"
    generate_env_file
}

generate_env_file() {
    local env_file=".env"
    local env_template=".env.example"

    # Check if .env already exists — prompt for confirmation before overwriting
    if [[ -f "${env_file}" ]]; then
        if [[ "${NON_INTERACTIVE}" == "true" ]]; then
            log WARN "Existing .env file will be overwritten (non-interactive mode)."
        else
            local confirm=""
            printf "%sA .env file already exists. Overwrite? [y/N] (30s timeout, default: abort): %s" \
                "${YELLOW}" "${RESET}" >&2
            if ! read -r -t 30 confirm; then
                printf "\n" >&2
                log WARN "No response within 30 seconds. Aborting to preserve existing .env."
                die "Aborted: existing .env file preserved" \
                    "Remove .env manually or answer 'y' to overwrite"
            fi
            case "${confirm}" in
                [yY]|[yY][eE][sS])
                    log INFO "User confirmed .env overwrite."
                    ;;
                *)
                    die "Aborted: existing .env file preserved" \
                        "Remove .env manually or answer 'y' to overwrite"
                    ;;
            esac
        fi
    fi

    # Verify template exists
    if [[ ! -f "${env_template}" ]]; then
        die "Template file '${env_template}' not found" \
            "Ensure you are running from the repository root"
    fi

    log INFO "Generating .env from ${env_template}..."

    # Copy template to .env
    cp "${env_template}" "${env_file}"

    # Replace all REPLACE_WITH_* placeholders with unique openssl rand -hex 32 tokens
    # Use a temporary file approach for sed compatibility across GNU and BSD
    local token=""
    local tmp_file="${env_file}.tmp"
    local line_num=""

    # Process one placeholder at a time to ensure each gets a unique token value.
    # Find the line number of the first occurrence, then replace only on that line.
    while line_num="$(grep -n 'REPLACE_WITH_[A-Za-z0-9_]*' "${env_file}" | head -1 | cut -d: -f1)" && [[ -n "${line_num}" ]]; do
        token="$(generate_token)"
        sed "${line_num}s|REPLACE_WITH_[A-Za-z0-9_]*|${token}|" "${env_file}" > "${tmp_file}" && mv "${tmp_file}" "${env_file}"
    done

    # Substitute domain-derived URLs for all 7 services
    # Append active (uncommented) public URL values at the end of the file
    {
        printf "\n"
        printf "# ---------------------------------------------------------------------------\n"
        printf "# Generated public URLs (domain: %s)\n" "${CONFIGURED_DOMAIN}"
        printf "# ---------------------------------------------------------------------------\n"
        printf "MINTKEY_MCP_PUBLIC_URL=http://%s:8082\n" "${CONFIGURED_DOMAIN}"
        printf "MINTKEY_PROXY_PUBLIC_URL=http://%s:8000\n" "${CONFIGURED_DOMAIN}"
        printf "MINTKEY_ADMIN_API_PUBLIC_URL=http://%s:8080\n" "${CONFIGURED_DOMAIN}"
        printf "MINTKEY_ADMIN_UI_PUBLIC_URL=http://%s:8081\n" "${CONFIGURED_DOMAIN}"
        printf "MINTKEY_KEYCLOAK_PUBLIC_URL=http://%s:8443\n" "${CONFIGURED_DOMAIN}"
        printf "MINTKEY_GRAFANA_PUBLIC_URL=http://%s:3003\n" "${CONFIGURED_DOMAIN}"
        printf "MINTKEY_JAEGER_PUBLIC_URL=http://%s:16686\n" "${CONFIGURED_DOMAIN}"
        printf "\n"
        printf "# ---------------------------------------------------------------------------\n"
        printf "# Generated admin configuration\n"
        printf "# ---------------------------------------------------------------------------\n"
        printf "MINTKEY_ADMIN_EMAIL=%s\n" "${CONFIGURED_EMAIL}"
        printf "MINTKEY_TENANT_NAME=%s\n" "${CONFIGURED_TENANT}"
        printf "\n"
        printf "# ---------------------------------------------------------------------------\n"
        printf "# Generated secrets (not in .env.example — required at startup)\n"
        printf "# ---------------------------------------------------------------------------\n"
        printf "MINTKEY_AUDIT_HMAC_KEY=%s\n" "$(openssl rand -hex 32)"
        printf "# Email-proxy shared secrets (ADR-0024 / C-11)\n"
        printf "MINTKEY_VAULT_EMAIL_PROXY_TOKEN=%s\n" "$(openssl rand -hex 32)"
        printf "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN=%s\n" "$(openssl rand -hex 32)"
    } >> "${env_file}"

    log INFO ".env file generated successfully."
}

phase_build() {
    log INFO "Starting container build phase..."

    # Set DOCKER_BUILDKIT=1 to enable BuildKit backend
    export DOCKER_BUILDKIT=1
    log INFO "DOCKER_BUILDKIT=1 enabled."

    # Execute docker compose build and capture output
    local build_exit=0
    local build_tmp="${LOG_FILE:-/tmp/install-build-output}.build.tmp"

    log INFO "Running docker compose build..."
    docker compose build >"${build_tmp}" 2>&1 || build_exit=$?

    # Append build output to log file
    if [[ -n "${LOG_FILE}" ]] && [[ -f "${build_tmp}" ]]; then
        cat "${build_tmp}" >> "${LOG_FILE}" 2>/dev/null || true
    fi

    if [[ ${build_exit} -ne 0 ]]; then
        # Attempt to identify the failing service from the build output
        local failing_service="unknown"
        if [[ -f "${build_tmp}" ]]; then
            # Docker Compose build errors typically mention the service name
            # Look for patterns like "failed to solve: ... service <name>" or "ERROR: Service '<name>'"
            # or "=> ERROR [<service> ..." or "------\n > [<service>"
            local detected
            detected="$(grep -oE 'Service .?[a-z][a-z0-9_-]+' "${build_tmp}" | tail -1 | sed "s/Service '\\{0,1\\}//" | sed "s/'$//" || true)"
            if [[ -z "${detected}" ]]; then
                detected="$(grep -oE '\[([a-z][a-z0-9_-]+)[[:space:]]' "${build_tmp}" | tail -1 | tr -d '[]' | tr -d ' ' || true)"
            fi
            if [[ -n "${detected}" ]]; then
                failing_service="${detected}"
            fi

            # Display last 50 lines of build error output
            printf "\n%s[BUILD FAILURE] Service: %s%s\n" "${RED}" "${failing_service}" "${RESET}" >&2
            printf "Last 50 lines of build output:\n" >&2
            tail -50 "${build_tmp}" >&2
        fi
        rm -f "${build_tmp}"
        die "[BUILD] docker compose build failed for service '${failing_service}'" \
            "Check Dockerfile syntax and build context. Last 50 lines of build output shown above."
    fi

    rm -f "${build_tmp}"
    log INFO "docker compose build completed successfully."

    # Verify all built services have non-empty image IDs
    log INFO "Verifying built images..."
    local images_output=""
    images_output="$(docker compose images 2>/dev/null || true)"

    if [[ -z "${images_output}" ]]; then
        die "[BUILD] Could not retrieve image list via 'docker compose images'" \
            "Ensure Docker is running and docker compose is functional."
    fi

    # Get list of services that have a build: context in docker-compose.yml
    local compose_file="docker-compose.yml"
    if [[ ! -f "${compose_file}" ]]; then
        compose_file="docker-compose.yaml"
    fi

    if [[ ! -f "${compose_file}" ]]; then
        log WARN "Could not find docker-compose.yml to verify built services. Skipping image verification."
        return 0
    fi

    # Parse services with build: context from the compose file
    # Look for lines with "build:" that follow a service name definition
    local missing_images=""
    local current_service=""
    local in_services=false
    local has_build=false

    while IFS= read -r line; do
        # Detect the services: top-level key
        if [[ "${line}" =~ ^services: ]]; then
            in_services=true
            continue
        fi
        # Detect another top-level key (end of services block)
        if [[ "${in_services}" == "true" ]] && [[ "${line}" =~ ^[a-z] ]] && [[ ! "${line}" =~ ^[[:space:]] ]]; then
            in_services=false
            continue
        fi
        if [[ "${in_services}" != "true" ]]; then
            continue
        fi
        # Detect a service name (2-space indented, ends with colon)
        if [[ "${line}" =~ ^[[:space:]][[:space:]][a-z][a-z0-9_-]+: ]] && [[ ! "${line}" =~ ^[[:space:]][[:space:]][[:space:]] ]]; then
            # If previous service had a build context, check it
            if [[ -n "${current_service}" ]] && [[ "${has_build}" == "true" ]]; then
                # Check if this service appears in docker compose images output with a non-empty image
                if ! printf "%s" "${images_output}" | grep -q "${current_service}"; then
                    missing_images="${missing_images}${current_service}, "
                fi
            fi
            current_service="$(printf "%s" "${line}" | sed 's/^[[:space:]]*//' | sed 's/:.*//')"
            has_build=false
        fi
        # Detect build: key for current service
        if [[ "${line}" =~ ^[[:space:]][[:space:]][[:space:]][[:space:]]build: ]] || [[ "${line}" =~ ^[[:space:]][[:space:]][[:space:]][[:space:]]build$ ]]; then
            has_build=true
        fi
    done < "${compose_file}"

    # Check the last service
    if [[ -n "${current_service}" ]] && [[ "${has_build}" == "true" ]]; then
        if ! printf "%s" "${images_output}" | grep -q "${current_service}"; then
            missing_images="${missing_images}${current_service}, "
        fi
    fi

    if [[ -n "${missing_images}" ]]; then
        # Remove trailing ", "
        missing_images="${missing_images%, }"
        die "[BUILD] The following services have no image after build: ${missing_images}" \
            "Re-run 'docker compose build' and check for errors in the listed services."
    fi

    log INFO "All built services have valid images. Build phase complete."
}

phase_migrate() {
    log INFO "Starting database migration phase (Liquibase)..."

    # Run the Liquibase one-shot job via Docker Compose.
    # The dependency graph ensures postgres is healthy before Liquibase starts.
    # On re-run, Liquibase detects no pending changesets and exits 0 (idempotent).
    local migrate_exit=0
    docker compose up --exit-code-from liquibase liquibase >>"${LOG_FILE:-/dev/null}" 2>&1 || migrate_exit=$?

    if [[ ${migrate_exit} -ne 0 ]]; then
        printf "\n%s[MIGRATE] Liquibase migration failed (exit code: %d)%s\n" \
            "${RED}" "${migrate_exit}" "${RESET}" >&2
        printf "Last 50 lines of Liquibase logs:\n" >&2
        docker compose logs --tail=50 liquibase >&2 2>&1 || true
        die "[MIGRATE] Liquibase migration failed" \
            "Check database connectivity and migration changelogs. Logs shown above."
    fi

    log INFO "Database migration completed successfully."
}

phase_seed() {
    log INFO "Starting seed phase..."

    # Wait for Keycloak /health/ready to return HTTP 200 before running seed-job.
    # The Docker Compose dependency graph handles ordering (seed-job depends_on
    # liquibase completed_successfully + keycloak healthy), but we also poll
    # explicitly to provide clear feedback and a controlled timeout.
    local keycloak_timeout=60
    local keycloak_elapsed=0
    local keycloak_ready=false

    log INFO "Waiting for Keycloak health endpoint (timeout: ${keycloak_timeout}s)..."

    while [[ ${keycloak_elapsed} -lt ${keycloak_timeout} ]]; do
        if curl -sf -o /dev/null "http://localhost:8443/health/ready" 2>/dev/null; then
            keycloak_ready=true
            break
        fi
        sleep 2
        keycloak_elapsed=$((keycloak_elapsed + 2))
    done

    if [[ "${keycloak_ready}" != "true" ]]; then
        die "[SEED] Keycloak did not become ready within ${keycloak_timeout} seconds" \
            "Ensure Keycloak is healthy. Check logs with: docker compose logs keycloak"
    fi

    log INFO "Keycloak is ready. Running seed-job..."

    # Run the seed-job with a 60-second timeout.
    # The seed-job uses conflict-safe inserts (ON CONFLICT DO NOTHING) for idempotency.
    local seed_timeout=60
    local seed_tmp="${LOG_FILE:-/tmp/install-seed}.seed.tmp"
    local seed_exit=0

    # Use a background process with manual timeout for Bash 4.0 compatibility
    docker compose up --exit-code-from seed-job seed-job >"${seed_tmp}" 2>&1 &
    local seed_pid=$!
    local seed_elapsed=0

    while kill -0 "${seed_pid}" 2>/dev/null; do
        if [[ ${seed_elapsed} -ge ${seed_timeout} ]]; then
            kill "${seed_pid}" 2>/dev/null || true
            wait "${seed_pid}" 2>/dev/null || true
            # Stop the seed-job container
            docker compose stop seed-job >/dev/null 2>&1 || true
            printf "\n%s[SEED] Seed-job timed out after %d seconds%s\n" \
                "${RED}" "${seed_timeout}" "${RESET}" >&2
            printf "Seed-job output:\n" >&2
            cat "${seed_tmp}" >&2 2>/dev/null || true
            rm -f "${seed_tmp}"
            die "[SEED] Seed-job exceeded ${seed_timeout}-second deadline" \
                "Ensure Keycloak is healthy and database is accessible. Seed-job output shown above."
        fi
        sleep 1
        seed_elapsed=$((seed_elapsed + 1))
    done

    wait "${seed_pid}" 2>/dev/null || seed_exit=$?

    # Append seed output to log file
    if [[ -n "${LOG_FILE}" ]] && [[ -f "${seed_tmp}" ]]; then
        cat "${seed_tmp}" >> "${LOG_FILE}" 2>/dev/null || true
    fi

    if [[ ${seed_exit} -ne 0 ]]; then
        printf "\n%s[SEED] Seed-job failed (exit code: %d)%s\n" \
            "${RED}" "${seed_exit}" "${RESET}" >&2
        printf "Seed-job stdout+stderr:\n" >&2
        cat "${seed_tmp}" >&2 2>/dev/null || true
        rm -f "${seed_tmp}"
        die "[SEED] Seed-job failed" \
            "Check seed-job logs above. Ensure database and Keycloak are accessible."
    fi

    rm -f "${seed_tmp}"
    log INFO "Seed phase completed successfully."
}

phase_start() {
    log INFO "Starting stack startup phase..."

    # Check if containers are already running
    local running_containers=""
    running_containers="$(docker compose ps -q 2>/dev/null || true)"

    if [[ -n "${running_containers}" ]]; then
        log INFO "Existing containers detected. Stopping via docker compose down (timeout: 30s)..."
        local down_exit=0
        docker compose down --timeout 30 >>"${LOG_FILE:-/dev/null}" 2>&1 || down_exit=$?
        if [[ ${down_exit} -ne 0 ]]; then
            log WARN "docker compose down exited with code ${down_exit}. Continuing..."
        fi
    fi

    # Handle --clean flag: remove volumes if confirmed
    # EvidenceRef: EV-DESTRUCTIVE-003 (2026-05-18-dev-settings-backup-recovery)
    if [[ "${CLEAN}" == "true" ]]; then
        if [[ "${NON_INTERACTIVE}" == "true" ]]; then
            # Non-interactive + clean: require --force-destroy to prevent silent data loss.
            # Without --force-destroy, print a warning + the volume list and exit 1 so the
            # operator can run 'bash scripts/dev-backup.sh' first.
            if [[ "${FORCE_DESTROY}" != "true" ]]; then
                printf "%s\n" "" >&2
                printf "ERROR: --clean --non-interactive requires --force-destroy to prevent\n" >&2
                printf "accidental data loss. The following volumes would be permanently deleted:\n" >&2
                printf "\n" >&2
                docker compose config --volumes 2>/dev/null | sed 's/^/  - /' >&2 || \
                    printf "  (could not enumerate volumes — docker compose not available)\n" >&2
                printf "\n" >&2
                printf "Back up first: bash scripts/dev-backup.sh\n" >&2
                printf "Then re-run with: --clean --non-interactive --force-destroy\n" >&2
                printf "\n" >&2
                exit 1
            fi
            # --force-destroy provided: proceed with volume removal
            log INFO "Removing Docker volumes (--clean --non-interactive --force-destroy)..."
            local clean_exit=0
            docker compose down -v --timeout 30 >>"${LOG_FILE:-/dev/null}" 2>&1 || clean_exit=$?
            if [[ ${clean_exit} -ne 0 ]]; then
                log WARN "docker compose down -v exited with code ${clean_exit}. Continuing..."
            fi
        else
            # Interactive + clean: prompt for confirmation
            local confirm=""
            printf "%sWARNING: --clean flag set. This will remove all Docker Compose project volumes (database data, vault data, bootstrap secrets).%s\n" \
                "${YELLOW}" "${RESET}" >&2
            printf "Are you sure you want to remove all volumes? [y/N]: " >&2
            if ! read -r -t 30 confirm; then
                printf "\n" >&2
                die "[START] No confirmation received for volume removal within 30 seconds" \
                    "Re-run with --clean and confirm, or remove --clean to preserve volumes"
            fi
            case "${confirm}" in
                [yY]|[yY][eE][sS])
                    log INFO "User confirmed volume removal. Removing Docker volumes..."
                    local clean_exit=0
                    docker compose down -v --timeout 30 >>"${LOG_FILE:-/dev/null}" 2>&1 || clean_exit=$?
                    if [[ ${clean_exit} -ne 0 ]]; then
                        log WARN "docker compose down -v exited with code ${clean_exit}. Continuing..."
                    fi
                    ;;
                *)
                    die "[START] User declined volume removal" \
                        "Re-run without --clean to preserve existing volumes, or confirm removal"
                    ;;
            esac
        fi
    fi

    # Start all 15 long-running services
    log INFO "Starting all services via docker compose up -d..."
    local up_tmp="${LOG_FILE:-/tmp/install-start}.up.tmp"
    local up_exit=0

    docker compose up -d >"${up_tmp}" 2>&1 || up_exit=$?

    # Append compose output to log file
    if [[ -n "${LOG_FILE}" ]] && [[ -f "${up_tmp}" ]]; then
        cat "${up_tmp}" >> "${LOG_FILE}" 2>/dev/null || true
    fi

    if [[ ${up_exit} -ne 0 ]]; then
        printf "\n%s[START] docker compose up -d failed (exit code: %d)%s\n" \
            "${RED}" "${up_exit}" "${RESET}" >&2
        printf "Compose error output:\n" >&2
        cat "${up_tmp}" >&2 2>/dev/null || true
        rm -f "${up_tmp}"
        die "[START] docker compose up -d failed" \
            "Check Docker resources (disk, memory). Compose output shown above."
    fi

    rm -f "${up_tmp}"
    log INFO "All services started successfully."
}

phase_verify() {
    log INFO "Starting health verification phase..."

    local timeout_seconds="${MINTKEY_HEALTH_TIMEOUT_SECONDS:-120}"
    local poll_interval=2
    local elapsed=0

    # The 15 long-running services to verify
    local services="postgres keycloak admin-api admin-ui mcp-server broker vault-adapter kong proxy-plugin kong-syncer demo-backend otel-collector jaeger prometheus grafana"

    # Get container names for the compose project
    local container_names=""
    container_names="$(docker compose ps --format '{{.Name}}' 2>/dev/null || true)"

    if [[ -z "${container_names}" ]]; then
        die "[VERIFY] No running containers found. docker compose ps returned empty output." \
            "Ensure 'docker compose up -d' completed successfully."
    fi

    log INFO "Polling healthcheck status for 15 services (timeout: ${timeout_seconds}s, interval: ${poll_interval}s)..."

    # Use associative array to track health status per service
    declare -A health_status

    while [[ ${elapsed} -lt ${timeout_seconds} ]]; do
        local all_healthy=true

        for svc in ${services}; do
            # Find the container name for this service from compose output
            local container=""
            container="$(printf "%s\n" "${container_names}" | grep -E "(^|[-_])${svc}([-_]|$)" | head -1 || true)"

            if [[ -z "${container}" ]]; then
                # Try refreshing container names in case they weren't ready yet
                container_names="$(docker compose ps --format '{{.Name}}' 2>/dev/null || true)"
                container="$(printf "%s\n" "${container_names}" | grep -E "(^|[-_])${svc}([-_]|$)" | head -1 || true)"
            fi

            if [[ -z "${container}" ]]; then
                health_status["${svc}"]="no_container"
                all_healthy=false
                continue
            fi

            # Query Docker healthcheck status
            local status=""
            status="$(docker inspect --format='{{.State.Health.Status}}' "${container}" 2>/dev/null || true)"

            if [[ "${status}" == "healthy" ]]; then
                health_status["${svc}"]="healthy"
            else
                health_status["${svc}"]="${status:-unknown}"
                all_healthy=false
            fi
        done

        if [[ "${all_healthy}" == "true" ]]; then
            log INFO "All 15 services report healthy after ${elapsed} seconds."
            return 0
        fi

        sleep "${poll_interval}"
        elapsed=$((elapsed + poll_interval))
    done

    # Timeout reached — collect unhealthy services and display logs
    local unhealthy_list=""
    for svc in ${services}; do
        if [[ "${health_status["${svc}"]:-unknown}" != "healthy" ]]; then
            unhealthy_list="${unhealthy_list}${svc} (${health_status["${svc}"]:-unknown}), "
        fi
    done

    # Remove trailing ", "
    unhealthy_list="${unhealthy_list%, }"

    printf "\n%s[VERIFY] Health check timed out after %d seconds.%s\n" \
        "${RED}" "${timeout_seconds}" "${RESET}" >&2
    printf "Unhealthy services: %s\n\n" "${unhealthy_list}" >&2

    # Display last 50 lines of logs for each unhealthy service
    for svc in ${services}; do
        if [[ "${health_status["${svc}"]:-unknown}" != "healthy" ]]; then
            printf "%s--- Logs for %s (status: %s) ---%s\n" \
                "${YELLOW}" "${svc}" "${health_status["${svc}"]:-unknown}" "${RESET}" >&2
            docker compose logs --tail=50 "${svc}" >&2 2>/dev/null || true
            printf "\n" >&2
        fi
    done

    die "[VERIFY] Services failed to become healthy within ${timeout_seconds} seconds: ${unhealthy_list}" \
        "Check logs with 'docker compose logs <service>'. Unhealthy service logs shown above."
}

print_summary() {
    local domain="${CONFIGURED_DOMAIN}"

    printf "\n"
    log INFO "=========================================="
    log INFO "  Mintkey Stack — Ready"
    log INFO "=========================================="
    printf "\n"
    printf "%s  %-14s  %s%s\n" "${GREEN}" "SERVICE" "URL" "${RESET}"
    printf "%s  %-14s  %s%s\n" "${GREEN}" "--------------" "----------------------------" "${RESET}"
    printf "%s  %-14s  http://%s:%s%s\n" "${GREEN}" "Admin UI" "${domain}" "8081" "${RESET}"
    printf "%s  %-14s  http://%s:%s%s\n" "${GREEN}" "Admin API" "${domain}" "8080" "${RESET}"
    printf "%s  %-14s  http://%s:%s%s\n" "${GREEN}" "MCP Server" "${domain}" "8082" "${RESET}"
    printf "%s  %-14s  http://%s:%s%s\n" "${GREEN}" "Kong proxy" "${domain}" "8000" "${RESET}"
    printf "%s  %-14s  http://%s:%s%s\n" "${GREEN}" "Keycloak" "${domain}" "8443" "${RESET}"
    printf "%s  %-14s  http://%s:%s%s\n" "${GREEN}" "Grafana" "${domain}" "3003" "${RESET}"
    printf "%s  %-14s  http://%s:%s%s\n" "${GREEN}" "Jaeger" "${domain}" "16686" "${RESET}"
    printf "\n"
    printf "%s  Bootstrap admin password: ./data/bootstrap-secrets/admin_password%s\n" "${GREEN}" "${RESET}"
    printf "\n"
}

# --- Platform compatibility check ---
check_platform_compatibility() {
    local os
    os="$(detect_os)"
    local os_version=""
    local os_label=""
    local is_tested=true

    case "${os}" in
        ubuntu|debian|fedora)
            if [[ -f /etc/os-release ]]; then
                # shellcheck disable=SC1091 # /etc/os-release is a system file, not a project file
                os_version="$(. /etc/os-release && printf "%s" "${VERSION_ID:-}")"
                # shellcheck disable=SC1091
                os_label="$(. /etc/os-release && printf "%s" "${PRETTY_NAME:-${ID} ${VERSION_ID}}")"
            fi
            ;;
        macos)
            if command -v sw_vers >/dev/null 2>&1; then
                os_version="$(sw_vers -productVersion 2>/dev/null || true)"
            fi
            os_label="macOS ${os_version}"
            ;;
        *)
            os_label="unknown ($(uname -s 2>/dev/null || printf 'undetected'))"
            is_tested=false
            ;;
    esac

    # Compare against minimum supported versions
    if [[ "${is_tested}" == "true" ]] && [[ -n "${os_version}" ]]; then
        case "${os}" in
            ubuntu)
                # Minimum: 22.04 — compare major.minor as integers
                local ubuntu_major="${os_version%%.*}"
                local ubuntu_minor="${os_version#*.}"
                ubuntu_minor="${ubuntu_minor%%.*}"
                if [[ "${ubuntu_major}" -lt 22 ]] || { [[ "${ubuntu_major}" -eq 22 ]] && [[ "${ubuntu_minor}" -lt 4 ]]; }; then
                    is_tested=false
                fi
                ;;
            debian)
                # Minimum: 12
                local debian_major="${os_version%%.*}"
                if [[ "${debian_major}" -lt 12 ]]; then
                    is_tested=false
                fi
                ;;
            fedora)
                # Minimum: 38
                local fedora_major="${os_version%%.*}"
                if [[ "${fedora_major}" -lt 38 ]]; then
                    is_tested=false
                fi
                ;;
            macos)
                # Minimum: 13 — compare major version
                local macos_major="${os_version%%.*}"
                if [[ "${macos_major}" -lt 13 ]]; then
                    is_tested=false
                fi
                ;;
        esac
    elif [[ "${is_tested}" == "true" ]] && [[ -z "${os_version}" ]]; then
        # Known OS family but could not determine version
        is_tested=false
    fi

    if [[ "${is_tested}" == "false" ]]; then
        printf "%sWarning: Detected OS '%s' is untested.%s\n" "${YELLOW}" "${os_label}" "${RESET}" >&2
        printf "%sTested platforms: Ubuntu 22.04+, Debian 12+, Fedora 38+, macOS 13+%s\n" "${YELLOW}" "${RESET}" >&2
        printf "%sThe script may work but is not guaranteed on this platform.%s\n" "${YELLOW}" "${RESET}" >&2

        if [[ "${NON_INTERACTIVE}" == "true" ]]; then
            log WARN "Untested OS '${os_label}' — continuing in non-interactive mode."
            return 0
        fi

        local confirm=""
        printf "Continue anyway? [y/N]: " >&2
        if ! read -r -t 30 confirm; then
            printf "\n" >&2
            die "No response within 30 seconds. Aborting." \
                "Re-run on a tested platform or use --non-interactive to skip this check"
        fi
        case "${confirm}" in
            [yY]|[yY][eE][sS])
                log WARN "User chose to continue on untested OS '${os_label}'."
                ;;
            *)
                die "Aborted: untested platform '${os_label}'" \
                    "Use a tested platform (Ubuntu 22.04+, Debian 12+, Fedora 38+, macOS 13+)"
                ;;
        esac
    fi
}

# --- Main entry point ---
main() {
    parse_args "$@"

    check_platform_compatibility

    phase_clone
    phase_prerequisites
    phase_configure
    phase_build
    phase_migrate
    phase_seed
    phase_start
    phase_verify
    print_summary
}

main "$@"
