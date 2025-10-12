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

        SPRINT 5.2.3: Resilient OTS parsing with multiple strategies:
        1. Try multiple regex patterns for different OTS output formats
        2. JSON parsing fallback for structured output
        3. Graceful degradation - returns None on parse failure

        ChatGPT Critical Issue #2: Use ots info to get the actual
        Bitcoin block timestamp instead of approximating with now().

        Returns:
            ISO timestamp string or None if parsing fails
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

            # SPRINT 5.2.3: Try multiple parsing strategies in order of reliability

            # Strategy 1: JSON parsing (most reliable if available)
            try:
                import json
                # Try to find JSON block in output
                json_start = output.find('{')
                json_end = output.rfind('}')
                if json_start >= 0 and json_end > json_start:
                    json_str = output[json_start:json_end + 1]
                    data = json.loads(json_str)
                    # Look for timestamp fields in JSON
                    for key in ['timestamp', 'confirmed_at', 'block_time', 'time']:
                        if key in data:
                            ts_value = data[key]
                            if isinstance(ts_value, int) and ts_value > 1000000000:
                                # Unix timestamp
                                dt = datetime.fromtimestamp(ts_value, tz=timezone.utc)
                                return dt.isoformat().replace("+00:00", "Z")
                            elif isinstance(ts_value, str):
                                # Try parsing as ISO string
                                dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                                return dt.isoformat().replace("+00:00", "Z")
            except Exception:
                pass

            # Strategy 2: Regex patterns for different OTS output formats
            # Pattern 1: "as of Thu 11 Jan 2025 20:15:43 UTC"
            time_patterns = [
                (r'as of\s+([A-Za-z]{3}\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2})', "%a %d %b %Y %H:%M:%S"),
                # Pattern 2: "on Wed Jan 15 2025 12:34:56"
                (r'on\s+([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{4}\s+\d{2}:\d{2}:\d{2})', "%a %b %d %Y %H:%M:%S"),
                # Pattern 3: "at 2025-01-15 12:34:56"
                (r'at\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', "%Y-%m-%d %H:%M:%S"),
            ]

            for pattern, date_format in time_patterns:
                time_match = re.search(pattern, output, re.IGNORECASE)
                if time_match:
                    time_str = time_match.group(1)
                    try:
                        dt = datetime.strptime(time_str, date_format)
                        dt = dt.replace(tzinfo=timezone.utc)
                        return dt.isoformat().replace("+00:00", "Z")
                    except ValueError:
                        continue

            # Strategy 3: ISO format "2025-01-11T20:15:43Z" or similar
            iso_patterns = [
                r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?)',
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
            ]

            for pattern in iso_patterns:
                iso_match = re.search(pattern, output)
                if iso_match:
                    time_str = iso_match.group(1).replace(' ', 'T')
                    try:
                        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                        return dt.isoformat().replace("+00:00", "Z")
                    except ValueError:
                        continue

            # Strategy 4: Unix timestamp variations
            unix_patterns = [
                r'timestamp:\s*(\d{10,})',
                r'time:\s*(\d{10,})',
                r'block_time:\s*(\d{10,})',
                r'confirmed:\s*(\d{10,})',
            ]

            for pattern in unix_patterns:
                unix_match = re.search(pattern, output, re.IGNORECASE)
                if unix_match:
                    try:
                        unix_ts = int(unix_match.group(1))
                        dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
                        return dt.isoformat().replace("+00:00", "Z")
                    except (ValueError, OSError):
                        continue

        except subprocess.TimeoutExpired:
            logging.warning(f"OTS info timeout for {proof_file}")
        except Exception as e:
            logging.debug(f"OTS timestamp extraction failed: {e}")

        # Graceful degradation: return None if all strategies fail
        return None

    @staticmethod
    def upgrade(proof_file: Path) -> bool:
        if not _ots_available() or not proof_file.exists():
            return False
        subprocess.run(["ots", "upgrade", str(proof_file)], check=False)
        return True
