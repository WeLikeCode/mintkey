"""
Shared helpers for install_script property-based tests.

Provides a helper to invoke Bash functions from install.sh via subprocess,
sourcing the script in a subshell and calling the target function.

The script's Bash 4.0 version guard and main() call are stripped so tests
can run on macOS default Bash 3.2 (the regex features under test work on 3.2+).
"""
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


def _get_sourceable_script() -> str:
    """
    Read install.sh and return a version that can be sourced without
    triggering the Bash version guard, set -euo pipefail, or running main().
    """
    content = INSTALL_SCRIPT.read_text()
    # Remove the version guard block (from the if to the closing fi)
    content = re.sub(
        r'if \[\[ -z "\$\{BASH_VERSINFO\[0\]:-\}" \]\].*?fi\n',
        '',
        content,
        flags=re.DOTALL,
    )
    # Remove set -euo pipefail so unrelated errors don't kill the subshell
    content = content.replace('set -euo pipefail', '# set -euo pipefail')
    # Remove the main "$@" call at the bottom so the script doesn't execute
    content = re.sub(r'^main "\$@"\s*$', '# main "$@"', content, flags=re.MULTILINE)
    return content


def invoke_bash_function(function_name: str, *args: str) -> subprocess.CompletedProcess:
    """
    Source install.sh in a subshell and invoke the named function with the given arguments.

    Returns the CompletedProcess with stdout, stderr, and returncode.
    """
    escaped_args = " ".join(f'"{a}"' for a in args)
    script_content = _get_sourceable_script()

    bash_code = f"""{script_content}

# Call the target function
{function_name} {escaped_args}
"""
    result = subprocess.run(
        ["bash", "-c", bash_code],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result
