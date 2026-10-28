"""test/test_write_face_doctor.py - W-15 / AC-006: the `mw doctor` write-face
refusal surface.

Card: `.agenticdoc/mw-write-face-guard/tasks/T-W-I15-doctor-refusal-surface.md`

The gap: both audit channels already write refusals (conductor timeline
`write-face-*` events, `autopilot/dispatch.py::_write_face_audit`; PM ledger
`phase:"dispatch-alarm"`/`kind:"write-face-refusal"` rows,
`pm-orchestrator.ts::recordDispatchAlarm`), but no read-only command surface
listed them.  `mw.py::_doctor_write_face` is that surface: shape
`{"total", "by_code", "by_source", "recent"}`.

Contract under test:
* (a) a fresh project is 0 with an empty `recent`, and the section never enters
  `issues` / never flips `summary.healthy` (0 and N both healthy);
* (b) conductor events: counts by code, per-source, `recent` sample fields;
* (c) PM ledger rows, with torn/other-kind/other-phase rows ignored;
* (d) rotated timeline generations (`.jsonl.1`) are still counted;
* (e) the section is zero-write: a project-tree hash snapshot is unchanged;
* (f) the CLI/report assembly reuses the existing doctor harness
  (`test_mwds_t08_doctor_blocked.py`) instead of re-inventing it.

Run: cd packages/multi-workers; python -m pytest test/test_write_face_doctor.py -q
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys

import pytest

PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

import mw  # noqa: E402
import mw_common  # noqa: E402
import test_mwds_t08_doctor_blocked as doctor_harness  # noqa: E402
from autopilot import timeline as timeline_mod  # noqa: E402

PROVIDERS = PKG_ROOT / "providers.json"
AUTOPILOT_DIR = pathlib.PurePosixPath(".agenticdoc/_autopilot")


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real `~/.agents/autopilot-defaults.json` may leak into these cases
    (same isolation as the reused t08 doctor harness)."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


def _timeline(project: pathlib.Path) -> timeline_mod.Timeline:
    return timeline_mod.Timeline(timeline_mod.timeline_path(project))


def _rotated_timeline(project: pathlib.Path, generation: int = 1) -> pathlib.Path:
    return project / ".agenticdoc" / "_autopilot" / f"timeline.jsonl.{generation}"


def _write_ledger(project: pathlib.Path, lines: list[str]) -> pathlib.Path:
    path = project / ".agenticdoc" / "_autopilot" / "auto-decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _doctor_json(project: pathlib.Path) -> tuple[int, dict]:
    """Run the real CLI entry (`mw.cmd_doctor`, JSON path) and parse stdout.

    The assembler (`doctor_harness._doctor_args`) is the existing t08 harness —
    reused, not re-created (card requirement 6f)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rc = mw.cmd_doctor(doctor_harness._doctor_args(project, as_json=True))
    return rc, json.loads(buffer.getvalue())


def _write_face(project: pathlib.Path) -> dict:
    return _doctor_json(project)[1]["write_face"]


def _plain_report(project: pathlib.Path) -> dict:
    return mw_common.doctor_report(
        project,
        fix=False,
        config=mw_common.load_providers(PROVIDERS),
        stale_after_sec=90,
        worktree_scan_roots=None,
    )


def _overlap_detail(task_key: str, other: str, sample: str) -> str:
    return f"{task_key}: overlap with {other} at {sample} (packages/x/** vs {sample})"


def _rejected_detail(task_key: str, code: str) -> str:
    return f"{task_key}: {code} entry '!packages/x/**'"


def _pm_row(seq: int, detail: str, *, phase: str = "dispatch-alarm",
            kind: str = "write-face-refusal", count: int = 1) -> str:
    return json.dumps(
        {"seq": seq, "phase": phase, "kind": kind, "count": count, "detail": detail}
    )


# ---------------------------------------------------------------------------
# (a) a fresh project is 0, empty, and never an issue
# ---------------------------------------------------------------------------


def test_a_empty_project_is_zero_and_out_of_the_health_verdict(tmp_path):
    rc, report = _doctor_json(tmp_path)
    section = report["write_face"]
    # The whole shape is locked: no extra keys, no invented buckets.
    assert section == {
        "total": 0,
        "by_code": {},
        "by_source": {"conductor": 0, "pm": 0},
        "recent": [],
    }
    assert mw._format_write_face_doctor_line(section) == (
        "write-face: no gate refusals (conductor=0, pm=0)"
    )
    # Not an issue, and the summary is byte-identical to the pre-section report.
    plain = _plain_report(tmp_path)
    assert report["summary"] == plain["summary"]
    assert report["summary"]["issues"] == plain["summary"]["issues"]
    assert not any("write-face" in str(item) for item in report["summary"]["issues"])
    assert all("write-face" not in str(item) for item in report["summary"]["suggestions"])
    assert rc == (0 if plain["summary"]["healthy"] else 1)


def test_a_zero_refusals_can_still_be_a_green_doctor(tmp_path):
    """The positive half of "0 must not be unhealthy": with the one unrelated
    axis (a live service) satisfied, `mw doctor` is green at total=0."""
    doctor_harness._make_service_running(tmp_path)
    plain = _plain_report(tmp_path)
    assert plain["summary"]["healthy"] is True, plain["summary"]["issues"]
    rc, report = _doctor_json(tmp_path)
    assert report["write_face"]["total"] == 0
    assert report["summary"]["healthy"] is True
    assert rc == 0


# ---------------------------------------------------------------------------
# (b) conductor timeline events
# ---------------------------------------------------------------------------


def test_b_conductor_events_count_by_code_and_carry_samples(tmp_path):
    tl = _timeline(tmp_path)
    tl.append(
        "write-face-overlap", key="wfk",
        detail=_overlap_detail("w-a", "w-b", "packages/x/file.ts"),
    )
    # D-006 fallback shape: `undecidable overlap with <key> (...)` — no sample.
    tl.append(
        "write-face-overlap", key="wfk",
        detail="w-c: undecidable overlap with w-d (unsupported-syntax: x) treated as overlap",
    )
    tl.append(
        "write-face-rejected", key="wfk",
        detail=_rejected_detail("w-e", "write-face-invalid-entry"),
    )
    tl.append("beat", key="-")  # unrelated event names are ignored

    section = _write_face(tmp_path)
    assert section["total"] == 3
    assert section["by_source"] == {"conductor": 3, "pm": 0}
    assert section["by_code"] == {"write-face-invalid-entry": 1, "write-face-overlap": 2}
    assert len(section["recent"]) == 3

    recent = section["recent"]
    # Newest first (all events share a second, so seq is the tiebreak).
    assert recent[0]["task_key"] == "w-e"
    assert recent[0]["source"] == "conductor"
    assert recent[0]["code"] == "write-face-invalid-entry"
    assert recent[0]["ts"]
    assert recent[0]["overlap_with"] is None
    assert recent[0]["sample"] is None

    provable = next(e for e in recent if e["overlap_with"] == "w-b")
    assert provable["task_key"] == "w-a"
    assert provable["sample"] == "packages/x/file.ts"
    assert provable["code"] == "write-face-overlap"

    unsupported = next(e for e in recent if e["overlap_with"] == "w-d")
    assert unsupported["sample"] is None
    assert unsupported["code"] == "write-face-overlap"


def test_b_undeclared_event_counts_with_its_event_name_code(tmp_path):
    tl = _timeline(tmp_path)
    tl.append(
        "write-face-undeclared", key="wfk",
        detail="w-u: write_face undeclared; 2 same-owner worker(s) in flight",
    )
    section = _write_face(tmp_path)
    assert section["total"] == 1
    assert section["by_code"] == {"write-face-undeclared": 1}
    assert section["recent"][0]["task_key"] == "w-u"
    assert section["recent"][0]["code"] == "write-face-undeclared"


def test_b_recent_is_capped_at_the_five_newest(tmp_path):
    tl = _timeline(tmp_path)
    for index in range(7):
        tl.append(
            "write-face-rejected", key="wfk",
            detail=f"w-{index}: write-face-escape ../{index}",
        )
    section = _write_face(tmp_path)
    assert section["total"] == 7
    assert len(section["recent"]) == 5
    assert [e["task_key"] for e in section["recent"]] == [
        "w-6", "w-5", "w-4", "w-3", "w-2",
    ]


def test_unexpected_detail_still_counts_with_null_side_fields(tmp_path):
    """Requirement 4: a row whose additional fields cannot be parsed is still
    counted; only the unread fields are null."""
    tl = _timeline(tmp_path)
    # No `": "` separator at all: no task key, but the code is the first token.
    tl.append("write-face-rejected", key="wfk", detail="write-face-escape ../x")
    # Empty detail: the event name is the whole information.
    tl.append("write-face-overlap", key="wfk", detail="")
    # Empty detail on a container event: the code itself is unreadable.
    tl.append("write-face-rejected", key="wfk")

    section = _write_face(tmp_path)
    assert section["total"] == 3
    assert section["by_source"]["conductor"] == 3
    assert section["by_code"] == {
        "unknown": 1,
        "write-face-escape": 1,
        "write-face-overlap": 1,
    }
    by_code = {entry["code"]: entry for entry in section["recent"]}
    assert "write-face-escape" in by_code
    assert by_code["write-face-escape"]["task_key"] is None
    assert by_code["write-face-overlap"]["overlap_with"] is None
    assert by_code["write-face-overlap"]["sample"] is None
    assert None in by_code  # the unreadable-code row is present, not dropped


# ---------------------------------------------------------------------------
# (c) PM ledger rows
# ---------------------------------------------------------------------------


def test_c_pm_ledger_rows_count_and_other_rows_are_ignored(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _pm_row(
                1,
                "w-x: write-face-overlap: overlap-with:w-y sample=packages/x/file.ts",
            ),
            # A different alarm kind on the same channel: never a refusal.
            _pm_row(2, "w-z", kind="write-scope-risk", count=2),
            # Same kind but a different phase: not the dispatch-alarm channel.
            _pm_row(3, "not-a-refusal", phase="decide"),
            _pm_row(4, "w-a: write-face-invalid-entry: entry '!x'"),
            "{ this is a torn line",
            json.dumps([1, 2, 3]),  # valid JSON, not a row object
        ],
    )

    section = _write_face(tmp_path)
    assert section["total"] == 2
    assert section["by_source"] == {"conductor": 0, "pm": 2}
    assert section["by_code"] == {
        "write-face-invalid-entry": 1,
        "write-face-overlap": 1,
    }
    assert [entry["source"] for entry in section["recent"]] == ["pm", "pm"]

    # Newest first by ledger seq (no timestamp exists on these rows).
    assert section["recent"][0]["task_key"] == "w-a"
    assert section["recent"][0]["code"] == "write-face-invalid-entry"
    assert section["recent"][0]["ts"] is None

    overlap = section["recent"][1]
    assert overlap["task_key"] == "w-x"
    assert overlap["code"] == "write-face-overlap"
    assert overlap["overlap_with"] == "w-y"
    assert overlap["sample"] == "packages/x/file.ts"


def test_c_unsupported_pm_refusal_keeps_the_key_without_a_sample(tmp_path):
    _write_ledger(
        tmp_path,
        [_pm_row(1, "w-p: write-face-overlap: overlap-with:w-q unsupported=glob-product-state-limit")],
    )
    section = _write_face(tmp_path)
    assert section["total"] == 1
    entry = section["recent"][0]
    assert entry["task_key"] == "w-p"
    assert entry["overlap_with"] == "w-q"
    assert entry["sample"] is None


def test_c_missing_ledger_is_zero_and_raises_nothing(tmp_path):
    # No `.agenticdoc/_autopilot/` at all.
    assert not (tmp_path / ".agenticdoc").exists()
    section = _write_face(tmp_path)
    assert section["total"] == 0
    assert section["by_source"] == {"conductor": 0, "pm": 0}
    assert not (tmp_path / ".agenticdoc").exists()


# ---------------------------------------------------------------------------
# (d) rotation
# ---------------------------------------------------------------------------


def test_d_rotated_generation_is_counted(tmp_path):
    tl = _timeline(tmp_path)
    tl.append(
        "write-face-overlap", key="wfk",
        detail=_overlap_detail("w-old", "w-peer", "a/b.ts"),
    )
    assert tl.rotate() is True
    assert _rotated_timeline(tmp_path, 1).exists()
    tl.append(
        "write-face-rejected", key="wfk",
        detail="w-new: write-face-escape ../x",
    )

    section = _write_face(tmp_path)
    assert section["total"] == 2
    assert section["by_source"]["conductor"] == 2
    assert section["by_code"] == {"write-face-escape": 1, "write-face-overlap": 1}
    assert {entry["task_key"] for entry in section["recent"]} == {"w-old", "w-new"}


# ---------------------------------------------------------------------------
# (e) zero-write proof
# ---------------------------------------------------------------------------


def test_e_doctor_write_face_is_zero_write(tmp_path):
    tl = _timeline(tmp_path)
    tl.append(
        "write-face-overlap", key="wfk",
        detail=_overlap_detail("w-a", "w-b", "packages/x/file.ts"),
    )
    tl.append(
        "write-face-rejected", key="wfk",
        detail=_rejected_detail("w-c", "write-face-outside-base"),
    )
    _write_ledger(
        tmp_path,
        [_pm_row(1, "w-p: write-face-overlap: overlap-with:w-q sample=packages/x/file.ts")],
    )

    before = doctor_harness._tree_hashes(tmp_path)
    assert f"{AUTOPILOT_DIR}/" in before  # both sources live inside the tree

    rc, report = _doctor_json(tmp_path)
    assert rc in (0, 1)
    assert report["write_face"]["total"] == 3
    mw._format_write_face_doctor_line(report["write_face"])
    text_buffer = io.StringIO()
    with contextlib.redirect_stdout(text_buffer):
        mw.cmd_doctor(doctor_harness._doctor_args(tmp_path, as_json=False))
    assert "write-face: 3 gate refusal(s)" in text_buffer.getvalue()

    after = doctor_harness._tree_hashes(tmp_path)
    assert doctor_harness._files_created(before, after) == 0
    assert after == before
    assert doctor_harness._tree_digest(after) == doctor_harness._tree_digest(before)


def test_e_no_new_files_even_on_a_bare_project(tmp_path):
    before = doctor_harness._tree_hashes(tmp_path)
    _write_face(tmp_path)
    after = doctor_harness._tree_hashes(tmp_path)
    assert after == before


# ---------------------------------------------------------------------------
# (f) the reused assembler is the real CLI shape
# ---------------------------------------------------------------------------


def test_f_reused_harness_assembler_drives_the_real_cli(tmp_path):
    """The t08 `_doctor_args` namespace is what `python mw.py doctor` parses;
    the section is therefore produced by the production entry, not a copy."""
    args = doctor_harness._doctor_args(tmp_path)
    assert args.project == str(tmp_path)
    assert args.json is False
    rc, report = _doctor_json(tmp_path)
    assert "write_face" in report
    assert rc in (0, 1)  # driven by summary.healthy, never by write_face


@pytest.mark.parametrize("as_json", [True, False])
def test_f_write_face_absent_from_issues_in_both_output_modes(tmp_path, as_json):
    tl = _timeline(tmp_path)
    tl.append("write-face-rejected", key="wfk", detail="w-x: write-face-escape ../y")
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rc = mw.cmd_doctor(doctor_harness._doctor_args(tmp_path, as_json=as_json))
    if as_json:
        report = json.loads(buffer.getvalue())
        assert report["write_face"]["total"] == 1
        assert not any("write-face" in str(item) for item in report["summary"]["issues"])
    else:
        assert "write-face: 1 gate refusal(s)" in buffer.getvalue()
    plain = _plain_report(tmp_path)
    assert rc == (0 if plain["summary"]["healthy"] else 1)
