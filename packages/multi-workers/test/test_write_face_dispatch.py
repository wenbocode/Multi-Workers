"""test/test_write_face_dispatch.py - W-03: the conductor dispatch write-face gate.

Card: `.agenticdoc/mw-write-face-guard/tasks/T-W-I03-dispatch-refusal.md`
(AC-001/002/003/008/014).  The gate under test is `autopilot/dispatch.py`:
the write-face judgement, the `task.md` write and the queue-row write share
ONE `.mw/workers.lock` critical section, and every refusal is zero-side-effect.

The lock is never mocked: the concurrency tests below spawn two real
`dispatch()` processes and race them through a file barrier (card requirement
10 forbids a mocked lock).

Run: cd packages/multi-workers; python -m pytest test/test_write_face_dispatch.py -q
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import mw_common  # noqa: E402
from autopilot import conductor  # noqa: E402
from autopilot import dispatch  # noqa: E402
from autopilot import timeline as timeline_mod  # noqa: E402
from autopilot import write_face as wf  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_PATH = PKG_ROOT / "test" / "fixtures" / "write-face-corpus.json"
OWNER = "wfk"

_CARD_HEAD = (
    "type: coding\n"
    "\n"
    "## 上下文\n"
    "\n"
    "上下文。\n"
    "\n"
    "## 要求\n"
    "\n"
    "要求。\n"
    "\n"
    "## 交付格式\n"
    "\n"
    "交付格式。\n"
    "\n"
)


def _ci() -> bool:
    return os.name == "nt"


def _timeline(project: pathlib.Path) -> timeline_mod.Timeline:
    return timeline_mod.Timeline(
        project / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )


def _write_card(project: pathlib.Path, owner: str, stem: str, section_body: str) -> None:
    """A real card file, so `dispatch_card` finds it and the renderer emits
    `write_face:` from the card's `## 写入允许面` section."""
    card_dir = project / ".agenticdoc" / owner / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{stem}.md").write_text(
        _CARD_HEAD + f"## 写入允许面\n\n{section_body}\n",
        encoding="utf-8",
        newline="\n",
    )


def _dispatch(project, owner, stem, tl, task_type="phase-writer"):
    return dispatch.dispatch(
        project, owner, stem, task_type, "Do the work.",
        loop=f"exec:{owner}:{stem}", attempt=1, timeline=tl,
    )


def _task_dir(project: pathlib.Path, owner: str, stem: str) -> pathlib.Path:
    return project / ".agenticdoc" / owner / "workers" / dispatch.task_key_for(owner, stem)


def _rows(project: pathlib.Path) -> list[dict]:
    return mw_common.parse_workers_file(mw_common.workers_path(project))


def _task_md_text(project: pathlib.Path, owner: str, stem: str) -> str:
    return (_task_dir(project, owner, stem) / "task.md").read_text(encoding="utf-8")


def _events(tl: timeline_mod.Timeline) -> list[dict]:
    return timeline_mod.query_events(tl.path).events


# ---------------------------------------------------------------------------
# AC-001 / AC-011 (D-001): the card section renders one `write_face:` head
# ---------------------------------------------------------------------------


def test_declared_face_renders_one_head_line_and_parses_back(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(
        tmp_path, OWNER, "t1",
        "- `packages/x/**`（新建）\n- packages/y/z.py\n",
    )
    result = _dispatch(tmp_path, OWNER, "t1", tl)
    assert result.ok and result.row_verified, result.reason
    text = _task_md_text(tmp_path, OWNER, "t1")
    assert "write_face: packages/x/**, packages/y/z.py\n" in text
    parsed = wf.parse_write_face(text, base=str(tmp_path), case_insensitive=_ci())
    assert isinstance(parsed, wf.WriteFace), parsed
    assert parsed.allow_entries == ("packages/x/**", "packages/y/z.py")
    assert [e["ev"] for e in _events(tl)] == ["dispatch"]


def test_declared_but_empty_section_renders_the_undeclared_marker(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "t1", "-")  # present section, zero entries
    result = _dispatch(tmp_path, OWNER, "t1", tl)
    assert result.ok
    text = _task_md_text(tmp_path, OWNER, "t1")
    assert "write_face: -\n" in text
    parsed = wf.parse_write_face(text, base=str(tmp_path), case_insensitive=_ci())
    assert isinstance(parsed, wf.Undeclared)
    # Card-backed + no contention still leaves the audit trail.
    assert [e["ev"] for e in _events(tl)] == ["write-face-undeclared", "dispatch"]


def test_card_less_render_has_no_write_face_line(tmp_path):
    result = dispatch.dispatch(
        tmp_path, OWNER, "t1", "repair", "Fix.",
        loop="repair:wfk", attempt=1,
    )
    assert result.ok
    assert "write_face:" not in _task_md_text(tmp_path, OWNER, "t1")


@pytest.mark.parametrize(
    "entries",
    [
        ["packages/x/**", "packages/y/z.py"],
        ["a/**/b/*.ts"],
        ["dir"],  # the normalized form of `dir/`
        ["A/**", "B/c.ts"],
        ["a/{b,c}/**"],
        ["packages/x/**", "a/{b,c}/**"],
    ],
    ids=[
        "plain",
        "mid-double-star",
        "normalized-trailing-slash",
        "case",
        "comma-brace",
        "mixed-comma",
    ],
)
def test_render_and_parse_are_the_same_source(entries):
    """D-113 identity contract: the rendered carrier parses back to exactly the
    declared (normalized) entries, order included.  The predicate must be the
    identity, not the historical "render == single-line join" comparison — that
    one re-read the lossy carrier and stayed green on the comma defect when
    `direct` was the single line (bad-on-bad false green)."""
    line = dispatch.render_write_face_line(entries)
    parsed = wf.parse_write_face(line, base=str(REPO_ROOT), case_insensitive=False)
    assert isinstance(parsed, wf.WriteFace), parsed
    assert list(parsed.allow_entries) == entries


def test_frozen_corpus_entries_roundtrip_through_the_renderer():
    """D-113 strong form: every frozen `parse` row whose expectation is an
    entry list (16 rows: P01/P05-P12/P17-P23) must survive
    `parse(render(row.expect.entries))` unchanged.  The corpus is read-only
    here; this is the machine lock tying renderer and corpus to one source."""
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    rows = [row for row in corpus["parse"] if row["expect"]["kind"] == "entries"]
    assert len(rows) == 16, [row["name"] for row in rows]
    for row in rows:
        entries = list(row["expect"]["entries"])
        line = dispatch.render_write_face_line(entries)
        parsed = wf.parse_write_face(line, base=str(REPO_ROOT), case_insensitive=False)
        assert isinstance(parsed, wf.WriteFace), row["name"]
        assert list(parsed.allow_entries) == entries, row["name"]


def test_card_render_roundtrip_matches_the_card_entries(tmp_path):
    card = {
        "path": "tasks/t1.md",
        "sha256": "x",
        "context": "c",
        "requirements": "r",
        "deliverables": "d",
        "extras": [{"title": "写入允许面", "body": "- `a/**`\n- `b/c.py`\n"}],
    }
    text = dispatch.render_task_md(
        "phase-writer", "p", loop="l", attempt=1, card=card
    )
    parsed = wf.parse_write_face(text, base=str(tmp_path), case_insensitive=False)
    assert isinstance(parsed, wf.WriteFace)
    assert parsed.allow_entries == ("a/**", "b/c.py")


def test_comma_entry_card_roundtrips_through_the_disk_task_md(tmp_path):
    """D-113 end-to-end: a card declaring the legal comma-bearing entry
    `a/{b,c}/**` dispatches (its own gate re-parses the block carrier), writes
    a task.md whose `write_face:` head is the block list, and that on-disk file
    parses back to exactly the declared entries in order."""
    tl = _timeline(tmp_path)
    _write_card(
        tmp_path, OWNER, "comma",
        "- `a/{b,c}/**`\n- `packages/x/**`\n",
    )
    result = _dispatch(tmp_path, OWNER, "comma", tl)
    assert result.ok and result.row_verified, result.reason
    text = _task_md_text(tmp_path, OWNER, "comma")
    assert "write_face:\n  - a/{b,c}/**\n  - packages/x/**\n" in text
    parsed = wf.parse_write_face(text, base=str(tmp_path), case_insensitive=_ci())
    assert isinstance(parsed, wf.WriteFace), parsed
    assert parsed.allow_entries == ("a/{b,c}/**", "packages/x/**")


# ---------------------------------------------------------------------------
# AC-001 / AC-002 (D-008): refusal is zero-side-effect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, code",
    [
        ("- `../outside/**`\n", wf.WRITE_FACE_ESCAPE),
        ("- `!a/**`\n", wf.WRITE_FACE_INVALID_ENTRY),
    ],
    ids=["escape", "invalid-entry"],
)
def test_own_face_parse_refusal_is_zero_side_effect(tmp_path, body, code):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "bad", body)
    result = _dispatch(tmp_path, OWNER, "bad", tl)
    assert not result.ok
    assert result.reason.startswith(code), result.reason
    assert result.task_md is None and result.row_verified is False
    assert not _task_dir(tmp_path, OWNER, "bad").exists()
    assert not mw_common.workers_path(tmp_path).exists()
    assert [e["ev"] for e in _events(tl)] == ["write-face-rejected"]


def test_own_face_outside_base_is_refused(tmp_path):
    tl = _timeline(tmp_path)
    outside = tmp_path.parent / "wf-outside" / "x.ts"
    _write_card(tmp_path, OWNER, "bad", f"- `{outside}`\n")
    result = _dispatch(tmp_path, OWNER, "bad", tl)
    assert not result.ok
    assert result.reason.startswith(wf.WRITE_FACE_OUTSIDE_BASE), result.reason
    assert not _task_dir(tmp_path, OWNER, "bad").exists()
    assert not mw_common.workers_path(tmp_path).exists()


def test_present_but_empty_head_is_refused_by_the_gate(tmp_path):
    """The rendered path maps an empty card section to `-` (undeclared), so a
    present-but-empty `write_face:` head only reaches the gate through a
    hand-written task.md — the gate still refuses it (D-001 §3.3)."""
    tl = _timeline(tmp_path)
    verdict = dispatch._write_face_verdict(
        tmp_path, OWNER, dispatch.task_key_for(OWNER, "x"),
        "---\ntype: coding\nwrite_face:\n---\n\nbody\n",
        card_backed=True, timeline=tl,
    )
    assert verdict is not None and not verdict.ok
    assert verdict.reason.startswith(wf.WRITE_FACE_EMPTY), verdict.reason
    assert not mw_common.workers_path(tmp_path).exists()
    assert [e["ev"] for e in _events(tl)] == ["write-face-rejected"]


def test_overlap_refusal_is_zero_side_effect_and_names_the_evidence(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "keep", "- `packages/x/**`\n")
    assert _dispatch(tmp_path, OWNER, "keep", tl).ok
    _write_card(tmp_path, OWNER, "new", "- `packages/x/file.ts`\n")

    result = _dispatch(tmp_path, OWNER, "new", tl)
    assert not result.ok
    assert result.reason.startswith("write-face-overlap"), result.reason
    assert "overlap-with:ap-wfk-keep" in result.reason
    assert "sample=packages/x/file.ts" in result.reason
    assert result.task_md is None
    # Zero side effects: no taskDir, no task.md, no new queue row.
    assert not _task_dir(tmp_path, OWNER, "new").exists()
    assert [r["task_key"] for r in _rows(tmp_path)] == ["ap-wfk-keep"]
    assert [e["ev"] for e in _events(tl)] == ["dispatch", "write-face-overlap"]


def test_non_overlapping_declared_face_dispatches(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "keep", "- `packages/x/**`\n")
    assert _dispatch(tmp_path, OWNER, "keep", tl).ok
    _write_card(tmp_path, OWNER, "new", "- `packages/other/**`\n")
    result = _dispatch(tmp_path, OWNER, "new", tl)
    assert result.ok, result.reason
    assert {r["task_key"] for r in _rows(tmp_path)} == {
        "ap-wfk-keep", "ap-wfk-new",
    }


def test_unsupported_operator_fallback_is_treated_as_overlap(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "keep", "- `!(a|b)`\n")
    assert _dispatch(tmp_path, OWNER, "keep", tl).ok
    _write_card(tmp_path, OWNER, "new", "- `x/y/**`\n")
    result = _dispatch(tmp_path, OWNER, "new", tl)
    assert not result.ok
    assert result.reason.startswith("write-face-overlap"), result.reason
    assert "overlap-with:ap-wfk-keep" in result.reason
    assert "unsupported=" in result.reason
    assert not _task_dir(tmp_path, OWNER, "new").exists()


def test_undeclared_inflight_side_does_not_refuse_by_overlap(tmp_path):
    """D-003: one undeclared side cannot prove an overlap, so no refusal."""
    tl = _timeline(tmp_path)
    assert _dispatch(tmp_path, OWNER, "keep", tl).ok  # card-less -> undeclared
    _write_card(tmp_path, OWNER, "new", "- `packages/x/**`\n")
    result = _dispatch(tmp_path, OWNER, "new", tl)
    assert result.ok, result.reason


# ---------------------------------------------------------------------------
# AC-003 (D-003): undeclared = serial-only for card-backed, never rejected
# ---------------------------------------------------------------------------


def test_card_backed_undeclared_is_serial_only(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "keep", "- `packages/x/**`\n")
    assert _dispatch(tmp_path, OWNER, "keep", tl).ok
    _write_card(tmp_path, OWNER, "undeclared", "-")  # renders `write_face: -`

    result = _dispatch(tmp_path, OWNER, "undeclared", tl)
    assert not result.ok
    assert result.reason.startswith("write-face-undeclared: serial-only"), result.reason
    assert result.task_md is None and result.row_verified is False
    assert not _task_dir(tmp_path, OWNER, "undeclared").exists()
    assert [r["task_key"] for r in _rows(tmp_path)] == ["ap-wfk-keep"]
    assert [e["ev"] for e in _events(tl)] == [
        "dispatch", "write-face-undeclared",
    ]


def test_card_backed_undeclared_without_contention_dispatches(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "solo", "-")
    result = _dispatch(tmp_path, OWNER, "solo", tl)
    assert result.ok, result.reason
    assert [e["ev"] for e in _events(tl)] == ["write-face-undeclared", "dispatch"]


def test_card_less_undeclared_is_audited_but_not_serialized(tmp_path):
    """Card-less internal dispatch (L3/repair/roadmap/phase-writer): audit the
    undeclared face, but never refuse a dispatch the conductor cannot retry
    with a fixable card (card requirement 5)."""
    tl = _timeline(tmp_path)
    assert _dispatch(tmp_path, OWNER, "keep", tl).ok  # card-less
    result = _dispatch(tmp_path, OWNER, "second", tl, task_type="repair")
    assert result.ok, result.reason
    assert [e["ev"] for e in _events(tl)] == [
        "dispatch", "write-face-undeclared", "dispatch",
    ]


def test_card_less_no_contention_has_no_extra_event(tmp_path):
    """No-contention card-less dispatch stays byte-identical to the pre-D-003
    flow (protects the AC-017 event-count assertions of the existing suite)."""
    tl = _timeline(tmp_path)
    assert _dispatch(tmp_path, OWNER, "solo", tl).ok
    assert [e["ev"] for e in _events(tl)] == ["dispatch"]


def test_same_task_key_is_not_self_refused_by_the_write_face_gate(tmp_path):
    """Requirement 3 excludes the dispatch's own task_key, so an in-flight
    same identity is never refused as `write-face-overlap`; the identity-level
    duplicate-dispatch guard (MDC M-04) is the refusal that fires instead, and
    it is zero-side-effect (no new task dir, no second row)."""
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "same", "- `packages/x/**`\n")
    first = _dispatch(tmp_path, OWNER, "same", tl)
    second = _dispatch(tmp_path, OWNER, "same", tl)
    assert first.ok, first.reason
    assert not second.ok, second.reason
    assert second.reason.startswith("duplicate-dispatch:"), second.reason
    assert second.task_md is None
    assert [r["task_key"] for r in _rows(tmp_path)] == ["ap-wfk-same"]


def test_other_owner_inflight_does_not_refuse(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, "other", "keep", "- `packages/x/**`\n")
    assert _dispatch(tmp_path, "other", "keep", tl).ok
    _write_card(tmp_path, OWNER, "new", "- `packages/x/file.ts`\n")
    result = _dispatch(tmp_path, OWNER, "new", tl)
    assert result.ok, result.reason


# ---------------------------------------------------------------------------
# AC-008: the in-flight set is recomputed from the live queue (no new column)
# ---------------------------------------------------------------------------


def test_no_queue_column_is_added(tmp_path):
    tl = _timeline(tmp_path)
    _write_card(tmp_path, OWNER, "t1", "- `packages/x/**`\n")
    assert _dispatch(tmp_path, OWNER, "t1", tl).ok
    raw = mw_common.workers_path(tmp_path).read_text(encoding="utf-8")
    for line in raw.splitlines():
        if not line.strip():
            continue
        assert len(line.split("|")) <= mw_common.WORKER_COLS_MAX


# ---------------------------------------------------------------------------
# AC-014 / requirement 10: two real processes race the same lock
# ---------------------------------------------------------------------------

_CHILD = r"""
import json, pathlib, sys, time

pkg, root, owner, stem, barrier = sys.argv[1:6]
sys.path.insert(0, pkg)
from autopilot import dispatch, timeline as tl_mod

root = pathlib.Path(root)
barrier = pathlib.Path(barrier)
(barrier / ("ready-" + stem)).write_text("1", encoding="utf-8")
deadline = time.time() + 60
while not (barrier / "start").exists():
    if time.time() > deadline:
        raise SystemExit("barrier timeout")
    time.sleep(0.005)
tl = tl_mod.Timeline(root / ".agenticdoc" / "_autopilot" / "timeline.jsonl")
r = dispatch.dispatch(
    root, owner, stem, "phase-writer", "Do the work.",
    loop="exec:" + owner + ":" + stem, attempt=1, timeline=tl,
)
print(json.dumps({"stem": stem, "ok": r.ok, "reason": r.reason}))
"""


def _race(tmp_path: pathlib.Path, owner: str, stems: list[str]) -> tuple[list[dict], list[dict]]:
    barrier = tmp_path / "barrier"
    barrier.mkdir()
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(PKG_ROOT), str(tmp_path), owner, stem, str(barrier)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for stem in stems
    ]
    deadline = time.time() + 60
    while not all((barrier / f"ready-{stem}").exists() for stem in stems):
        if time.time() > deadline:
            break
        time.sleep(0.005)
    (barrier / "start").write_text("go", encoding="utf-8")
    results: list[dict] = []
    for proc, stem in zip(procs, stems):
        out, err = proc.communicate(timeout=120)
        lines = [line for line in out.splitlines() if line.strip()]
        assert proc.returncode == 0, (stem, proc.returncode, err)
        results.append(json.loads(lines[-1]))
    return results, _events(_timeline(tmp_path))


def test_race_distinct_task_keys_overlapping_faces_exactly_one_grant(tmp_path):
    """AC-014/requirement 10: two real processes, one owner, two distinct
    identities whose declared faces overlap.  The verdict must be exactly one
    grant, one `dispatch` event and one queue row (RQ-D3's
    `grants=1/refusals=1` shape); a judgement outside the lock would let both
    through."""
    _write_card(tmp_path, OWNER, "a1", "- `packages/x/**`\n")
    _write_card(tmp_path, OWNER, "a2", "- `packages/x/file.ts`\n")
    results, events = _race(tmp_path, OWNER, ["a1", "a2"])
    grants = [r for r in results if r["ok"]]
    refusals = [r for r in results if not r["ok"]]
    assert len(grants) == 1, results
    assert len(refusals) == 1, results
    assert refusals[0]["reason"].startswith("write-face-overlap"), results
    assert [e["ev"] for e in events].count("dispatch") == 1, events
    assert [e["ev"] for e in events].count("write-face-overlap") == 1, events
    assert len(_rows(tmp_path)) == 1


def test_race_same_task_key_exactly_one_grant(tmp_path):
    """The same identity raced by two processes: the identity-level guard
    (MDC M-04) must let exactly one through — one grant, one
    `duplicate-dispatch:` refusal, one `dispatch` event, one row. The lock is
    never mocked (WFG requirement 10), and the old request 3 write-face
    self-exclusion still holds: the refusal is never `write-face-overlap`."""
    _write_card(tmp_path, OWNER, "a1", "- `packages/x/**`\n")
    results, events = _race(tmp_path, OWNER, ["a1", "a1"])
    grants = [r for r in results if r["ok"]]
    refusals = [r for r in results if not r["ok"]]
    assert len(grants) == 1, results
    assert len(refusals) == 1, results
    assert refusals[0]["reason"].startswith("duplicate-dispatch:"), results
    assert [e["ev"] for e in events].count("dispatch") == 1, events
    assert len(_rows(tmp_path)) == 1


# ---------------------------------------------------------------------------
# MDC M-04: the identity refusal is a dispatch-wait refusal, never a stall
# ---------------------------------------------------------------------------

def test_duplicate_dispatch_refusal_is_a_wait_class_refusal():
    """`conductor.execute_loop` only lets `_write_face_wait_reason` refusals
    wait for the next tick; every other `ok=False` stalls the key. The identity
    guard's `duplicate-dispatch:` reason must therefore be in that wait set, or
    a normal duplicate dispatch attempt would manufacture a permanent stall
    (M-04 requirement 3b). This pins the tuple + the shared predicate, not a
    reimplementation."""
    assert conductor._WRITE_FACE_WAIT_REFUSALS == (
        "write-face-overlap", "write-face-undeclared", "duplicate-dispatch"
    )
    assert conductor._write_face_wait_reason(
        "duplicate-dispatch: ap-wfk-same already in flight (pending)"
    )
    # the historical wait-class reasons are unchanged
    assert conductor._write_face_wait_reason("write-face-overlap: overlap-with:x")
    assert conductor._write_face_wait_reason("write-face-undeclared: serial-only (1)")
    # author errors still take the historical stall path
    assert not conductor._write_face_wait_reason("write-face-empty: no entries")
