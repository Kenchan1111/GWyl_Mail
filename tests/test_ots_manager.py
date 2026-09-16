"""OTSManager unit tests (SPRINT 5 debt, delivered in SPRINT 7).

All 'ots' subprocess calls are faked: these tests run on any machine.
"""

import json
from pathlib import Path

from gwyl_mail import ots_manager
from gwyl_mail.ots_manager import OTSManager


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_ots_run_factory(pending: bool = False, confirmed: bool = False, info_output: str = ""):
    """Build a subprocess.run fake dispatching on the ots subcommand."""

    def fake_run(cmd, *args, **kwargs):
        sub = cmd[1] if len(cmd) > 1 else ""
        target = Path(cmd[2]) if len(cmd) > 2 else None
        if sub == "stamp":
            if target is not None:
                Path(str(target) + ".ots").write_bytes(b"fake-ots")
            return FakeResult(0, stdout="Submitted to remote calendar, waiting for confirmation")
        if sub == "verify":
            if pending:
                return FakeResult(0, stdout="Pending confirmation in Bitcoin blockchain")
            if confirmed:
                return FakeResult(
                    0,
                    stdout="Success! Bitcoin block 829456 attests data existed as of Thu 11 Jan 2025 20:15:43 UTC",
                )
            return FakeResult(1, stderr="Error: could not verify")
        if sub == "info":
            return FakeResult(0, stdout=info_output)
        if sub == "upgrade":
            return FakeResult(0)
        return FakeResult(1, stderr="unknown subcommand")

    return fake_run


# --- submit -----------------------------------------------------------------


def test_submit_without_ots_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: False)
    assert OTSManager.submit(b"hello", tmp_path) is None


def test_submit_with_ots_creates_stamp_file(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)
    monkeypatch.setattr(ots_manager.subprocess, "run", _fake_ots_run_factory())
    result = OTSManager.submit(b"hello", tmp_path)
    assert result is not None and result.exists() and result.suffix == ".ots"


def test_submit_stamp_failure_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)

    def failing(cmd, *a, **k):
        return FakeResult(1, stderr="calendar unreachable")

    monkeypatch.setattr(ots_manager.subprocess, "run", failing)
    assert OTSManager.submit(b"hello", tmp_path) is None


# --- verify -----------------------------------------------------------------


def test_verify_missing_file_is_failed(tmp_path):
    status = OTSManager.verify(tmp_path / "nonexistent.ots")
    assert status.status == "FAILED"


def test_verify_without_ots_is_pending(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: False)
    f = tmp_path / "p.ots"
    f.write_bytes(b"x")
    status = OTSManager.verify(f)
    assert status.status == "PENDING"


def test_verify_pending_output(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)
    monkeypatch.setattr(ots_manager.subprocess, "run", _fake_ots_run_factory(pending=True))
    f = tmp_path / "p.ots"
    f.write_bytes(b"x")
    status = OTSManager.verify(f)
    assert status.status == "PENDING"
    assert status.bitcoin_block is None


def test_verify_confirmed_extracts_block_and_timestamp(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)
    info_output = "Timestamp id 1234\nSubmit time: 2025-01-11T20:15:40Z\n"
    monkeypatch.setattr(
        ots_manager.subprocess,
        "run",
        _fake_ots_run_factory(confirmed=True, info_output=info_output),
    )
    f = tmp_path / "p.ots"
    f.write_bytes(b"x")
    status = OTSManager.verify(f)
    assert status.status == "CONFIRMED"
    assert status.bitcoin_block == 829456
    assert status.confirmed_at is not None
    assert status.confirmed_at.startswith("2025-01-11T20:15:4")


def test_verify_error_output_is_pending(monkeypatch, tmp_path):
    # Hard failure without pending marker degrades to PENDING, never CONFIRMED.
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)
    monkeypatch.setattr(ots_manager.subprocess, "run", _fake_ots_run_factory())
    f = tmp_path / "p.ots"
    f.write_bytes(b"x")
    status = OTSManager.verify(f)
    assert status.status == "PENDING"


# --- _extract_real_timestamp (Sprint 5.2.3 strategies) ----------------------


def _extract_with_output(monkeypatch, tmp_path, output: str, returncode: int = 0):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)
    monkeypatch.setattr(
        ots_manager.subprocess, "run", lambda cmd, *a, **k: FakeResult(returncode, stdout=output)
    )
    f = tmp_path / "p.ots"
    f.write_bytes(b"x")
    return OTSManager._extract_real_timestamp(f)


def test_extract_timestamp_json_strategy(monkeypatch, tmp_path):
    out = f"info\n{json.dumps({'timestamp': 1736631343})}"
    ts = _extract_with_output(monkeypatch, tmp_path, out)
    assert ts == "2025-01-11T21:35:43Z"


def test_extract_timestamp_human_format(monkeypatch, tmp_path):
    ts = _extract_with_output(
        monkeypatch, tmp_path, "data existed as of Thu 11 Jan 2025 20:15:43 UTC"
    )
    assert ts == "2025-01-11T20:15:43Z"


def test_extract_timestamp_iso_format(monkeypatch, tmp_path):
    ts = _extract_with_output(monkeypatch, tmp_path, "confirmed at 2025-01-15 12:34:56")
    assert ts == "2025-01-15T12:34:56Z"


def test_extract_timestamp_unix_strategy(monkeypatch, tmp_path):
    ts = _extract_with_output(monkeypatch, tmp_path, "block timestamp: 1736631343 seconds")
    assert ts == "2025-01-11T21:35:43Z"


def test_extract_timestamp_garbage_returns_none(monkeypatch, tmp_path):
    assert _extract_with_output(monkeypatch, tmp_path, "nothing parseable here") is None


def test_extract_timestamp_nonzero_returncode_returns_none(monkeypatch, tmp_path):
    assert _extract_with_output(monkeypatch, tmp_path, "whatever", returncode=1) is None


# --- upgrade ----------------------------------------------------------------


def test_upgrade_without_ots_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: False)
    assert OTSManager.upgrade(tmp_path / "p.ots") is False


def test_upgrade_missing_file_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)
    assert OTSManager.upgrade(tmp_path / "nonexistent.ots") is False


def test_upgrade_runs_ots(monkeypatch, tmp_path):
    monkeypatch.setattr(ots_manager, "_ots_available", lambda: True)
    called = {}

    def fake_run(cmd, *a, **k):
        called["cmd"] = cmd
        return FakeResult(0)

    monkeypatch.setattr(ots_manager.subprocess, "run", fake_run)
    f = tmp_path / "p.ots"
    f.write_bytes(b"x")
    assert OTSManager.upgrade(f) is True
    assert called["cmd"][:2] == ["ots", "upgrade"]
