"""
test_autopilot_timeline.py — L1 tests for autopilot/timeline.py (T-04, VC-019).

Scope per the task contract: timeline mechanics — append line schema, seq
recovery across restarts (no regress, no duplicate), key sentinel derivation
(never null), rotation chain (over-threshold rename, 2 generations, rotated
files never rewritten), replay old→new→current with watermark filtering and
the pruned notice, and §9 append-failure tolerance (never raises).

The full per-transition matrix (VC-019 per_transition=all) is owned by the
T-10 conductor tests; the 60s beat window (VC-021) by T-16.

All fixtures build timeline files under tmp_path with explicit path
parameters — no project root, no autopilot.config import.
"""
import datetime
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import timeline as tl


def _verify(**kv: object) -> None:
    print("[VERIFY] VC-019: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _read_lines(path: pathlib.Path) -> list[dict]:
    """Strictly parse every non-blank line of a JSONL file (test helper)."""
    out: list[dict] = []
    for raw in path.read_bytes().split(b"\n"):
        if raw.strip():
            out.append(json.loads(raw.decode("utf-8")))
    return out


# ── Append: line schema, event-type vocabulary ───────────────────────────────

def test_append_line_schema_all_event_types(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    for ev in sorted(tl.EVENT_TYPES):
        assert writer.append(ev, key=f"key-{ev}", stage=1, detail=f"detail for {ev}") is not None
    assert len(tl.EVENT_TYPES) == 14  # enum locked by D-109

    raw = path.read_bytes()
    assert b"\r" not in raw  # newline symmetry: LF only, never \r\n
    events = _read_lines(path)
    assert len(events) == 14
    assert [e["seq"] for e in events] == list(range(1, 15))  # dense, increasing
    for e in events:
        assert set(e) == {"ts", "seq", "ev", "key", "stage", "detail"}
        assert isinstance(e["seq"], int)
        assert e["key"] == f"key-{e['ev']}"
        assert e["stage"] == 1
        datetime.datetime.fromisoformat(e["ts"])  # ts is real iso8601
    _verify(event_lines=14, per_type="all", schema="valid")


def test_unknown_ev_accepted_and_filter(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    writer.append("beat")
    writer.append("dispatch", key="k1", stage=1)
    writer.append("some-future-event")  # enum is a vocabulary, not a gate

    all_events = tl.query_events(path).events
    assert [e["ev"] for e in all_events] == ["beat", "dispatch", "some-future-event"]
    only_dispatch = tl.query_events(path, ev_filter={"dispatch"})
    assert [e["ev"] for e in only_dispatch.events] == ["dispatch"]
    # Include-set semantics: an enum-based filter also drops unknown types —
    # the unfiltered query is what keeps them (enum is a vocabulary, not a gate).
    no_beats = tl.query_events(path, ev_filter=tl.EVENT_TYPES - {"beat"})
    assert [e["ev"] for e in no_beats.events] == ["dispatch"]
    _verify(unknown_ev_accepted="true", ev_filter="pass")


# ── seq recovery: restart continues, never regresses or duplicates ──────────

def test_seq_recovery_restart_no_regress_no_duplicate(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    first = tl.Timeline(path)
    assert first.next_seq == 1
    assert [first.append("beat") for _ in range(3)] == [1, 2, 3]

    # "Restart": a brand-new writer instance must continue, not restart.
    second = tl.Timeline(path)
    assert second.next_seq == 4
    assert second.append("beat") == 4
    third = tl.Timeline(path)
    assert third.next_seq == 5
    assert third.append("dispatch", key="k1", stage=1) == 5

    seqs = [e["seq"] for e in tl.query_events(path).events]
    assert seqs == [1, 2, 3, 4, 5]  # no regress, no duplicate
    assert len(set(seqs)) == len(seqs)
    _verify(seq_monotonic="true", seq_recovery_no_regress="true", seq_recovery_no_duplicate="true")


def test_seq_recovery_after_rotation_current_absent(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    assert writer.append("beat") == 1
    assert writer.append("advance", key="k1", stage=1) == 2
    assert writer.rotate() is True
    assert not path.exists()  # rotated away, not yet re-created

    # Restart landing between rotation and the next append: the counter must
    # come from the rotated generation, not restart at 1.
    restarted = tl.Timeline(path)
    assert restarted.next_seq == 3
    assert restarted.append("beat") == 3
    _verify(seq_recovery_after_rotate="true")


def test_torn_tail_line_recovery(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    writer.append("beat")
    writer.append("beat")
    # Simulate a mid-write crash: torn last line, no trailing newline.
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write('{"ts": "2026-01-01T00:00:00+00:00", "seq": 3, "ev": "be')

    restarted = tl.Timeline(path)
    assert restarted.next_seq == 3  # last parseable line is seq 2
    assert restarted.append("beat") == 3  # healing newline isolates the torn line

    result = tl.query_events(path)
    assert [e["seq"] for e in result.events] == [1, 2, 3]  # dense, no dup
    assert result.skipped == 1  # torn line counted, never silently dropped
    _verify(torn_tail_recovery="true", skipped_counted="true")


# ── key sentinel: never null (AC-017 erratum) ────────────────────────────────

def test_key_sentinel_never_null(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    writer.append("dispatch", key="k1", stage=1, detail="key-level event")
    writer.append("stage-close", stage=2, detail="stage-level: key = stage number")
    writer.append("stage-close", key=tl.KEY_SENTINEL, stage=2, detail="explicit dash")
    writer.append("config", detail="global event")
    writer.append("goal-halt", key=None, stage=None, detail="explicit None -> dash")
    writer.append("beat", key="", stage=3, detail="empty key derives stage")

    events = _read_lines(path)
    for e in events:
        assert e["key"] is not None  # AC-017 erratum
        assert isinstance(e["key"], str) and e["key"] != ""
    assert events[0]["key"] == "k1"
    assert events[1]["key"] == "2"  # stage number
    assert events[2]["key"] == "-"
    assert events[3]["key"] == "-"
    assert events[4]["key"] == "-"
    assert events[5]["key"] == "3"
    _verify(key_field_no_null="true", key_sentinel_dash="true", stage_number_key="true")


# ── Rotation: chain shifts, threshold trigger, replay order ─────────────────

def test_rotate_moves_current_into_chain(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    gen1 = path.with_name(path.name + ".1")
    gen2 = path.with_name(path.name + ".2")
    writer = tl.Timeline(path)
    for i in range(3):
        writer.append("beat", detail=f"e{i + 1}")
    first_batch = path.read_bytes()

    assert writer.rotate() is True
    assert not path.exists()  # renamed, not copied
    assert gen1.read_bytes() == first_batch  # content intact
    assert writer.rotate() is False  # nothing to rotate; .1 untouched
    assert gen1.read_bytes() == first_batch

    writer.append("beat", detail="e4")
    writer.append("beat", detail="e5")
    second_batch = path.read_bytes()
    assert writer.rotate() is True
    assert gen2.read_bytes() == first_batch  # shifted down byte-identical
    assert gen1.read_bytes() == second_batch  # rotated files never rewritten
    writer.append("beat", detail="e6")

    # Three-file chain: .2 (oldest) → .1 → current, replayed as one stream.
    assert [e["seq"] for e in tl.query_events(path).events] == [1, 2, 3, 4, 5, 6]
    _verify(rotate_rename="true", rotated_files_unchanged="true")


def test_auto_rotation_over_threshold(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    gen1 = path.with_name(path.name + ".1")
    gen2 = path.with_name(path.name + ".2")
    gen3 = path.with_name(path.name + ".3")
    assert tl.ROTATE_THRESHOLD_BYTES == 10 * 1024 * 1024  # spec'd default

    writer = tl.Timeline(path, rotate_threshold_bytes=1)  # rotate on every append
    for _ in range(5):
        assert writer.append("beat") is not None

    assert path.is_file() and gen1.is_file() and gen2.is_file()
    assert not gen3.exists()  # generations=2: the 3rd generation is dropped
    assert [e["seq"] for e in _read_lines(path)] == [5]
    assert [e["seq"] for e in _read_lines(gen1)] == [4]
    assert [e["seq"] for e in _read_lines(gen2)] == [3]
    _verify(auto_threshold_rotate="true", generations_kept=2)


def test_replay_order_old_to_new_to_current(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    for detail in ("oldest-1", "oldest-2", "older-3", "newer-4", "newer-5", "current-6"):
        writer.append("reconcile", detail=detail)
        if detail in ("older-3", "newer-5"):
            writer.rotate()
    # Chain: .2 = seq 1-3, .1 = seq 4-5, current = seq 6.
    result = tl.query_events(path)
    assert [e["seq"] for e in result.events] == [1, 2, 3, 4, 5, 6]
    assert [e["detail"] for e in result.events] == [
        "oldest-1", "oldest-2", "older-3", "newer-4", "newer-5", "current-6",
    ]
    _verify(replay_order="old_to_new_to_current")


# ── Query: watermark filter, pruned notice, empty/missing chains ────────────

def test_watermark_filter(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    for i in range(5):
        writer.append("beat", detail=f"e{i + 1}")
    assert [e["seq"] for e in tl.query_events(path, watermark=0).events] == [1, 2, 3, 4, 5]
    assert [e["seq"] for e in tl.query_events(path, watermark=2).events] == [3, 4, 5]
    assert tl.query_events(path, watermark=5).events == []
    ahead = tl.query_events(path, watermark=99)
    assert ahead.events == [] and ahead.pruned == 0
    assert [e["seq"] for e in tl.query_events(path, watermark=-3).events] == [1, 2, 3, 4, 5]
    _verify(watermark_filter="true")


def test_pruned_notice_beyond_retained_generations(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path, rotate_threshold_bytes=1)
    for _ in range(6):
        writer.append("beat")
    # Retained chain after six one-line files: .2=[4], .1=[5], current=[6];
    # seqs 1-3 were rotated out and dropped (超 2 代轮转).
    assert [e["seq"] for e in tl.query_events(path).events] == [4, 5, 6]
    fresh = tl.query_events(path, watermark=0)  # new session: full replay asked
    assert fresh.pruned == 3  # 3 events gone, reported — not silent
    stale = tl.query_events(path, watermark=1)
    assert stale.pruned == 2  # seqs 2-3 gone
    caught_up = tl.query_events(path, watermark=3)
    assert caught_up.pruned == 0  # nothing missing
    assert [e["seq"] for e in caught_up.events] == [4, 5, 6]
    _verify(pruned_notice="true", pruned_count=3)


def test_query_missing_and_empty_chain(tmp_path: pathlib.Path) -> None:
    missing = tl.query_events(tmp_path / "nothing" / "timeline.jsonl")
    assert missing.events == [] and missing.pruned == 0 and missing.skipped == 0

    path = tmp_path / "timeline.jsonl"
    path.write_bytes(b"")
    assert tl.query_events(path).events == []
    # Empty chain with a non-zero watermark: everything the console ever saw
    # is gone — report at least that much instead of silence.
    gone = tl.query_events(path, watermark=7)
    assert gone.events == [] and gone.pruned == 7
    _verify(missing_chain_empty="true", empty_chain_pruned_lower_bound="true")


# ── §9 fault tolerance: append failures never reach the caller ──────────────

def test_append_failure_injected_no_raise(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    assert writer.append("beat") == 1

    def disk_full(path: pathlib.Path, line: str) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(tl, "_write_line", disk_full)
    assert writer.append("beat") is None  # tolerated, not raised
    monkeypatch.undo()
    # The failed append consumed no seq: the sequence stays dense.
    assert writer.append("dispatch", key="k1", stage=1) == 2

    result = tl.query_events(path)
    assert [e["seq"] for e in result.events] == [1, 2]
    assert "append failed" in capsys.readouterr().err  # logged to stderr (§9)
    _verify(append_failure_tolerated="true", seq_not_consumed="true")


def test_append_failure_os_level_no_raise(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocked = tmp_path / "blocked"  # a FILE where a directory is needed
    blocked.write_text("not a directory", encoding="utf-8")
    writer = tl.Timeline(blocked / "timeline.jsonl")

    # The caller pattern (conductor tick) keeps looping across failures.
    for _ in range(2):
        assert writer.append("beat") is None  # mkdir fails: OSError swallowed
    assert not (blocked / "timeline.jsonl").exists()
    assert capsys.readouterr().err.count("append failed") == 2
    _verify(append_failure_os_level="true", no_raise="true")


# ── Encoding: UTF-8 content, LF-only line endings ────────────────────────────

def test_utf8_and_newline_symmetry(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    writer = tl.Timeline(path)
    assert writer.append("config", detail="轮转超阈值：保留 2 代") is not None
    assert writer.append("goal-snapshot", key="k1", stage=1, detail="goal mtime 1234567890") is not None

    raw = path.read_bytes()
    assert b"\r" not in raw  # no \r\n doubling (Windows pitfall, spec §5)
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")  # strict decode: valid UTF-8 throughout
    events = [json.loads(line) for line in text.splitlines()]
    assert events[0]["detail"] == "轮转超阈值：保留 2 代"
    _verify(newline_lf_only="true", utf8_roundtrip="true")


# ── Path contract ────────────────────────────────────────────────────────────

def test_timeline_path_helper(tmp_path: pathlib.Path) -> None:
    assert tl.timeline_path(tmp_path) == tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    assert not (tmp_path / ".agenticdoc").exists()  # pure computation, no footprint

    deep = tl.timeline_path(tmp_path)
    writer = tl.Timeline(deep)
    assert writer.append("beat") == 1  # append creates its parent dirs
    assert deep.is_file()
    _verify(explicit_paths="true", parent_autocreate="true")
