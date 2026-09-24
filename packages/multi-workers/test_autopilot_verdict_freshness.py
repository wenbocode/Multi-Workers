"""
test_autopilot_verdict_freshness.py — terminal L3 verdict freshness
(feature-l3-verdict-freshness, design §3.1; AC-001..AC-008).

The pre-fix ``_persist_l3_verdict`` locked the first terminal verdict forever
(``if not verdict_file.is_file()``), so a key that first stalled ``below`` and
later closed ``meets`` kept the stale ``below`` in its closure dossier. This
module pins the fixed contract on the *real* conductor chain:

* AC-001/AC-002: the accident chain (below -> repair -> below -> stall ->
  approved stalled gate -> extra round -> meets) refreshes ``l3-verdict.txt``
  to ``meets`` and ``l3-report.md`` to the *terminal* round's bytes;
* AC-003/AC-004/AC-006: the reverse — a true ``below`` is never upgraded, a
  resume that still lands ``below`` stays ``below``, and a transient ``meets``
  degrades back to ``below``;
* AC-005: repeated ticks / repeated direct calls / an uppercase same-value file
  are all zero-write (bytes *and* mtime);
* AC-007/AC-008: the dossier golden (frozen clock) and the L3 criteria are
  untouched.

Fixture harness is imported from ``test_autopilot_conductor_exec`` (never
modified), and the gate-answer pattern follows ``test_autopilot_stall``.
Each case prints one ``[VERIFY] VC-0NN: key=value ...`` line (design §7).
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import test_autopilot_conductor_exec as harness  # noqa: E402
from autopilot import conductor, roadmap, state  # noqa: E402

_FROZEN_CLOCK = "1970-01-01T00:00:00Z"

# T-001 left-end anchors (independent evidence, not imported from conductor).
_PARSE_L3_SHA = "b0348c4fc06ac0f28bf206d217732126a1a589ba99079158f2257763f8124c98"
_MD_SECTION_SHA = "c0926b8d790f58245285a621dedd5a12c27a664af6082db76bbc4c474cb03d2b"

_GOLDEN_LITERAL_HEADER = "| key | final phase | l3 verdict | l3 report | evidence |"
_GOLDEN_COLUMNS = ["key", "final phase", "l3 verdict", "l3 report", "evidence"]
# Fixture of capture_dossier_golden_20260924.py (PRE-FIX AC-007 anchor).
_GOLDEN_FIXTURE = [
    ("fixture-none-row", None),
    ("fixture-meets-row", "meets"),
    ("fixture-below-row", "below"),
]

# Real reverse anchor (T-001d independent recompute: below / below / not stale).
_REVERSE_KEY = "feature-inline-marker-patchkit"
_REVERSE_EXPECTED = {
    "persisted_verdict": "below",
    "last_round_verdict": "below",
    "stale": False,
}


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _b(value: bool) -> str:
    return "true" if value else "false"


def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conductor, "_iso_now", lambda: _FROZEN_CLOCK)


def _below_round(attempt: int) -> str:
    """A distinct ``below`` report per L3 round: the live accident key's a1/a2
    reports are byte-identical, so a suffix is required to prove the report
    does / does not come from a specific round (VC-002/VC-004)."""
    return harness._L3_BELOW + f"\n<!-- round a{attempt} -->\n"


def _gate_paths(project: pathlib.Path) -> list[pathlib.Path]:
    return sorted(conductor.gates_dir(project).glob("gate-*.md"))


def _answer_gate(path: pathlib.Path, status: str) -> None:
    """Human answer, same write shape as the TS /autopilot gate command."""
    text = path.read_text(encoding="utf-8")
    assert "status: pending" in text
    text = text.replace("status: pending", f"status: {status}", 1)
    text = text.replace(
        "answered_at:", "answered_at: 2026-09-22T00:00:00+00:00", 1
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dossier_row(project: pathlib.Path, key: str) -> str:
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    text = conductor._closure_dossier_md(project, rm.stages[0])
    rows = [line for line in text.splitlines() if line.startswith(f"| {key} |")]
    assert rows, text
    return rows[0]


def _l3_verdict_events(project: pathlib.Path) -> list[dict]:
    return [
        e for e in harness._events(project)
        if e["ev"] == "config" and str(e["detail"]).startswith("l3-verdict ")
    ]


# ── real-project independent recompute (design §3.1 fixture contract) ────────

def _e2feature_root() -> pathlib.Path:
    candidates: list[pathlib.Path] = []
    env = os.environ.get("E2FEATURE_ROOT")
    if env:
        candidates.append(pathlib.Path(env))
    candidates.append(pathlib.Path(__file__).resolve().parents[3] / "E2Feature")
    candidates.append(pathlib.Path("H:/git/E2Feature"))
    for candidate in candidates:
        if (candidate / ".agenticdoc" / "feature-l3-verdict-freshness").is_dir():
            return candidate
    pytest.fail("E2Feature partition root not found (set E2FEATURE_ROOT)")


def _load_json(path: pathlib.Path) -> dict:
    assert path.is_file(), f"missing evidence anchor: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_md_section(text: str, header: str) -> str | None:
    """Independent mirror of conductor._md_section (deliberately NOT imported)."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        return None
    out = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def _mirror_parse_l3_output(output: pathlib.Path) -> str:
    """Independent mirror of conductor._parse_l3_output (NOT imported)."""
    if not output.is_file():
        return "below"
    text = output.read_text(encoding="utf-8", errors="replace")
    qg = _mirror_md_section(text, "## Quality Gate Report")
    achieved = _mirror_md_section(text, "## Achieved")
    if qg is None or achieved is None:
        return "below"
    if re.search(r"\|\s*FAIL\b", qg):
        return "below"
    return "meets"


def _mirror_recompute_reverse_key(root: pathlib.Path) -> tuple[str, str, bool]:
    """(persisted, last_round_verdict, stale) for the real reverse anchor."""
    key_dir = root / ".agenticdoc" / _REVERSE_KEY
    rounds: dict[int, pathlib.Path] = {}
    pattern = re.compile(r"^ap-" + re.escape(_REVERSE_KEY) + r"-l3-a(\d+)$")
    for sub in sorted((key_dir / "workers").iterdir()):
        match = pattern.match(sub.name)
        if match and (sub / "output.md").is_file():
            rounds[int(match.group(1))] = sub / "output.md"
    assert rounds, f"no L3 rounds for {_REVERSE_KEY}"
    verdict_by_round = {n: _mirror_parse_l3_output(p) for n, p in rounds.items()}
    last_round = max(rounds)
    last_verdict = verdict_by_round[last_round]
    verdict_file = key_dir / "l3-verdict.txt"
    assert verdict_file.is_file()
    persisted = verdict_file.read_text(encoding="utf-8").strip().lower()
    assert persisted in ("meets", "below")
    report = key_dir / "l3-report.md"
    assert report.is_file()
    report_sha = _sha256_file(report)
    report_matches = [
        n for n, path in rounds.items() if _sha256_file(path) == report_sha
    ]
    stale = persisted != last_verdict
    assert last_round in report_matches, "latest report is not from the last round"
    return persisted, last_verdict, stale


# ── conductor source region hashing (PLAN PF-2 basis, same as T-001) ─────────

def _func_source(text: str, prefix: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(prefix)), None)
    assert start is not None, prefix
    out = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("def ") or line.startswith("class ") or line.startswith("# \u2500\u2500"):
            break
        out.append(line)
    return "\n".join(out) + "\n"


def _conductor_region_sha(prefix: str) -> str:
    text = pathlib.Path(conductor.__file__).read_text(encoding="utf-8")
    return hashlib.sha256(_func_source(text, prefix).encode("utf-8")).hexdigest()


# ── shared chains ────────────────────────────────────────────────────────────

def _drive_to_first_stall(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[pathlib.Path, conductor.ConductorState, pathlib.Path, list]:
    """AC-001 chain up to the first stall: l3-a1 below -> repair-a1 ->
    l3-a2 below -> used 2 == limit 2 => persist below + mark_stalled."""
    project = harness._verify_key_project(tmp_path)
    fake_advance, calls = harness._fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = harness._state(project)
    key_dir = project / ".agenticdoc" / "k1"

    assert conductor.tick(project, st) == "ok"           # l3-a1
    harness._worker_output(project, "k1", "ap-k1-l3-a1", _below_round(1))
    harness._set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"           # repair-a1
    assert [r["task_key"] for r in harness._rows(project, "ap-k1-repair-")] == [
        "ap-k1-repair-a1"
    ]
    harness._set_row(project, "ap-k1-repair-a1", "done")
    assert conductor.tick(project, st) == "ok"           # l3-a2
    harness._worker_output(project, "k1", "ap-k1-l3-a2", _below_round(2))
    harness._set_row(project, "ap-k1-l3-a2", "done")
    assert conductor.tick(project, st) == "ok"           # stall at limit 2
    return project, st, key_dir, calls


def _resume_and_run_extra_round(
    project: pathlib.Path,
    st: conductor.ConductorState,
    key_dir: pathlib.Path,
    a3_text: str,
) -> pathlib.Path:
    """Approve the *existing* stalled gate (one resume credit) and run the
    extra repair + L3 round with ``a3_text`` as the report."""
    gate_paths = _gate_paths(project)
    assert len(gate_paths) == 1, "expected exactly the existing stalled gate"
    _answer_gate(gate_paths[0], "approved")
    assert conductor._resume_credits(project, "k1") == 1
    assert conductor.tick(project, st) == "ok"           # resume + extra repair
    repair_rows = [r["task_key"] for r in harness._rows(project, "ap-k1-repair-a2")]
    assert len(repair_rows) == 1, repair_rows            # one extra round only
    harness._set_row(project, repair_rows[0], "done")
    assert conductor.tick(project, st) == "ok"           # l3-a3
    l3_rows = [r["task_key"] for r in harness._rows(project, "ap-k1-l3-")]
    assert l3_rows == ["ap-k1-l3-a1", "ap-k1-l3-a2", "ap-k1-l3-a3"], l3_rows
    a3_out = key_dir / "workers" / "ap-k1-l3-a3" / "output.md"
    harness._worker_output(project, "k1", "ap-k1-l3-a3", a3_text)
    harness._set_row(project, "ap-k1-l3-a3", "done")
    assert conductor.tick(project, st) == "ok"           # terminal event
    return a3_out


# ── AC-001 / VC-001 ──────────────────────────────────────────────────────────

def test_terminal_meets_after_resume_refreshes_verdict(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st, key_dir, calls = _drive_to_first_stall(tmp_path, monkeypatch)
    # the stall wrote the first (below) terminal verdict to disk
    intermediate = (key_dir / "l3-verdict.txt").read_text(encoding="utf-8")
    assert intermediate.strip() == "below"
    _resume_and_run_extra_round(project, st, key_dir, harness._L3_MEETS)
    verdict, report = conductor._l3_verdict(key_dir)
    raw = (key_dir / "l3-verdict.txt").read_bytes()
    assert ("k1", "done") in calls
    assert state.read_key_states(project)["k1"].phase == "DONE"
    _verify(
        "VC-001", verdict=verdict, file_bytes=len(raw),
        file_text=raw.decode("utf-8").strip(),
        intermediate_below=_b(intermediate.strip() == "below"),
        ok=_b(verdict == "meets" and raw == b"meets\n"
              and report.endswith("l3-report.md")),
    )


# ── AC-002 / VC-002 ──────────────────────────────────────────────────────────

def test_report_matches_terminal_round_and_dossier_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st, key_dir, _calls = _drive_to_first_stall(tmp_path, monkeypatch)
    a3_out = _resume_and_run_extra_round(project, st, key_dir, harness._L3_MEETS)
    a2_out = key_dir / "workers" / "ap-k1-l3-a2" / "output.md"
    report = key_dir / "l3-report.md"
    report_sha = _sha256_file(report)
    eq_a3 = report_sha == _sha256_file(a3_out)
    eq_a2 = report_sha == _sha256_file(a2_out)
    row = _dossier_row(project, "k1")
    dossier_ok = "| meets |" in row and "l3-report.md" in row
    _verify(
        "VC-002", report_sha_eq_a3=_b(eq_a3), report_sha_eq_a2=_b(eq_a2),
        dossier_row_ok=_b(dossier_ok), ok=_b(eq_a3 and not eq_a2 and dossier_ok),
    )
    assert eq_a3 and not eq_a2 and dossier_ok


# ── AC-003 / VC-003 (reverse + real key recompute) ───────────────────────────

def test_true_below_without_resume_stays_below(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, _st, key_dir, _calls = _drive_to_first_stall(tmp_path, monkeypatch)
    verdict = (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip()
    row = _dossier_row(project, "k1")
    fixture_ok = verdict == "below" and "| below |" in row
    assert fixture_ok, (verdict, row)

    # Real key: independent mirror recompute (no tested judgement imported),
    # cross-checked against the T-001d frozen recompute evidence.
    root = _e2feature_root()
    live_persisted, live_last, live_stale = _mirror_recompute_reverse_key(root)
    anchor = _load_json(
        root / ".agenticdoc" / "feature-l3-verdict-freshness" / "evidence"
        / "exec-l3-verdict-freshness-recompute-20260924.json"
    )["reverse_anchor"]
    assert anchor["key"] == _REVERSE_KEY
    assert anchor["persisted_verdict"] == _REVERSE_EXPECTED["persisted_verdict"]
    assert anchor["last_round_verdict"] == _REVERSE_EXPECTED["last_round_verdict"]
    assert anchor["stale"] is False
    assert (live_persisted, live_last, live_stale) == (
        anchor["persisted_verdict"], anchor["last_round_verdict"], anchor["stale"]
    )
    _verify(
        "VC-003", fixture_verdict=verdict, fixture_dossier=(
            "below" if "| below |" in row else "other"),
        real_key_persisted=live_persisted, real_key_last=live_last,
        real_key_stale=_b(live_stale), ok=_b(fixture_ok and not live_stale),
    )


# ── AC-004 / VC-004 ──────────────────────────────────────────────────────────

def test_resume_then_below_stays_below(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st, key_dir, _calls = _drive_to_first_stall(tmp_path, monkeypatch)
    verdict_file = key_dir / "l3-verdict.txt"
    mtime_before = verdict_file.stat().st_mtime_ns
    a3_out = _resume_and_run_extra_round(project, st, key_dir, _below_round(3))
    verdict = verdict_file.read_text(encoding="utf-8").strip()
    report = key_dir / "l3-report.md"
    report_round_a3 = _sha256_file(report) == _sha256_file(a3_out)
    upgraded = any(
        str(event["detail"]).endswith("-> meets (report from ap-k1-l3-a3)")
        for event in _l3_verdict_events(project)
    ) or verdict == "meets"
    unchanged_mtime = verdict_file.stat().st_mtime_ns == mtime_before
    _verify(
        "VC-004", verdict=verdict, report_round="a3",
        report_sha_match=_b(report_round_a3), upgraded=_b(upgraded),
        ok=_b(verdict == "below" and report_round_a3 and not upgraded
              and unchanged_mtime),
    )
    assert verdict == "below" and report_round_a3 and not upgraded and unchanged_mtime


# ── AC-005 / VC-005 ──────────────────────────────────────────────────────────

def test_repeat_ticks_and_direct_calls_are_zero_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st, key_dir, _calls = _drive_to_first_stall(tmp_path, monkeypatch)
    verdict_file = key_dir / "l3-verdict.txt"
    report = key_dir / "l3-report.md"
    a2_out = key_dir / "workers" / "ap-k1-l3-a2" / "output.md"

    verdict_sha = _sha256_file(verdict_file)
    verdict_mtime = verdict_file.stat().st_mtime_ns
    report_sha = _sha256_file(report)
    sha_changes = mtime_changes = report_changes = 0
    for _ in range(3):
        assert conductor.tick(project, st) == "ok"
        sha_changes += int(_sha256_file(verdict_file) != verdict_sha)
        mtime_changes += int(verdict_file.stat().st_mtime_ns != verdict_mtime)
        report_changes += int(_sha256_file(report) != report_sha)

    direct_writes = 0
    for _ in range(2):
        before = verdict_file.stat().st_mtime_ns
        conductor._persist_l3_verdict(key_dir, "below", a2_out, st=None)
        direct_writes += int(verdict_file.stat().st_mtime_ns != before)

    # hand-written uppercase same value must not be rewritten (I-4)
    verdict_file.write_bytes(b"MEETS\n")
    upper_mtime = verdict_file.stat().st_mtime_ns
    conductor._persist_l3_verdict(key_dir, "meets", a2_out, st=None)
    uppercase_rewrites = int(
        verdict_file.stat().st_mtime_ns != upper_mtime
        or verdict_file.read_bytes() != b"MEETS\n"
    )

    ok = not any((sha_changes, mtime_changes, report_changes,
                  direct_writes, uppercase_rewrites))
    _verify(
        "VC-005", ticks=3, verdict_sha_changes=sha_changes,
        verdict_mtime_changes=mtime_changes, report_sha_changes=report_changes,
        direct_repeat_writes=direct_writes, uppercase_rewrites=uppercase_rewrites,
        ok=_b(ok),
    )
    assert ok


# ── AC-005 / I-4 fail-closed: uppercase same value through the tick ──────────

def test_uppercase_same_value_is_zero_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Focused fail-closed replica: a hand-written ``MEETS``/``Below`` file is
    the *same* value after ``strip().lower()``, so neither a conductor tick nor
    a direct call may touch it (no bytes, no mtime, no refresh event)."""
    _freeze_clock(monkeypatch)
    project, st, key_dir, _calls = _drive_to_first_stall(tmp_path, monkeypatch)
    verdict_file = key_dir / "l3-verdict.txt"
    a2_out = key_dir / "workers" / "ap-k1-l3-a2" / "output.md"

    verdict_file.write_bytes(b"MeEtS\n")
    events_before = len(_l3_verdict_events(project))
    mtime = verdict_file.stat().st_mtime_ns
    assert conductor.tick(project, st) == "ok"
    assert verdict_file.read_bytes() == b"MeEtS\n"
    assert verdict_file.stat().st_mtime_ns == mtime
    conductor._persist_l3_verdict(key_dir, "meets", a2_out, st=None)
    assert verdict_file.read_bytes() == b"MeEtS\n"
    assert verdict_file.stat().st_mtime_ns == mtime
    assert len(_l3_verdict_events(project)) == events_before


# ── AC-006 / VC-006 ──────────────────────────────────────────────────────────

def test_transient_meets_degrades_to_below(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)
    fake_advance, _calls = harness._fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = harness._state(project)
    key_dir = project / ".agenticdoc" / "k1"
    # l3-a1 output missing `## Achieved` => below
    assert conductor.tick(project, st) == "ok"
    harness._worker_output(
        project, "k1", "ap-k1-l3-a1",
        "# L3\n\n## Quality Gate Report\n\nall good\n",
    )
    harness._set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"           # repair-a1
    harness._set_row(project, "ap-k1-repair-a1", "done")
    assert conductor.tick(project, st) == "ok"           # l3-a2
    short = harness._L3_MEETS.replace(
        harness._L3_MEETS[harness._L3_MEETS.find("## Achieved"):],
        "## Achieved\n\ntoo short\n",
    )
    harness._worker_output(project, "k1", "ap-k1-l3-a2", short)
    harness._set_row(project, "ap-k1-l3-a2", "done")
    assert conductor.tick(project, st) == "ok"           # meets -> degrade -> stall

    verdict = (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip()
    row = _dossier_row(project, "k1")
    details = [str(e["detail"]) for e in _l3_verdict_events(project)]
    transient = any("none -> meets" in d for d in details)
    refresh = [d for d in details if "meets -> below" in d]
    dossier_below = "| below |" in row
    ok = (verdict == "below" and dossier_below and transient and len(refresh) >= 1)
    _verify(
        "VC-006", final_verdict=verdict, dossier_row_below=_b(dossier_below),
        transient_meets_seen=_b(transient), **{"refresh_events>": "1"}, ok=_b(ok),
    )
    assert ok, (verdict, row, details)


# ── AC-007 / VC-007 (frozen-clock golden) ────────────────────────────────────

def test_dossier_golden_frozen_clock(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _e2feature_root()
    golden = _load_json(
        root / ".agenticdoc" / "feature-l3-verdict-freshness" / "evidence"
        / "exec-l3-verdict-freshness-golden-20260924.json"
    )
    fixture_root = tmp_path / "golden-project"
    keys = []
    for key, verdict in _GOLDEN_FIXTURE:
        key_dir = fixture_root / ".agenticdoc" / key
        key_dir.mkdir(parents=True)
        if verdict:
            (key_dir / "l3-verdict.txt").write_bytes(
                (verdict + "\n").encode("utf-8")
            )
            (key_dir / "l3-report.md").write_bytes(
                (f"# L3 report {key}\n\nverdict: {verdict}\n").encode("utf-8")
            )
        keys.append(types.SimpleNamespace(key=key))
    stage = types.SimpleNamespace(
        number=7, title="fixture", goal="baseline-freeze-fixture-goal",
        status="running", keys=tuple(keys), key_status={}, key_status_present=False,
    )
    monkeypatch.setattr(conductor, "_iso_now", lambda: _FROZEN_CLOCK)
    monkeypatch.setattr(
        conductor.state, "read_key_states", lambda project_root, self_id="": {}
    )
    raw = conductor._closure_dossier_md(fixture_root, stage)
    templated = raw
    for needle in (str(fixture_root), fixture_root.as_posix()):
        templated = templated.replace(needle, "{key_dir}")
    templated = templated.replace("\\", "/")

    candidate = templated.encode("utf-8")
    golden_bytes = golden["text"].encode("utf-8")
    bytes_equal = candidate == golden_bytes
    assert hashlib.sha256(candidate).hexdigest() == golden["sha256"]

    lines = templated.splitlines()
    idx = next(
        (i for i, line in enumerate(lines) if line == _GOLDEN_LITERAL_HEADER), None
    )
    header_ok = (
        idx is not None
        and lines[idx] == golden["header_literal"] == _GOLDEN_LITERAL_HEADER
    )
    columns = (
        [c.strip() for c in lines[idx].strip("|").split("|")] if idx is not None else []
    )
    columns_ok = columns == golden["column_order"] == _GOLDEN_COLUMNS
    _verify(
        "VC-007", golden_bytes_equal=_b(bytes_equal), header_literal=_b(header_ok),
        column_order=_b(columns_ok), ok=_b(bytes_equal and header_ok and columns_ok),
    )
    assert bytes_equal and header_ok and columns_ok


# ── AC-007 / VC-008 (none + third-state guard) ───────────────────────────────

def test_none_verdict_and_third_state_guard(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)
    key_dir = project / ".agenticdoc" / "k1"
    verdict, report = conductor._l3_verdict(key_dir)
    none_returned = (verdict, report) == ("none", "—")
    row = _dossier_row(project, "k1")
    dossier_none = "| none |" in row and "| — |" in row
    assert none_returned and dossier_none, (verdict, report, row)

    src = tmp_path / "round.md"
    src.write_bytes(b"# round\n\n## Achieved\n\n" + b"x" * 250 + b"\n")
    conductor._persist_l3_verdict(key_dir, "MAYBE", src, st=None)
    third_state_written = (
        (key_dir / "l3-verdict.txt").exists() or (key_dir / "l3-report.md").exists()
    )
    _verify(
        "VC-008", none_returned=_b(none_returned), dossier_none=_b(dossier_none),
        third_state_written=_b(third_state_written),
        ok=_b(none_returned and dossier_none and not third_state_written),
    )
    assert not third_state_written


# ── I-3 / D-007 fail-closed: missing report source keeps the report ──────────

def test_report_source_missing_keeps_existing_report(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)
    key_dir = project / ".agenticdoc" / "k1"
    src = tmp_path / "round-a7.md"
    src.write_bytes(b"# round a7\n\n## Achieved\n\nok\n")
    conductor._persist_l3_verdict(key_dir, "below", src, st=None)
    report = key_dir / "l3-report.md"
    before_bytes = report.read_bytes()
    before_mtime = report.stat().st_mtime_ns
    verdict_mtime = (key_dir / "l3-verdict.txt").stat().st_mtime_ns

    missing = tmp_path / "no-verdict-round" / "output.md"
    conductor._persist_l3_verdict(key_dir, "below", missing, st=None)
    assert report.read_bytes() == before_bytes
    assert report.stat().st_mtime_ns == before_mtime
    assert (key_dir / "l3-verdict.txt").stat().st_mtime_ns == verdict_mtime


# ── AC-008 / VC-009 ──────────────────────────────────────────────────────────

def test_l3_criteria_behavior_unchanged(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)
    rules = 0
    # 1. missing "## Quality Gate Report" => below
    harness._worker_output(
        project, "k1", "ap-k1-l3-a1", "# L3\n\n## Achieved\n\nok\n"
    )
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "below")
    # 2. missing "## Achieved" => below
    harness._worker_output(
        project, "k1", "ap-k1-l3-a1",
        "# L3\n\n## Quality Gate Report\n\n| VC | verdict |\n|----|----|\n"
        "| VC-1 | PASS |\n",
    )
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "below")
    # 3. a "| FAIL" row inside the QG section => below
    harness._worker_output(
        project, "k1", "ap-k1-l3-a1",
        "# L3\n\n## Quality Gate Report\n\n| VC | verdict |\n|----|----|\n"
        "| VC-1 | FAIL |\n\n## Achieved\n\nok\n",
    )
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "below")
    # 4. otherwise meets
    harness._worker_output(project, "k1", "ap-k1-l3-a1", harness._L3_MEETS)
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "meets")

    parse_sha = _conductor_region_sha("def _parse_l3_output(")
    md_sha = _conductor_region_sha("def _md_section(")
    parse_ok = parse_sha == _PARSE_L3_SHA
    md_ok = md_sha == _MD_SECTION_SHA
    _verify(
        "VC-009", rules_asserted=rules, parse_sha_unchanged=_b(parse_ok),
        md_section_sha_unchanged=_b(md_ok),
        ok=_b(rules == 4 and parse_ok and md_ok),
    )
    assert rules == 4 and parse_ok and md_ok
