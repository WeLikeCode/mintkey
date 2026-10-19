"""
Verifies that changeset 015 does not contain literal role passwords in git.

Source: openspec/changes/kubernetes-readiness/specs/db-role-secret-parameterization/spec.md
"""
from __future__ import annotations

import pathlib


_CHANGELOG = (
    pathlib.Path(__file__).resolve().parents[3]
    / "db"
    / "changelog"
    / "015-app-role-passwords.yaml"
)


def test_no_literal_app_password() -> None:
    content = _CHANGELOG.read_text()
    assert "mintkey_app_password" not in content


def test_no_literal_subscriber_password() -> None:
    content = _CHANGELOG.read_text()
    assert "mintkey_subscriber_password" not in content


def test_property_substitution_present() -> None:
    content = _CHANGELOG.read_text()
    assert "${db_app_password}" in content
    assert "${db_subscriber_password}" in content
