"""
test_guide_content.py — smoke tests for guide file content correctness.

Verifies that each guide file:
- Loads without error (fail-fast guaranteed by bootstrap.py module-level load).
- Contains its required keywords.
- Does NOT reference non-existent tools (e.g. `whoami`).
- The email guide states the REST-only caveat.
"""
from __future__ import annotations

import pytest

from mcp_server.tools.bootstrap import _GUIDE_RESOURCES


_BOOTSTRAP_MD_PATH = None  # loaded via bootstrap module


def _guide(uri: str) -> str:
    text = _GUIDE_RESOURCES.get(uri)
    assert text is not None, f"Guide {uri!r} not found in _GUIDE_RESOURCES"
    return text


def test_rest_api_guide_keywords() -> None:
    """REST-API guide mentions mintkey_request_token and proxy."""
    text = _guide("mintkey://guides/rest-api")
    assert "mintkey_request_token" in text, "REST guide must mention mintkey_request_token"
    assert "proxy" in text.lower(), "REST guide must mention proxy"
    assert len(text) > 500, "REST guide must be non-trivial"


def test_ssh_guide_keywords() -> None:
    """SSH guide mentions bastion and port 2222."""
    text = _guide("mintkey://guides/ssh")
    assert "bastion" in text, "SSH guide must mention bastion"
    assert "2222" in text, "SSH guide must mention port 2222"
    assert len(text) > 500, "SSH guide must be non-trivial"


def test_secrets_guide_keywords() -> None:
    """Secrets guide mentions secret_put and operator."""
    text = _guide("mintkey://guides/secrets")
    assert "secret_put" in text, "Secrets guide must mention secret_put"
    assert "operator" in text, "Secrets guide must mention operator"
    assert len(text) > 500, "Secrets guide must be non-trivial"


def test_email_guide_keywords() -> None:
    """Email guide mentions email_list_mailboxes and email-proxy."""
    text = _guide("mintkey://guides/email")
    assert "email_list_mailboxes" in text, "Email guide must mention email_list_mailboxes"
    assert "email-proxy" in text, "Email guide must mention email-proxy"
    assert len(text) > 500, "Email guide must be non-trivial"


def test_email_guide_rest_only_caveat() -> None:
    """Email guide must state that email_* tools are REST-only (not MCP tools/call)."""
    text = _guide("mintkey://guides/email")
    # Must contain a caveat about REST-only invocation
    assert "REST" in text, "Email guide must mention REST"
    assert "tools/call" in text or "tools/list" in text, (
        "Email guide must mention that tools/call or tools/list does not expose email_* tools"
    )


def test_quick_reference_keywords() -> None:
    """Quick reference mentions svc_ prefix."""
    text = _guide("mintkey://quick-reference")
    assert "svc_" in text, "Quick reference must mention svc_ prefix"
    assert len(text) > 200, "Quick reference must be non-trivial"


def test_no_guide_references_whoami_mcp_tool() -> None:
    """No guide should reference the non-existent Mintkey 'whoami' MCP tool.

    Note: 'whoami' as a Unix shell command (e.g. in an SSH bastion example) is valid
    and is distinct from the Mintkey `whoami` MCP tool which does not exist.
    We check for the MCP tool invocation pattern: "tool": "whoami" or mintkey_whoami.
    """
    for uri, text in _GUIDE_RESOURCES.items():
        assert '"whoami"' not in text or "tool" not in text, (
            f"Guide {uri!r} references non-existent 'whoami' MCP tool via JSON"
        )
        assert "mintkey_whoami" not in text, (
            f"Guide {uri!r} references non-existent 'mintkey_whoami' tool"
        )


def test_no_guide_references_mk_agentkey_prefix() -> None:
    """No guide should use the wrong key prefix mk_agentkey_ (correct is mk_agent_)."""
    for uri, text in _GUIDE_RESOURCES.items():
        assert "mk_agentkey_" not in text, (
            f"Guide {uri!r} uses deprecated key prefix 'mk_agentkey_'; use 'mk_agent_'"
        )
