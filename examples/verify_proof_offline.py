#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict

from gwyl_mail.canonical import GWylCanonical


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _safe_in_dir(target: Path, base: Path) -> bool:
    try:
        return target.resolve().is_relative_to(base.resolve())
    except Exception:
        t = str(target.resolve())
        b = str(base.resolve())
        return t.startswith(b + "/") or t == b


def verify_canonical(eml_path: Path, proof: Dict[str, Any]) -> bool:
    msg = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    expected = (proof.get("canonical", {}) or {}).get("content_hash")
    actual = GWylCanonical.hash(msg)
    return expected == actual


def verify_sigstore_bundle(bundle_path: str | None, content_hash: str) -> bool:
    if not bundle_path or not _has("cosign"):
        return False

    bp = Path(bundle_path)
    base = Path(".gwyl_mail/proofs/sigstore")
    # Path-safety: must be in allowed directory and be a file
    if not bp.exists() or not bp.is_file() or not _safe_in_dir(bp, base):
        print(json.dumps({"error": "bundle_path_invalid"}), file=sys.stderr)
        return False

    # No shell: pass args list; deny suspicious characters in path
    illegal = [';', '|', '&', '$', '`']
    if any(ch in str(bundle_path) for ch in illegal):
        print(json.dumps({"error": "bundle_path_illegal_chars"}), file=sys.stderr)
        return False

    # Prepare blob temp file
    tmp = Path(".gwyl_mail/proofs/_tmp_blob.txt")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content_hash or "")
    try:
        res = subprocess.run(
            ["cosign", "verify-blob", str(tmp), "--bundle", str(bp)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return res.returncode == 0
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "sigstore_timeout"}), file=sys.stderr)
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception as e:
            print(json.dumps({"warn": f"tmp_cleanup_failed:{e}"}), file=sys.stderr)


def verify_ots(proof_file: str | None) -> bool:
    if not proof_file or not _has("ots"):
        return False
    res = subprocess.run(["ots", "verify", proof_file], capture_output=True, text=True)
    if res.returncode != 0:
        return False
    out = (res.stdout or "") + (res.stderr or "")
    # Treat explicit "Pending" as not complete
    if "Pending confirmation" in out or "not complete" in out:
        return False
    return True


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
