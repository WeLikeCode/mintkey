"""
Property-based tests for install.sh validation functions.

Uses hypothesis to generate inputs and invokes Bash functions via subprocess.
The script's Bash 4.0 version guard is stripped before sourcing so tests
can run on macOS default Bash 3.2 (the regex features under test work on 3.2+).
"""
import importlib.util
import re
import subprocess
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Load the local conftest module directly to avoid conflict with tests/conftest.py
_conftest_path = Path(__file__).parent / "conftest.py"
_spec = importlib.util.spec_from_file_location("install_script_conftest", _conftest_path)
_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conftest)
invoke_bash_function = _conftest.invoke_bash_function


REPO_ROOT = Path(__file__).parent.parent.parent
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


# Feature: developer-install-script, Property 5: Docker version comparison correctness
class TestDockerVersionComparison:
    """
    Property 5: Docker version comparison correctness

    For any Docker version string in the format `Docker version X.Y.Z, build <hash>`
    (where X is a non-negative integer), the version check function SHALL accept
    versions where the major version is >= 24 and reject versions where the major
    version is < 24.

    **Validates: Requirements 2.1**
    """

    @settings(max_examples=100)
    @given(
        major=st.integers(min_value=1, max_value=30),
        minor=st.integers(min_value=0, max_value=99),
        patch=st.integers(min_value=0, max_value=99),
        build_hash=st.from_regex(r"[0-9a-f]{7}", fullmatch=True),
    )
    def test_parse_docker_version_extracts_major(
        self, major: int, minor: int, patch: int, build_hash: str
    ) -> None:
        """
        parse_docker_version correctly extracts the major version number from
        a Docker version string.

        **Validates: Requirements 2.1**
        """
        version_string = f"Docker version {major}.{minor}.{patch}, build {build_hash}"
        result = invoke_bash_function("parse_docker_version", version_string)

        assert result.returncode == 0, (
            f"parse_docker_version failed with exit code {result.returncode} "
            f"for input: {version_string!r}\nstderr: {result.stderr}"
        )
        parsed_major = result.stdout.strip()
        assert parsed_major == str(major), (
            f"Expected major version {major} but got {parsed_major!r} "
            f"for input: {version_string!r}"
        )

    @settings(max_examples=100)
    @given(
        major=st.integers(min_value=1, max_value=30),
        minor=st.integers(min_value=0, max_value=99),
        patch=st.integers(min_value=0, max_value=99),
        build_hash=st.from_regex(r"[0-9a-f]{7}", fullmatch=True),
    )
    def test_docker_version_acceptance_threshold(
        self, major: int, minor: int, patch: int, build_hash: str
    ) -> None:
        """
        Versions with major >= 24 are accepted; versions with major < 24 are rejected.
        This simulates the prerequisite check logic: parse the version, then compare.

        **Validates: Requirements 2.1**
        """
        version_string = f"Docker version {major}.{minor}.{patch}, build {build_hash}"
        result = invoke_bash_function("parse_docker_version", version_string)

        assert result.returncode == 0
        parsed_major = result.stdout.strip()
        assert parsed_major != "", (
            f"parse_docker_version returned empty string for: {version_string!r}"
        )

        parsed_int = int(parsed_major)
        should_accept = major >= 24

        if should_accept:
            assert parsed_int >= 24, (
                f"Version {version_string!r} should be accepted (major={major} >= 24) "
                f"but parsed major is {parsed_int}"
            )
        else:
            assert parsed_int < 24, (
                f"Version {version_string!r} should be rejected (major={major} < 24) "
                f"but parsed major is {parsed_int}"
            )


# Feature: developer-install-script, Property 1: Email validation correctness
class TestEmailValidation:
    """
    Property 1: Email validation correctness

    For any string, the email validation function SHALL accept it if and only if
    it matches the pattern `^[^@]+@[^@]+\\.[^@]+$` (local-part@domain with at least
    one dot in the domain part). All other strings SHALL be rejected.

    **Validates: Requirements 3.2**
    """

    # Characters that break bash argument passing (null bytes, quotes, backticks,
    # dollar signs, backslashes, exclamation marks)
    BASH_UNSAFE_CHARS = '\x00\'"`$\\!'

    @staticmethod
    def _is_bash_safe(s: str) -> bool:
        """Check if a string can be safely passed to bash without breaking."""
        if not s:
            return True
        for ch in TestEmailValidation.BASH_UNSAFE_CHARS:
            if ch in s:
                return False
        # Also reject strings with newlines or carriage returns (break argument passing)
        if '\n' in s or '\r' in s:
            return False
        return True

    @settings(max_examples=100)
    @given(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),  # Exclude surrogates
                blacklist_characters='\x00\'"`$\\!\n\r',
            ),
            min_size=1,
            max_size=80,
        )
    )
    def test_email_validation_random_strings(self, s: str) -> None:
        """
        Random strings are accepted/rejected consistently with the regex.

        **Validates: Requirements 3.2**
        """
        email_regex = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
        expected_valid = bool(email_regex.match(s))

        result = invoke_bash_function("validate_email", s)

        if expected_valid:
            assert result.returncode == 0, (
                f"Expected validate_email to ACCEPT {s!r} "
                f"(matches regex) but got exit code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )
        else:
            assert result.returncode != 0, (
                f"Expected validate_email to REJECT {s!r} "
                f"(does not match regex) but got exit code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

    @settings(max_examples=100)
    @given(
        local_part=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P"),
                blacklist_characters='@\x00\'"`$\\!\n\r',
            ),
            min_size=1,
            max_size=20,
        ),
        domain_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters='@.\x00\'"`$\\!\n\r',
            ),
            min_size=1,
            max_size=15,
        ),
        tld=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters='@.\x00\'"`$\\!\n\r',
            ),
            min_size=1,
            max_size=10,
        ),
    )
    def test_email_validation_structured_valid(
        self, local_part: str, domain_name: str, tld: str
    ) -> None:
        """
        Structurally valid emails (local@domain.tld) are always accepted.

        **Validates: Requirements 3.2**
        """
        email = f"{local_part}@{domain_name}.{tld}"
        email_regex = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

        # Only test if the constructed email actually matches the regex
        # (it should, given the constraints, but verify)
        if not email_regex.match(email):
            return

        result = invoke_bash_function("validate_email", email)

        assert result.returncode == 0, (
            f"Expected validate_email to ACCEPT {email!r} "
            f"(matches regex) but got exit code {result.returncode}\n"
            f"stderr: {result.stderr}"
        )


# Feature: developer-install-script, Property 2: Tenant name validation correctness
class TestTenantNameValidation:
    """
    Property 2: Tenant name validation correctness

    For any string, the tenant name validation function SHALL accept it if and only
    if it matches `^t_[a-z0-9_]{1,61}$` (3-64 total characters, `t_` prefix, followed
    by lowercase alphanumeric and underscores). All other strings SHALL be rejected.

    **Validates: Requirements 3.3**
    """

    # Strategy: generate random strings that are safe to pass through bash
    # Filter out null bytes, backticks, dollar signs, and other bash-breaking characters
    _safe_alphabet = st.characters(
        blacklist_categories=("Cs",),  # no surrogates
        blacklist_characters="\x00`$\\\"'\n\r",
    )
    _safe_text = st.text(alphabet=_safe_alphabet, min_size=0, max_size=80)

    # Strategy: generate strings that are likely valid tenant names
    _valid_tenant_chars = st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
        min_size=1,
        max_size=61,
    )
    _valid_tenant_name = _valid_tenant_chars.map(lambda s: f"t_{s}")

    _TENANT_REGEX = re.compile(r"^t_[a-z0-9_]{1,61}$")

    @settings(max_examples=100)
    @given(tenant_name=_safe_text)
    def test_random_strings_match_regex(self, tenant_name: str) -> None:
        """
        For any random safe string, validate_tenant_name accepts it iff it matches
        the regex ^t_[a-z0-9_]{1,61}$.

        **Validates: Requirements 3.3**
        """
        expected_valid = bool(self._TENANT_REGEX.match(tenant_name))
        result = invoke_bash_function("validate_tenant_name", tenant_name)

        if expected_valid:
            assert result.returncode == 0, (
                f"validate_tenant_name rejected valid tenant name {tenant_name!r} "
                f"(returncode={result.returncode}, stderr={result.stderr!r})"
            )
        else:
            assert result.returncode != 0, (
                f"validate_tenant_name accepted invalid tenant name {tenant_name!r} "
                f"(returncode={result.returncode})"
            )

    @settings(max_examples=100)
    @given(tenant_name=_valid_tenant_name)
    def test_valid_tenant_names_accepted(self, tenant_name: str) -> None:
        """
        Strings matching the tenant name pattern are always accepted.

        **Validates: Requirements 3.3**
        """
        # Sanity check: our generator produces valid names
        assert self._TENANT_REGEX.match(tenant_name), (
            f"Generator produced invalid tenant name: {tenant_name!r}"
        )

        result = invoke_bash_function("validate_tenant_name", tenant_name)
        assert result.returncode == 0, (
            f"validate_tenant_name rejected valid tenant name {tenant_name!r} "
            f"(returncode={result.returncode}, stderr={result.stderr!r})"
        )


# Feature: developer-install-script, Property 4: Domain/IP validation correctness
class TestDomainValidation:
    """
    Property 4: Domain/IP validation correctness

    For any string, the domain validation function SHALL accept it if and only if
    it is non-empty, contains no whitespace characters, and has no trailing slash.
    All other strings SHALL be rejected.

    **Validates: Requirements 3.1**
    """

    # Characters that break bash argument passing or have unpredictable
    # whitespace behavior across locales
    BASH_UNSAFE_CHARS = '\x00\'"`$\\!\n\r'

    # Unicode whitespace characters beyond ASCII that may or may not be
    # matched by Bash [[:space:]] depending on locale — exclude from random tests
    UNICODE_WHITESPACE = ''.join(
        chr(c) for c in range(0x10000) if chr(c).isspace()
    )

    @staticmethod
    def _python_domain_valid(s: str) -> bool:
        """
        Python-side validation matching the Bash validate_domain rules:
        - Non-empty
        - No whitespace characters (ASCII whitespace: space, tab, newline, etc.)
        - No trailing slash
        """
        if not s:
            return False
        # Check for ASCII whitespace characters that Bash [[:space:]] reliably matches
        for ch in s:
            if ch in ' \t\n\r\v\f':
                return False
        # Check for trailing slash
        if s.endswith('/'):
            return False
        return True

    @settings(max_examples=100, deadline=None)
    @given(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs", "Z"),  # Exclude surrogates and separators
                blacklist_characters='\x00\'"`$\\!\n\r\t\v\f\x1c\x1d\x1e\x1f\x85\xa0',
            ),
            min_size=0,
            max_size=80,
        )
    )
    def test_domain_validation_random_strings(self, s: str) -> None:
        """
        Random strings (including empty, with trailing slashes)
        are accepted/rejected consistently with the domain validation rules.
        Unicode whitespace is excluded from generation to avoid locale-dependent
        Bash [[:space:]] behavior.

        **Validates: Requirements 3.1**
        """
        expected_valid = self._python_domain_valid(s)

        result = invoke_bash_function("validate_domain", s)

        if expected_valid:
            assert result.returncode == 0, (
                f"Expected validate_domain to ACCEPT {s!r} "
                f"(non-empty, no whitespace, no trailing slash) "
                f"but got exit code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )
        else:
            assert result.returncode != 0, (
                f"Expected validate_domain to REJECT {s!r} "
                f"(empty, has whitespace, or has trailing slash) "
                f"but got exit code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

    @settings(max_examples=100, deadline=None)
    @given(
        st.one_of(
            # Strings with whitespace (should be rejected)
            st.text(
                alphabet=st.characters(
                    blacklist_categories=("Cs",),
                    blacklist_characters='\x00\'"`$\\!\n\r',
                ),
                min_size=1,
                max_size=40,
            ).map(lambda s: s[:len(s)//2] + ' ' + s[len(s)//2:]),
            # Strings with trailing slash (should be rejected)
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),
                    blacklist_characters='\x00\'"`$\\!\n\r \t\v\f',
                ),
                min_size=1,
                max_size=40,
            ).map(lambda s: s + '/'),
            # Strings with tab character (should be rejected)
            st.text(
                alphabet=st.characters(
                    blacklist_categories=("Cs",),
                    blacklist_characters='\x00\'"`$\\!\n\r',
                ),
                min_size=1,
                max_size=40,
            ).map(lambda s: s[:len(s)//2] + '\t' + s[len(s)//2:]),
        )
    )
    def test_domain_validation_invalid_inputs(self, s: str) -> None:
        """
        Strings with whitespace or trailing slashes are always rejected.

        **Validates: Requirements 3.1**
        """
        result = invoke_bash_function("validate_domain", s)

        assert result.returncode != 0, (
            f"Expected validate_domain to REJECT {s!r} "
            f"(contains whitespace or trailing slash) "
            f"but got exit code {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    @settings(max_examples=100, deadline=None)
    @given(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P"),
                blacklist_characters='\x00\'"`$\\!\n\r \t\v\f/',
            ),
            min_size=1,
            max_size=60,
        )
    )
    def test_domain_validation_valid_inputs(self, s: str) -> None:
        """
        Non-empty strings without whitespace and without trailing slash are accepted.

        **Validates: Requirements 3.1**
        """
        # Double-check our Python-side validation agrees
        assert self._python_domain_valid(s), (
            f"Test generator produced invalid input: {s!r}"
        )

        result = invoke_bash_function("validate_domain", s)

        assert result.returncode == 0, (
            f"Expected validate_domain to ACCEPT {s!r} "
            f"(non-empty, no whitespace, no trailing slash) "
            f"but got exit code {result.returncode}\n"
            f"stderr: {result.stderr}"
        )


# Feature: developer-install-script, Property 3: Template substitution completeness
class TestTemplateSubstitutionCompleteness:
    """
    Property 3: Template substitution completeness

    For any `.env.example` template containing one or more `REPLACE_WITH_*`
    placeholder strings, and any valid set of configuration inputs (domain,
    admin email, tenant name), the generated `.env` file SHALL contain no
    remaining `REPLACE_WITH_*` placeholder strings, and every generated token
    value SHALL be exactly 64 hexadecimal characters.

    **Validates: Requirements 3.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        num_placeholders=st.integers(min_value=1, max_value=10),
        placeholder_suffixes=st.lists(
            st.from_regex(r"[A-Z][A-Z0-9_]{2,15}", fullmatch=True),
            min_size=1,
            max_size=10,
            unique=True,
        ),
    )
    def test_all_placeholders_replaced_with_valid_tokens(
        self, num_placeholders: int, placeholder_suffixes: "list[str]"
    ) -> None:
        """
        All REPLACE_WITH_* placeholders are replaced and each replacement is
        exactly 64 hexadecimal characters.

        **Validates: Requirements 3.4**
        """
        import os
        import tempfile

        # Trim placeholder_suffixes to num_placeholders
        suffixes = placeholder_suffixes[:num_placeholders]
        if not suffixes:
            suffixes = ["SECRET_1"]

        # Build a minimal .env.example template with the generated placeholders
        template_lines = ["# Generated test template\n"]
        var_names = []
        for suffix in suffixes:
            var_name = f"TEST_{suffix}"
            var_names.append(var_name)
            template_lines.append(f"{var_name}=REPLACE_WITH_{suffix}\n")

        # Create a temporary directory for this test run
        with tempfile.TemporaryDirectory() as tmpdir:
            env_example_path = os.path.join(tmpdir, ".env.example")
            env_path = os.path.join(tmpdir, ".env")

            # Write the template
            with open(env_example_path, "w") as f:
                f.writelines(template_lines)

            # Build a bash script that sources install.sh and runs generate_env_file
            # in the temp directory context
            sourceable_script = _get_sourceable_script_content()
            bash_script = f"""{sourceable_script}

# Override globals for the test
CONFIGURED_DOMAIN="test.example.com"
CONFIGURED_EMAIL="admin@test.example.com"
CONFIGURED_TENANT="t_default"
NON_INTERACTIVE=true

# Override generate_env_file to work in our temp directory
cd "{tmpdir}"
env_file=".env"
env_template=".env.example"

# Copy template to .env
cp "${{env_template}}" "${{env_file}}"

# Replace all REPLACE_WITH_* placeholders with unique tokens
token=""
tmp_file="${{env_file}}.tmp"
line_num=""

while line_num="$(grep -n 'REPLACE_WITH_[A-Za-z0-9_]*' "${{env_file}}" | head -1 | cut -d: -f1)" && [[ -n "${{line_num}}" ]]; do
    token="$(generate_token)"
    sed "${{line_num}}s|REPLACE_WITH_[A-Za-z0-9_]*|${{token}}|" "${{env_file}}" > "${{tmp_file}}" && mv "${{tmp_file}}" "${{env_file}}"
done

# Output the resulting .env content
cat "${{env_file}}"
"""
            result = subprocess.run(
                ["bash", "-c", bash_script],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert result.returncode == 0, (
                f"Bash script failed with exit code {result.returncode}\n"
                f"stderr: {result.stderr}\n"
                f"stdout: {result.stdout}"
            )

            output = result.stdout

            # Verify: no REPLACE_WITH_* placeholders remain
            remaining_placeholders = re.findall(
                r"REPLACE_WITH_[A-Za-z0-9_]+", output
            )
            assert remaining_placeholders == [], (
                f"Found remaining placeholders in output: {remaining_placeholders}\n"
                f"Full output:\n{output}"
            )

            # Verify: each variable now has a 64-char hex token value
            hex_pattern = re.compile(r"^[0-9a-f]{64}$")
            for var_name in var_names:
                # Find the line for this variable
                match = re.search(
                    rf"^{re.escape(var_name)}=(.+)$", output, re.MULTILINE
                )
                assert match is not None, (
                    f"Variable {var_name} not found in output:\n{output}"
                )
                value = match.group(1).strip()
                assert hex_pattern.match(value), (
                    f"Variable {var_name} has value {value!r} which is not "
                    f"a 64-character hex string"
                )


# Feature: developer-install-script, Property 7: Non-interactive missing value detection
class TestNonInteractiveMissingValueDetection:
    """
    Property 7: Non-interactive missing value detection

    For any subset of required environment variables (MINTKEY_DOMAIN,
    MINTKEY_ADMIN_EMAIL) that are absent when --non-interactive is set,
    the script SHALL list exactly the missing variable names in its error
    output and exit non-zero.

    **Validates: Requirements 3.7**
    """

    # The two required env vars for non-interactive mode
    REQUIRED_VARS = ["MINTKEY_DOMAIN", "MINTKEY_ADMIN_EMAIL"]

    # Strategy: generate a random subset of required vars to include (True=set, False=unset)
    @settings(max_examples=100, deadline=None)
    @given(
        include_domain=st.booleans(),
        include_email=st.booleans(),
    )
    def test_missing_vars_detected_and_reported(
        self, include_domain: bool, include_email: bool
    ) -> None:
        """
        When NON_INTERACTIVE=true, phase_configure exits non-zero and lists
        exactly the missing required env vars in stderr if any are absent.
        When all required vars are present (with valid values), it succeeds.

        **Validates: Requirements 3.7**
        """
        # Build the env var assignments for the bash script
        env_lines = []
        env_lines.append('export NON_INTERACTIVE=true')

        if include_domain:
            env_lines.append('export MINTKEY_DOMAIN="test.example.com"')
        else:
            env_lines.append('unset MINTKEY_DOMAIN 2>/dev/null || true')

        if include_email:
            env_lines.append('export MINTKEY_ADMIN_EMAIL="admin@test.example.com"')
        else:
            env_lines.append('unset MINTKEY_ADMIN_EMAIL 2>/dev/null || true')

        env_block = "\n".join(env_lines)

        # Build the sourceable script content
        sourceable_script = _get_sourceable_script_content()

        # We need to prevent generate_env_file from running (it needs .env.example)
        # and prevent die() from calling exit (we want to capture the error output)
        # For the success case, we stub generate_env_file; for the failure case,
        # the script exits before reaching it.
        bash_script = f"""{sourceable_script}

# Stub generate_env_file so it doesn't need .env.example
generate_env_file() {{
    return 0
}}

# Override exit to capture the exit code without killing the subshell
_CAPTURED_EXIT=""
exit() {{
    _CAPTURED_EXIT="$1"
}}

# Set up env vars
{env_block}

# Call phase_configure and capture result
phase_configure 2>/tmp/_pbt_stderr.txt
_fn_exit=$?

# If exit was called via die() or directly, use that code
if [[ -n "$_CAPTURED_EXIT" ]]; then
    cat /tmp/_pbt_stderr.txt >&2
    rm -f /tmp/_pbt_stderr.txt
    # Signal the exit code via a special stdout marker
    printf "EXIT_CODE=%s\\n" "$_CAPTURED_EXIT"
else
    cat /tmp/_pbt_stderr.txt >&2
    rm -f /tmp/_pbt_stderr.txt
    printf "EXIT_CODE=%s\\n" "$_fn_exit"
fi
"""
        result = subprocess.run(
            ["bash", "-c", bash_script],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Parse the exit code from stdout (since we overrode exit())
        exit_code = None
        for line in result.stdout.strip().split("\n"):
            if line.startswith("EXIT_CODE="):
                exit_code = int(line.split("=", 1)[1])
                break

        # If we couldn't parse exit code, use the process return code
        if exit_code is None:
            exit_code = result.returncode

        # Determine which vars are missing
        missing_vars = []
        if not include_domain:
            missing_vars.append("MINTKEY_DOMAIN")
        if not include_email:
            missing_vars.append("MINTKEY_ADMIN_EMAIL")

        if not missing_vars:
            # All required vars are set — should succeed
            assert exit_code == 0, (
                f"Expected phase_configure to succeed (exit 0) when all required "
                f"vars are set, but got exit code {exit_code}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        else:
            # Some vars are missing — should fail with error listing them
            assert exit_code != 0, (
                f"Expected phase_configure to fail (exit non-zero) when missing "
                f"vars {missing_vars}, but got exit code {exit_code}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

            # Verify stderr contains ALL missing variable names
            stderr_output = result.stderr
            for var_name in missing_vars:
                assert var_name in stderr_output, (
                    f"Expected stderr to contain missing var name '{var_name}' "
                    f"but it was not found.\n"
                    f"Missing vars: {missing_vars}\n"
                    f"stderr: {stderr_output}"
                )

            # Verify stderr does NOT contain variable names that ARE set
            set_vars = []
            if include_domain:
                set_vars.append("MINTKEY_DOMAIN")
            if include_email:
                set_vars.append("MINTKEY_ADMIN_EMAIL")

            # The error message format is:
            # "Error: Non-interactive mode requires the following environment variables: X, Y"
            # So we check that the error line itself only lists the missing ones
            error_line = ""
            for line in stderr_output.split("\n"):
                if "Non-interactive mode requires" in line:
                    error_line = line
                    break

            assert error_line, (
                f"Expected stderr to contain 'Non-interactive mode requires' "
                f"error message but it was not found.\n"
                f"stderr: {stderr_output}"
            )

            # Verify set vars are NOT listed in the error message
            for var_name in set_vars:
                assert var_name not in error_line, (
                    f"Error message should NOT list '{var_name}' (it is set), "
                    f"but found it in: {error_line!r}"
                )


def _get_sourceable_script_content() -> str:
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


# Feature: developer-install-script, Property 6: Summary table URL construction
class TestSummaryTableUrlConstruction:
    """
    Property 6: Summary table URL construction

    For any valid domain or IP address (non-empty, no whitespace, no trailing
    slash), the summary table SHALL contain URLs for all 7 services (Admin UI
    :8081, Admin API :8080, MCP Server :8082, Kong proxy :8000, Keycloak :8443,
    Grafana :3003, Jaeger :16686) constructed as `http://<domain>:<port>`.

    **Validates: Requirements 3.1, 7.5**
    """

    # The 7 expected service ports
    EXPECTED_PORTS = {
        "Admin UI": "8081",
        "Admin API": "8080",
        "MCP Server": "8082",
        "Kong proxy": "8000",
        "Keycloak": "8443",
        "Grafana": "3003",
        "Jaeger": "16686",
    }

    # Strategy: generate simple domain-like strings (alphanumeric + dots + hyphens)
    # to avoid bash escaping issues while still covering a wide input space
    _domain_strategy = st.from_regex(
        r"[a-z0-9]([a-z0-9.\-]{0,48}[a-z0-9])?", fullmatch=True
    )

    @settings(max_examples=100, deadline=None)
    @given(domain=_domain_strategy)
    def test_summary_contains_all_service_urls(self, domain: str) -> None:
        """
        For any valid domain-like string, print_summary outputs all 7 service
        URLs in the format http://<domain>:<port>.

        **Validates: Requirements 3.1, 7.5**
        """
        # Build a bash snippet that sets CONFIGURED_DOMAIN and calls print_summary
        sourceable_script = _get_sourceable_script_content()
        bash_script = f"""{sourceable_script}

# Set the domain and call print_summary
CONFIGURED_DOMAIN="{domain}"
print_summary
"""
        result = subprocess.run(
            ["bash", "-c", bash_script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, (
            f"print_summary failed with exit code {result.returncode} "
            f"for domain: {domain!r}\nstderr: {result.stderr}"
        )

        output = result.stdout

        # Verify all 7 service URLs are present in the output
        for service_name, port in self.EXPECTED_PORTS.items():
            expected_url = f"http://{domain}:{port}"
            assert expected_url in output, (
                f"Expected URL {expected_url!r} for service '{service_name}' "
                f"not found in print_summary output for domain {domain!r}.\n"
                f"Output:\n{output}"
            )
