#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Real Postfix interoperability test (SPRINT 10, KPI_POC.md: >=95%).

Full round trip through a REAL MTA:
  1. sign N sample messages (embedded proof; degraded if cosign absent)
  2. send each via SMTP to a Postfix container
  3. read the delivered mailbox (Postfix adds Received/Delivered-To/Return-Path)
  4. run the recipient 'check' verification on each delivered message
  5. report the interop rate (KPI target: >= 95%)

Container management: with --docker, (re)starts boky/postfix with a local
test domain; otherwise expects an SMTP server already listening.

Usage:
    python scripts/interop_postfix.py [--count 50] [--docker]
"""

from __future__ import annotations

import argparse
import json
import mailbox
import shutil
import smtplib
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

CONTAINER = "gwyl-postfix"
DOMAIN = "gb.test"
SMTP_HOST, SMTP_PORT = "127.0.0.1", 2525
RECIPIENT = f"rcpt@{DOMAIN}"


def docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def ensure_container() -> bool:
    """(Re)start the Postfix test container; returns True when ready."""
    if shutil.which("docker") is None:
        print("docker not available — run manually: see this script's header")
        return False
    docker("rm", "-f", CONTAINER)
    res = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "-e",
            f"ALLOWED_SENDER_DOMAINS={DOMAIN}",
            "-e",
            "ALLOW_EMPTY_SENDER_DOMAINS=yes",
            "-e",
            "MESSAGE_SIZE_LIMIT=52428800",
            "-p",
            f"{SMTP_PORT}:25",
            "boky/postfix:latest",
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"docker run failed: {res.stderr}")
        return False
    # Local delivery config: accept the test domain and create the recipient
    for cmd in (
        [
            "docker",
            "exec",
            CONTAINER,
            "postconf",
            "-e",
            f"mydestination = mail.{DOMAIN}, localhost.localdomain, localhost, {DOMAIN}",
        ],
        ["docker", "exec", CONTAINER, "postconf", "-e", "local_recipient_maps ="],
        ["docker", "exec", CONTAINER, "sh", "-c", "useradd -m -s /bin/false rcpt || true"],
    ):
        subprocess.run(cmd, capture_output=True, text=True)
    docker("exec", CONTAINER, "postfix", "reload")
    time.sleep(5)
    return True


def _message(i: int) -> EmailMessage:
    m = EmailMessage()
    m["From"] = f"sender@{DOMAIN}"
    m["To"] = RECIPIENT
    m["Subject"] = f"Interop test #{i}"
    m["Date"] = "Thu, 17 Sep 2026 10:00:00 +0000"
    m["Message-ID"] = f"<interop-{i}@{DOMAIN}>"
    m.set_content(f"Interop message {i}\nUnique body {i}: the quick brown fox jumps.\n")
    if i % 3 == 0:
        m.add_attachment(
            f"attachment {i}".encode(), maintype="text", subtype="plain", filename=f"note{i}.txt"
        )
    return m


def run(count: int, use_docker: bool) -> int:
    from gwyl_mail.dual_proof import create_proof
    from gwyl_mail.eml_io import inject_proof

    if use_docker and not ensure_container():
        return 1

    with tempfile.TemporaryDirectory(prefix="gwyl_interop_") as tmpdir:
        tmp = Path(tmpdir)
        sent_dir = tmp / "sent"
        sent_dir.mkdir()

        # 1. Sign and send each message
        sent = 0
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            for i in range(1, count + 1):
                draft = _message(i)
                draft_bytes = draft.as_bytes()
                envelope, _ = create_proof(
                    draft,
                    identity=f"sender@{DOMAIN}",
                    dsse=True,
                    profile="strict",
                    portable=True,
                    return_artifacts=True,
                )
                ots_bytes = None  # degraded path; OTS submit per message would
                # exhaust calendar politeness in a test run
                signed = inject_proof(draft_bytes, envelope, ots_bytes=ots_bytes)
                (sent_dir / f"{i}.eml").write_bytes(signed)
                from email import message_from_bytes

                smtp.send_message(message_from_bytes(signed))
                sent += 1
        print(f"sent: {sent}/{count} via real Postfix SMTP")

        # 2. Let Postfix deliver, then read the mailbox
        time.sleep(3)
        res = docker("exec", CONTAINER, "cat", "/var/mail/rcpt")
        if res.returncode != 0:
            print(f"cannot read mailbox: {res.stderr}")
            return 1
        mbox_path = tmp / "rcpt.mbox"
        mbox_path.write_bytes(res.stdout.encode("utf-8", errors="replace"))

        # 3. Verify each delivered message like the recipient would
        inbox_root = tmp / "checkdir"
        inbox_root.mkdir()
        delivered = 0
        verified = 0
        for key, msg in mailbox.mbox(mbox_path, create=False).iteritems():
            raw = msg.as_bytes()
            if b"X-GWyl-Proof" not in raw and b"gwylproof.json" not in raw:
                continue
            delivered += 1
            out = inbox_root / f"{key}.eml"
            out.write_bytes(raw)
            rc = 0
            try:
                rc = subprocess.run(
                    [sys.executable, "-m", "gwyl_mail.cli", "check", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(tmp),
                ).returncode
            except subprocess.TimeoutExpired:
                rc = 1
            if rc == 0:
                verified += 1

        rate = (verified / delivered * 100) if delivered else 0.0
        kpi_pass = rate >= 95.0 and delivered == count
        print(f"delivered with proof: {delivered}/{count}")
        print(f"verified by recipient check: {verified}/{delivered} ({rate:.1f}%)")
        print(f"KPI interop >= 95%: {'PASS' if kpi_pass else 'FAIL'}")
        report = {
            "sent": sent,
            "delivered": delivered,
            "verified": verified,
            "rate_percent": round(rate, 1),
            "kpi_pass": kpi_pass,
        }
        (tmp / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    return 0 if kpi_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--docker", action="store_true", help="(Re)start the Postfix container")
    args = parser.parse_args()
    return run(args.count, args.docker)


if __name__ == "__main__":
    raise SystemExit(main())
