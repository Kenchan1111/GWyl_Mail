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

            # SPRINT 3: Extract REAL timestamp using ots info
            confirmed_at = OTSManager._extract_real_timestamp(proof_file)

            return OTSStatus(
                status="CONFIRMED",
                proof_file=proof_file,
                bitcoin_block=bitcoin_block,
                confirmed_at=confirmed_at
            )

        # Default: failed or pending
        return OTSStatus(status="PENDING", proof_file=proof_file)

    @staticmethod
    def _extract_real_timestamp(proof_file: Path) -> str | None:
        """
        Extract real Bitcoin timestamp using ots info

        ChatGPT Critical Issue #2: Use ots info to get the actual
        Bitcoin block timestamp instead of approximating with now().

        Returns:
            ISO timestamp string or None
        """
        try:
            # Run ots info to get detailed timestamp information
            res = subprocess.run(
                ["ots", "info", str(proof_file)],
                capture_output=True,
                text=True,
                timeout=10
            )

            if res.returncode != 0:
                return None

            output = res.stdout or ""

            # Parse the output for attestation timestamp
            # Example output format from ots info:
            # "Bitcoin block height: 829456"
            # Or from verify: "as of Thu 11 Jan 2025 20:15:43 UTC"

            # Try to extract timestamp from different formats
            # Format 1: "as of Thu 11 Jan 2025 20:15:43 UTC"
            time_match = re.search(
                r'as of\s+([A-Za-z]{3}\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2})',
                output
            )
            if time_match:
                time_str = time_match.group(1)
                try:
                    # Parse format: "Thu 11 Jan 2025 20:15:43"
                    dt = datetime.strptime(time_str, "%a %d %b %Y %H:%M:%S")
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat().replace("+00:00", "Z")
                except ValueError:
                    pass

            # Format 2: ISO format "2025-01-11T20:15:43Z" or similar
            iso_match = re.search(
                r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})',
                output
            )
            if iso_match:
                time_str = iso_match.group(1).replace(' ', 'T')
                try:
                    dt = datetime.fromisoformat(time_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat().replace("+00:00", "Z")
                except ValueError:
                    pass

            # Format 3: Unix timestamp
            unix_match = re.search(r'timestamp:\s*(\d{10,})', output, re.IGNORECASE)
            if unix_match:
                unix_ts = int(unix_match.group(1))
                dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
                return dt.isoformat().replace("+00:00", "Z")

        except Exception:
            pass

        return None

    @staticmethod
    def upgrade(proof_file: Path) -> bool:
        if not _ots_available() or not proof_file.exists():
            return False
        subprocess.run(["ots", "upgrade", str(proof_file)], check=False)
        return True
