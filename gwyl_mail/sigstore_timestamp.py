from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _cosign_available() -> bool:
    return shutil.which("cosign") is not None


@dataclass
class SigstoreProof:
    bundle_path: str | None
    cert_issuer: str | None
    rekor_entry: str | None
    rekor_timestamp: int | None
    rekor_log_index: int | None


def sign_and_timestamp(data: bytes, identity: str | None = None) -> SigstoreProof:
    """Minimal wrapper; falls back to offline if cosign is unavailable.

    Note: Interactive OIDC may not be suitable for headless runs.
    """
    if not _cosign_available():
        return SigstoreProof(bundle_path=None, cert_issuer=None, rekor_entry=None, rekor_timestamp=None, rekor_log_index=None)

    with tempfile.TemporaryDirectory() as td:
        blob = Path(td) / "blob.txt"
        blob.write_bytes(data)
        bundle = Path(td) / "bundle.json"
        cmd = [
            "cosign",
            "sign-blob",
            str(blob),
            "--bundle",
            str(bundle),
        ]
        # Optional identity token handled externally if needed
        subprocess.run(cmd, check=False)
        if not bundle.exists():
            return SigstoreProof(bundle_path=None, cert_issuer=None, rekor_entry=None, rekor_timestamp=None, rekor_log_index=None)
        try:
            meta = json.loads(bundle.read_text())
        except Exception:
            meta = {}
        # Best-effort extraction
        issuer = None
        rekor_entry = None
        rekor_timestamp = None
        log_index = None
        # Rekor info varies per version; keep None if unknown
        return SigstoreProof(
            bundle_path=str(bundle),
            cert_issuer=issuer,
            rekor_entry=rekor_entry,
            rekor_timestamp=rekor_timestamp,
            rekor_log_index=log_index,
        )

