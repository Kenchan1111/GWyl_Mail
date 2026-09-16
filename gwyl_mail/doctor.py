# SPDX-License-Identifier: GPL-3.0-only
"""Environment health check (SPRINT 7).

'gwyl-mail doctor' verifies every external dependency the proof workflow
relies on: the cosign and ots binaries, the Python packages imported by the
core modules, and (best-effort) network reachability of Sigstore Rekor and an
OpenTimestamps calendar.

Exit code: 0 when all required checks pass, 1 otherwise. Network checks never
fail the command on their own — they are informational.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Required tools (binary on PATH) with install hints.
REQUIRED_TOOLS: Dict[str, str] = {
    "cosign": "Sigstore signing CLI (Go binary). Install: https://github.com/sigstore/cosign/releases",
    "ots": "OpenTimestamps client. Install: pip install opentimestamps-client",
}

# Python packages imported by core modules (import name -> pip name).
REQUIRED_PACKAGES: Dict[str, str] = {
    "yaml": "pyyaml",
    "jsonschema": "jsonschema",
    "cryptography": "cryptography",
}

# Informational endpoints (never fail the run on their own).
NETWORK_ENDPOINTS: List[str] = [
    "https://rekor.sigstore.dev",
    "https://alice.btc.calendar.opentimestamps.org",
]

_NETWORK_TIMEOUT_SECONDS = 3


@dataclass
class CheckResult:
    name: str
    ok: bool
    required: bool
    detail: str
    hint: Optional[str] = None


@dataclass
class DoctorReport:
    results: List[CheckResult] = field(default_factory=list)

    @property
    def all_required_ok(self) -> bool:
        return all(r.ok for r in self.results if r.required)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.all_required_ok,
            "checks": [
                {
                    "name": r.name,
                    "ok": r.ok,
                    "required": r.required,
                    "detail": r.detail,
                    "hint": r.hint,
                }
                for r in self.results
            ],
        }


def _check_tool(name: str, hint: str) -> CheckResult:
    path = shutil.which(name)
    if path is None:
        return CheckResult(name, ok=False, required=True, detail="not found on PATH", hint=hint)

    # Best-effort version probe; a failing version flag is not fatal.
    version = "unknown version"
    for flag in ("--version", "version"):
        try:
            res = subprocess.run([name, flag], capture_output=True, text=True, timeout=5)
            first_line = ((res.stdout or "") + (res.stderr or "")).strip().splitlines()
            if res.returncode in (0, 1) and first_line:
                version = first_line[0][:80]
                break
        except (subprocess.TimeoutExpired, OSError):
            continue
    return CheckResult(name, ok=True, required=True, detail=f"{path} ({version})")


def _check_package(import_name: str, pip_name: str) -> CheckResult:
    try:
        module = __import__(import_name)
        version = getattr(module, "__version__", "unknown version")
        return CheckResult(f"python:{pip_name}", ok=True, required=True, detail=version)
    except ImportError:
        return CheckResult(
            f"python:{pip_name}",
            ok=False,
            required=True,
            detail="import failed",
            hint=f"pip install {pip_name}",
        )


def _check_network(url: str) -> CheckResult:
    name = f"network:{url}"
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=_NETWORK_TIMEOUT_SECONDS):
            return CheckResult(name, ok=True, required=False, detail="reachable")
    except Exception as e:
        return CheckResult(
            name,
            ok=False,
            required=False,
            detail=f"unreachable ({e.__class__.__name__})",
            hint="Network is optional for offline verification, required for signing/anchoring.",
        )


def run_doctor(skip_network: bool = False) -> DoctorReport:
    """Run all environment checks and return the report."""
    report = DoctorReport()

    for tool, hint in REQUIRED_TOOLS.items():
        report.results.append(_check_tool(tool, hint))
    for import_name, pip_name in REQUIRED_PACKAGES.items():
        report.results.append(_check_package(import_name, pip_name))
    if not skip_network:
        for url in NETWORK_ENDPOINTS:
            report.results.append(_check_network(url))

    return report


def _render(report: DoctorReport) -> str:
    lines = ["GWyl Mail environment check", ""]
    for r in report.results:
        marker = "✅" if r.ok else ("❌" if r.required else "⚠️ ")
        scope = "required" if r.required else "optional"
        lines.append(f"{marker} {r.name}: {r.detail} ({scope})")
        if not r.ok and r.hint:
            lines.append(f"     → {r.hint}")
    lines.append("")
    if report.all_required_ok:
        lines.append("All required checks passed. You can create and verify full proofs.")
    else:
        missing = [r.name for r in report.results if r.required and not r.ok]
        lines.append(f"FAILED: missing required dependencies: {', '.join(missing)}")
        lines.append(
            "Without them, 'create-proof' only works with --allow-degraded (reduced guarantees)."
        )
    return "\n".join(lines)


def cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(skip_network=bool(getattr(args, "skip_network", False)))
    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(_render(report))
    return 0 if report.all_required_ok else 1
