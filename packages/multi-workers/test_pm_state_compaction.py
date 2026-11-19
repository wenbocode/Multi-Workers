import gzip
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest


CLI = Path(__file__).with_name("mw.py")
KEY = "sample"
FIELDS = b"- Key: sample\r\n- Claim-Id: \r\n- Phase: EXECUTE\r\n- Updated: 2026-11-19\r\n- PM mode: mw\r\n"
PASS = b"- PASS: L3 evidence/quality-gate-report-example.md\r\n"
SUMMARY = """## Notes

确认本地工具入口，下一步核对任务卡。

## Task Status

等待 T01 复核。

## Decisions

沿用现有工具入口，见 design.md。

## Evidence Ledger

AC-001 待独立验证，见 evidence/check.md。
"""


@pytest.fixture
def project(tmp_path):
    key_dir = tmp_path / ".agenticdoc" / KEY
    key_dir.mkdir(parents=True)
    (tmp_path / ".agenticdoc" / "_index.parallel").write_bytes(
        "| sample | idle | EXECUTE | — | — | Example | — |\n".encode()
    )
    (key_dir / "pm-state.md").write_bytes(
        b"# Example\r\n\r\n## 1. Snapshot\r\n" + FIELDS + PASS
        + b"## 7. Process Log\r\n" + b"old log\r\n" * 40_000 + "最后一行".encode()
    )
    (tmp_path / "summary.md").write_text(SUMMARY, encoding="utf-8")
    return tmp_path, key_dir


def run(project, *args, summary_file=None, input_text=None):
    return subprocess.run(
        [sys.executable, str(CLI), "pm-state", "compact", "--project", str(project), "--key", KEY,
         "--summary", summary_file or str(project / "summary.md"), *args],
        capture_output=True, encoding="utf-8", input=input_text,
    )


def test_preview_and_apply_preserve_original_and_gate_evidence(project):
    root, key_dir = project
    state = key_dir / "pm-state.md"
    original = state.read_bytes()
    authority = key_dir.parent / "_index.parallel"
    original_index = authority.read_bytes()
    preview = run(root)
    assert preview.returncode == 0, preview.stderr
    report = json.loads(preview.stdout)
    sha = hashlib.sha256(original).hexdigest()
    assert report["source_sha256"] == sha
    assert report["can_apply"] and not report["applied"]
    assert state.read_bytes() == original
    assert not (key_dir / "pm-state-history").exists()
    assert not (root / ".mw").exists()

    applied = run(root, "--apply", sha)
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout) == {**report, "applied": True}
    compacted = state.read_bytes()
    assert len(compacted) == report["after_bytes"] < 1024
    assert FIELDS in compacted and PASS in compacted
    assert b"old log" not in compacted and report["archive"].encode() in compacted
    assert gzip.decompress((key_dir / report["archive"]).read_bytes()) == original
    assert authority.read_bytes() == original_index
    assert list((root / ".mw").iterdir()) == []


@pytest.mark.parametrize("case", ("active", "stale", "phase", "gate", "short", "summary"))
def test_refuses_unsafe_application(project, case):
    root, key_dir = project
    state = key_dir / "pm-state.md"
    original = state.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    if case == "active":
        (key_dir.parent / "_index.parallel").write_text(
            "| sample | active | EXECUTE | host:123 | - | Example | - |\n", encoding="utf-8"
        )
        assert json.loads(run(root).stdout)["can_apply"] is False
    elif case == "stale":
        state.write_bytes(original + b"\nNew progress\n")
    elif case == "phase":
        state.write_bytes(original.replace(b"- Phase: EXECUTE", b"- Phase: init"))
        sha = hashlib.sha256(state.read_bytes()).hexdigest()
    elif case == "gate":
        state.write_bytes(original.replace(PASS, b""))
        sha = hashlib.sha256(state.read_bytes()).hexdigest()
        (root / "summary.md").write_text(SUMMARY + "\nPremature PASS\n", encoding="utf-8")
    elif case == "short":
        state.write_bytes(FIELDS)
        sha = hashlib.sha256(state.read_bytes()).hexdigest()
    else:
        (root / "summary.md").write_text(SUMMARY + "\n- Phase: DONE\n", encoding="utf-8")
    before = state.read_bytes()
    result = run(root, "--apply", sha)
    assert result.returncode == 2
    assert state.read_bytes() == before
    assert not (key_dir / "pm-state-history").exists()


def test_archive_collision_fails_before_state_replacement(project):
    root, key_dir = project
    original = (key_dir / "pm-state.md").read_bytes()
    preview = json.loads(run(root).stdout)
    archive = key_dir / preview["archive"]
    archive.parent.mkdir()
    wrong_archive = gzip.compress(b"wrong source")
    archive.write_bytes(wrong_archive)
    result = run(root, "--apply", preview["source_sha256"])
    assert result.returncode == 2
    assert "Existing archive does not match" in result.stderr
    assert archive.read_bytes() == wrong_archive
    assert (key_dir / "pm-state.md").read_bytes() == original


@pytest.mark.parametrize("case", ("owned", "other_process", "claim_drift", "stale"))
def test_pi_parent_claim_applies_with_standard_input(project, case):
    root, key_dir = project
    authority = key_dir.parent / "_index.parallel"
    pid = os.getpid() if case != "other_process" else os.getppid()
    claim = f"{socket.gethostname()}:{pid}"
    index = f"| sample | active | EXECUTE | {claim} | — | Example | — |\n".encode()
    authority.write_bytes(index)
    state = key_dir / "pm-state.md"
    claim_bytes = claim.encode() if case != "claim_drift" else b"foreign:123"
    original = state.read_bytes().replace(b"- Claim-Id: \r\n", b"- Claim-Id: " + claim_bytes + b"\r\n")
    state.write_bytes(original)
    sha = hashlib.sha256(original).hexdigest() if case != "stale" else "1" * 64

    result = run(root, "--apply", sha, "--window-claim-id", claim, summary_file="-", input_text=SUMMARY)
    assert authority.read_bytes() == index
    if case != "owned":
        assert result.returncode == 2
        assert state.read_bytes() == original
        assert not (key_dir / "pm-state-history").exists()
        return

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["applied"] and report["claim_id"] == claim and report["status"] == "active"
    assert b"- Claim-Id: " + claim_bytes + b"\r\n" in state.read_bytes()
    assert gzip.decompress((key_dir / report["archive"]).read_bytes()) == original
