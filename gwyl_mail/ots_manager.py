from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _ots_available() -> bool:
    return shutil.which("ots") is not None


@dataclass
class OTSStatus:
    status: str  # PENDING | CONFIRMED | FAILED
    proof_file: Path | None
    confirmed_at: str | None = None
    bitcoin_block: int | None = None


class OTSManager:
    @staticmethod
    def submit(data: bytes, out_dir: Path) -> Path | None:
        out_dir.mkdir(parents=True, exist_ok=True)
        f = out_dir / "content_hash.txt"
        f.write_bytes(data)
        if _ots_available():
            subprocess.run(["ots", "stamp", str(f)], check=False)
            p = Path(str(f) + ".ots")
            return p if p.exists() else None
        return None

    @staticmethod
    def verify(proof_file: Path) -> OTSStatus:
        if not proof_file.exists():
            return OTSStatus(status="FAILED", proof_file=proof_file)
        if not _ots_available():
            return OTSStatus(status="PENDING", proof_file=proof_file)
        res = subprocess.run(["ots", "verify", str(proof_file)], capture_output=True, text=True)
        if res.returncode == 0:
            return OTSStatus(status="CONFIRMED", proof_file=proof_file)
        return OTSStatus(status="PENDING", proof_file=proof_file)

    @staticmethod
    def upgrade(proof_file: Path) -> bool:
        if not _ots_available() or not proof_file.exists():
            return False
        subprocess.run(["ots", "upgrade", str(proof_file)], check=False)
        return True

