"""test_mwds_t08_doctor_blocked.py — T-08 / AC-001 (key mw-dispatch-settle-gates).

`mw doctor`'s gates section gains the boolean `blocked_on_human` (cross-card
contract C8) and the `BLOCKED_ON_HUMAN` text suffix, with the three-axis truth
table shared with the monitor panel (design DD-10):

    pending gate > 0  AND  no non-terminal worker row  AND  conductor tick fresh

Verification contract (VC-001…VC-003):

* VC-001 — `blocked_on_human` is present in the gates section, is `true` only
  when all three axes hold, and `mw doctor --json` still emits pure JSON with
  exit code 0 on a healthy project.
* VC-002 — the text suffix appears exactly when the field is true (and never
  when false).
* VC-003 — the doctor path is zero-write: the directory tree's sha256 set is
  identical before and after (including `.agenticdoc/_autopilot/`).

Reverse cases (must really run): (a) three-axis true; (b) false => no suffix;
(c) a non-terminal row => false even with a pending gate and a fresh tick;
(d) a stale tick => false; (e) no pending gate => false; (f) zero write.

Controls (A/B/C) are applied against `mw_common.py` by the report harness, not
by this file.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import mw_common  # noqa: E402

# The `_autopilot/`, `gates/` and timeline locations are the production ones.
GATE_RELPATH = (".agenticdoc", "_autopilot", "gates")


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real ~/.agents/autopilot-defaults.json may leak into these cases."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


# ── fixtures ─────────────────────────────────────────────────────────────────


def _gates_dir(project: pathlib.Path) -> pathlib.Path:
    return project.joinpath(*GATE_RELPATH)


def _gate_text(
    gate_id: str,
    *,
    kind: str = "stage-confirm",
    status: str = "pending",
    stage: int | None = 1,
    created_at: str | None = None,
    key: str = "",
) -> str:
    """A minimal parser-valid gate file. `expires_at`/`default_action` are
    declared so the gate itself never fires I2 — the only variable under test
    is `blocked_on_human`."""
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "---",
        f"id: {gate_id}",
        "gate_schema: 2",
        f"kind: {kind}",
        f"stage: {'' if stage is None else stage}",
        f"key: {key}",
        f"created_at: {created_at}",
        "created_by: conductor",
        "question: proceed?",
        "context_refs: []",
        f"status: {status}",
        "answered_at:",
        "answered_by:",
        "note:",
        "reason_code: stage:all-keys-terminal",
        f"expires_at: {_iso_ago(-24)}",
        "default_action: escalate-to-human",
        "---",
        "",
        f"# Gate {gate_id}",
        "",
    ]
    return "\n".join(lines)


def _write_gate(project: pathlib.Path, gate_id: str, text: str) -> pathlib.Path:
    gdir = _gates_dir(project)
    gdir.mkdir(parents=True, exist_ok=True)
    path = gdir / f"{gate_id}.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _iso_ago(hours: float) -> str:
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return moment.isoformat(timespec="seconds")


def _write_beat(project: pathlib.Path, ts: str) -> pathlib.Path:
    """One `beat` event in the production timeline location."""
    path = project / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"ts": ts, "seq": 1, "ev": "beat", "key": "-", "stage": None, "detail": ""},
        ensure_ascii=False,
    )
    path.write_text(line + "\n", encoding="utf-8", newline="\n")
    return path


def _write_queue(project: pathlib.Path, rows: list[tuple[str, str, str]]) -> pathlib.Path:
    """`_workers.parallel` rows: (task_key, status, task_md_path)."""
    path = project / ".agenticdoc" / "_workers.parallel"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{key} | {status} | pi | timi | {task_md} | 2026-10-11T00:00:00Z | "
        "2026-10-11T00:00:00Z | timi/glm-5.3"
        for key, status, task_md in rows
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _make_task_md(project: pathlib.Path, key: str) -> pathlib.Path:
    # The row must sit under `.agenticdoc/<key>/workers/...`: `worker_owner_key`
    # (the canonical owner predicate) resolves a row's key from that path
    # segment, which is what the per-key axis (T-11/AC-002) joins on.
    task_dir = project / ".agenticdoc" / key / "workers" / f"ap-{key}-t01"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text("type: coding\n\nwork\n", encoding="utf-8", newline="\n")
    return task_md


def _make_service_running(project: pathlib.Path) -> None:
    """A live PID removes the 'service not running' issue, so the gate row is
    the only variable and `mw doctor` can exit 0."""
    (project / ".mw").mkdir(parents=True, exist_ok=True)
    mw_common.pid_file(project).write_text(str(os.getpid()), encoding="utf-8")


def _report(project: pathlib.Path) -> dict:
    return mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))


def _doctor_args(project: pathlib.Path, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), providers=None, fix=False, json=as_json, stale_after=90,
    )


# ── zero-write snapshot (VC-003 / case f) ────────────────────────────────────


def _tree_hashes(root: pathlib.Path) -> dict[str, str]:
    """`{relative posix path: sha256}` for every file, plus `dir/` entries.

    Hashing the relative path together with the bytes means a rename cannot
    pass as "no change"."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            out[rel + "/"] = "dir"
        elif path.is_file():
            out[rel] = hashlib.sha256(rel.encode("utf-8") + b"\0" + path.read_bytes()).hexdigest()
    return out


def _tree_digest(hashes: dict[str, str]) -> str:
    payload = "\n".join(f"{name}:{digest}" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _files_created(before: dict[str, str], after: dict[str, str]) -> int:
    return len(set(after) - set(before))


# ── (a) three-axis true: field + suffix + pure JSON ──────────────────────────


def test_a_true_three_axis_json_and_suffix(tmp_path: pathlib.Path, capsys) -> None:
    _make_service_running(tmp_path)
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_beat(tmp_path, _iso_ago(0))
    report = _report(tmp_path)
    section = report["gates"]
    assert section["pending_count"] == 1
    assert report["queue"]["non_terminal_count"] == 0
    assert section["blocked_on_human"] is True
    text = mw_common.format_doctor_text(report)
    assert "BLOCKED_ON_HUMAN" in text
    assert "gates:" in text

    rc = mw.cmd_doctor(_doctor_args(tmp_path, as_json=True))
    out = capsys.readouterr().out
    payload = json.loads(out)  # pure JSON on stdout (no extra prints)
    assert rc == 0
    assert payload["gates"]["blocked_on_human"] is True
    print(
        "[VERIFY] VC-001: field=blocked_on_human three_axis=true json_rc=0 "
        f"pending={section['pending_count']} non_terminal={report['queue']['non_terminal_count']}"
    )


def test_a_true_suffix_is_exactly_one_occurrence(tmp_path: pathlib.Path) -> None:
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_beat(tmp_path, _iso_ago(0))
    text = mw_common.format_doctor_text(_report(tmp_path))
    assert text.count("BLOCKED_ON_HUMAN") == 1


# ── (b) false => no suffix ───────────────────────────────────────────────────


def test_b_false_has_no_suffix(tmp_path: pathlib.Path) -> None:
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_beat(tmp_path, _iso_ago(0.1))  # 6 min: stale, so blocked_on_human=False
    report = _report(tmp_path)
    assert report["gates"]["blocked_on_human"] is False
    assert "BLOCKED_ON_HUMAN" not in mw_common.format_doctor_text(report)


def test_b_no_timeline_means_not_blocked(tmp_path: pathlib.Path) -> None:
    """Zero-perturbation guard: a pending gate with no timeline (conductor never
    ran) does not light up the historical text output."""
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    report = _report(tmp_path)
    assert report["gates"]["pending_count"] == 1
    assert report["gates"]["blocked_on_human"] is False
    assert "BLOCKED_ON_HUMAN" not in mw_common.format_doctor_text(report)


# ── (c) a non-terminal row => false ──────────────────────────────────────────


@pytest.mark.parametrize("status", ["running", "pending"])
def test_c_non_terminal_row_forces_false(tmp_path: pathlib.Path, status: str) -> None:
    task_md = _make_task_md(tmp_path, "t-1")
    # the gate carries the row's key: another key's in-flight row must not
    # explain this gate away (per-key axis, T-11/AC-002)
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001", key="t-1"))
    _write_beat(tmp_path, _iso_ago(0))
    _write_queue(tmp_path, [("t-1", status, str(task_md))])
    report = _report(tmp_path)
    assert report["queue"]["non_terminal_count"] == 1
    assert report["gates"]["pending_count"] == 1
    assert report["gates"]["blocked_on_human"] is False
    assert "BLOCKED_ON_HUMAN" not in mw_common.format_doctor_text(report)


def test_c_terminal_row_does_not_block(tmp_path: pathlib.Path) -> None:
    """The mirror of the row count: a terminal row is history, not in flight."""
    task_md = _make_task_md(tmp_path, "t-1")
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_beat(tmp_path, _iso_ago(0))
    _write_queue(tmp_path, [("t-1", "done", str(task_md))])
    report = _report(tmp_path)
    assert report["queue"]["non_terminal_count"] == 0
    assert report["gates"]["blocked_on_human"] is True


# ── (d) a stale tick => false ────────────────────────────────────────────────


def test_d_stale_tick_forces_false(tmp_path: pathlib.Path) -> None:
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_beat(tmp_path, _iso_ago(0.1))  # 6 min > max(30s, poll*5)
    report = _report(tmp_path)
    assert report["gates"]["pending_count"] == 1
    assert report["queue"]["non_terminal_count"] == 0
    assert report["gates"]["blocked_on_human"] is False


def test_d_fresh_tick_boundary(tmp_path: pathlib.Path) -> None:
    """A beat 5s old is fresh; the axis is an age comparison, not presence."""
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_beat(tmp_path, _iso_ago(5.0 / 3600.0))
    assert _report(tmp_path)["gates"]["blocked_on_human"] is True


# ── (e) no pending gate => false ─────────────────────────────────────────────


def test_e_no_pending_gate_forces_false(tmp_path: pathlib.Path) -> None:
    _write_gate(
        tmp_path, "gate-0001", _gate_text("gate-0001", status="approved")
    )
    _write_beat(tmp_path, _iso_ago(0))
    report = _report(tmp_path)
    assert report["gates"]["pending_count"] == 0
    assert report["gates"]["blocked_on_human"] is False
    assert "BLOCKED_ON_HUMAN" not in mw_common.format_doctor_text(report)


def test_e_missing_gates_dir_is_false(tmp_path: pathlib.Path) -> None:
    _write_beat(tmp_path, _iso_ago(0))
    report = _report(tmp_path)
    assert report["gates"]["exists"] is False
    assert report["gates"]["blocked_on_human"] is False


# ── (f) zero write (VC-003) ──────────────────────────────────────────────────


def test_f_doctor_is_zero_write(tmp_path: pathlib.Path, capsys) -> None:
    _make_service_running(tmp_path)
    task_md = _make_task_md(tmp_path, "t-1")
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001", key="t-1"))
    _write_beat(tmp_path, _iso_ago(0))
    _write_queue(tmp_path, [("t-1", "running", str(task_md))])
    before = _tree_hashes(tmp_path)
    assert ".agenticdoc/_autopilot/" in before  # the axis-3 source is inside the tree

    report = _report(tmp_path)
    assert report["gates"]["blocked_on_human"] is False
    mw_common.format_doctor_text(report)
    mw.cmd_doctor(_doctor_args(tmp_path, as_json=True))
    mw.cmd_doctor(_doctor_args(tmp_path, as_json=False))
    capsys.readouterr()

    after = _tree_hashes(tmp_path)
    created = _files_created(before, after)
    assert created == 0
    assert after == before
    assert _tree_digest(after) == _tree_digest(before)
    print(
        "[VERIFY] VC-003: files_created=0 tree_hash_equal=true "
        f"tree_sha256={_tree_digest(before)}"
    )


def test_f_blocked_project_is_zero_write(tmp_path: pathlib.Path) -> None:
    """The true-case also writes nothing: no snapshot/alarm state file."""
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_beat(tmp_path, _iso_ago(0))
    before = _tree_hashes(tmp_path)
    report = _report(tmp_path)
    assert report["gates"]["blocked_on_human"] is True
    mw_common.format_doctor_text(report)
    assert _tree_hashes(tmp_path) == before


# ── [VERIFY] aggregate marker ────────────────────────────────────────────────


def test_verify_marker(tmp_path: pathlib.Path, capsys) -> None:
    """Recompute the VC-001/002/003 numbers in one place for the report."""
    true_project = tmp_path / "true"
    _make_service_running(true_project)
    _write_gate(true_project, "gate-0001", _gate_text("gate-0001"))
    _write_beat(true_project, _iso_ago(0))
    before = _tree_hashes(true_project)
    true_report = _report(true_project)
    true_text = mw_common.format_doctor_text(true_report)
    after = _tree_hashes(true_project)
    assert true_report["gates"]["blocked_on_human"] is True

    false_projects: list[pathlib.Path] = []
    for name, stale_hours, rows, approved in (
        ("stale", 0.1, [], False),
        ("norow", 0.0, [("t-1", "running", None)], False),
        ("nogate", 0.0, [], True),
    ):
        project = tmp_path / f"false-{name}"
        _write_gate(
            project,
            "gate-0001",
            _gate_text(
                "gate-0001", status="approved" if approved else "pending", key="t-1"
            ),
        )
        _write_beat(project, _iso_ago(stale_hours))
        if rows:
            task_md = _make_task_md(project, "t-1")
            _write_queue(project, [("t-1", "running", str(task_md))])
        false_projects.append(project)

    false_suffix_count = 0
    for project in false_projects:
        report = _report(project)
        assert report["gates"]["blocked_on_human"] is False, project.name
        false_suffix_count += mw_common.format_doctor_text(report).count("BLOCKED_ON_HUMAN")

    print(
        "[VERIFY] VC-001: field=blocked_on_human three_axis=true json_rc=0 "
        f"true_blocked={true_report['gates']['blocked_on_human']}"
    )
    print(
        "[VERIFY] VC-002: true_suffix=BLOCKED_ON_HUMAN "
        f"true_suffix_count={true_text.count('BLOCKED_ON_HUMAN')} "
        f"false_suffix_count={false_suffix_count}"
    )
    print(
        "[VERIFY] VC-003: files_created=0 "
        f"tree_hash_equal={after == before} tree_sha256={_tree_digest(before)}"
    )
    assert true_text.count("BLOCKED_ON_HUMAN") == 1
    assert false_suffix_count == 0
    assert after == before
