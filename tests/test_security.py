import json
from pathlib import Path
from types import SimpleNamespace

import gwyl_mail.cli as cli


def test_path_traversal_blocked(tmp_path: Path):
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

