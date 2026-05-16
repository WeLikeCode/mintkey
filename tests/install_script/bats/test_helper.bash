#!/usr/bin/env bash
# Helper for bats tests — sources install.sh functions without executing main()
# or triggering the Bash version guard.

# Resolve paths
BATS_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${BATS_TEST_DIR}/../../.." && pwd)"
INSTALL_SCRIPT="${REPO_ROOT}/install.sh"

# Load bats-support and bats-assert
load "${REPO_ROOT}/node_modules/bats-support/load.bash"
load "${REPO_ROOT}/node_modules/bats-assert/load.bash"

# Source install.sh functions by creating a modified version in a temp file
# that strips the version guard, set -euo pipefail, and main call.
_source_install_script() {
    local tmp_script
    tmp_script="$(mktemp)"

    # Read install.sh, strip problematic parts
    sed \
        -e '/^set -euo pipefail/d' \
        -e '/^if \[\[ -z "\${BASH_VERSINFO\[0\]:-}" \]\]/,/^fi$/d' \
        -e '/^main "\$@"$/d' \
        -e '/^_init_log_file$/d' \
        "${INSTALL_SCRIPT}" > "${tmp_script}"

    # Disable color and log file for testing
    export NO_COLOR=1
    export LOG_FILE=""

    # Source the modified script
    # shellcheck disable=SC1090
    source "${tmp_script}"

    # Reset color variables (since we set NO_COLOR before sourcing)
    GREEN=""
    RED=""
    YELLOW=""
    RESET=""

    rm -f "${tmp_script}"
}

# Source the script once
_source_install_script
