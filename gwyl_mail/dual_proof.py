from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional

from .canonical import GWylCanonical
from .sigstore_timestamp import sign_and_timestamp
from .ots_manager import OTSManager
from .validation import ProofValidator, ProofValidationError
from .policy_utils import compute_policy_hash, extract_policy_metadata
from .dsse_signer import sign_proof_dsse


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _hash_email(addr: str) -> str:
    return _sha256_hex(addr.lower().encode())


def create_proof(message: EmailMessage, identity: str, policy_path: Optional[Path] = None, dsse: bool = True) -> Dict[str, Any]:
    content_hash = GWylCanonical.hash(message)
    ts = _utcnow_iso()

    # SPRINT 5.3.2: Extract EML From header for privacy metadata
    from email.utils import parseaddr
    from_header = message.get("From", "")
    from_email = parseaddr(from_header)[1] if from_header else None

    # Sigstore (best effort; offline if unavailable)
    sigstore = sign_and_timestamp(content_hash.encode(), identity)

    # OTS (pending by default)
    ots_dir = Path(".gwyl_mail/proofs/ots")
    proof_file = OTSManager.submit(content_hash.encode(), ots_dir)

    # Verify OTS immediately to populate metadata if already confirmed
    ots_status = OTSManager.verify(proof_file) if proof_file else OTSManager.verify(Path("/dev/null"))

    # Policy metadata (if provided)
    policy_data: Optional[Dict[str, Any]] = None
    if policy_path and policy_path.exists():
        try:
            metadata = extract_policy_metadata(policy_path)
            policy_data = {
                "policy_id": metadata.get('policy_id', 'default'),
                "policy_hash": compute_policy_hash(policy_path),
                "policy_url": metadata.get('policy_url')
            }
        except Exception:
            # Fallback: no policy (warn mode compatible)
            policy_data = None

    # Signer metadata (SPRINT 5: Extract at creation time)
    signer_data: Optional[Dict[str, Any]] = None
    if sigstore.cert_identity or sigstore.cert_issuer:
        signer_data = {
            "identity": sigstore.cert_identity,
            "issuer": sigstore.cert_issuer,
            "extracted_at": ts,
        }

    proof: Dict[str, Any] = {
        "version": "0.2.0",
        "message_id": _sha256_hex((identity + ts + content_hash).encode())[:36],
        "canonical": {
            "algorithm": "gwyl-canonical-v0.2",
            "profile": "strict",
            "nfc_scope": "filenames_only",
            "content_hash": content_hash,
        },
        "signer": signer_data,
        "policy": policy_data,
        "sigstore": {
            "bundle_path": sigstore.bundle_path,
            "bundle_digest": sigstore.bundle_digest,
            "cert_issuer": sigstore.cert_issuer,
            "rekor_entry": sigstore.rekor_entry,
            "rekor_timestamp": sigstore.rekor_timestamp,
            "rekor_log_index": sigstore.rekor_log_index,
            "trust_level": "MEDIUM" if sigstore.bundle_path else "LOW",
        },
        "opentimestamps": {
            "status": ots_status.status if proof_file else "FAILED",
            "proof_file": str(proof_file) if proof_file else None,
            "submitted_at": ts,
            "confirmed_at": ots_status.confirmed_at if proof_file else None,
            "bitcoin_block": ots_status.bitcoin_block if proof_file else None,
            "trust_level": "HIGH" if (proof_file and ots_status.status == "CONFIRMED") else ("PENDING" if proof_file else "FAILED"),
        },
        "coherence": {
            "rekor_ots_delta_seconds": None,
            "rekor_ots_delta_hours": None,
            "threshold_hours": 24,
            "valid": None,
        },
        "anti_replay": {
            "nonce": secrets.token_hex(16),
            "created_at": ts,
            "expires_at": (datetime.fromisoformat(ts.replace("Z", "+00:00")) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            "ttl_seconds": 300
        },
        "privacy": {
            "metadata_disclosure": "minimal",
            "sender_hash": _hash_email(identity),
            "from_hash": _hash_email(from_email) if from_email else None,  # SPRINT 5.3.2
            "recipient_hash": _hash_email(message.get("To", "")) if message.get("To") else None,
            "salted": False,
            "salt_id": None,
        },
        "verification": {
            "trust_level": "MEDIUM" if sigstore.bundle_path else "LOW",
            "offline_mode": False if sigstore.bundle_path else True,
            "instant_verifiable": ["sigstore"] if sigstore.bundle_path else [],
            "legal_grade": ["opentimestamps"] if proof_file else [],
            "revocation_status": "unknown",
            "reasons": ["canonical_ok"] if content_hash else [],
        },
    }

    # proof_canonical_digest (JCS-like minimal)
    proof["proof_canonical_digest"] = _sha256_hex(
        json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()
    )
    # Validate against schema (strict)
    validator = ProofValidator()
    result = validator.validate(proof)
    if not result.valid:
        raise ProofValidationError(f"Generated proof invalid: {result.error}")

    # DSSE signature (wrap proof in DSSE envelope if requested)
    if dsse:
        envelope = sign_proof_dsse(proof, identity)
        return envelope

    return proof
