#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""KPI benchmark harness (SPRINT 10, KPI_POC.md thresholds).

Measures, on the local machine and with the tools actually available:
  1. canonical-hash latency (S/M/L messages, up to 25 MB attachment)
  2. proof creation latency (degraded without cosign; OTS submit when ots present)
  3. verification latency (full 'check' path on an embedded-proof message)
  4. embedded proof overhead (bytes added to the .eml)
  5. OTS submit latency (real, network — only when the ots binary is present)

Output: human table + optional JSON. Thresholds from docs/specs/KPI_POC.md:
verify < 150 ms, overhead < 50 KB, Sigstore creation < 1 s, OTS submit < 5 s.

Usage:
    python scripts/benchmark.py [--json results.json] [--markdown results.md] [--repeat 20]
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import sys
import tempfile
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from email import policy  # noqa: E402
from email.parser import BytesParser  # noqa: E402

from gwyl_mail.canonical import GWylCanonical  # noqa: E402
from gwyl_mail.dual_proof import create_proof  # noqa: E402
from gwyl_mail.eml_io import inject_proof, strip_proof  # noqa: E402

EXAMPLES = Path(__file__).parent.parent / "examples"

# KPI_POC.md thresholds
KPI_VERIFY_MS = 150
KPI_OVERHEAD_BYTES = 50 * 1024
KPI_SIGSTORE_CREATION_S = 1.0
KPI_OTS_SUBMIT_S = 5.0


def _cosign_available() -> bool:
    return shutil.which("cosign") is not None


def _ots_available() -> bool:
    return shutil.which("ots") is not None


def _sample(name: str) -> bytes:
    return (EXAMPLES / name).read_bytes()


def _generated_message(size_bytes: int) -> bytes:
    msg = EmailMessage()
    msg["From"] = "bench@gwyl.local"
    msg["To"] = "rcpt@gwyl.local"
    msg["Subject"] = "benchmark payload"
    msg["Date"] = "Thu, 17 Sep 2026 10:00:00 +0000"
    msg["Message-ID"] = "<bench@gwyl.local>"
    msg.set_content("benchmark body")
    msg.add_attachment(
        b"\0" * size_bytes, maintype="application", subtype="octet-stream", filename="payload.bin"
    )
    return msg.as_bytes()


def bench_canonical_hash(sizes: List[tuple], repeat: int) -> List[Dict[str, Any]]:
    rows = []
    for label, data in sizes:
        msg = BytesParser(policy=policy.default).parsebytes(data)
        GWylCanonical.hash(msg)  # warmup
        times = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            GWylCanonical.hash(msg)
            times.append(time.perf_counter() - t0)
        rows.append(
            {
                "metric": f"canonical_hash_{label}",
                "value_ms": round(statistics.mean(times) * 1000, 2),
                "p95_ms": (
                    round(statistics.quantiles(times, n=20)[-1] * 1000, 2)
                    if len(times) >= 2
                    else None
                ),
                "size_bytes": len(data),
            }
        )
    return rows


def bench_creation_and_overhead(tmp: Path, repeat: int) -> List[Dict[str, Any]]:
    import os

    os.chdir(tmp)
    data = _sample("sample_plain_text.eml")
    msg = BytesParser(policy=policy.default).parsebytes(data)

    times = []
    overheads = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        envelope, artifacts = create_proof(
            msg,
            identity="bench@gwyl.local",
            dsse=True,
            profile="strict",
            portable=True,
            return_artifacts=True,
        )
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        ots_bytes = (
            artifacts.ots_path.read_bytes()
            if artifacts.ots_path and artifacts.ots_path.exists()
            else None
        )
        signed = inject_proof(data, envelope, ots_bytes=ots_bytes)
        overheads.append(len(signed) - len(data))

    cosign = _cosign_available()
    ots = _ots_available()
    creation_note = "degraded (no cosign)" if not cosign else "with cosign"
    threshold = KPI_SIGSTORE_CREATION_S if cosign else None
    return [
        {
            "metric": f"proof_creation_{creation_note}",
            "value_ms": round(statistics.mean(times) * 1000, 2),
            "threshold_ms": threshold * 1000 if threshold else None,
            "pass": (statistics.mean(times) < threshold) if threshold else None,
            "note": (
                "threshold applies to Sigstore signing; unavailable without cosign"
                if not cosign
                else None
            ),
        },
        {
            "metric": "embedded_overhead_bytes",
            "value_bytes": int(statistics.mean(overheads)),
            "threshold_bytes": KPI_OVERHEAD_BYTES,
            "pass": statistics.mean(overheads) < KPI_OVERHEAD_BYTES,
            "note": (
                "includes real OTS stamp" if ots else "degraded proof (no OTS stamp, no bundle)"
            ),
        },
    ]


def _verify_once(cli, verify_args) -> None:
    cli.cmd_verify(verify_args)


def bench_verify(tmp: Path, repeat: int) -> List[Dict[str, Any]]:
    """Verification latency on an embedded-proof message, two variants:

    - offline_core: PATH stripped of ots/cosign → pure local verification
      (the KPI_POC.md '<150ms offline' scenario for the recipient)
    - full_binary_check: with the real ots binary → adds an `ots verify`
      subprocess call on the pending stamp
    """
    import os

    os.chdir(tmp)
    data = _sample("sample_plain_text.eml")
    msg = BytesParser(policy=policy.default).parsebytes(data)
    envelope, artifacts = create_proof(
        msg,
        identity="bench@gwyl.local",
        dsse=True,
        profile="strict",
        portable=True,
        return_artifacts=True,
    )
    inbox = tmp / "bench_inbox"
    inbox.mkdir(exist_ok=True)
    proof_path = inbox / "gwylproof.json"
    proof_path.write_text(json.dumps(envelope))
    if artifacts.ots_path and artifacts.ots_path.exists():
        (inbox / "gwylproof.ots").write_bytes(artifacts.ots_path.read_bytes())
    stripped = inbox / "message_stripped.eml"
    stripped.write_bytes(strip_proof(inject_proof(data, envelope)))

    import gwyl_mail.cli as cli

    verify_args = argparse.Namespace(
        eml=str(stripped),
        proof=str(proof_path),
        strict=False,
        policy=None,
        expect_identity=None,
        allow_issuer=None,
        profile_override=None,
        lookup_dir=str(inbox),
    )

    results: List[Dict[str, Any]] = []
    original_path = os.environ.get("PATH", "")
    variants = [
        ("verify_offline_core_ms", "", KPI_VERIFY_MS),
        ("verify_with_ots_binary_ms", original_path, None),
    ]
    for name, _path_env, threshold in variants:
        if name.endswith("offline_core_ms"):
            # Keep only system dirs: no venv bin, no local bin → ots/cosign unseen
            os.environ["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"
        else:
            os.environ["PATH"] = original_path
            if not _ots_available():
                results.append(
                    {
                        "metric": name,
                        "value_ms": None,
                        "threshold_ms": None,
                        "pass": None,
                        "note": "ots binary not available",
                    }
                )
                continue

        _verify_once(cli, verify_args)  # warmup
        times = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            _verify_once(cli, verify_args)
            times.append(time.perf_counter() - t0)
        mean_ms = statistics.mean(times) * 1000
        results.append(
            {
                "metric": name,
                "value_ms": round(mean_ms, 2),
                "p95_ms": (
                    round(statistics.quantiles(times, n=20)[-1] * 1000, 2)
                    if len(times) >= 2
                    else None
                ),
                "threshold_ms": threshold,
                "pass": (mean_ms < threshold) if threshold else None,
                "note": (
                    ("pure local verification (KPI offline scenario)")
                    if threshold
                    else ("includes real 'ots verify' subprocess on pending stamp")
                ),
            }
        )
    os.environ["PATH"] = original_path
    return results


def bench_ots_submit(tmp: Path) -> Dict[str, Any]:
    import os
    import subprocess

    os.chdir(tmp)
    if not _ots_available():
        return {
            "metric": "ots_submit",
            "value_ms": None,
            "threshold_ms": KPI_OTS_SUBMIT_S * 1000,
            "pass": None,
            "note": "ots binary not available",
        }
    data = b"benchmark-" + str(time.time()).encode()
    f = tmp / "bench_ots.txt"
    f.write_bytes(data)
    t0 = time.perf_counter()
    res = subprocess.run(["ots", "stamp", str(f)], capture_output=True, text=True, timeout=30)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    stamp = Path(str(f) + ".ots")
    return {
        "metric": "ots_submit",
        "value_ms": round(elapsed_ms, 2),
        "threshold_ms": KPI_OTS_SUBMIT_S * 1000,
        "pass": (res.returncode == 0 and stamp.exists() and elapsed_ms / 1000 < KPI_OTS_SUBMIT_S),
        "note": "real network submission to public calendars",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="Write JSON results to this path")
    parser.add_argument("--markdown", help="Write markdown results to this path")
    parser.add_argument("--repeat", type=int, default=20)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="gwyl_bench_") as tmpdir:
        tmp = Path(tmpdir)
        sizes = [
            ("S_plain", _sample("sample_plain_text.eml")),
            ("M_html", _sample("sample_html.eml")),
            ("M_attachments", _sample("sample_with_attachments.eml")),
            ("L_5MB", _generated_message(5 * 1024 * 1024)),
            ("XL_25MB", _generated_message(25 * 1024 * 1024)),
        ]
        results: List[Dict[str, Any]] = []
        results.extend(bench_canonical_hash(sizes, args.repeat))
        results.extend(bench_creation_and_overhead(tmp, args.repeat))
        results.extend(bench_verify(tmp, args.repeat))
        results.append(bench_ots_submit(tmp))

    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cosign_available": _cosign_available(),
        "ots_available": _ots_available(),
        "repeat": args.repeat,
    }

    lines = [
        "# GWyl Mail — Résultats de benchmark",
        "",
        f"Env: Python {env['python']}, cosign={'oui' if env['cosign_available'] else 'non'}, "
        f"ots={'oui' if env['ots_available'] else 'non'}, repeat={args.repeat}",
        "",
        "| Métrique | Mesure | Seuil KPI | Statut |",
        "|---|---|---|---|",
    ]
    for r in results:
        value = r.get("value_ms")
        value_str = (
            f"{value} ms"
            if value is not None
            else (f"{r.get('value_bytes')} o" if r.get("value_bytes") is not None else "n/a")
        )
        thr = r.get("threshold_ms")
        thr_str = (
            f"{thr} ms"
            if thr
            else (f"{r.get('threshold_bytes')} o" if r.get("threshold_bytes") else "—")
        )
        status = (
            "✅ PASS" if r.get("pass") else ("❌ FAIL" if r.get("pass") is False else "ℹ️  INFO")
        )
        lines.append(f"| {r['metric']} | {value_str} | {thr_str} | {status} |")
    report = "\n".join(lines)
    print(report)

    if args.json:
        Path(args.json).write_text(json.dumps({"env": env, "results": results}, indent=2))
        print(f"\nJSON written to {args.json}")
    if args.markdown:
        Path(args.markdown).write_text(report + "\n")
        print(f"Markdown written to {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
