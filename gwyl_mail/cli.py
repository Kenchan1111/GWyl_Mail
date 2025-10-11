from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict, List

from .canonical import GWylCanonical
from .dual_proof import create_proof
from .ots_manager import OTSManager


def cmd_canonical(args: argparse.Namespace) -> int:
    data = Path(args.eml).read_bytes()
    msg = BytesParser(policy=policy.default).parsebytes(data)
    h = GWylCanonical.hash(msg)
    print(h)
    return 0


def cmd_proof(args: argparse.Namespace) -> int:
    data = Path(args.eml).read_bytes()
    msg = BytesParser(policy=policy.default).parsebytes(data)
    proof = create_proof(msg, identity=args.identity)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, ensure_ascii=False, indent=2))
    print(f"Proof written to {out}")
    return 0


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _safe_in_dir(target: Path, base: Path) -> bool:
    try:
        return target.resolve().is_relative_to(base.resolve())
    except Exception:
        # Python < 3.9 fallback
        t = str(target.resolve())
        b = str(base.resolve())
        return t.startswith(b + "/") or t == b


def _append_audit(entry: Dict[str, Any]) -> None:
    log_path = Path("logs/verification_audit.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def cmd_verify(args: argparse.Namespace) -> int:
    eml = Path(args.eml)
    proof_path = Path(args.proof)
    strict = bool(args.strict)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    reasons: List[str] = []

    try:
        proof = json.loads(proof_path.read_text())
    except Exception as e:
        entry = {"timestamp": now, "action": "verify", "status": "error", "error": f"invalid_proof_json:{e}"}
        _append_audit(entry)
        print(json.dumps({"error": "invalid_proof_json"}))
        return 1

    # 1) Canonical
    try:
        msg = BytesParser(policy=policy.default).parsebytes(eml.read_bytes())
        expected_hash = (proof.get("canonical", {}) or {}).get("content_hash")
        actual_hash = GWylCanonical.hash(msg)
        canonical_ok = (expected_hash == actual_hash)
        if canonical_ok:
            reasons.append("canonical_ok")
        else:
            reasons.append("canonical_mismatch")
    except Exception as e:
        canonical_ok = False
        reasons.append("canonical_error")

    # 2) Sigstore bundle
    bundle_ok = False
    bundle_path = (proof.get("sigstore", {}) or {}).get("bundle_path")
    if bundle_path and _has("cosign"):
        bp = Path(bundle_path)
        base = Path(".gwyl_mail/proofs/sigstore")
        if _safe_in_dir(bp, base) and bp.exists():
            tmp = Path(".gwyl_mail/proofs/_tmp_blob.txt")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text((proof.get("canonical", {}) or {}).get("content_hash", ""))
            try:
                res = subprocess.run(["cosign", "verify-blob", str(tmp), "--bundle", str(bp)], capture_output=True, text=True, timeout=30)
                bundle_ok = (res.returncode == 0)
            except subprocess.TimeoutExpired:
                reasons.append("sigstore_timeout")
            finally:
                try:
                    tmp.unlink()
                except Exception:
                    pass
        else:
            reasons.append("bundle_path_invalid")

    # 3) OTS
    ots_ok = False
    ots_info = proof.get("opentimestamps", {}) or {}
    ots_file = ots_info.get("proof_file")
    if ots_file and _has("ots"):
        try:
            res = subprocess.run(["ots", "verify", str(ots_file)], capture_output=True, text=True)
            ots_ok = (res.returncode == 0)
        except Exception:
            reasons.append("ots_verify_failed")
    elif ots_file:
        reasons.append("ots_cli_missing")

    # Trust level
    if ots_ok:
        trust = "HIGH"
    elif bundle_ok:
        trust = "MEDIUM"
    else:
        trust = "LOW"

    summary = {
        "canonical": canonical_ok,
        "sigstore_bundle": bundle_ok,
        "ots": ots_ok,
        "trust_level": trust,
        "reasons": reasons,
    }

    status = "ok" if (canonical_ok and (bundle_ok or ots_ok)) else "fail"
    audit = {"timestamp": now, "action": "verify", "status": status, **summary}
    _append_audit(audit)
    print(json.dumps(summary, indent=2))

    if strict:
        return 0 if (canonical_ok and (bundle_ok or ots_ok)) else 1
    return 0 if canonical_ok else 1


def cmd_ots_upgrade(args: argparse.Namespace) -> int:
    proof_file = Path(args.proof)
    ok = OTSManager.upgrade(proof_file)
    print("Upgraded" if ok else "No upgrade performed")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="gwyl-mail", description="GWyl Mail CLI (minimal)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("canonical-hash", help="Compute canonical hash for an EML file")
    c.add_argument("eml")
    c.set_defaults(func=cmd_canonical)

    pr = sub.add_parser("create-proof", help="Create proof for an EML file")
    pr.add_argument("eml")
    pr.add_argument("--identity", required=True)
    pr.add_argument("--out", default=".gwyl_mail/proofs/proof.json")
    pr.set_defaults(func=cmd_proof)

    up = sub.add_parser("upgrade-ots", help="Upgrade an OTS proof file")
    up.add_argument("proof")
    up.set_defaults(func=cmd_ots_upgrade)

    vf = sub.add_parser("verify", help="Verify a proof offline")
    vf.add_argument("--eml", required=True)
    vf.add_argument("--proof", required=True)
    vf.add_argument("--strict", action="store_true")
    vf.set_defaults(func=cmd_verify)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
