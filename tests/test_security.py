import json
from pathlib import Path
from types import SimpleNamespace

import gwyl_mail.cli as cli


def test_path_traversal_blocked(tmp_path: Path):
    """Test basic path traversal protection (existing test)."""
    base = tmp_path / "safe"
    base.mkdir(parents=True)
    # Inside allowed dir OK
    inside = base / "bundle.json"
    inside.write_text("{}")
    assert cli._safe_in_dir(inside, base)
    # Explicit traversal
    traversal = base / ".." / "etc" / "passwd"
    assert not cli._safe_in_dir(traversal, base)
    # Completely different path
    other = tmp_path / "other" / "file"
    other.parent.mkdir(parents=True)
    other.write_text("{}")
    assert not cli._safe_in_dir(other, base)


def test_symlink_traversal_blocked(tmp_path: Path):
    """Test symlink-based path traversal protection (SPRINT 5.2.2).

    Security: Prevents symlink attacks where attacker creates a symlink
    inside allowed directory pointing to sensitive file outside.
    """
    base = tmp_path / "safe"
    base.mkdir(parents=True)

    # Create target outside base
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    secret = outside / "secret.txt"
    secret.write_text("sensitive data")

    # Create symlink inside base pointing to outside
    symlink = base / "link_to_secret"
    symlink.symlink_to(secret)

    # Symlink should be blocked even though it's "inside" base directory
    assert not cli._safe_in_dir(symlink, base), "Symlink attack should be blocked"

    # Regular file inside base should still work
    regular = base / "regular.txt"
    regular.write_text("safe data")
    assert cli._safe_in_dir(regular, base), "Regular file should be allowed"


def test_symlink_directory_traversal_blocked(tmp_path: Path):
    """Test symlink directory traversal protection (SPRINT 5.2.2).

    Security: Prevents symlink directory attacks where a directory component
    is a symlink pointing outside the allowed base.
    """
    base = tmp_path / "safe"
    base.mkdir(parents=True)

    # Create target directory outside base
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)

    # Create symlink directory inside base pointing outside
    symlink_dir = base / "evil_dir"
    symlink_dir.symlink_to(outside)

    # Create file through symlink directory
    (outside / "file.txt").write_text("data")

    # Access through symlink directory should be blocked
    through_symlink = symlink_dir / "file.txt"
    assert not cli._safe_in_dir(through_symlink, base), "Symlink directory attack should be blocked"


def test_nonexistent_path_in_safe_dir_allowed(tmp_path: Path):
    """Test that nonexistent paths within safe directory are allowed (SPRINT 5.2.2).

    Security: Allows creating new files in safe directory (normal use case).
    The path structure validation works even if file doesn't exist yet.
    """
    base = tmp_path / "safe"
    base.mkdir(parents=True)

    # Path that doesn't exist but is within safe directory
    nonexistent = base / "new_file.txt"
    assert cli._safe_in_dir(nonexistent, base), "Nonexistent path in safe dir should be allowed"

    # But traversal through nonexistent intermediate dirs should still be blocked
    traversal = base / ".." / "outside" / "file.txt"
    assert not cli._safe_in_dir(traversal, base), "Traversal to nonexistent outside path should be blocked"


def test_absolute_path_outside_blocked(tmp_path: Path):
    """Test that absolute paths outside base are blocked (SPRINT 5.2.2)."""
    base = tmp_path / "safe"
    base.mkdir(parents=True)

    # Absolute path outside base
    outside = Path("/etc/passwd")
    assert not cli._safe_in_dir(outside, base), "Absolute path outside base should be blocked"


def test_command_injection_blocked(monkeypatch, tmp_path: Path):
    # Prepare minimal eml and proof
    eml = tmp_path / "mail.eml"
    eml.write_text(
        "From: a@b\nTo: c@d\nSubject: t\nDate: Fri, 10 Jan 2025 10:20:30 +0000\nMessage-ID: <x@x>\n\nBody\n"
    )
    proof = {
        "version": "0.2.0",
        "message_id": "id",
        "canonical": {"algorithm": "gwyl-canonical-v0.2", "content_hash": ""},
        "sigstore": {"bundle_path": "/tmp/bad; rm -rf /"},
        "opentimestamps": {"proof_file": None},
        "anti_replay": {"nonce": "0" * 32, "expires_at": "2025-01-11T10:25:30Z"},
    }
    proof_path = tmp_path / "proof.json"
    proof_path.write_text(json.dumps(proof))

    # Force cosign available to trigger validation path and illegal char check
    monkeypatch.setattr(cli, "_has", lambda c: True)

    args = SimpleNamespace(
        eml=str(eml), proof=str(proof_path), strict=True, policy=None, expect_identity=None, allow_issuer=None
    )

    rc = cli.cmd_verify(args)
    # Must fail due to invalid bundle path (illegal chars)
    assert rc != 0

