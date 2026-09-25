"""
test_autopilot_verdict_provenance_guard.py — L1 contract tests for the L3
verdict provenance guard (key `feature-verdict-provenance-guard`,
design D-001..D-014 / plan S1 T-003).

New file only (D-013 / AC-017): **no existing test file is modified**. The
fixture tool-box is imported from ``test_autopilot_conductor_exec`` (harness)
and the source-fallback conventions from
``test_autopilot_verdict_source_fallback``; every mtime is built explicitly
with ``os.utime(ns=...)`` inside ``tmp_path`` fixtures, so no real project
tree and no other key's ``.agenticdoc`` state is read (AC head-note /
"需规避坑点 10").  The F-P4 write-directive predicate lives HERE (test side)
so the T-002 prompt text and these assertions share one definition.

AC coverage (machine-readable, one line per AC):

# AC-001 -> test_normal_round_not_suspect
# AC-002 -> test_time_overrun_marks_suspect_and_fails_closed
# AC-003 -> test_copy_signature_marks_suspect
# AC-004 -> test_citage_shape_post_trace_rewrite
# AC-005 -> test_per_round_anchor_no_cross_round_false_positive
# AC-006 -> test_missing_trace_abstains_and_legacy_fallback_still_passes
# AC-007 -> test_value_domain_closed_suspect_only_in_sidecar
# AC-008 -> test_repair_prompt_forbids_deciding_source_write
# AC-009 -> test_suspect_round_dispatches_next_reviewer_not_repair
# AC-010 -> test_reviewer_prompt_documents_provenance
# AC-011 -> test_optimistic_key_done_refused
# AC-012 -> test_legitimate_done_preserved
# AC-013 -> test_frozen_anchors_and_criteria_unchanged
# AC-014 -> test_only_tighten_no_below_to_meets
# AC-020 -> test_idempotent_zero_write_and_io_bound
# AC-021 -> test_worker_status_priority_not_degraded
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import test_autopilot_conductor_exec as harness  # noqa: E402
import test_autopilot_verdict_source_fallback as fallback  # noqa: E402
from autopilot import conductor, roadmap  # noqa: E402

# ── fixture tool-box contract (F-P5: import only, never modify) ──────────────

_HARNESS_SYMBOLS = (
    "_verify_key_project", "_worker_output", "_set_row", "_rows", "_L3_MEETS",
    "_L3_BELOW", "_fake_advance_factory", "_state", "_set_index_phase_file",
)
_FALLBACK_SYMBOLS = ("_boot", "_output", "_report", "_dispatch_a1")

# T-001 / design §0 frozen left-end anchors (independent literals).
_PARSE_L3_SHA = "b0348c4fc06ac0f28bf206d217732126a1a589ba99079158f2257763f8124c98"
_MD_SECTION_SHA = "c0926b8d790f58245285a621dedd5a12c27a664af6082db76bbc4c474cb03d2b"

# Reverse / fail-closed lower bound (design §8: >= 6).
_FAIL_CLOSED_CASES = (
    "test_time_overrun_marks_suspect_and_fails_closed",
    "test_copy_signature_marks_suspect",
    "test_citage_shape_post_trace_rewrite",
    "test_missing_trace_abstains_and_legacy_fallback_still_passes",
    "test_repair_prompt_forbids_deciding_source_write",
    "test_suspect_round_dispatches_next_reviewer_not_repair",
    "test_optimistic_key_done_refused",
    "test_worker_status_priority_not_degraded",
)

# ── F-P4 predicate (plan §9; single definition shared with T-002) ────────────

_TARGET_AC008 = ("output.md", "report.md")   # AC-008 target set (basenames)
_TARGET_AC009 = "workers/"                   # AC-009 target set (literal)
_WRITE_VERBS = (
    "写", "写入", "另写", "修改", "改动", "改写", "补写", "重写",
    "编辑", "更新", "覆盖", "追加", "落盘", "保存",
    "write", "edit", "modify", "update", "overwrite", "append", "save",
    "rewrite", "patch",
)
_NEG_MARKERS = (
    "禁止", "不得", "不可", "不能", "不要", "只读", "不改",
    "read-only", "must not", "never", "do not",
)
_CLAUSE_DELIMS = re.compile(r"[\n。；！!]")


def _split_clauses(text: str) -> list[str]:
    return [c for c in _CLAUSE_DELIMS.split(text) if c.strip()]


def _contains_any(text: str, needles) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


def _t1_count(text: str) -> list[str]:
    """AC-008: clauses naming output.md/report.md AND a write verb."""
    return [
        c for c in _split_clauses(text)
        if _contains_any(c, _TARGET_AC008) and _contains_any(c, _WRITE_VERBS)
    ]


def _t2_count(text: str) -> list[str]:
    """AC-009: clauses naming ``workers/`` AND a write verb AND no negation."""
    return [
        c for c in _split_clauses(text)
        if _TARGET_AC009 in c and _contains_any(c, _WRITE_VERBS)
        and not _contains_any(c, _NEG_MARKERS)
    ]


# ── helpers ──────────────────────────────────────────────────────────────────

_T0 = 1_700_000_000_000_000_000        # arbitrary fixed epoch (ns)
_SLACK_NS = 60_000_000_000             # conductor._PROVENANCE_SLACK_SEC
_LONG_NS = 600_000_000_000             # 600 s: comfortably past the slack

_UNQUALIFIED_DRAFT = "# L3 draft\n\nonly prose, no L3 sections yet\n"

_PKG_DIR = pathlib.Path(__file__).parent
_CONDUCTOR_FAMILY = (
    "test_autopilot_conductor_exec.py",
    "test_autopilot_conductor_stage.py",
    "test_autopilot_conductor.py",
    "test_autopilot_stall.py",
)


def _b(value) -> str:
    return harness.true_str(bool(value))


def _require_symbols() -> None:
    missing = [n for n in _HARNESS_SYMBOLS if not hasattr(harness, n)]
    missing += [n for n in _FALLBACK_SYMBOLS if not hasattr(fallback, n)]
    assert not missing, f"fixture tool-box drift (F-P5): {missing}"


@pytest.fixture(autouse=True)
def _toolbox() -> None:
    _require_symbols()


def _write_at(path: pathlib.Path, text: str, mtime_ns: int) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def _sha256(path: pathlib.Path | str) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _mtime_ns(path: pathlib.Path | str) -> int:
    return pathlib.Path(path).stat().st_mtime_ns


def _sidecar(key_dir: pathlib.Path) -> list[dict]:
    path = key_dir / conductor._PROVENANCE_FILENAME
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _record_for(key_dir: pathlib.Path, task_key: str) -> dict:
    return next(r for r in _sidecar(key_dir) if r["task_key"] == task_key)


def _dispatched_task_mds(key_dir: pathlib.Path) -> list[str]:
    return [
        p.read_text(encoding="utf-8")
        for p in sorted((key_dir / "workers").glob("*/task.md"))
    ]


def _func_source(text: str, prefix: str) -> str:
    """Byte-same algorithm as test_autopilot_verdict_freshness._func_source
    (region hash, trailing ``\\n`` included — F-P2)."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(prefix)), None)
    assert start is not None, prefix
    out = [lines[start]]
    for line in lines[start + 1:]:
        if (
            line.startswith("def ")
            or line.startswith("class ")
            or line.startswith("# \u2500\u2500")
        ):
            break
        out.append(line)
    return "\n".join(out) + "\n"


def _conductor_region_sha(prefix: str) -> str:
    text = pathlib.Path(conductor.__file__).read_text(encoding="utf-8")
    return hashlib.sha256(_func_source(text, prefix).encode("utf-8")).hexdigest()


def _run_pytest(files) -> tuple[int, int]:
    """Run one test subset in a child interpreter; (returncode, passed)."""
    cmd = [
        sys.executable, "-X", "utf8", "-m", "pytest", *files,
        "-q", "-p", "no:cacheprovider",
    ]
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PYTEST_CURRENT_TEST", "PYTEST_ADDOPTS")
    }
    proc = subprocess.run(
        cmd, cwd=str(_PKG_DIR), capture_output=True, text=True, env=env
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(r"(\d+) passed", out)
    return proc.returncode, (int(match.group(1)) if match else -1)


def _tree_digest(root: pathlib.Path) -> str:
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            h.update(f"D {rel}\n".encode("utf-8"))
        else:
            h.update(f"F {rel} {_sha256(path)} {path.stat().st_mtime_ns}\n".encode("utf-8"))
    return h.hexdigest()


# ── AC-001 / VC-001 ──────────────────────────────────────────────────────────

def test_normal_round_not_suspect(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean terminal round (trace anchored, source written before the round
    end) must not be suspect and must stay `meets`."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    _write_at(worker / "output.md", harness._L3_MEETS, _T0)
    _write_at(worker / "trace.log", "round 1 end\n", _T0 + 5_000_000_000)
    assert not (worker / "report.md").exists()
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    rec = _record_for(key_dir, task_key)
    ok = (
        rec["suspect"] is False and rec["reasons"] == []
        and rec["raw_verdict"] == "meets" and rec["verdict"] == "meets"
    )
    print(
        f"[VERIFY] VC-001: suspect={_b(rec['suspect'])} "
        f"reasons=[] verdict={rec['verdict']}"
    )
    assert ok, rec


# ── AC-002 / VC-002 ──────────────────────────────────────────────────────────

def test_time_overrun_marks_suspect_and_fails_closed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T1: the deciding source written 600 s AFTER the round's trace.log end is
    suspect; with round_budget=1 the terminal verdict is `below`."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    fallback._budget_one(project)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    anchor_ns = _T0
    _write_at(worker / "trace.log", "round 1 end\n", anchor_ns)
    _write_at(worker / "output.md", harness._L3_MEETS, anchor_ns + _LONG_NS)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    rec = _record_for(key_dir, task_key)
    terminal = (
        (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip()
    )
    delta_ok = any("600.0s AFTER trace.log end" in r for r in rec["reasons"])
    ok = (
        rec["suspect"] is True and delta_ok
        and rec["verdict"] == "below" and terminal == "below"
    )
    print(
        "[VERIFY] VC-002: "
        f"suspect={_b(rec['suspect'])} delta_substring=600.0s "
        f"verdict={rec['verdict']} terminal={terminal}"
    )
    assert ok, (rec, terminal)


# ── AC-003 / VC-003 ──────────────────────────────────────────────────────────

def test_copy_signature_marks_suspect(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T2: output.md's two sections are byte-equal to the same round's
    report.md but written 600 s later, while T1 does NOT fire (within slack)."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    anchor_ns = _T0
    source_ns = anchor_ns + 10_000_000_000          # inside the 60 s slack
    report_ns = source_ns - _LONG_NS                # 600 s before the rewrite
    _write_at(worker / "trace.log", "round 1 end\n", anchor_ns)
    _write_at(worker / "output.md", harness._L3_MEETS, source_ns)
    _write_at(worker / "report.md", harness._L3_MEETS, report_ns)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    rec = _record_for(key_dir, task_key)
    t1_fired = any("AFTER trace.log end" in r for r in rec["reasons"])
    bytes_equals = any(
        "byte-equal report.md but written later" in r for r in rec["reasons"]
    )
    ok = rec["suspect"] is True and bytes_equals and t1_fired is False
    print(
        f"[VERIFY] VC-003: suspect={_b(rec['suspect'])} "
        f"reason_bytes_equals={_b(bytes_equals)} t1={_b(t1_fired)}"
    )
    assert ok, rec


# ── AC-004 / VC-004 ──────────────────────────────────────────────────────────

def test_citage_shape_post_trace_rewrite(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """citage shape: an unqualified draft is rewritten into a qualified meets
    submission after the round ended (copying report.md's two sections) ->
    suspect, verdict below, and report.md is byte-unchanged."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    anchor_ns = _T0
    _write_at(worker / "trace.log", "round 1 end\n", anchor_ns)
    # pre-trace unqualified draft (mtime <= trace end)
    _write_at(worker / "output.md", _UNQUALIFIED_DRAFT, anchor_ns - 5_000_000_000)
    _write_at(worker / "report.md", harness._L3_MEETS, anchor_ns - 10_000_000_000)
    report_sha_before = _sha256(worker / "report.md")
    # post-trace rewrite into a qualified meets submission
    _write_at(worker / "output.md", harness._L3_MEETS, anchor_ns + _LONG_NS)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    rec = _record_for(key_dir, task_key)
    report_sha_unchanged = _sha256(worker / "report.md") == report_sha_before
    ok = (
        rec["suspect"] is True and bool(rec["reasons"])
        and rec["verdict"] == "below" and report_sha_unchanged
    )
    print(
        f"[VERIFY] VC-004: suspect={_b(rec['suspect'])} "
        f"reasons_nonempty={_b(bool(rec['reasons']))} "
        f"report_sha_unchanged={_b(report_sha_unchanged)}"
    )
    assert ok, rec


# ── AC-005 / VC-005 ──────────────────────────────────────────────────────────

def test_per_round_anchor_no_cross_round_false_positive(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The anchor is the same round's trace.log: ``l3-a2`` lands before its own
    trace end, so it is clean even though its absolute mtime is later than
    round 1 (per-round directory comparison, GC-13/I-13)."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    key_dir = project / ".agenticdoc" / "k1"
    a1 = fallback._dispatch_a1(project, st)
    # round 1: clean but below -> repair -> round 2
    _write_at(key_dir / "workers" / a1 / "trace.log", "round 1 end\n", _T0 - 50_000_000_000)
    _write_at(key_dir / "workers" / a1 / "output.md", harness._L3_BELOW, _T0)
    harness._set_row(project, a1, "done")
    assert conductor.tick(project, st) == "ok"          # repair-a1 dispatched
    repair_key = "ap-k1-repair-a1"
    harness._set_row(project, repair_key, "done")
    assert conductor.tick(project, st) == "ok"          # l3-a2 dispatched

    a2 = "ap-k1-l3-a2"
    a2_worker = key_dir / "workers" / a2
    _write_at(a2_worker / "trace.log", "round 2 end\n", _T0 + 100_000_000_000)
    _write_at(a2_worker / "output.md", harness._L3_MEETS, _T0 + 90_000_000_000)
    harness._set_row(project, a2, "done")
    assert conductor.tick(project, st) == "ok"

    rec = _record_for(key_dir, a2)
    ok = rec["suspect"] is False and rec["verdict"] == "meets"
    print(
        f"[VERIFY] VC-005: a2_suspect={_b(rec['suspect'])} "
        f"a2_verdict={rec['verdict']}"
    )
    assert ok, rec


# ── AC-006 / VC-006 ──────────────────────────────────────────────────────────

def test_missing_trace_abstains_and_legacy_fallback_still_passes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No trace.log -> abstain (suspect=false, reasons=[], anchor_path=null);
    the 15 legacy source-fallback assertions stay green (GC-13/R-B)."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    _write_at(worker / "output.md", harness._L3_MEETS, _T0)
    assert not (worker / "trace.log").exists()          # abstain fixture
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    rec = _record_for(key_dir, task_key)
    abstain = (
        rec["suspect"] is False and rec["reasons"] == []
        and rec["anchor_path"] is None
    )
    rc, passed = _run_pytest(("test_autopilot_verdict_source_fallback.py",))
    legacy_15_passed = rc == 0 and passed == 15
    ok = abstain and legacy_15_passed and rec["verdict"] == "meets"
    print(
        f"[VERIFY] VC-006: abstain={_b(abstain)} "
        f"legacy_15_passed={_b(legacy_15_passed)}"
    )
    assert ok, (rec, rc, passed)


# ── AC-007 / VC-007 ──────────────────────────────────────────────────────────

def test_value_domain_closed_suspect_only_in_sidecar(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """l3-verdict.txt stays in the frozen two-value domain and `suspect` never
    leaks out of the sidecar (l3-verdict.txt / l3-report.md)."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    fallback._budget_one(project)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    _write_at(worker / "trace.log", "round 1 end\n", _T0)
    _write_at(worker / "output.md", harness._L3_MEETS, _T0 + _LONG_NS)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    verdict_text = (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip()
    report_text = (key_dir / "l3-report.md").read_text(encoding="utf-8")
    sidecar_text = (
        key_dir / conductor._PROVENANCE_FILENAME
    ).read_text(encoding="utf-8")
    value_domain_closed = (
        conductor._VERDICT_VALUES == ("meets", "below")
        and verdict_text in conductor._VERDICT_VALUES
    )
    suspect_only_in_sidecar = (
        "suspect" in sidecar_text
        and "suspect" not in verdict_text
        and "suspect" not in report_text
    )
    ok = value_domain_closed and suspect_only_in_sidecar
    print(
        f"[VERIFY] VC-007: value_domain_closed={_b(value_domain_closed)} "
        f"suspect_only_in_sidecar={_b(suspect_only_in_sidecar)}"
    )
    assert ok, (verdict_text, suspect_only_in_sidecar)


# ── AC-008 / VC-008 ──────────────────────────────────────────────────────────

def test_repair_prompt_forbids_deciding_source_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_repair_prompt` forbids editing the deciding source, keeps the
    ``- L3 报告：`` line verbatim in both reference shapes, and contains no
    clause with a write verb next to output.md/report.md (F-P4 T1 = 0)."""
    report_rel = ".agenticdoc/k1/workers/ap-k1-l3-a1/report.md"
    output_rel = ".agenticdoc/k1/workers/ap-k1-l3-a1/output.md"
    prompts = (
        (conductor._repair_prompt("k1", 1, report_rel), report_rel),
        (conductor._repair_prompt("k1", 1, output_rel), output_rel),
    )
    forbids = all(
        "禁止" in p and "workers/*-l3-*/" in p and "re-review" in p
        for p, _ in prompts
    )
    report_line_verbatim = all(
        f"- L3 报告：{rel}" in p
        and any(
            line.startswith(f"- L3 报告：{rel}") for line in p.splitlines()
        )
        for p, rel in prompts
    )
    directives = sum(
        len(_t1_count(p)) + len(_t2_count(p)) for p, _ in prompts
    )
    ok = forbids and report_line_verbatim and directives == 0
    print(
        f"[VERIFY] VC-008: forbids={_b(forbids)} "
        f"report_line_verbatim={_b(report_line_verbatim)} "
        f"write_directives={directives}"
    )
    assert ok, (directives, forbids, report_line_verbatim)


# ── AC-009 / VC-009 ──────────────────────────────────────────────────────────

def test_suspect_round_dispatches_next_reviewer_not_repair(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A suspect meets-round spends the budget on a fresh reviewer (never the
    repair path); no dispatched task.md carries a write directive."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    _write_at(worker / "trace.log", "round 1 end\n", _T0)
    _write_at(worker / "output.md", _UNQUALIFIED_DRAFT, _T0 - 5_000_000_000)
    _write_at(worker / "report.md", harness._L3_MEETS, _T0 - 10_000_000_000)
    _write_at(worker / "output.md", harness._L3_MEETS, _T0 + _LONG_NS)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    rows = harness._rows(project, "ap-k1-")
    keys = [r["task_key"] for r in rows]
    next_key = "ap-k1-l3-a2"
    repair_key = "ap-k1-repair-a1"
    next_md = (key_dir / "workers" / next_key / "task.md").read_text(encoding="utf-8")
    dispatched = (
        "reviewer"
        if ("type: reviewer" in next_md and next_key.endswith("l3-a2"))
        else "other"
    )
    directives = sum(
        len(_t1_count(t)) + len(_t2_count(t))
        for t in _dispatched_task_mds(key_dir)
    )
    ok = (
        next_key in keys and repair_key not in keys
        and dispatched == "reviewer" and directives == 0
    )
    print(
        f"[VERIFY] VC-009: dispatched={dispatched} "
        f"write_directives={directives} next_stem=l3-a2"
    )
    assert ok, (keys, directives)


# ── AC-010 / VC-010 ──────────────────────────────────────────────────────────

def test_reviewer_prompt_documents_provenance(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_l3_prompt` documents the provenance guard (suspect / 本轮) while the
    eight legacy substrings stay in place."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    task_key = fallback._dispatch_a1(project, st)
    prompt = conductor._l3_prompt("k1", 1)
    task_md = (
        project / ".agenticdoc" / "k1" / "workers" / task_key / "task.md"
    ).read_text(encoding="utf-8")
    legacy = (
        "report.md", "回退源", "output.md", "首选",
        "## Quality Gate Report", "## Achieved", "FAIL", "below",
    )
    legacy_hits = sum(1 for s in legacy if s in prompt)
    suspect_documented = "suspect" in prompt and "本轮" in prompt
    ok = suspect_documented and legacy_hits == 8 and "output.md" in task_md
    print(
        f"[VERIFY] VC-010: suspect_documented={_b(suspect_documented)} "
        f"legacy_substrings={legacy_hits}"
    )
    assert ok, (legacy_hits, suspect_documented)


# ── AC-011 / VC-011 ──────────────────────────────────────────────────────────

def test_optimistic_key_done_refused(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare index Phase=DONE without the done derivatives must be refused:
    roadmap key-status stays `running` and the refusal is on the timeline."""
    project = harness._verify_key_project(tmp_path)
    fake_advance, _calls = harness._fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    harness._set_index_phase_file(project, "k1", "DONE")
    st = harness._state(project)
    assert conductor.tick(project, st) == "ok"

    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    key_status = rm.stages[0].key_status["k1"]
    refused = [
        e for e in harness._events(project)
        if e["ev"] == "config" and "key-done refused" in str(e.get("detail", ""))
    ]
    ok = key_status == "running" and len(refused) >= 1
    print(
        f"[VERIFY] VC-011: key_status={key_status} "
        f"refused_events>={max(1, len(refused))}"
    )
    assert ok, (key_status, refused)


# ── AC-012 / VC-012 ──────────────────────────────────────────────────────────

def test_legitimate_done_preserved(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The standard done transaction still reaches roadmap key-status=done and
    the whole conductor test family stays green."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    task_key = fallback._dispatch_a1(project, st)
    harness._worker_output(project, "k1", task_key, harness._L3_MEETS)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"      # done transaction
    assert conductor.tick(project, st) == "ok"      # phase DONE -> mark done
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    key_status = rm.stages[0].key_status["k1"]

    rc, passed = _run_pytest(_CONDUCTOR_FAMILY)
    status = "passed" if rc == 0 else "failed"
    ok = key_status == "done" and status == "passed" and passed > 0
    print(
        f"[VERIFY] VC-012: key_status={key_status} "
        f"conductor_family={passed} {status}"
    )
    assert ok, (key_status, rc, passed)


# ── AC-013 / VC-013 ──────────────────────────────────────────────────────────

def test_frozen_anchors_and_criteria_unchanged(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two frozen primitives keep their exact region sha and
    `_l3_round_verdict` still returns a 3-tuple."""
    parse_sha = _conductor_region_sha("def _parse_l3_output(")
    md_sha = _conductor_region_sha("def _md_section(")
    project, st = fallback._boot(tmp_path, monkeypatch)
    fallback._dispatch_a1(project, st)
    result = conductor._l3_round_verdict(project, harness._rows(project), "k1", 1)
    tuple_len = len(result) if isinstance(result, tuple) else -1
    parse_ok = parse_sha == _PARSE_L3_SHA
    md_ok = md_sha == _MD_SECTION_SHA
    ok = parse_ok and md_ok and tuple_len == 3
    print(
        f"[VERIFY] VC-013: parse_sha_match={_b(parse_ok)} "
        f"md_section_sha_match={_b(md_ok)} tuple_len={tuple_len}"
    )
    assert ok, (parse_sha, md_sha, tuple_len)


# ── AC-014 / VC-014 (fixture synthetic semantics; real corpus = T-004) ───────

# (task_key, pre-guard verdict, trace delta s or None, note)
_AC014_CASES = (
    ("ap-synth-l3-a1", "meets", None),   # no trace -> abstain -> meets
    ("ap-synth-l3-a2", "meets", 0),      # clean round -> meets
    ("ap-synth-l3-a3", "meets", 600),    # overrun -> below (the only flip)
    ("ap-synth-l3-a4", "below", 600),    # overrun, already below -> below
    ("ap-synth-l3-a5", "below", 0),      # clean below -> below
)


def test_only_tighten_no_below_to_meets(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic fixture matrix: the guard only tightens (exactly one
    meets->below flip), never promotes below->meets, and is read-only."""
    key_dir = tmp_path / ".agenticdoc" / "synth"
    olds: list[str] = []
    sources: list[pathlib.Path] = []
    for task_key, old_verdict, delta_s in _AC014_CASES:
        worker = key_dir / "workers" / task_key
        worker.mkdir(parents=True, exist_ok=True)
        body = harness._L3_MEETS if old_verdict == "meets" else harness._L3_BELOW
        out = worker / "output.md"
        out.write_text(body, encoding="utf-8", newline="\n")
        if delta_s is None:
            os.utime(out, ns=(_T0, _T0))
        else:
            trace = worker / "trace.log"
            trace.write_text("round end\n", encoding="utf-8", newline="\n")
            os.utime(trace, ns=(_T0, _T0))
            stamp = _T0 + delta_s * 10**9
            os.utime(out, ns=(stamp, stamp))
        olds.append(old_verdict)
        sources.append(out)

    before = _tree_digest(key_dir)
    records = [
        conductor._l3_provenance_record(key_dir, task_key, source, old_verdict)
        for (task_key, old_verdict, _delta), source in zip(_AC014_CASES, sources)
    ]
    after = _tree_digest(key_dir)

    changed = sum(1 for old, rec in zip(olds, records) if rec["verdict"] != old)
    below_to_meets = sum(
        1 for old, rec in zip(olds, records)
        if old == "below" and rec["verdict"] == "meets"
    )
    flips = sum(
        1 for rec in records
        if rec["suspect"] and rec["raw_verdict"] == "meets" and rec["verdict"] == "below"
    )
    zero_write = before == after
    ok = changed == 1 and below_to_meets == 0 and flips == 1 and zero_write
    print(
        f"[VERIFY] VC-014: changed={changed} "
        f"below_to_meets={below_to_meets} zero_write={_b(zero_write)}"
    )
    assert ok, (changed, below_to_meets, flips, zero_write)


# ── AC-020 / VC-020 ──────────────────────────────────────────────────────────

def test_idempotent_zero_write_and_io_bound(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replaying tick() (crash-retry) leaves the three terminal artifacts
    byte- and mtime-identical, and a clean provenance round costs 2 mtime
    stats / 0 reads / 0 directory scans."""
    project, st = fallback._boot(tmp_path, monkeypatch)
    fallback._budget_one(project)
    task_key = fallback._dispatch_a1(project, st)
    key_dir = project / ".agenticdoc" / "k1"
    worker = key_dir / "workers" / task_key
    _write_at(worker / "trace.log", "round 1 end\n", _T0)
    _write_at(worker / "output.md", harness._L3_MEETS, _T0 + _LONG_NS)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"

    files = (
        key_dir / "l3-verdict.txt",
        key_dir / "l3-report.md",
        key_dir / conductor._PROVENANCE_FILENAME,
    )
    assert all(f.is_file() for f in files)
    shas = [_sha256(f) for f in files]
    mtimes = [_mtime_ns(f) for f in files]
    sha_changes = mtime_changes = 0
    for _ in range(3):
        conductor.tick(project, st)
        sha_changes += sum(1 for f, s in zip(files, shas) if _sha256(f) != s)
        mtime_changes += sum(1 for f, m in zip(files, mtimes) if _mtime_ns(f) != m)
    replay_sha_stable = sha_changes == 0
    replay_mtime_stable = mtime_changes == 0

    # IO bound on a clean terminal round (guard code only, direct call).
    io_key = tmp_path / "io" / ".agenticdoc" / "kio"
    io_worker = io_key / "workers" / "ap-kio-l3-a1"
    _write_at(io_worker / "trace.log", "round end\n", _T0)
    io_out = _write_at(io_worker / "output.md", harness._L3_MEETS, _T0)
    counts = {"stat": 0, "read": 0, "scan": 0}
    real_stat = pathlib.Path.stat
    real_read_text = pathlib.Path.read_text
    real_iterdir = pathlib.Path.iterdir
    real_glob = pathlib.Path.glob
    real_scandir = os.scandir
    prefix = str(io_key)

    def _under(path) -> bool:
        try:
            return str(pathlib.Path(path)).startswith(prefix)
        except TypeError:
            return False

    def counting_stat(self, *args, **kwargs):
        if _under(self):
            counts["stat"] += 1
        return real_stat(self, *args, **kwargs)

    def counting_read_text(self, *args, **kwargs):
        if _under(self):
            counts["read"] += 1
        return real_read_text(self, *args, **kwargs)

    def counting_scan(self, *args, **kwargs):
        if _under(self):
            counts["scan"] += 1
        return real_iterdir(self, *args, **kwargs)

    def counting_glob(self, *args, **kwargs):
        if _under(self):
            counts["scan"] += 1
        return real_glob(self, *args, **kwargs)

    def counting_scandir(path=".", *args, **kwargs):
        if _under(path):
            counts["scan"] += 1
        return real_scandir(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "stat", counting_stat)
    monkeypatch.setattr(pathlib.Path, "read_text", counting_read_text)
    monkeypatch.setattr(pathlib.Path, "iterdir", counting_scan)
    monkeypatch.setattr(pathlib.Path, "glob", counting_glob)
    monkeypatch.setattr(os, "scandir", counting_scandir)
    io_rec = conductor._l3_provenance_record(io_key, "ap-kio-l3-a1", io_out, "meets")

    mtime_stats = max(0, counts["stat"] - 1)      # minus the one anchor probe
    io_limit = (
        counts["read"] == 0 and counts["scan"] == 0
        and mtime_stats <= 2 and io_rec["suspect"] is False
    )
    ok = replay_sha_stable and replay_mtime_stable and io_limit
    print(
        f"[VERIFY] VC-020: replay_sha_stable={_b(replay_sha_stable)} "
        f"replay_mtime_stable={_b(replay_mtime_stable)} io_limit={_b(io_limit)}"
    )
    assert ok, (sha_changes, mtime_changes, counts, mtime_stats)


# ── AC-021 / VC-021 ──────────────────────────────────────────────────────────

def test_worker_status_priority_not_degraded(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker-status/availability gates keep priority over the provenance
    guard: failed -> no-verdict, no source -> no-verdict, report-only -> verdict."""
    # (a) failed status + qualified source + suspicious provenance
    p1, st1 = fallback._boot(tmp_path / "a", monkeypatch)
    t1 = fallback._dispatch_a1(p1, st1)
    kd1 = p1 / ".agenticdoc" / "k1"
    _write_at(kd1 / "workers" / t1 / "trace.log", "round 1 end\n", _T0)
    _write_at(kd1 / "workers" / t1 / "output.md", harness._L3_MEETS, _T0 + _LONG_NS)
    harness._set_row(p1, t1, "failed")
    assert conductor.tick(p1, st1) == "ok"
    failed_status = conductor._l3_round_verdict(
        p1, harness._rows(p1), "k1", 1
    )[0]
    failed_sidecar = _sidecar(kd1)

    # (b) no readable source
    p2, st2 = fallback._boot(tmp_path / "b", monkeypatch)
    t2 = fallback._dispatch_a1(p2, st2)
    harness._set_row(p2, t2, "done")
    no_source = conductor._l3_round_verdict(p2, harness._rows(p2), "k1", 1)[0]
    assert conductor.tick(p2, st2) == "ok"
    no_source_sidecar = _sidecar(p2 / ".agenticdoc" / "k1")

    # (c) only report.md qualifies
    p3, st3 = fallback._boot(tmp_path / "c", monkeypatch)
    t3 = fallback._dispatch_a1(p3, st3)
    kd3 = p3 / ".agenticdoc" / "k1"
    _write_at(kd3 / "workers" / t3 / "output.md", _UNQUALIFIED_DRAFT, _T0)
    fallback._report(p3, "k1", t3, harness._L3_MEETS)
    harness._set_row(p3, t3, "done")
    report_only = conductor._l3_round_verdict(p3, harness._rows(p3), "k1", 1)[0]

    report_only_token = (
        "verdict" if report_only in conductor._VERDICT_VALUES else report_only
    )
    ok = (
        failed_status == "no-verdict" and not failed_sidecar
        and no_source == "no-verdict" and not no_source_sidecar
        and report_only == "meets"
    )
    print(
        f"[VERIFY] VC-021: failed_status={failed_status} "
        f"no_source={no_source} report_only={report_only_token}"
    )
    assert ok, (failed_status, failed_sidecar, no_source, report_only)
