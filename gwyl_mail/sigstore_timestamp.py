from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class SigstoreUnavailableError(RuntimeError):
    pass


class SigstoreError(RuntimeError):
    pass


def _cosign_available() -> bool:
    return shutil.which("cosign") is not None


@dataclass
class SigstoreProof:
    bundle_path: Optional[str]
    bundle_digest: Optional[str]
    cert_issuer: Optional[str]
    cert_identity: Optional[str]  # Email extracted from certificate
    rekor_entry: Optional[str]
    rekor_timestamp: Optional[int]
    rekor_log_index: Optional[int]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_and_timestamp(data: bytes, identity: str | None = None) -> SigstoreProof:
    """Robust Sigstore wrapper using cosign sign-blob with bundle output.

    If cosign is unavailable or signing fails, returns an offline placeholder proof
    (bundle_path=None) to keep the pipeline usable, and delegates trust to OTS.
    """
    if not _cosign_available():
        return SigstoreProof(
            bundle_path=None,
            bundle_digest=None,
            cert_issuer=None,
            cert_identity=None,
            rekor_entry=None,
            rekor_timestamp=None,
            rekor_log_index=None,
        )

    # Persist bundle for offline verification
    out_dir = Path(".gwyl_mail/proofs/sigstore")
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp_data:
        tmp_data.write(data)
        tmp_data.flush()
        blob_path = Path(tmp_data.name)

    # Timestamped bundle filename to avoid overwrite/ambiguity
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_path = out_dir / f"bundle_{ts}.json"
    cmd = [
        "cosign",
        "sign-blob",
        str(blob_path),
        "--bundle",
        str(bundle_path),
        "--output-certificate",
        "/dev/null",
        "--output-signature",
        "/dev/null",
    ]

    try:
        timeout_s = int(os.getenv("SIGSTORE_TIMEOUT", "30"))
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s
        )
        if result.returncode != 0:
            # Graceful fallback
            return SigstoreProof(
                bundle_path=None,
                bundle_digest=None,
                cert_issuer=None,
                cert_identity=None,
                rekor_entry=None,
                rekor_timestamp=None,
                rekor_log_index=None,
            )
        if not bundle_path.exists():
            return SigstoreProof(
                bundle_path=None,
                bundle_digest=None,
                cert_issuer=None,
                cert_identity=None,
                rekor_entry=None,
                rekor_timestamp=None,
                rekor_log_index=None,
            )

        # Parse bundle best-effort (format may vary across cosign versions)
        try:
            bundle_data = json.loads(bundle_path.read_text())
        except Exception:
            bundle_data = {}

        issuer = None
        rekor_entry = None
        rekor_ts: Optional[int] = None
        log_index: Optional[int] = None

        # Some cosign bundles include Rekor payload; keep best-effort extraction
        rekor_entry = (
            bundle_data.get("rekorEntry")
            or bundle_data.get("RekorEntry")
            or None
        )
        if isinstance(rekor_entry, dict):
            rekor_ts = rekor_entry.get("integratedTime") or rekor_entry.get("IntegratedTime")
            log_index = rekor_entry.get("logIndex") or rekor_entry.get("LogIndex")
            # Build a string URL if present
            rekor_entry_str = rekor_entry.get("url") or rekor_entry.get("URL") or None
        else:
            rekor_entry_str = None

        bundle_digest = _sha256_file(bundle_path)

        # Extract identity from bundle (SPRINT 5: Extract at creation time)
        cert_identity_extracted: Optional[str] = None
        cert_issuer_extracted: Optional[str] = None
        try:
            from .sigstore_identity import extract_identity_from_bundle
            sig_identity = extract_identity_from_bundle(bundle_path)
            cert_identity_extracted = sig_identity.email
            cert_issuer_extracted = sig_identity.issuer or issuer
        except Exception:
            # Fallback: use best-effort issuer from bundle parsing above
            cert_issuer_extracted = issuer

        return SigstoreProof(
            bundle_path=str(bundle_path),
            bundle_digest=bundle_digest,
            cert_issuer=cert_issuer_extracted,
            cert_identity=cert_identity_extracted,
            rekor_entry=rekor_entry_str,
            rekor_timestamp=rekor_ts,
            rekor_log_index=log_index,
        )
    except subprocess.TimeoutExpired:
        return SigstoreProof(
            bundle_path=None,
            bundle_digest=None,
            cert_issuer=None,
            cert_identity=None,
            rekor_entry=None,
            rekor_timestamp=None,
            rekor_log_index=None,
        )
    finally:
        try:
            blob_path.unlink(missing_ok=True)
        except Exception:
            pass
