"""
test_autopilot_verdict_source_fallback.py — L3 verdict source fallback
(feature-l3-verdict-source-fallback, design §3.1; AC-001..AC-013 + AC-021).

The pre-fix ``_l3_round_verdict`` decided the L3 round verdict from
``output.md`` alone, so a reviewer whose long report lived in the
harness-first-class ``report.md`` was mis-judged ``below`` (F-3) and a
``| **FAIL** |`` cell was missed by the frozen ``\\|\\s*FAIL\\b`` regex (F-4).
This module pins the fixed contract on the *real* conductor chain:

* AC-001/AC-002: documented fallback ``output.md`` -> ``report.md`` (the
  preferred carrier never loses priority);
* AC-003/AC-004/AC-005: fail-closed — a qualifying source's FAIL is never
  whitewashed by another source's PASS, ``**FAIL**`` is detected (strict
  superset of the frozen regex), and two section-less candidates never
  fabricate artifacts;
* AC-006: the 4 + 3 + 10 change classes are reproduced on fixture-synthesized
  rounds (the real 17-round corpus is T-004's read-only script, E-3);
* AC-007/AC-008: the frozen primitives' region sha and the criteria/threshold
  face are unchanged, and the new FAIL regex is a strict superset;
* AC-009/AC-010/AC-011: the deciding source is threaded through the done
  transaction, the QG report/achieved draft and the repair prompt;
* AC-012/AC-021: the worker-status gate stays first, the availability gate
  distinguishes "no source" from "unqualified source", and
  ``report-<slug>.md`` is deliberately NOT a fallback source;
* AC-013: this module self-audits its case count / fail-closed count / AC
  coverage / absence of real-tree reads.

Fixture harness is imported from ``test_autopilot_conductor_exec`` (never
modified); the gate-free L3 chain follows ``test_autopilot_stall``. Each case
prints ``[VERIFY] VC-0NN: key=value ...`` lines (design §7).

# AC-001..AC-013, AC-021 coverage:
# AC-001 -> test_report_fallback_meets_and_pointer
# AC-002 -> test_output_priority_when_both_qualify
# AC-003 -> test_report_fail_not_whitewashed_by_output_pass
# AC-004 -> test_bold_fail_detected_and_frozen_primitive_differs
# AC-005 -> test_both_unqualified_is_below_without_fabricated_artifacts
# AC-006 -> test_change_classes_fixture_reproduce_4_plus_3
# AC-007 -> test_frozen_region_sha_and_criteria_passed
# AC-008 -> test_config_snapshot_and_fail_regex_superset
# AC-009 -> test_done_transaction_takes_deciding_source
# AC-010 -> test_done_transaction_takes_deciding_source
# AC-011 -> test_repair_prompt_references_deciding_source
# AC-012 -> test_worker_status_priority_and_availability_gate
# AC-013 -> test_ac013_self_coverage_audit
# AC-021 -> test_slug_report_is_not_a_fallback_source
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import test_autopilot_conductor_exec as harness  # noqa: E402
from autopilot import conductor, config, dispatch, roadmap  # noqa: E402

_FROZEN_CLOCK = "1970-01-01T00:00:00Z"

# T-001 left-end anchors (independent literal evidence; not imported from the
# tested module, and not read from any real project tree).
_PARSE_L3_SHA = "b0348c4fc06ac0f28bf206d217732126a1a589ba99079158f2257763f8124c98"
_MD_SECTION_SHA = "c0926b8d790f58245285a621dedd5a12c27a664af6082db76bbc4c474cb03d2b"
_FRESHNESS_FILE_SHA = "1aed6ba0abbf2f23e972dcb19b91ff9129e32c040f56cd0bb3aad2210055f7c6"

_verify = harness._verify
_b = harness.true_str

# design §3.1: the five reverse / fail-closed cases (AC-013 lower bound >= 4).
_FAIL_CLOSED_CASES = [
    "test_report_fail_not_whitewashed_by_output_pass",
    "test_bold_fail_detected_and_frozen_primitive_differs",
    "test_both_unqualified_is_below_without_fabricated_artifacts",
    "test_worker_status_priority_and_availability_gate",
    "test_slug_report_is_not_a_fallback_source",
]

# Facts collected by the self-audit case, consumed by the session finalizer.
_VERIFY_FACTS: dict[str, dict] = {}

# ── source documents (distinct per round/source, design §3.1 fixture #2) ─────

_L3_MEETS = harness._L3_MEETS
_L3_BELOW = harness._L3_BELOW

_OUTPUT_ONLY_TOKEN = "OUTPUT-ONLY-TOKEN-9f3"
_REPORT_QG_TOKEN = "REPORT-QG-TOKEN-7b1"
_REPORT_ACHIEVED_TOKEN = "REPORT-ACHIEVED-TOKEN-4c2"

# Two sections missing -> unqualified (AC-005: the file exists, the content
# does not qualify — never "file absent", which is AC-012).
_OUTPUT_ONLY = (
    "# L3 output carrier\n\n"
    f"{_OUTPUT_ONLY_TOKEN}\n\n"
    "只写了一半：没有任何两节。\n"
)
_REPORT_NO_SECTIONS = "# L3 long report\n\nno sections at all\n"

_REPORT_MEETS = _L3_MEETS + "\n<!-- src=report -->\n"
_OUTPUT_MEETS = _L3_MEETS + "\n<!-- src=output -->\n"
_REPORT_BELOW = _L3_BELOW + "\n<!-- src=report below -->\n"
_BOLD_FAIL = _L3_BELOW.replace(
    "| VC-002 | FAIL | (missing) |", "| VC-002 | **FAIL** | (missing) |"
)
_OUTPUT_BOLD_FAIL = _BOLD_FAIL + "\n<!-- bold-fail round -->\n"

# Distinct bytes prove which source the terminal l3-report.md points at
# (VC-001/VC-002) and which source the done transaction consumed (VC-010).
_REPORT_MEETS_TOKENS = (
    "# L3 Report\n\n"
    "## Quality Gate Report\n\n"
    "| VC | verdict | evidence |\n"
    "|----|---------|----------|\n"
    f"| VC-001 | PASS | evidence/runs/{_REPORT_QG_TOKEN}.md |\n"
    "\n"
    "## Achieved\n\n"
    + (
        "达成摘要：本 key 完成了全部任务书列出的交付物，验证套件全绿，"
        "证据链闭合无缺口，目标收益如 spec 所述已经落地。"
        * 3
    )
    + f"\n{_REPORT_ACHIEVED_TOKEN}\n"
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conductor, "_iso_now", lambda: _FROZEN_CLOCK)


def _sha256(path: pathlib.Path | str) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _write_worker_file(
    project: pathlib.Path, key: str, task_key: str, name: str, text: str
) -> pathlib.Path:
    path = project / ".agenticdoc" / key / "workers" / task_key / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _report(project: pathlib.Path, key: str, task_key: str, text: str) -> pathlib.Path:
    """The round-level ``report.md`` fallback carrier (never a key-level
    ``l3-report.md``, design §3.1 fixture #5)."""
    return _write_worker_file(project, key, task_key, "report.md", text)


def _output(project: pathlib.Path, key: str, task_key: str, text: str) -> None:
    harness._worker_output(project, key, task_key, text)


def _budget_one(project: pathlib.Path) -> None:
    """Terminal-ize ``below`` inside the fixture project (design §3.1 fixture
    #4): the real ``.agenticdoc/_autopilot/config.json`` is never touched."""
    cfg = config.load_config(project)
    cfg["round_budget"] = 1
    config.save_config(project, cfg)


def _boot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[pathlib.Path, conductor.ConductorState]:
    project = harness._verify_key_project(tmp_path)
    fake_advance, _calls = harness._fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    return project, harness._state(project)


def _dispatch_a1(project: pathlib.Path, st: conductor.ConductorState) -> str:
    assert conductor.tick(project, st) == "ok"
    return dispatch.task_key_for("k1", "l3-a1")


def _dossier_row(project: pathlib.Path, key: str) -> str:
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    text = conductor._closure_dossier_md(project, rm.stages[0])
    rows = [line for line in text.splitlines() if line.startswith(f"| {key} |")]
    assert rows, text
    return rows[0]


def _func_source(text: str, prefix: str) -> str:
    """Same algorithm as ``test_autopilot_verdict_freshness._func_source``
    (T-001 region-hash口径, F-P1)."""
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


def _stdout_archived() -> bool:
    """True when the run's stdout is archived: declared by the task runner
    (``MW_L3_STDOUT_ARCHIVE``) or captured/redirected rather than an
    interactive tty."""
    if os.environ.get("MW_L3_STDOUT_ARCHIVE"):
        return True
    try:
        return not sys.stdout.isatty()
    except Exception:  # noqa: BLE001 — a closed stream must not break the run
        return False


# ── AC-001 / VC-001 ──────────────────────────────────────────────────────────

def test_report_fallback_meets_and_pointer(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    task_key = _dispatch_a1(project, st)
    output_path = project / ".agenticdoc" / "k1" / "workers" / task_key / "output.md"
    _output(project, "k1", task_key, _OUTPUT_ONLY)  # present but unqualified
    report_path = _report(project, "k1", task_key, _REPORT_MEETS)
    assert _sha256(output_path) != _sha256(report_path)
    harness._set_row(project, task_key, "done")

    verdict, status, source = conductor._l3_round_verdict(
        project, harness._rows(project), "k1", 1
    )
    assert (verdict, source) == ("meets", report_path), (verdict, status, source)

    assert conductor.tick(project, st) == "ok"  # meets -> done transaction
    key_dir = project / ".agenticdoc" / "k1"
    l3_report = key_dir / "l3-report.md"
    pointer_eq_report = _sha256(l3_report) == _sha256(report_path)
    pointer_eq_output = _sha256(l3_report) == _sha256(output_path)
    ok = verdict == "meets" and pointer_eq_report and not pointer_eq_output
    _verify(
        "VC-001", verdict=verdict, source=source.name,
        pointer_eq_report=_b(pointer_eq_report),
        pointer_eq_output=_b(pointer_eq_output), ok=_b(ok),
    )
    assert ok


# ── AC-002 / VC-002 ──────────────────────────────────────────────────────────

def test_output_priority_when_both_qualify(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    task_key = _dispatch_a1(project, st)
    output_path = _write_worker_file(
        project, "k1", task_key, "output.md", _OUTPUT_MEETS
    )
    report_path = _report(project, "k1", task_key, _REPORT_MEETS)
    assert _sha256(output_path) != _sha256(report_path)
    harness._set_row(project, task_key, "done")

    verdict, _status, source = conductor._l3_round_verdict(
        project, harness._rows(project), "k1", 1
    )
    assert (verdict, source) == ("meets", output_path), (verdict, source)

    assert conductor.tick(project, st) == "ok"  # done transaction
    l3_report = project / ".agenticdoc" / "k1" / "l3-report.md"
    pointer_eq_output = _sha256(l3_report) == _sha256(output_path)
    priority_respected = pointer_eq_output and (
        _sha256(l3_report) != _sha256(report_path)
    )
    ok = verdict == "meets" and priority_respected
    _verify(
        "VC-002", verdict=verdict, source=source.name,
        pointer_eq_output=_b(pointer_eq_output),
        priority_respected=_b(priority_respected), ok=_b(ok),
    )
    assert ok


# ── AC-003 / VC-003 (reverse: no whitewash) ──────────────────────────────────

def test_report_fail_not_whitewashed_by_output_pass(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    _budget_one(project)  # terminal below on the same tick (fixture #4)
    task_key = _dispatch_a1(project, st)
    output_path = _write_worker_file(
        project, "k1", task_key, "output.md", _OUTPUT_MEETS
    )
    report_path = _report(project, "k1", task_key, _REPORT_BELOW)
    harness._set_row(project, task_key, "done")

    verdict, _status, source = conductor._l3_round_verdict(
        project, harness._rows(project), "k1", 1
    )
    assert (verdict, source) == ("below", report_path), (verdict, source)

    assert conductor.tick(project, st) == "ok"  # persist below(report) + stall
    key_dir = project / ".agenticdoc" / "k1"
    l3_report = key_dir / "l3-report.md"
    pointer_eq_report = l3_report.is_file() and (
        _sha256(l3_report) == _sha256(report_path)
    )
    whitewash = (
        l3_report.is_file() and _sha256(l3_report) == _sha256(output_path)
    )
    dossier_below = "| below |" in _dossier_row(project, "k1")
    ok = verdict == "below" and pointer_eq_report and not whitewash and dossier_below
    _verify(
        "VC-003", verdict=verdict, source=source.name,
        pointer_eq_report=_b(pointer_eq_report), dossier_below=_b(dossier_below),
        whitewash=_b(whitewash), ok=_b(ok),
    )
    assert ok


# ── AC-004 / VC-004 (reverse: bold FAIL not missed) ──────────────────────────

def test_bold_fail_detected_and_frozen_primitive_differs(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)
    task_key = dispatch.task_key_for("k1", "l3-a1")
    output_path = _write_worker_file(
        project, "k1", task_key, "output.md", _OUTPUT_BOLD_FAIL
    )
    assert not (project / ".agenticdoc" / "k1" / "workers" / task_key / "report.md").exists()

    verdict, _status, source = conductor._l3_round_verdict(
        project, harness._rows(project), "k1", 1
    )
    frozen_parse = conductor._parse_l3_output(project, "k1", 1)
    qg = conductor._md_section(
        output_path.read_text(encoding="utf-8"), "## Quality Gate Report"
    )
    new_re_hit = bool(conductor._L3_FAIL_RE.search(qg or ""))
    old_re_hit = bool(re.search(r"\|\s*FAIL\b", qg or ""))
    ok = (
        verdict == "below"
        and source == output_path
        and frozen_parse == "meets"
        and new_re_hit
        and not old_re_hit
    )
    _verify(
        "VC-004", new_verdict=verdict, frozen_parse=frozen_parse,
        new_re_hit=_b(new_re_hit), old_re_hit=_b(old_re_hit), ok=_b(ok),
    )
    assert ok


# ── AC-005 / VC-005 (reverse: no fabricated artifacts) ───────────────────────

def test_both_unqualified_is_below_without_fabricated_artifacts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    _budget_one(project)
    task_key = _dispatch_a1(project, st)
    # F-P11: AC-005 is "both files EXIST but neither qualifies" (AC-012 owns
    # "both files absent").
    _output(project, "k1", task_key, _OUTPUT_ONLY)
    _report(project, "k1", task_key, _REPORT_NO_SECTIONS)
    harness._set_row(project, task_key, "done")

    verdict, _status, source = conductor._l3_round_verdict(
        project, harness._rows(project), "k1", 1
    )
    assert verdict == "below" and source is None, (verdict, source)

    assert conductor.tick(project, st) == "ok"  # persist below(None) + stall
    key_dir = project / ".agenticdoc" / "k1"
    l3_report_created = (key_dir / "l3-report.md").exists()
    evidence_dir = key_dir / "evidence"
    qg_reports = len(list(evidence_dir.glob("quality-gate-report-*.md"))) if (
        evidence_dir.is_dir()
    ) else 0
    pm_state = key_dir / "pm-state.md"
    pass_lines = (
        sum(1 for line in pm_state.read_text(encoding="utf-8").splitlines() if "PASS" in line)
        if pm_state.is_file() else 0
    )
    verdict_text = (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip()
    ok = (
        verdict == "below"
        and source is None
        and not l3_report_created
        and qg_reports == 0
        and pass_lines == 0
        and verdict_text == "below"
    )
    _verify(
        "VC-005", verdict=verdict, source="none",
        l3_report_created=_b(l3_report_created), qg_reports=qg_reports,
        pass_lines=pass_lines, ok=_b(ok),
    )
    assert ok


# ── AC-006 / VC-006 (fixture-synthesized 4 + 3 change classes) ───────────────

def test_change_classes_fixture_reproduce_4_plus_3(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fixture-only reproduction of the classification semantics (E-3): the
    real 17-round corpus recompute is T-004's read-only script. 17 synthetic
    rounds: 4 unqualified-output / qualifying-report (below->meets),
    3 ``| **FAIL** |`` rounds (meets->below), 10 unchanged."""
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)

    rounds: list[tuple[int, str, str | None]] = []
    index = 0
    for i in range(4):  # 4 x below -> meets (the fallback supplies the source)
        index += 1
        rounds.append(
            (index, _OUTPUT_ONLY + f"\n<!-- out {index} -->\n",
             _REPORT_MEETS + f"\n<!-- rpt {index} -->\n")
        )
    for i in range(3):  # 3 x meets -> below (old regex missed the bold cell)
        index += 1
        rounds.append((index, _OUTPUT_BOLD_FAIL + f"\n<!-- bold {index} -->\n", None))
    for i in range(5):  # 5 x unchanged meets
        index += 1
        rounds.append(
            (index, _L3_MEETS + f"\n<!-- o {index} -->\n",
             _L3_MEETS + f"\n<!-- r {index} -->\n")
        )
    for i in range(5):  # 5 x unchanged below
        index += 1
        rounds.append(
            (index, _OUTPUT_ONLY + f"\n<!-- o {index} -->\n",
             _REPORT_NO_SECTIONS + f"\n<!-- r {index} -->\n")
        )
    assert index == 17

    below_to_meets = meets_to_below = unchanged = false_meets = 0
    for number, out_text, rpt_text in rounds:
        task_key = dispatch.task_key_for("k1", f"l3-a{number}")
        _write_worker_file(project, "k1", task_key, "output.md", out_text)
        if rpt_text is not None:
            _report(project, "k1", task_key, rpt_text)
        legacy = conductor._parse_l3_output(project, "k1", number)
        rows = [{"task_key": task_key, "status": "done"}]
        candidate, _status, _src = conductor._l3_round_verdict(
            project, rows, "k1", number
        )
        if legacy == "below" and candidate == "meets":
            below_to_meets += 1
        elif legacy == "meets" and candidate == "below":
            meets_to_below += 1
        else:
            assert legacy == candidate, (number, legacy, candidate)
            unchanged += 1
        sources = [
            (path, text)
            for path, text in (
                (project / ".agenticdoc" / "k1" / "workers" / task_key / "output.md",
                 out_text),
                ((project / ".agenticdoc" / "k1" / "workers" / task_key / "report.md"),
                 rpt_text),
            )
            if text is not None
        ]
        if candidate == "meets" and any(
            conductor._l3_qualifies(text)
            and conductor._L3_FAIL_RE.search(
                conductor._md_section(text, "## Quality Gate Report") or ""
            )
            for _path, text in sources
        ):
            false_meets += 1

    ok = (
        below_to_meets == 4
        and meets_to_below == 3
        and unchanged == 10
        and false_meets == 0
    )
    _verify(
        "VC-006", scope="fixture", rounds=len(rounds),
        below_to_meets=below_to_meets, meets_to_below=meets_to_below,
        unchanged=unchanged, false_meets=false_meets, ok=_b(ok),
    )
    assert ok


# ── AC-007 / VC-007 (frozen anchors + criteria node) ─────────────────────────

def test_frozen_region_sha_and_criteria_passed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)
    task_key = dispatch.task_key_for("k1", "l3-a1")
    rules = 0
    # 1. missing "## Quality Gate Report" => below
    _write_worker_file(project, "k1", task_key, "output.md", "# L3\n\n## Achieved\n\nok\n")
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "below")
    # 2. missing "## Achieved" => below
    _write_worker_file(
        project, "k1", task_key, "output.md",
        "# L3\n\n## Quality Gate Report\n\n| VC | verdict |\n|----|----|\n| VC-1 | PASS |\n",
    )
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "below")
    # 3. a plain "| FAIL" row inside the QG section => below
    _write_worker_file(
        project, "k1", task_key, "output.md",
        "# L3\n\n## Quality Gate Report\n\n| VC | verdict |\n|----|----|\n"
        "| VC-1 | FAIL |\n\n## Achieved\n\nok\n",
    )
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "below")
    # 4. otherwise meets
    _write_worker_file(project, "k1", task_key, "output.md", _L3_MEETS)
    rules += int(conductor._parse_l3_output(project, "k1", 1) == "meets")

    parse_sha = _conductor_region_sha("def _parse_l3_output(")
    md_sha = _conductor_region_sha("def _md_section(")
    freshness = pathlib.Path(conductor.__file__).resolve().parents[1] / (
        "test_autopilot_verdict_freshness.py"
    )
    parse_ok = parse_sha == _PARSE_L3_SHA
    md_ok = md_sha == _MD_SECTION_SHA
    freshness_ok = _sha256(freshness) == _FRESHNESS_FILE_SHA
    # the frozen-node criterion is recomputed, not hardcoded
    node = (
        "test_autopilot_verdict_freshness.py::"
        "test_l3_criteria_behavior_unchanged"
    )
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", node, "-q",
         "-p", "no:cacheprovider"],
        cwd=str(freshness.parent), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    criteria_test_passed = proc.returncode == 0
    ok = rules == 4 and parse_ok and md_ok and freshness_ok and criteria_test_passed
    _verify(
        "VC-007", parse_sha_unchanged=_b(parse_ok),
        md_section_sha_unchanged=_b(md_ok),
        freshness_file_unchanged=_b(freshness_ok),
        criteria_test_passed=_b(criteria_test_passed), ok=_b(ok),
    )
    assert ok


# ── AC-008 / VC-008 (fixture thresholds + strict-superset regex) ─────────────

def test_config_snapshot_and_fail_regex_superset(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project = harness._verify_key_project(tmp_path)
    cfg_path = config.config_path(project)
    before = cfg_path.read_bytes()
    task_key = dispatch.task_key_for("k1", "l3-a1")
    _write_worker_file(
        project, "k1", task_key, "output.md",
        "# L3\n\n## Quality Gate Report\n\n| VC | verdict |\n|----|----|\n| VC-1 | PASS |\n",
    )
    verdict, _status, _source = conductor._l3_round_verdict(project, [], "k1", 1)
    missing_section_below = verdict == "below"

    # strict-superset probe on fixture-synthesized QG sections: every old hit
    # must be a new hit (old_only=0), and the bold form adds 4 new hits.
    samples = [
        "| VC | verdict |\n|----|----|\n| VC-1 | FAIL |\n",
        "| VC | verdict |\n|----|----|\n| VC-1 | **FAIL** |\n",
        "| VC | verdict |\n|----|----|\n| VC-1 |  **FAIL**  |\n",
        "| VC | verdict |\n|----|----|\n| VC-1 |**FAIL**|\n",
        "| VC | verdict |\n|----|----|\n| VC-1 | *FAIL* |\n",
        "| VC | verdict |\n|----|----|\n| VC-1 | PASS |\n",
        "| VC | verdict |\n|----|----|\n| VC-1 | FAILED |\n",
    ]
    old_re = re.compile(r"\|\s*FAIL\b")
    old_hits = {i for i, text in enumerate(samples) if old_re.search(text)}
    new_hits = {i for i, text in enumerate(samples) if conductor._L3_FAIL_RE.search(text)}
    old_only = len(old_hits - new_hits)
    new_only = len(new_hits - old_hits)
    superset = old_hits <= new_hits

    after = cfg_path.read_bytes()
    config_unchanged = before == after
    ok = (
        config_unchanged and missing_section_below and old_only == 0
        and new_only == 4 and superset
    )
    _verify(
        "VC-008", scope="fixture", config_unchanged=_b(config_unchanged),
        missing_section_below=_b(missing_section_below), old_only=old_only,
        new_only=new_only, superset=_b(superset), ok=_b(ok),
    )
    assert ok


# ── AC-009 / AC-010 / VC-009 / VC-010 (deciding source threads through) ──────

def test_done_transaction_takes_deciding_source(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    task_key = _dispatch_a1(project, st)
    _output(project, "k1", task_key, _OUTPUT_ONLY)
    report_path = _report(project, "k1", task_key, _REPORT_MEETS_TOKENS)
    harness._set_row(project, task_key, "done")

    seen: dict[str, object] = {}
    real_done = conductor._done_transaction

    def spy(project_root, state_obj, key, l3_output):
        result = real_done(project_root, state_obj, key, l3_output)
        seen["ret"] = result
        seen["src"] = pathlib.Path(l3_output)
        return result

    monkeypatch.setattr(conductor, "_done_transaction", spy)
    assert conductor.tick(project, st) == "ok"  # meets -> done transaction
    for _ in range(3):  # mark key done + closure dossier
        assert conductor.tick(project, st) == "ok"

    key_dir = project / ".agenticdoc" / "k1"
    l3_report = key_dir / "l3-report.md"
    dossier = _dossier_row(project, "k1")
    dossier_verdict = "meets" if "| meets |" in dossier else dossier
    report_bytes_eq_source = (
        l3_report.is_file() and _sha256(l3_report) == _sha256(report_path)
    )
    ok9 = (
        dossier_verdict == "meets"
        and "l3-report.md" in dossier
        and report_bytes_eq_source
    )
    _verify(
        "VC-009", dossier_verdict=dossier_verdict, dossier_report="l3-report.md",
        report_bytes_eq_source=_b(report_bytes_eq_source), ok=_b(ok9),
    )
    assert ok9

    transaction_non_below = seen.get("ret") not in (None, "below")
    qg_files = list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    assert len(qg_files) == 1, qg_files
    qg_text = qg_files[0].read_text(encoding="utf-8")
    qg_from_report = (
        _REPORT_QG_TOKEN in qg_text and "report.md" in qg_text
    )
    achieved_text = (key_dir / "achieved.md").read_text(encoding="utf-8")
    achieved_from_report = _REPORT_ACHIEVED_TOKEN in achieved_text
    output_only_text_absent = (
        _OUTPUT_ONLY_TOKEN not in qg_text and _OUTPUT_ONLY_TOKEN not in achieved_text
    )
    ok10 = (
        bool(transaction_non_below) and qg_from_report
        and achieved_from_report and output_only_text_absent
    )
    _verify(
        "VC-010", transaction_non_below=_b(bool(transaction_non_below)),
        qg_from_report=_b(qg_from_report),
        achieved_from_report=_b(achieved_from_report),
        output_only_text_absent=_b(output_only_text_absent), ok=_b(ok10),
    )
    assert ok10


# ── AC-011 / VC-011 (repair prompt points at the deciding source) ────────────

def test_repair_prompt_references_deciding_source(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)

    def _drive(case_dir: pathlib.Path, output_text: str, report_text: str | None) -> str:
        project, st = _boot(case_dir, monkeypatch)
        task_key = _dispatch_a1(project, st)
        _output(project, "k1", task_key, output_text)
        if report_text is not None:
            _report(project, "k1", task_key, report_text)
        harness._set_row(project, task_key, "done")
        assert conductor.tick(project, st) == "ok"  # below -> repair-a1
        repair_md = (
            project / ".agenticdoc" / "k1" / "workers" / "ap-k1-repair-a1" / "task.md"
        )
        assert repair_md.is_file(), "repair round not dispatched"
        return repair_md.read_text(encoding="utf-8")

    def _report_line(md: str) -> str:
        lines = [l for l in md.splitlines() if l.startswith("- L3 报告：")]
        assert lines, md
        return lines[0]

    report_case = _report_line(
        _drive(tmp_path / "report_case", _OUTPUT_ONLY, _REPORT_BELOW)
    )
    report_case_ref = "report.md" in report_case and "output.md" not in report_case
    output_case = _report_line(
        _drive(tmp_path / "output_case", _L3_BELOW + "\n<!-- round -->\n", None)
    )
    output_case_ref = "output.md" in output_case and "report.md" not in output_case
    ok = report_case_ref and output_case_ref
    _verify(
        "VC-011", report_case_ref=_b(report_case_ref),
        output_case_ref=_b(output_case_ref), ok=_b(ok),
    )
    assert ok


# ── AC-012 / VC-012 (reverse: status gate + availability gate) ───────────────

def test_worker_status_priority_and_availability_gate(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    task_key = _dispatch_a1(project, st)
    report_path = _report(project, "k1", task_key, _REPORT_MEETS)

    harness._set_row(project, task_key, "failed")
    v1 = conductor._l3_round_verdict(project, harness._rows(project), "k1", 1)
    failed_status_no_verdict = v1[0] == "no-verdict" and v1[2] is None
    assert failed_status_no_verdict  # a qualifying report is never read

    # a crashed reviewer is re-reviewed, never repaired against its report
    assert conductor.tick(project, st) == "ok"
    no_repair_on_failed = not (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-repair-a1"
    ).exists()
    assert no_repair_on_failed

    # availability gate: nothing readable -> no-verdict (AC-012, not AC-005)
    harness._set_row(project, task_key, "done")
    report_path.unlink()
    output_path = project / ".agenticdoc" / "k1" / "workers" / task_key / "output.md"
    assert not output_path.exists()
    v2 = conductor._l3_round_verdict(project, harness._rows(project), "k1", 1)
    both_absent_no_verdict = v2[0] == "no-verdict" and v2[2] is None
    assert both_absent_no_verdict

    # healthy status + only report.md qualifies -> meets from report.md
    _report(project, "k1", task_key, _REPORT_MEETS)
    v3 = conductor._l3_round_verdict(project, harness._rows(project), "k1", 1)
    report_only_meets = (
        v3[0] == "meets" and v3[2] is not None and v3[2].name == "report.md"
    )
    assert report_only_meets

    ok = (
        failed_status_no_verdict and no_repair_on_failed
        and both_absent_no_verdict and report_only_meets
    )
    _verify(
        "VC-012", failed_status_no_verdict=_b(failed_status_no_verdict),
        both_absent_no_verdict=_b(both_absent_no_verdict),
        report_only_meets=_b(report_only_meets), ok=_b(ok),
    )
    assert ok


# ── AC-021 / VC-021 (reverse: slug report is not a fallback source) ──────────

def test_slug_report_is_not_a_fallback_source(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    _budget_one(project)
    task_key = _dispatch_a1(project, st)
    _output(project, "k1", task_key, _OUTPUT_ONLY)
    slug = _write_worker_file(
        project, "k1", task_key, "report-f1.md", _REPORT_MEETS
    )  # qualifies, but the name is not in the fallback scope
    assert conductor._l3_qualifies(slug.read_text(encoding="utf-8"))
    harness._set_row(project, task_key, "done")

    verdict, _status, source = conductor._l3_round_verdict(
        project, harness._rows(project), "k1", 1
    )
    assert verdict == "below" and source is None, (verdict, source)

    assert conductor.tick(project, st) == "ok"  # persist below(None) + stall
    key_dir = project / ".agenticdoc" / "k1"
    slug_reports_used = int((key_dir / "l3-report.md").exists())
    source_order_ok = conductor._L3_SOURCE_ORDER == ("output.md", "report.md")
    ok = verdict == "below" and slug_reports_used == 0 and source_order_ok
    _verify(
        "VC-021", verdict=verdict, slug_reports_used=slug_reports_used,
        source_order_ok=_b(source_order_ok), ok=_b(ok),
    )
    assert ok


# ── AC-020 / VC-020 (zero write with the report source) ──────────────────────

def test_zero_write_with_report_source(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    _budget_one(project)
    task_key = _dispatch_a1(project, st)
    _output(project, "k1", task_key, _OUTPUT_ONLY)
    report_path = _report(project, "k1", task_key, _REPORT_BELOW)
    harness._set_row(project, task_key, "done")
    assert conductor.tick(project, st) == "ok"  # below(report) + stall

    key_dir = project / ".agenticdoc" / "k1"
    verdict_file = key_dir / "l3-verdict.txt"
    report_file = key_dir / "l3-report.md"
    assert verdict_file.read_text(encoding="utf-8").strip() == "below"
    assert _sha256(report_file) == _sha256(report_path)

    verdict_sha = _sha256(verdict_file)
    verdict_mtime = verdict_file.stat().st_mtime_ns
    report_sha = _sha256(report_file)
    ticks = 3
    verdict_sha_changes = verdict_mtime_changes = report_sha_changes = 0
    for _ in range(ticks):
        assert conductor.tick(project, st) == "ok"
        verdict_sha_changes += int(_sha256(verdict_file) != verdict_sha)
        verdict_mtime_changes += int(verdict_file.stat().st_mtime_ns != verdict_mtime)
        report_sha_changes += int(_sha256(report_file) != report_sha)

    direct_repeat_writes = 0
    for _ in range(2):
        before = (verdict_file.stat().st_mtime_ns, report_file.stat().st_mtime_ns)
        conductor._persist_l3_verdict(key_dir, "below", report_path, st=None)
        after = (verdict_file.stat().st_mtime_ns, report_file.stat().st_mtime_ns)
        direct_repeat_writes += int(before != after)

    ok = not any((
        verdict_sha_changes, verdict_mtime_changes, report_sha_changes,
        direct_repeat_writes,
    ))
    _verify(
        "VC-020", ticks=ticks, verdict_sha_changes=verdict_sha_changes,
        verdict_mtime_changes=verdict_mtime_changes,
        report_sha_changes=report_sha_changes,
        direct_repeat_writes=direct_repeat_writes, ok=_b(ok),
    )
    assert ok


# ── AC-019 / VC-019 (reviewer prompt documents the fallback) ─────────────────

def test_reviewer_prompt_documents_fallback(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze_clock(monkeypatch)
    project, st = _boot(tmp_path, monkeypatch)
    task_key = _dispatch_a1(project, st)
    prompt = conductor._l3_prompt("k1", 1)
    task_md = (
        project / ".agenticdoc" / "k1" / "workers" / task_key / "task.md"
    ).read_text(encoding="utf-8")

    fallback_documented = (
        "report.md" in prompt and "回退源" in prompt and "report.md" in task_md
    )
    output_preferred = "output.md" in prompt and "首选" in prompt
    both_sections_named = (
        "## Quality Gate Report" in prompt and "## Achieved" in prompt
    )
    fail_to_below_kept = "FAIL" in prompt and "below" in prompt
    ok = (
        fallback_documented and output_preferred
        and both_sections_named and fail_to_below_kept
    )
    _verify(
        "VC-019", fallback_documented=_b(fallback_documented),
        output_preferred=_b(output_preferred),
        both_sections_named=_b(both_sections_named),
        fail_to_below_kept=_b(fail_to_below_kept), ok=_b(ok),
    )
    assert ok


# ── AC-013 / VC-013 (self coverage audit) ────────────────────────────────────

def test_ac013_self_coverage_audit(request: pytest.FixtureRequest) -> None:
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    new_tests = re.findall(r"^def (test_\w+)\(", source, flags=re.MULTILINE)
    coverage = dict(re.findall(r"^# (AC-0\d+) -> (test_\w+)$", source, flags=re.MULTILINE))
    expected_ac = [f"AC-{n:03d}" for n in range(1, 14)] + ["AC-021"]
    fail_closed = [name for name in _FAIL_CLOSED_CASES if name in new_tests]
    collected = {item.name for item in request.session.items if item.module is sys.modules[__name__]}
    # real-tree needles assembled so this very source never contains them.
    needles = ["H:" + "/git/E2Feature", "H:" + "\\git\\E2Feature", "_e2feature" + "_root"]
    real_tree_deps = sum(source.count(needle) for needle in needles)

    assert len(new_tests) == 15, new_tests
    assert set(coverage) == set(expected_ac), sorted(coverage)
    assert all(name in new_tests for name in coverage.values()), coverage
    assert len(fail_closed) == 5, fail_closed
    assert real_tree_deps == 0, needles
    assert set(new_tests) <= collected, sorted(set(new_tests) - collected)  # node ids

    _VERIFY_FACTS["facts"] = {
        "new_tests": len(new_tests),
        "ac_covered": len(coverage),
        "fail_closed_cases": len(fail_closed),
        "real_tree_deps": real_tree_deps,
    }


@pytest.fixture(scope="session", autouse=True)
def _emit_vc013_after_session(request: pytest.Session) -> None:
    """Emit VC-013 once the whole session is over, with the REAL session
    failure count (``request.session.testsfailed``) — never hardcoded. Emitted
    only when the self-audit facts were collected; a missing line makes the
    task runner fail closed."""
    yield
    facts = _VERIFY_FACTS.get("facts")
    if not facts:
        return
    stdout_archived = _stdout_archived()
    failed = request.session.testsfailed
    ok = (
        failed == 0 and facts["new_tests"] == 15
        and facts["fail_closed_cases"] == 5 and facts["ac_covered"] == 14
        and facts["real_tree_deps"] == 0
    )
    _verify(
        "VC-013", new_tests=facts["new_tests"], failed=failed,
        fail_closed_cases=facts["fail_closed_cases"],
        ac_covered=facts["ac_covered"], real_tree_deps=facts["real_tree_deps"],
        self_audit="true", stdout_archived=_b(stdout_archived), ok=_b(ok),
    )
