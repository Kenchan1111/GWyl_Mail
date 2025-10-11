#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict

from gwyl_mail.canonical import GWylCanonical


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def verify_canonical(eml_path: Path, proof: Dict[str, Any]) -> bool:
    msg = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    expected = proof.get("canonical", {}).get("content_hash")
    actual = GWylCanonical.hash(msg)
    return expected == actual


def verify_sigstore_bundle(bundle_path: str | None, content_hash: str) -> bool:
    if not bundle_path:
        return False
    if not _has("cosign"):
        return False
    # cosign verify-blob --bundle <bundle> <file>
    # We pass the hash as a temp file (blob)
    tmp = Path(".gwyl_mail/proofs/_tmp_blob.txt")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content_hash)
    try:
        res = subprocess.run(
            ["cosign", "verify-blob", str(tmp), "--bundle", bundle_path],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


def verify_ots(proof_file: str | None) -> bool:
    if not proof_file:
        return False
    if not _has("ots"):
        return False
    res = subprocess.run(["ots", "verify", proof_file], capture_output=True, text=True)
    return res.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline verifier for GWyl proof JSON")
    ap.add_argument("--eml", required=True, type=Path, help="Path to the EML file")
    ap.add_argument("--proof", required=True, type=Path, help="Path to the proof JSON file")
    args = ap.parse_args()

    proof = json.loads(args.proof.read_text())

    # 1) Canonical verification
    canonical_ok = verify_canonical(args.eml, proof)

    # 2) Sigstore bundle (if present)
    content_hash = proof.get("canonical", {}).get("content_hash", "")
    bundle_path = proof.get("sigstore", {}).get("bundle_path")
    sigstore_ok = verify_sigstore_bundle(bundle_path, content_hash)

    # 3) OTS verification (if present and confirmed)
    ots_info = proof.get("opentimestamps", {})
    ots_file = ots_info.get("proof_file")
    ots_ok = verify_ots(ots_file) if ots_file else False

    # 4) Trust level heuristic (similar to spec)
    if ots_ok:
        trust = "HIGH"
    elif sigstore_ok:
        trust = "MEDIUM"
    else:
        trust = "LOW"

    summary = {
        "canonical": canonical_ok,
        "sigstore_bundle": sigstore_ok,
        "ots": ots_ok,
        "trust_level": trust,
    }

    print(json.dumps(summary, indent=2))
    return 0 if canonical_ok and (sigstore_ok or ots_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

