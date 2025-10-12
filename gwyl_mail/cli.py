from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from .canonical import GWylCanonical
from .dual_proof import create_proof
from .ots_manager import OTSManager
from .sigstore_identity import extract_identity_from_bundle
from .dsse_signer import verify_proof_dsse, extract_proof_from_dsse


def cmd_canonical(args: argparse.Namespace) -> int:
    data = Path(args.eml).read_bytes()
    msg = BytesParser(policy=policy.default).parsebytes(data)
    profile = getattr(args, 'profile', 'strict')  # SPRINT 6.2.1
    h = GWylCanonical.hash(msg, profile=profile)
    print(h)
    return 0


def cmd_proof(args: argparse.Namespace) -> int:
    data = Path(args.eml).read_bytes()
    msg = BytesParser(policy=policy.default).parsebytes(data)
    use_dsse = not getattr(args, 'no_dsse', False)
    profile = getattr(args, 'profile', 'strict')  # SPRINT 6.2.1
    proof = create_proof(msg, identity=args.identity, dsse=use_dsse, profile=profile)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, ensure_ascii=False, indent=2))
    if use_dsse:
        print(f"DSSE-signed proof written to {out} (profile: {profile})")
    else:
        print(f"Proof written to {out} (profile: {profile})")
    return 0


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _safe_in_dir(target: Path, base: Path) -> bool:
    """Check if target path is safely within base directory.

    Security (SPRINT 5.2.2):
    - Explicitly blocks symlinks to prevent directory traversal
    - Uses resolve() to get absolute canonical paths
    - Rejects any path outside base directory
    - No permissive fallback to ensure strict validation

    Returns False if target contains symlinks or is outside base.
    """
    try:
        # Resolve both paths to absolute canonical paths
        target_resolved = target.resolve()
        base_resolved = base.resolve()

        # Check if any component in target path is a symlink
        # Walk from target up to the common parent
        check_path = target
        while check_path != check_path.parent:
            if check_path.is_symlink():
                return False
            check_path = check_path.parent

        # Check if target is within base directory
        return target_resolved.is_relative_to(base_resolved)
    except (ValueError, OSError, RuntimeError):
        # Any error (permission denied, path doesn't exist, etc.) = reject
        return False


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
    profile_override: Optional[str] = getattr(args, "profile_override", None)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    reasons: List[str] = []

    try:
        proof_data = json.loads(proof_path.read_text())
    except Exception as e:
        entry = {"timestamp": now, "action": "verify", "status": "error", "error": f"invalid_proof_json:{e}"}
        _append_audit(entry)
        print(json.dumps({"error": "invalid_proof_json"}))
        return 1

    # Check if DSSE envelope (has "payload" and "payloadType")
    dsse_verified = False
    dsse_error = None
    if "payload" in proof_data and "payloadType" in proof_data:
        # DSSE envelope detected
        verified, proof, error = verify_proof_dsse(proof_data)
        dsse_verified = verified
        dsse_error = error
        if not verified:
            reasons.append(f"dsse_verification_failed: {error or 'unknown'}")
            if strict:
                entry = {"timestamp": now, "action": "verify", "status": "error", "error": f"dsse_verification_failed:{error}"}
                _append_audit(entry)
                print(json.dumps({"error": "dsse_verification_failed", "details": error}))
                return 1
    else:
        # Plain proof JSON (backward compat)
        proof = proof_data

    # 1) Canonical (SPRINT 6.2.1: Use profile from proof or override)
    try:
        msg = BytesParser(policy=policy.default).parsebytes(eml.read_bytes())
        expected_hash = (proof.get("canonical", {}) or {}).get("content_hash")
        # Extract profile from proof (default to "strict" for backward compat)
        canonical_section = proof.get("canonical", {}) or {}
        proof_profile = canonical_section.get("profile")

        # Apply profile override if provided (ChatGPT recommendation #6)
        if profile_override:
            effective_profile = profile_override
            if proof_profile and proof_profile != profile_override:
                print(f"⚠️  Profile override: Using '{profile_override}' instead of proof's '{proof_profile}'", file=sys.stderr)
                reasons.append(f"profile_overridden_{proof_profile}_to_{profile_override}")
            else:
                reasons.append(f"profile_override_{profile_override}")
        else:
            # Warn if profile missing (backward compat with old proofs)
            if proof_profile is None:
                proof_profile = "strict"
                print("⚠️  Warning: Proof missing 'profile' field, assuming 'strict' (backward compatibility)", file=sys.stderr)
                reasons.append("profile_missing_assumed_strict")
            effective_profile = proof_profile

        actual_hash = GWylCanonical.hash(msg, profile=effective_profile)
        canonical_ok = (expected_hash == actual_hash)
        if canonical_ok:
            reasons.append(f"canonical_ok(profile={effective_profile})")
        else:
            reasons.append(f"canonical_mismatch(profile={effective_profile})")
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
            # Use unique temp file to avoid collisions
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_file:
                tmp_file.write((proof.get("canonical", {}) or {}).get("content_hash", ""))
                tmp_path = tmp_file.name
            try:
                res = subprocess.run(["cosign", "verify-blob", tmp_path, "--bundle", str(bp)], capture_output=True, text=True, timeout=30)
                bundle_ok = (res.returncode == 0)
                if bundle_ok:
                    # SPRINT 3: Use robust identity extraction instead of heuristic
                    try:
                        from .sigstore_identity import extract_identity_from_bundle
                        sig_identity = extract_identity_from_bundle(bp)
                        bundle_identity = sig_identity.email
                        bundle_issuer = sig_identity.issuer
                    except Exception:
                        # Fallback to old heuristic method if robust extraction fails
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
                    Path(tmp_path).unlink(missing_ok=True)
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
    # SPRINT 5.3.1: Expose coherence delta details for transparency
    coherence_ok = True
    coherence_details: Optional[Dict[str, Any]] = None
    rekor_ts = (proof.get("sigstore", {}) or {}).get("rekor_timestamp")
    ots_ts = (proof.get("opentimestamps", {}) or {}).get("confirmed_at")
    if rekor_ts and ots_ts:
        try:
            rt = datetime.utcfromtimestamp(int(rekor_ts))
            ot = datetime.fromisoformat(str(ots_ts).replace('Z', '+00:00'))
            delta_seconds = abs((rt - ot).total_seconds())
            delta_h = delta_seconds / 3600.0

            # Build detailed coherence information (SPRINT 5.3.1)
            coherence_details = {
                "rekor_timestamp": rt.isoformat().replace("+00:00", "Z"),
                "ots_timestamp": ot.isoformat().replace("+00:00", "Z"),
                "delta_seconds": int(delta_seconds),
                "delta_hours": round(delta_h, 2),
                "threshold_hours": 24,
                "within_threshold": delta_h <= 24
            }

            if delta_h <= 24:
                reasons.append("coherence_ok")
                coherence_ok = True
            else:
                reasons.append("coherence_failed")
                coherence_ok = False
        except Exception as e:
            reasons.append("coherence_unknown")
            coherence_details = {"error": f"timestamp_parse_failed: {str(e)}"}

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
        "dsse_signed": dsse_verified,
        "trust_level": trust,
        "reasons": reasons,
        "identity": bundle_identity,
        "issuer": bundle_issuer,
    }

    # SPRINT 5.3.1: Add coherence details if available
    if coherence_details is not None:
        summary["coherence_details"] = coherence_details

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
    c.add_argument("--profile", choices=["strict", "relaxed"], default="strict", help="Canonicalization profile (Sprint 6.2.1)")
    c.set_defaults(func=cmd_canonical)

    pr = sub.add_parser("create-proof", help="Create proof for an EML file")
    pr.add_argument("eml")
    pr.add_argument("--identity", required=True)
    pr.add_argument("--out", default=".gwyl_mail/proofs/proof.json")
    pr.add_argument("--no-dsse", action="store_true", help="Disable DSSE signature (backward compatibility)")
    pr.add_argument("--profile", choices=["strict", "relaxed"], default="strict", help="Canonicalization profile: 'strict' (default, no MTA tolerance) or 'relaxed' (tolerates MTA modifications)")
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
    vf.add_argument("--profile-override", choices=["strict", "relaxed"], help="Override canonicalization profile (useful for old proofs failing due to MTA modifications)")
    vf.set_defaults(func=cmd_verify)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
