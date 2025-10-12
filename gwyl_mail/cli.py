from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    except Exception as e:
        print(f"⚠️ Audit logging failed: {e}", file=sys.stderr)


def cmd_verify(args: argparse.Namespace) -> int:
    eml = Path(args.eml)
    proof_path = Path(args.proof)
    strict = bool(args.strict)
    policy_path: Optional[Path] = Path(args.policy) if getattr(args, "policy", None) else None
    expect_identity: Optional[str] = getattr(args, "expect_identity", None)
    allow_issuer: Optional[str] = getattr(args, "allow_issuer", None)

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
    bundle_identity: Optional[str] = None
    bundle_issuer: Optional[str] = None
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
                if bundle_ok:
                    # Try parse identity/issuer directly from bundle JSON (best-effort)
                    try:
                        bdata = json.loads(bp.read_text())
                        # Heuristic extraction: search for strings containing '@' for identity and issuer-like URLs
                        def walk(d):
                            nonlocal bundle_identity, bundle_issuer
                            if isinstance(d, dict):
                                for k, v in d.items():
                                    kl = str(k).lower()
                                    if isinstance(v, (dict, list)):
                                        walk(v)
                                    else:
                                        if isinstance(v, str):
                                            if '@' in v and bundle_identity is None:
                                                bundle_identity = v
                                            if ('http://' in v or 'https://' in v or 'issuer' in kl) and bundle_issuer is None:
                                                bundle_issuer = v
                            elif isinstance(d, list):
                                for x in d:
                                    walk(x)
                        walk(bdata)
                    except Exception:
                        pass
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
            if res.returncode != 0:
                ots_ok = False
                reasons.append("ots_verify_failed")
            else:
                out = (res.stdout or "") + (res.stderr or "")
                if "Pending confirmation" in out or "not complete" in out:
                    ots_ok = False
                    reasons.append("ots_pending")
                else:
                    ots_ok = True
        except Exception:
            reasons.append("ots_verify_failed")
    elif ots_file:
        reasons.append("ots_cli_missing")

    # Policy/Identity checks (optional)
    policy_ok = True
    if policy_path and policy_path.exists():
        try:
            from .identity_policy import IdentityPolicy
            pol = IdentityPolicy(policy_path)
            # Prefer EML From when available
            from_addr = ""
            try:
                from email.utils import parseaddr
                from_addr = parseaddr(msg.get("From", ""))[1] if canonical_ok else ""
            except Exception:
                pass
            cert_subj = bundle_identity or ""
            cert_iss = bundle_issuer or ""
            res = pol.verify(from_addr, cert_subj, cert_iss)
            policy_ok = res.get("valid", False) or (res.get("enforcement") == "warn")
            if policy_ok:
                reasons.append("policy_ok")
            else:
                reasons.append("policy_violation")
        except Exception:
            reasons.append("policy_error")

    if expect_identity and bundle_identity:
        if bundle_identity.lower() == expect_identity.lower():
            reasons.append("identity_ok")
        else:
            reasons.append("identity_mismatch")
            policy_ok = False if strict else policy_ok

    if allow_issuer and bundle_issuer:
        if allow_issuer in bundle_issuer:
            reasons.append("issuer_ok")
        else:
            reasons.append("issuer_not_allowed")
            policy_ok = False if strict else policy_ok

    # Coherence Rekor/OTS (best-effort if timestamps available)
    coherence_ok = True
    rekor_ts = (proof.get("sigstore", {}) or {}).get("rekor_timestamp")
    ots_ts = (proof.get("opentimestamps", {}) or {}).get("confirmed_at")
    if rekor_ts and ots_ts:
        try:
            rt = datetime.utcfromtimestamp(int(rekor_ts))
            ot = datetime.fromisoformat(str(ots_ts).replace('Z', '+00:00'))
            delta_h = abs((rt - ot).total_seconds()) / 3600.0
            if delta_h <= 24:
                reasons.append("coherence_ok")
                coherence_ok = True
            else:
                reasons.append("coherence_failed")
                coherence_ok = False
        except Exception:
            reasons.append("coherence_unknown")

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

    status = "ok" if (canonical_ok and (bundle_ok or ots_ok) and policy_ok and coherence_ok) else "fail"
    audit = {"timestamp": now, "action": "verify", "status": status, **summary}
    _append_audit(audit)
    print(json.dumps(summary, indent=2))

    if strict:
        return 0 if (canonical_ok and (bundle_ok or ots_ok) and policy_ok and coherence_ok) else 1
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
    vf.add_argument("--policy", help="Path to identity policy YAML")
    vf.add_argument("--expect-identity", help="Expected signer identity (email)")
    vf.add_argument("--allow-issuer", help="Allowed OIDC issuer substring")
    vf.set_defaults(func=cmd_verify)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
