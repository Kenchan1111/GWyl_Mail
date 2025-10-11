import json
from pathlib import Path
from types import SimpleNamespace

import gwyl_mail.cli as cli


def test_safe_in_dir(tmp_path: Path):
    base = tmp_path / "allowed"
    base.mkdir(parents=True)
    inside = base / "bundle.json"
    inside.write_text("{}")

    outside = tmp_path / ".." / "etc" / "passwd"

    assert cli._safe_in_dir(inside, base) is True
    assert cli._safe_in_dir(base, base) is True
    # outside path should resolve outside base
    assert cli._safe_in_dir(outside, base) is False


def test_ots_pending_detection(monkeypatch, tmp_path: Path):
    proof_file = tmp_path / "proof.ots"
    proof_file.write_text("dummy")

    class Run:
        def __init__(self, rc: int, out: str):
            self.returncode = rc
            self.stdout = out
            self.stderr = ""

    def fake_has(cmd: str) -> bool:
        return True

    def fake_run(cmd, capture_output=True, text=True):
        # Simulate OTS verify returning 0 but pending message
        return Run(0, "Pending confirmation in Bitcoin blockchain")

    monkeypatch.setattr(cli, "_has", fake_has)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    # Build minimal proof and eml for cli.verify
    eml = tmp_path / "mail.eml"
    eml.write_text(
        "From: a@b\nTo: c@d\nSubject: t\nDate: Fri, 10 Jan 2025 10:20:30 +0000\nMessage-ID: <x@x>\n\nBody\n"
    )
    proof = {
        "version": "0.2.0",
        "message_id": "id",
        "canonical": {"algorithm": "gwyl-canonical-v0.2", "content_hash": ""},
        "sigstore": {"bundle_path": None},
        "opentimestamps": {"proof_file": str(proof_file)},
        "anti_replay": {"nonce": "0" * 32, "expires_at": "2025-01-11T10:25:30Z"},
    }
    proof_path = tmp_path / "proof.json"
    proof_path.write_text(json.dumps(proof))

    # Invoke verify
    args = SimpleNamespace(
        eml=str(eml), proof=str(proof_path), strict=False, policy=None, expect_identity=None, allow_issuer=None
    )
    # We call the internal function directly to avoid argparse
    rc = cli.cmd_verify(args)
    # Should fail (canonical empty, and ots pending) → rc non-zero
    assert rc != 0

