"""
Tests for generate_admin_ui_keypair — admin-ui Ed25519 key bootstrap.

Source: openspec/changes/kubernetes-readiness/specs/admin-ui-key-bootstrap/spec.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGenerateAdminUiKeypair:
    def test_generate_keypair_creates_files(self, tmp_path: Path) -> None:
        import main as m
        m.generate_admin_ui_keypair(tmp_path)
        assert (tmp_path / "admin_ui_private.pem").exists()
        assert (tmp_path / "admin_ui_public.pem").exists()

    def test_private_key_mode_0400(self, tmp_path: Path) -> None:
        import main as m
        m.generate_admin_ui_keypair(tmp_path)
        mode = (tmp_path / "admin_ui_private.pem").stat().st_mode & 0o777
        assert mode == 0o400, f"Expected 0o400, got 0o{mode:o}"

    def test_idempotent_second_run_unchanged(self, tmp_path: Path) -> None:
        import main as m
        m.generate_admin_ui_keypair(tmp_path)
        priv_bytes = (tmp_path / "admin_ui_private.pem").read_bytes()
        pub_bytes = (tmp_path / "admin_ui_public.pem").read_bytes()
        m.generate_admin_ui_keypair(tmp_path)
        assert (tmp_path / "admin_ui_private.pem").read_bytes() == priv_bytes
        assert (tmp_path / "admin_ui_public.pem").read_bytes() == pub_bytes

    def test_public_key_is_valid_ed25519(self, tmp_path: Path) -> None:
        import main as m
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        m.generate_admin_ui_keypair(tmp_path)
        pub_pem = (tmp_path / "admin_ui_public.pem").read_bytes()
        key = load_pem_public_key(pub_pem)
        assert isinstance(key, Ed25519PublicKey)
