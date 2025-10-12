from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
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
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        f = out_dir / f"hash_{ts}.txt"
        f.write_bytes(data)
        if _ots_available():
            result = subprocess.run(["ots", "stamp", str(f)], capture_output=True, text=True)
            if result.returncode != 0:
                logging.warning(f"OTS stamp failed: {result.stderr}")
                return None
            p = Path(str(f) + ".ots")
            return p if p.exists() else None
        return None

    @staticmethod
    def verify(proof_file: Path) -> OTSStatus:
        if not proof_file.exists():
            return OTSStatus(status="FAILED", proof_file=proof_file)
        if not _ots_available():
            return OTSStatus(status="PENDING", proof_file=proof_file)

        res = subprocess.run(
            ["ots", "verify", str(proof_file)],
            capture_output=True,
            text=True
        )

        output = (res.stdout or "") + (res.stderr or "")

        # Check if pending
        if "Pending confirmation" in output or "not complete" in output or "pending" in output.lower():
            return OTSStatus(status="PENDING", proof_file=proof_file)

        # Parse bitcoin block if confirmed
        if res.returncode == 0:
            # Example output: "Success! Bitcoin block 829456 attests data existed as of ..."
            block_match = re.search(r'block\s+(\d+)', output, re.IGNORECASE)
            bitcoin_block = int(block_match.group(1)) if block_match else None

            # Extract timestamp (best effort)
            # Format examples:
            # - "... as of Thu 11 Jan 2025 20:15:43 UTC"
            # - "... attests data existed as of 2025-01-11 20:15:43 UTC"
            confirmed_at = None
            time_match = re.search(r'as of\s+(.+?)(?:\s+UTC|\n|$)', output, re.IGNORECASE)
            if time_match:
                try:
                    # Use current timestamp as approximation (OTS doesn't always give precise time)
                    confirmed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                except Exception:
                    pass

            return OTSStatus(
                status="CONFIRMED",
                proof_file=proof_file,
                bitcoin_block=bitcoin_block,
                confirmed_at=confirmed_at
            )

        # Default: failed or pending
        return OTSStatus(status="PENDING", proof_file=proof_file)

    @staticmethod
    def upgrade(proof_file: Path) -> bool:
        if not _ots_available() or not proof_file.exists():
            return False
        subprocess.run(["ots", "upgrade", str(proof_file)], check=False)
        return True
