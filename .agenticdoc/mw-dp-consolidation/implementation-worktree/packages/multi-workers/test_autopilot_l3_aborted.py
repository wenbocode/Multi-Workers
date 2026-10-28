"""
test_autopilot_l3_aborted.py — G1 stream-abort fingerprint (`l3-aborted`).

T-01 (`packages/multi-workers/autopilot/conductor.py`, key
`mw-gate-verdict-hardening`) classified one more L3 round verdict:
``aborted`` = the tail 64 KiB of the round's ``worker.log`` carries the
substring ``stream closed before response.completed`` AND no readable L3
source (``output.md`` / ``report.md``) has both sections. The fingerprint
sits *before* the worker-status gate, so the live abort rounds — which the
launcher writes back as queue ``status=failed`` — are no longer swallowed by
``no-verdict``. Budget exhausted ⇒ ``mark_stalled(reason_code="l3-aborted")``.

This module pins every T-01 criterion as a recomputable case (AC-001..AC-004,
AC-014 / VC-001..VC-006, VC-017):

* P1-P7 positives: marker ∧ no qualifying source ⇒ ``aborted``; the
  ``l3-aborted`` event ``data`` is the fixed eight-tuple; the dedicated
  ``l3abort:{key}`` reroll; the shared budget is not consumed; a reroll that
  produces a verdict resumes the normal path; a qualifying ``report.md`` /
  ``output.md`` is never ``aborted``.
* N1-N6 negatives: no marker; marker outside the 64 KiB tail window; a
  provider-403 round; a real FAIL marker line; the prose ``report.md``
  (fourth class); two sections + marker.
* X1/X2 non-vacuous controls: removing the fingerprint turns P1 red; moving
  the marker out of the tail window fails closed (never ``aborted``).

The fixtures replicate the measured minimal shape (RQ-1 F1/F5): ``worker.log``
160-179 B, the marker is the last content line 40 B from EOF, the harness
still wrote ``[worker] done exit=0``, and the queue row is ``status=failed``
(the launcher writes the real exit code back). The real corpus lives outside
this repo and is never read here; every assertion runs the production entry
``conductor._l3_round_verdict`` or the production ``conductor.tick`` chain.

# AC/VC coverage:
# AC-001 -> test_p1_..., test_p2_..., test_p8_...
# AC-002 -> test_vc003_...
# AC-003 -> test_p3_..., test_p4_..., test_p5_..., test_p8_...
# AC-004 -> test_p6_..., test_p7_..., test_n1_..test_n6_, test_vc006_...
# AC-014 -> test_x1_..., test_x2_..., test_x3_..., test_fixture_minimal_shape_...
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import test_autopilot_conductor_exec as harness  # noqa: E402
from autopilot import conductor, config, dispatch, gates, roadmap, state  # noqa: E402

_verify = harness._verify
_b = harness.true_str

# ── measured minimal fixture shape (RQ-1 F1/F5) ──────────────────────────────
# The marker is a substring, never a byte-exact line: the real gateway emits
# it without a `WebSocket ` prefix (F1). The key length mirrors the live
# corpus abort rounds so the three-line worker.log lands at 167 B.
MARKER = "stream closed before response.completed"
_LONG_KEY = "feature-inline-marker-patchkit"
_PLACEHOLDER = "# Task completed\n\nNo verdict was rendered.\n"
_PROVIDER_403 = (
    'OpenAI API error (403): {"message":"The model gpt-5.6-sol does not exist"}'
)
_PROSE_REPORT = (
    "# L3 review\n\n"
    "## 0. 复评范围\n\n"
    "reviewed the artefacts only\n\n"
    "## 4. VC 断言表\n\n"
    "| VC | verdict |\n|----|----|\n| VC-001 | PASS |\n"
)
_ABORT_DATA_KEYS = {
    "round",
    "task_key",
    "worker_status",
    "output_bytes",
    "done_exit_zero",
    "retry_used",
    "retry_limit",
    "recorded_at",
}


# ── fixtures / helpers ───────────────────────────────────────────────────────

def _task_key(stem: str, key: str = _LONG_KEY) -> str:
    return dispatch.task_key_for(key, stem)


def _round_log(
    stem: str,
    *,
    marker: bool = False,
    done_exit_zero: bool = True,
    provider_403: bool = False,
    key: str = _LONG_KEY,
) -> str:
    """The three-line live abort shape: start / done exit=0 / [403] / marker."""
    lines = [f"[worker] start task={_task_key(stem, key)} type=reviewer phases=-"]
    if done_exit_zero:
        lines.append("[worker] done exit=0 elapsed=2m52s tools=43")
    if provider_403:
        lines.append(_PROVIDER_403)
    if marker:
        lines.append(MARKER)
    return "\n".join(lines) + "\n"


def _round_dir(
    root: pathlib.Path, stem: str, key: str = _LONG_KEY
) -> pathlib.Path:
    return root / ".agenticdoc" / key / "workers" / _task_key(stem, key)


def _write_round(
    root: pathlib.Path,
    stem: str,
    *,
    log: str | None = None,
    output: str | None = _PLACEHOLDER,
    report: str | None = None,
    key: str = _LONG_KEY,
) -> pathlib.Path:
    d = _round_dir(root, stem, key)
    d.mkdir(parents=True, exist_ok=True)
    if log is not None:
        (d / "worker.log").write_text(log, encoding="utf-8", newline="\n")
    if output is not None:
        (d / "output.md").write_text(output, encoding="utf-8", newline="\n")
    if report is not None:
        (d / "report.md").write_text(report, encoding="utf-8", newline="\n")
    return d


def _rows_for(stem: str, status: str, key: str = _LONG_KEY) -> list[dict]:
    return [{"task_key": _task_key(stem, key), "status": status}]


def _round_verdict(
    root: pathlib.Path, stem: str, status: str, key: str = _LONG_KEY
) -> tuple[str, str, pathlib.Path | None, str | None]:
    attempt = int(stem.rsplit("-a", 1)[1])
    return conductor._l3_round_verdict(root, _rows_for(stem, status, key), key, attempt)


def _verify_project(tmp_path: pathlib.Path, key: str = _LONG_KEY) -> pathlib.Path:
    """`harness._verify_key_project` for an arbitrary (long) key."""
    project = harness._key_project(tmp_path, phases={key: "VERIFY"})
    key_dir = project / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("spec.md", "# Spec\n" + "x" * 600),
        ("design.md", "# Design\n" + "x" * 600),
        ("plan.md", "# Plan\n" + "x" * 400),
        ("achieved.md", "# interim\n"),
    ):
        (key_dir / name).write_text(text, encoding="utf-8")
    harness._tasks(project, key, ["T-01-first"])
    return project


def _boot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, key: str = _LONG_KEY
) -> tuple[pathlib.Path, conductor.ConductorState]:
    project = _verify_project(tmp_path, key)
    fake_advance, _calls = harness._fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    return project, harness._state(project)


def _abort_round(project: pathlib.Path, stem: str, status: str = "failed") -> str:
    """Materialize one live abort round on disk + in the queue.

    ``_write_round`` (not ``harness._worker_output``) keeps the LF-only byte
    shape, so ``output_bytes`` is exactly the placeholder length on every OS.
    """
    tk = _task_key(stem)
    _write_round(project, stem, log=_round_log(stem, marker=True))
    harness._set_row(project, tk, status)
    return tk


def _aborted_events(project: pathlib.Path) -> list[dict]:
    return [e for e in harness._events(project) if e["ev"] == "l3-aborted"]


def _rounds(project: pathlib.Path) -> dict[str, int]:
    return state.used_rounds(conductor._all_workers_dirs(project))


# ── P1 / VC-001: marker ∧ no qualifying source ⇒ aborted ─────────────────────

def test_p1_marker_without_qualifying_source_is_aborted(
    tmp_path: pathlib.Path,
) -> None:
    _write_round(tmp_path, "l3-a1", log=_round_log("l3-a1", marker=True))
    assert not conductor._l3_qualifies(_PLACEHOLDER)

    verdict, status, source, fail_line = _round_verdict(
        tmp_path, "l3-a1", "failed"
    )
    assert (verdict, status, source, fail_line) == (
        "aborted", "failed", None, None,
    ), (verdict, status, source, fail_line)
    _verify(
        "VC-001", aborted=1, no_verdict=0, worker_status=status,
        deciding_source="none",
    )


# ── P2 / VC-002: the event data is the fixed eight-tuple ─────────────────────

def test_p2_aborted_event_data_is_fixed_eight_tuple(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, st = _boot(tmp_path, monkeypatch)
    assert conductor.tick(project, st) == "ok"  # dispatch l3-a1
    tk = _abort_round(project, "l3-a1")
    assert conductor.tick(project, st) == "ok"  # evaluate round 1

    events = _aborted_events(project)
    assert len(events) == 1, events
    event = events[0]
    data = event["data"]
    assert set(data) == _ABORT_DATA_KEYS, sorted(data)
    assert data["round"] == 1
    assert data["task_key"] == tk
    assert data["worker_status"] == "failed"
    assert data["output_bytes"] == len(_PLACEHOLDER.encode("utf-8"))
    assert data["done_exit_zero"] is True
    assert data["retry_used"] == 0
    assert data["retry_limit"] == 1
    assert isinstance(data["recorded_at"], str) and data["recorded_at"]
    assert "stream-closed" in event["detail"] and tk in event["detail"]
    _verify(
        "VC-002", keys=len(data), done_exit_zero=_b(bool(data["done_exit_zero"])),
        retry_used=data["retry_used"], retry_limit=data["retry_limit"],
    )


# ── P3 / VC-004: dedicated bounded reroll + independent count ────────────────

def test_p3_reroll_dispatches_dedicated_l3abort_round(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, st = _boot(tmp_path, monkeypatch)
    assert conductor.tick(project, st) == "ok"
    _abort_round(project, "l3-a1")
    assert conductor.tick(project, st) == "ok"

    a2 = _task_key("l3-a2")
    assert a2 in [r["task_key"] for r in harness._rows(project, "ap-")]
    a2_md = (
        project / ".agenticdoc" / _LONG_KEY / "workers" / a2 / "task.md"
    ).read_text(encoding="utf-8")
    assert f"loop: l3abort:{_LONG_KEY}" in a2_md
    assert "attempt: 1" in a2_md
    rounds = _rounds(project)
    assert rounds.get(f"l3:{_LONG_KEY}") == 1  # round 1 (shared stem)
    assert rounds.get(f"l3abort:{_LONG_KEY}") == 1  # dedicated counter
    _verify("VC-004", reroll=_b(True), abort_used=rounds[f"l3abort:{_LONG_KEY}"])


# ── P4 / VC-005: abort does not consume the shared L3 budget ────────────────

def test_p4_reroll_ignores_shared_budget_exhaustion(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, st = _boot(tmp_path, monkeypatch)
    cfg = config.load_config(project)
    cfg["round_budget"] = 1  # the shared L3 limit is spent by l3-a1
    config.save_config(project, cfg)

    assert conductor.tick(project, st) == "ok"
    _abort_round(project, "l3-a1")
    assert conductor.tick(project, st) == "ok"

    a2 = _task_key("l3-a2")
    a2_md = (
        project / ".agenticdoc" / _LONG_KEY / "workers" / a2 / "task.md"
    ).read_text(encoding="utf-8")
    rounds = _rounds(project)
    assert f"loop: l3abort:{_LONG_KEY}" in a2_md
    assert rounds.get(f"l3:{_LONG_KEY}") == 1
    assert rounds.get(f"l3abort:{_LONG_KEY}") == 1
    _verify("VC-005", reroll=_b(True), used=rounds[f"l3:{_LONG_KEY}"], limit=1)


# ── P5 / AC-003: a reroll that yields a verdict resumes the normal path ─────

def test_p5_reroll_verdict_resumes_normal_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, st = _boot(tmp_path, monkeypatch)
    assert conductor.tick(project, st) == "ok"
    _abort_round(project, "l3-a1")
    assert conductor.tick(project, st) == "ok"  # abort -> reroll l3-a2

    a2 = _task_key("l3-a2")
    harness._worker_output(project, _LONG_KEY, a2, harness._L3_MEETS)
    harness._set_row(project, a2, "done")
    assert conductor.tick(project, st) == "ok"  # meets on the reroll round

    key_dir = project / ".agenticdoc" / _LONG_KEY
    assert state.read_key_states(project)[_LONG_KEY].phase == "DONE"
    assert (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip() == "meets"
    advance = [
        e for e in harness._events(project)
        if e["ev"] == "advance" and "verify->done exit=0" in e["detail"]
    ]
    assert advance, [e["detail"] for e in harness._events(project)]
    _verify(
        "VC-004", reroll_verdict="meets", phase="DONE",
        advance_exit=0, aborted_events=len(_aborted_events(project)),
    )


# ── P6 / P7 / N6 / VC-006: a qualifying source is never aborted ──────────────

def test_p6_qualifying_report_source_is_not_aborted(tmp_path: pathlib.Path) -> None:
    _write_round(
        tmp_path, "l3-a1",
        log=_round_log("l3-a1", marker=True), report=harness._L3_MEETS,
    )
    # status=failed: a marker-alone predicate would say aborted; the correct
    # `∧ no qualifying source` clause keeps the status gate in charge.
    failed = _round_verdict(tmp_path, "l3-a1", "failed")
    assert failed[0] == "no-verdict" and failed[0] != "aborted"
    # status=done: report.md is the deciding source -> meets.
    done_verdict, _status, source, _fail = _round_verdict(
        tmp_path, "l3-a1", "done"
    )
    assert done_verdict == "meets" and source is not None
    assert source.name == "report.md"
    _verify("VC-006", false_positives=0, case="report-qualifies",
            failed_status=failed[0], done_status=done_verdict)


def test_p7_qualifying_output_source_is_not_aborted(tmp_path: pathlib.Path) -> None:
    _write_round(
        tmp_path, "l3-a1",
        log=_round_log("l3-a1", marker=True), output=harness._L3_MEETS,
    )
    failed = _round_verdict(tmp_path, "l3-a1", "failed")
    assert failed[0] == "no-verdict" and failed[0] != "aborted"
    done_verdict, _status, source, _fail = _round_verdict(
        tmp_path, "l3-a1", "done"
    )
    assert done_verdict == "meets" and source is not None
    assert source.name == "output.md"
    _verify("VC-006", false_positives=0, case="output-qualifies",
            failed_status=failed[0], done_status=done_verdict)


def test_n6_two_sections_with_marker_is_not_aborted(tmp_path: pathlib.Path) -> None:
    """Boundary: the marker and two qualifying sections coexist. The abort
    predicate must stay `∧ no qualifying source` — a marker-only predicate
    would misfire here."""
    _write_round(
        tmp_path, "l3-a1",
        log=_round_log("l3-a1", marker=True), output=harness._L3_MEETS,
    )
    log_path = _round_dir(tmp_path, "l3-a1") / "worker.log"
    assert MARKER in log_path.read_text(encoding="utf-8")
    verdict, _status, source, _fail = _round_verdict(tmp_path, "l3-a1", "done")
    assert verdict == "meets" and source is not None and source.name == "output.md"
    _verify("VC-006", false_positives=0, case="two-sections-plus-marker",
            marker_present=_b(True), verdict=verdict)


# ── N1 / VC-006: no marker ───────────────────────────────────────────────────

def test_n1_no_marker_is_not_aborted(tmp_path: pathlib.Path) -> None:
    _write_round(tmp_path, "l3-a1", log=_round_log("l3-a1", marker=False))
    verdict, status, source, _fail = _round_verdict(tmp_path, "l3-a1", "failed")
    assert verdict == "no-verdict" and status == "failed" and source is None
    _verify("VC-006", false_positives=0, case="no-marker", verdict=verdict)


# ── N2 / X2: marker outside the 64 KiB tail window (fail-closed) ────────────

def test_n2_marker_outside_tail_window_is_not_aborted(
    tmp_path: pathlib.Path,
) -> None:
    far = MARKER + "\n" + ("y" * 70000) + "\n"
    _write_round(tmp_path, "l3-a1", log=far)
    log_path = _round_dir(tmp_path, "l3-a1") / "worker.log"
    assert MARKER in log_path.read_text(encoding="utf-8")  # it IS present...
    assert MARKER not in conductor._l3_worker_log_tail(log_path)  # ...not in the window
    verdict, _status, _source, _fail = _round_verdict(tmp_path, "l3-a1", "failed")
    assert verdict != "aborted"
    _verify("VC-006", false_positives=0, case="marker-outside-tail",
            verdict=verdict)


# ── N3 / VC-006: provider 403 is not this class ─────────────────────────────

def test_n3_provider_403_is_not_aborted(tmp_path: pathlib.Path) -> None:
    """D class (RQ-1 F4/F5): a 403 round carries its own error line and the
    same misleading `[worker] done exit=0`, but no stream marker; the abort
    predicate must keep it at zero false positives."""
    log = _round_log("l3-a1", marker=False, provider_403=True)
    assert "[worker] done exit=0" in log
    assert "403" in log and MARKER not in log
    _write_round(tmp_path, "l3-a1", log=log)
    verdict, _status, _source, _fail = _round_verdict(tmp_path, "l3-a1", "failed")
    assert verdict != "aborted"
    _verify("VC-006", false_positives=0, case="provider-403", verdict=verdict)


# ── N4 / VC-006 + VC-003 part: a real FAIL is below, never aborted ───────────

def test_n4_real_fail_marker_is_below(tmp_path: pathlib.Path) -> None:
    _write_round(
        tmp_path, "l3-a1",
        log=_round_log("l3-a1", marker=False), output=harness._L3_BELOW,
    )
    verdict, _status, source, fail_line = _round_verdict(
        tmp_path, "l3-a1", "done"
    )
    assert verdict == "below" and source is not None and fail_line is not None
    assert "FAIL" in fail_line

    # Control: the marker coexisting with a FAIL-bearing qualifying source must
    # still resolve below (the abort fingerprint may not swallow a real FAIL).
    _write_round(
        tmp_path, "l3-a2",
        log=_round_log("l3-a2", marker=True), output=harness._L3_BELOW,
    )
    with_marker, _s2, src2, fail2 = _round_verdict(tmp_path, "l3-a2", "done")
    assert with_marker == "below" and fail2 is not None and "FAIL" in fail2
    _verify("VC-006", false_positives=0, case="real-fail",
            verdict=verdict, marker_variant=with_marker)


# ── N5 / VC-006: the prose `report.md` (fourth class) is below ──────────────

def test_n5_prose_report_is_below(tmp_path: pathlib.Path) -> None:
    assert not conductor._l3_qualifies(_PROSE_REPORT)
    _write_round(
        tmp_path, "l3-a1",
        log=_round_log("l3-a1", marker=False),
        output=_PLACEHOLDER, report=_PROSE_REPORT,
    )
    verdict, _status, source, _fail = _round_verdict(tmp_path, "l3-a1", "done")
    assert verdict == "below" and source is None
    _verify("VC-006", false_positives=0, case="prose-report", verdict=verdict)


# ── VC-006 sweep: every negative class contributes zero false positives ──────

def test_vc006_false_positive_sweep(tmp_path: pathlib.Path) -> None:
    cases: list[tuple[str, str, str | None]] = [
        ("l3-a1", "failed", _round_log("l3-a1", marker=False)),
        ("l3-a2", "failed", MARKER + "\n" + ("y" * 70000) + "\n"),
        ("l3-a3", "failed", _round_log("l3-a3", marker=False, provider_403=True)),
        # a real FAIL (two sections) + a prose report are below/meets paths,
        # not abort paths; they are covered by N4/N5 directly.
    ]
    aborted = 0
    for stem, status, log in cases:
        _write_round(tmp_path, stem, log=log)
        aborted += int(_round_verdict(tmp_path, stem, status)[0] == "aborted")
    _write_round(
        tmp_path, "l3-a4",
        log=_round_log("l3-a4", marker=False), output=harness._L3_BELOW,
    )
    _write_round(
        tmp_path, "l3-a5",
        log=_round_log("l3-a5", marker=False),
        output=_PLACEHOLDER, report=_PROSE_REPORT,
    )
    aborted += int(_round_verdict(tmp_path, "l3-a4", "done")[0] == "aborted")
    aborted += int(_round_verdict(tmp_path, "l3-a5", "done")[0] == "aborted")
    _write_round(
        tmp_path, "l3-a6",
        log=_round_log("l3-a6", marker=True), output=harness._L3_MEETS,
    )
    aborted += int(_round_verdict(tmp_path, "l3-a6", "done")[0] == "aborted")
    assert aborted == 0, aborted
    _verify("VC-006", false_positives=aborted, cases=6)


# ── VC-003: the three no-verdict classes are pairwise exclusive ─────────────

def test_vc003_three_way_exclusivity(tmp_path: pathlib.Path) -> None:
    # A: wrong carrier, long report in report.md (documented fallback).
    _write_round(
        tmp_path, "l3-a1",
        log=_round_log("l3-a1", marker=False), report=harness._L3_MEETS,
    )
    # B: provider stream abort (marker, no qualifying source).
    _write_round(tmp_path, "l3-a2", log=_round_log("l3-a2", marker=True))
    # C: real FAIL (both sections + FAIL row).
    _write_round(
        tmp_path, "l3-a3",
        log=_round_log("l3-a3", marker=False), output=harness._L3_BELOW,
    )
    a = _round_verdict(tmp_path, "l3-a1", "done")
    b = _round_verdict(tmp_path, "l3-a2", "failed")
    c = _round_verdict(tmp_path, "l3-a3", "done")
    assert a[0] == "meets" and a[2] is not None and a[2].name == "report.md"
    assert b[0] == "aborted"
    assert c[0] == "below" and c[3] is not None and "FAIL" in c[3]
    classes = {a[0], b[0], c[0]}
    assert len(classes) == 3, classes
    _verify(
        "VC-003", exclusive=_b(True), classes=len(classes),
        a=a[0], b=b[0], c=c[0],
    )


# ── X1 / VC-017: the fingerprint is load-bearing for P1 ─────────────────────

def test_x1_fingerprint_is_load_bearing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-vacuous control: with the fingerprint removed (the pre-T-01 chain
    order) the P1 fixture no longer yields ``aborted`` — the status gate fires
    first and P1's assertion would be red."""
    _write_round(tmp_path, "l3-a1", log=_round_log("l3-a1", marker=True))
    on, _s, _src, _fail = _round_verdict(tmp_path, "l3-a1", "failed")
    assert on == "aborted"

    monkeypatch.setattr(
        conductor, "_l3_stream_aborted", lambda key_dir, task_key: False
    )
    off, _s2, _src2, _fail2 = _round_verdict(tmp_path, "l3-a1", "failed")
    assert off == "no-verdict" and off != "aborted"
    _verify(
        "VC-017", counterfactual="fingerprint-removed", with_fingerprint=on,
        without_fingerprint=off, p1_would_be_red=_b(off != "aborted"),
    )


# ── X2 / VC-017: the tail-window boundary fails closed ──────────────────────

def test_x2_tail_window_is_fail_closed(tmp_path: pathlib.Path) -> None:
    """Control for X2/N2: the same marker inside the window is aborted, while
    the marker pushed out of the tail 64 KiB is not (the fail-closed
    direction); the window read itself stays bounded."""
    _write_round(tmp_path, "l3-a1", log=_round_log("l3-a1", marker=True))
    inside_log = _round_dir(tmp_path, "l3-a1") / "worker.log"
    inside = _round_verdict(tmp_path, "l3-a1", "failed")
    assert inside[0] == "aborted"
    tail_bytes = len(conductor._l3_worker_log_tail(inside_log))
    assert tail_bytes <= 64 * 1024

    far = MARKER + "\n" + ("z" * 70000) + "\n"
    _write_round(tmp_path, "l3-a2", log=far)
    far_log = _round_dir(tmp_path, "l3-a2") / "worker.log"
    outside = _round_verdict(tmp_path, "l3-a2", "failed")
    assert MARKER in far_log.read_text(encoding="utf-8")
    assert MARKER not in conductor._l3_worker_log_tail(far_log)
    assert outside[0] != "aborted"
    _verify(
        "VC-017", counterfactual="marker-outside-tail",
        inside=inside[0], outside=outside[0],
        tail_bytes=tail_bytes, fail_closed=_b(outside[0] != "aborted"),
    )


# ── X3 / VC-017: the `∧ no qualifying source` clause is load-bearing ───────

def test_x3_qualifying_source_clause_is_load_bearing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second non-vacuity control: with the `no qualifying source` clause
    removed from the predicate, the P6 fixture (marker + qualifying
    ``report.md``) flips to ``aborted`` — so P6/P7/N6 depend on that
    clause, not on the marker alone."""
    _write_round(
        tmp_path, "l3-a1",
        log=_round_log("l3-a1", marker=True), report=harness._L3_MEETS,
    )
    on, _s, _src, _fail = _round_verdict(tmp_path, "l3-a1", "done")
    assert on == "meets"

    monkeypatch.setattr(conductor, "_l3_qualifies", lambda text: False)
    off, _s2, _src2, _fail2 = _round_verdict(tmp_path, "l3-a1", "done")
    assert off == "aborted"
    _verify(
        "VC-017", counterfactual="qualifying-source-clause-removed",
        with_clause=on, without_clause=off,
        p6_would_be_red=_b(off == "aborted"),
    )


# ── fixture shape lock (AC-014 / P-023: real code path, measured shape) ──────

def test_fixture_minimal_shape_matches_measurement(tmp_path: pathlib.Path) -> None:
    """The abort fixture must replicate the measured corpus shape: 160-179 B
    worker.log, marker 40 B from EOF, the misleading `[worker] done exit=0`
    line, and the real queue row `status=failed`."""
    _write_round(tmp_path, "l3-a1", log=_round_log("l3-a1", marker=True))
    raw = (_round_dir(tmp_path, "l3-a1") / "worker.log").read_bytes()
    size = len(raw)
    from_eof = size - raw.find(MARKER.encode("utf-8"))
    assert 160 <= size <= 179, size
    assert from_eof == 40, from_eof
    assert b"[worker] done exit=0" in raw
    rows = _rows_for("l3-a1", "failed")
    assert rows[0]["status"] == "failed" and rows[0]["task_key"] == _task_key("l3-a1")
    _verify(
        "VC-002", worker_log_bytes=size, marker_from_eof=from_eof,
        queue_status=rows[0]["status"],
    )


# ── P8 / AC-003 + AC-001: budget exhausted ⇒ stall with the machine code ────

def test_p8_abort_budget_exhausted_stalls_l3_aborted(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, st = _boot(tmp_path, monkeypatch)
    assert conductor.tick(project, st) == "ok"
    _abort_round(project, "l3-a1")
    assert conductor.tick(project, st) == "ok"  # abort -> dedicated reroll
    _abort_round(project, "l3-a2")
    assert conductor.tick(project, st) == "ok"  # dedicated budget spent -> stall

    assert _task_key("l3-a3") not in [r["task_key"] for r in harness._rows(project, "ap-")]
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status[_LONG_KEY] == "stalled"
    stalled = [
        g for g in gates.enumerate(conductor.gates_dir(project)) if g.kind == "stalled"
    ]
    assert len(stalled) == 1, stalled
    gate = stalled[0]
    assert gate.reason_code == "l3-aborted"
    assert gate.loop == f"l3abort:{_LONG_KEY}"
    assert (gate.used_rounds, gate.round_limit, gate.credits_used) == (1, 1, 0)
    assert conductor._stall_family(gate) == "l3"
    cause = conductor.recompute_stall_cause(project, gate)
    assert cause == "l3-aborted", cause
    key_dir = project / ".agenticdoc" / _LONG_KEY
    assert (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip() == "below"
    _verify(
        "VC-001", aborted_events=len(_aborted_events(project)),
        stalled=_b(True), reason_code=gate.reason_code, loop=gate.loop,
        cause_class=cause,
    )
