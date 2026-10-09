"""test_doctor_gates.py — doctor gate segment + `mw autopilot gates` (T-13).

Key mw-autopilot-slot-capacity, AC-006 / AC-012 / AC-019 / AC-031,
VC-007 / VC-014 / VC-024 / VC-049. Covers:

* the segment shape (design D6 §D4.1) and its read-only discipline;
* alerts I1-I6 with their fix strings and issue/suggestion levels;
* the I7 zero-perturbation rule (no `gates:` text line on a healthy project)
  and I8 (answered-only queue is JSON-only information);
* `missing_fields` restricted to PENDING schema-2 gates (G-D6-1: the 34
  historical answered gates must not flood the surface);
* the AC-031 roadmap visibility (`validate_roadmap` is called by the doctor);
* the `mw autopilot gates [--json]` CLI (layer-B 13-line cards + machine JSON).

Non-vacuous counterfactuals live here too: (a) a corrupt gate fires I1 and the
doctor exit code becomes 1; (b) a fully healthy project keeps `healthy=true`
with NO `gates:` line; (c) a directory snapshot before/after running the doctor
is identical (creating anything goes red); (d) an invalid/old-format roadmap
surfaces a validation problem.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import mw_common  # noqa: E402


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real ~/.agents/autopilot-defaults.json may leak into these cases."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


def _gates_dir(project: pathlib.Path) -> pathlib.Path:
    return project / ".agenticdoc" / "_autopilot" / "gates"


def _gate_text(
    gate_id: str,
    *,
    kind: str = "stage-confirm",
    status: str = "pending",
    created_at: str | None = None,
    stage: int | None = 1,
    key: str | None = None,
    question: str = "proceed?",
    schema: int = 2,
    extra: dict[str, str] | None = None,
) -> str:
    """A minimal, parser-valid gate file (frontmatter + body)."""
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "---",
        f"id: {gate_id}",
        f"gate_schema: {schema}",
        f"kind: {kind}",
        f"stage: {'' if stage is None else stage}",
        f"key: {key or ''}",
        f"created_at: {created_at}",
        "created_by: conductor",
        f"question: {question}",
        "context_refs: []",
        f"status: {status}",
    ]
    extras = dict(extra or {})
    for placeholder in ("answered_at", "answered_by", "note"):
        if placeholder not in extras:
            lines.append(f"{placeholder}:")
    for name, value in extras.items():
        lines.append(f"{name}: {value}")
    lines += ["---", "", f"# Gate {gate_id}", ""]
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


def _write_roadmap(project: pathlib.Path, text: str) -> pathlib.Path:
    path = project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _snapshot(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def _make_service_running(project: pathlib.Path) -> None:
    """Doctor's service check reads `.mw/mw.pid`; a live PID removes the
    'service not running' issue so the gate alerts are the only variable."""
    (project / ".mw").mkdir(parents=True, exist_ok=True)
    mw_common.pid_file(project).write_text(str(os.getpid()), encoding="utf-8")


def _report(project: pathlib.Path) -> dict:
    return mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))


def _doctor_args(project: pathlib.Path, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), providers=None, fix=False, json=as_json, stale_after=90,
    )


VALID_ROADMAP = """# Roadmap

## Stage 1: foundation
> goal: deliver the python infrastructure modules
> status: running
> key-status: k1=done, k2=running
### Keys
| key | role | depends_on |
|-----|------|-----------|
| k1 | parser | - |
| k2 | validator | k1 |
"""


# ── segment shape + read-only discipline ─────────────────────────────────────


SEGMENT_KEYS = (
    "dir",
    "exists",
    "total",
    "pending_count",
    "schema_versions",
    "parse_errors",
    "pending",
    "missing_fields",
    "drift",
    "replayed",
    "error",
)


def test_segment_present_and_read_only(tmp_path: pathlib.Path) -> None:
    before = _snapshot(tmp_path)
    report = _report(tmp_path)
    section = report["gates"]
    for key in SEGMENT_KEYS:
        assert key in section, key
    assert section["exists"] is False
    assert section["total"] == 0
    assert section["pending_count"] == 0
    assert section["error"] is None
    assert report["gates"]["roadmap_validation"]["exists"] is False
    read_only = _snapshot(tmp_path) == before
    assert read_only
    assert not (tmp_path / ".mw").exists()
    _verify("VC-014", segment_keys=len(SEGMENT_KEYS), read_only=read_only)


def test_schema_versions_and_pending_counts(tmp_path: pathlib.Path) -> None:
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_gate(
        tmp_path, "gate-0002",
        _gate_text("gate-0002", schema=1, status="approved",
                   extra={"answered_at": _iso_ago(1), "answered_by": "human"}),
    )
    section = _report(tmp_path)["gates"]
    assert section["total"] == 2
    assert section["pending_count"] == 1
    assert section["schema_versions"] == {"1": 1, "2": 1}
    assert [e["id"] for e in section["pending"]] == ["gate-0001"]


# ── I1 parse error (counterfactual a) ────────────────────────────────────────


def test_i1_parse_error_issue_fix_string_and_exit_code(tmp_path: pathlib.Path, capsys) -> None:
    _make_service_running(tmp_path)
    # Required fields removed: `created_by`, `kind`, `created_at`, `question`.
    _write_gate(tmp_path, "gate-0099", "---\nid: gate-0099\nstatus: pending\n---\n")
    report = _report(tmp_path)
    assert len(report["gates"]["parse_errors"]) == 1
    err = report["gates"]["parse_errors"][0]
    assert "gate-0099" in err["path"]
    issues = report["summary"]["issues"]
    assert any("fix the frontmatter" in i for i in issues)
    assert report["summary"]["healthy"] is False
    text = mw_common.format_doctor_text(report)
    assert "gates:" in text
    assert "1 parse error(s)" in text
    # The exit code is driven by summary.healthy (mw.py cmd_doctor).
    rc = mw.cmd_doctor(_doctor_args(tmp_path))
    out = capsys.readouterr().out
    assert rc == 1
    assert "fix the frontmatter" in out
    _verify(
        "VC-024",
        parse_error_issue=bool(report["gates"]["parse_errors"]),
        fix_hint="fix the frontmatter",
        exit_code=rc,
    )


def test_i1_issue_absent_when_no_parse_errors(tmp_path: pathlib.Path) -> None:
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    report = _report(tmp_path)
    assert report["gates"]["parse_errors"] == []
    assert not any("fix the frontmatter" in i for i in report["summary"]["issues"])


# ── I2 missing expires_at/default_action (AC-019) ────────────────────────────


def test_i2_missing_default_action_is_an_issue(tmp_path: pathlib.Path) -> None:
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text("gate-0001", extra={"reason_code": "stage:all-keys-terminal"}),
    )
    section = _report(tmp_path)["gates"]
    assert section["missing_fields"] == [
        {"id": "gate-0001", "fields": ["expires_at", "default_action"]}
    ]
    issues = _report(tmp_path)["summary"]["issues"]
    match = [i for i in issues if "no expires_at/default_action" in i]
    assert len(match) == 1
    assert "AC-019" in match[0]
    _verify(
        "VC-024",
        alert="no expires_at/default_action",
        ac_019=any("AC-019" in issue for issue in issues),
    )


def test_i2_silent_when_both_declared(tmp_path: pathlib.Path) -> None:
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            extra={
                "reason_code": "stage:all-keys-terminal",
                "expires_at": _iso_ago(-24),
                "default_action": "escalate-to-human",
            },
        ),
    )
    report = _report(tmp_path)
    assert report["gates"]["missing_fields"] == []
    assert not any("no expires_at/default_action" in i for i in report["summary"]["issues"])
    assert "gates:" not in mw_common.format_doctor_text(report)


# ── I3 overdue gates ─────────────────────────────────────────────────────────


def test_i3_overdue_24h_is_a_suggestion(tmp_path: pathlib.Path) -> None:
    _make_service_running(tmp_path)
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            created_at=_iso_ago(30),
            extra={
                "reason_code": "stage:all-keys-terminal",
                "expires_at": _iso_ago(-1),
                "default_action": "escalate-to-human",
            },
        ),
    )
    report = _report(tmp_path)
    suggestions = report["summary"]["suggestions"]
    assert any("gate-0001 pending" in s and "to review" in s for s in suggestions)
    assert not any("gate-0001 pending" in i for i in report["summary"]["issues"])
    assert report["summary"]["healthy"] is True  # suggestion never flips healthy
    assert "gates:" in mw_common.format_doctor_text(report)


def test_i3_overdue_72h_escalates_to_issue(tmp_path: pathlib.Path) -> None:
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            created_at=_iso_ago(100),
            extra={
                "reason_code": "stage:all-keys-terminal",
                "expires_at": _iso_ago(-1),
                "default_action": "escalate-to-human",
            },
        ),
    )
    issues = _report(tmp_path)["summary"]["issues"]
    assert any("gate-0001 pending 100h" in i for i in issues)


# ── I4 drift ─────────────────────────────────────────────────────────────────


def test_i4_evidence_drift_is_a_suggestion(tmp_path: pathlib.Path) -> None:
    evidence = tmp_path / ".agenticdoc" / "k1" / "l3-verdict.txt"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("meets\n", encoding="utf-8")  # mtime = now
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            created_at=_iso_ago(2),
            extra={
                "reason_code": "l3-below",
                "expires_at": _iso_ago(-1),
                "default_action": "escalate-to-human",
                "evidence_refs": '\'["l3-verdict:k1/l3-verdict.txt"]\'',
            },
        ),
    )
    section = _report(tmp_path)["gates"]
    assert section["drift"] and section["drift"][0]["id"] == "gate-0001"
    assert section["pending"][0]["drift_detail"]
    suggestions = _report(tmp_path)["summary"]["suggestions"]
    assert any("re-derive the evidence" in s for s in suggestions)


def test_i4_no_drift_when_evidence_older_than_gate(tmp_path: pathlib.Path) -> None:
    evidence = tmp_path / ".agenticdoc" / "k1" / "l3-verdict.txt"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("meets\n", encoding="utf-8")
    old = datetime.datetime.now(datetime.timezone.utc).timestamp() - 7200
    os.utime(evidence, (old, old))
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            created_at=_iso_ago(0.1),
            extra={"evidence_refs": '\'["l3-verdict:k1/l3-verdict.txt"]\''},
        ),
    )
    section = _report(tmp_path)["gates"]
    assert section["drift"] == []


# ── I5 replay ────────────────────────────────────────────────────────────────


def test_i5_replayed_gate_is_an_issue(tmp_path: pathlib.Path) -> None:
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text("gate-0001", kind="stage-close", status="approved",
                   extra={"answered_at": _iso_ago(5), "answered_by": "human"}),
    )
    _write_gate(tmp_path, "gate-0002", _gate_text("gate-0002", kind="stage-close"))
    section = _report(tmp_path)["gates"]
    assert section["replayed"] == [
        {"id": "gate-0002", "prior_gate": "gate-0001", "kind": "stage-close", "scope": "stage=1"}
    ]
    issues = _report(tmp_path)["summary"]["issues"]
    assert any("check gate consumption" in i for i in issues)
    _verify(
        "VC-007",
        replay_prior=section["replayed"][0]["prior_gate"],
        replay_issue=bool(section["replayed"]),
    )


def test_i5_no_replay_across_keys(tmp_path: pathlib.Path) -> None:
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text("gate-0001", kind="stalled", status="approved", stage=None, key="k1",
                   extra={"answered_at": _iso_ago(5), "answered_by": "human"}),
    )
    _write_gate(tmp_path, "gate-0002",
                _gate_text("gate-0002", kind="stalled", stage=None, key="k2"))
    assert _report(tmp_path)["gates"]["replayed"] == []


# ── I6 schema-2 pending missing decision fields ──────────────────────────────


def test_i6_schema2_missing_reason_code_is_a_suggestion(tmp_path: pathlib.Path) -> None:
    # T-20: `reason_code` is required only for `stalled` (the 12 mark_stalled
    # call sites); this fixture must therefore use a stalled gate.
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            kind="stalled",
            stage=None,
            key="k1",
            extra={"expires_at": _iso_ago(-1), "default_action": "escalate-to-human"},
        ),
    )
    section = _report(tmp_path)["gates"]
    assert section["missing_fields"] == [{"id": "gate-0001", "fields": ["reason_code"]}]
    suggestions = _report(tmp_path)["summary"]["suggestions"]
    assert any("is schema 2 but missing reason_code" in s for s in suggestions)


# Human-decision kinds (plus the budget predicate that does not use
# `reason_code`): the T-13 all-kinds rule reported a spurious missing field for
# each of these (T-20 false positives).
_REASON_CODE_FREE_KINDS = (
    "stage-confirm",
    "stage-close",
    "goal-change",
    "budget-exhausted",
    "xkey-authorize",
)


def test_reason_code_not_required_for_human_decision_kinds(tmp_path: pathlib.Path) -> None:
    """T-20 / VC-024: only `stalled` requires `reason_code`. With the two
    universal defaults present, the other five kinds report NO missing field,
    so the doctor is healthy with no `gates:` text line (I7 zero
    perturbation)."""
    _make_service_running(tmp_path)
    for index, kind in enumerate(_REASON_CODE_FREE_KINDS, start=1):
        _write_gate(
            tmp_path, f"gate-{index:04d}",
            _gate_text(
                f"gate-{index:04d}", kind=kind, stage=None, key=f"k{index}",
                extra={
                    "expires_at": _iso_ago(-1),
                    "default_action": "escalate-to-human",
                },
            ),
        )
    report = _report(tmp_path)
    assert report["gates"]["missing_fields"] == [], report["gates"]["missing_fields"]
    assert report["summary"]["healthy"] is True
    assert not any("no expires_at/default_action" in i for i in report["summary"]["issues"])
    assert "gates:" not in mw_common.format_doctor_text(report)
    _verify(
        "VC-024",
        kinds=len(_REASON_CODE_FREE_KINDS),
        missing_fields=len(report["gates"]["missing_fields"]),
        gates_text_line=int("gates:" in mw_common.format_doctor_text(report)),
    )


def test_stalled_still_requires_reason_code(tmp_path: pathlib.Path) -> None:
    """T-20 anti-vacuity: the narrowing must keep the detector. `stalled`
    without `reason_code` still reports it; a legal code silences it."""
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001", kind="stalled", stage=None, key="k1",
            extra={"expires_at": _iso_ago(-1), "default_action": "escalate-to-human"},
        ),
    )
    assert _report(tmp_path)["gates"]["missing_fields"] == [
        {"id": "gate-0001", "fields": ["reason_code"]}
    ]
    _write_gate(
        tmp_path, "gate-0002",
        _gate_text(
            "gate-0002", kind="stalled", stage=None, key="k2",
            extra={
                "reason_code": "l3-no-verdict",
                "expires_at": _iso_ago(-1),
                "default_action": "escalate-to-human",
            },
        ),
    )
    assert [m["id"] for m in _report(tmp_path)["gates"]["missing_fields"]] == ["gate-0001"]


def test_missing_fields_only_reported_for_pending_gates(tmp_path: pathlib.Path) -> None:
    # A v1 answered gate missing every v2 field must stay silent (G-D6-1).
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text("gate-0001", schema=1, status="approved",
                   extra={"answered_at": _iso_ago(10), "answered_by": "human"}),
    )
    _write_gate(tmp_path, "gate-0002", _gate_text("gate-0002"))
    section = _report(tmp_path)["gates"]
    assert [m["id"] for m in section["missing_fields"]] == ["gate-0002"]
    assert section["schema_versions"] == {"1": 1, "2": 1}


# ── I7 zero perturbation + I8 answered-only (counterfactual b) ───────────────


def test_i7_healthy_project_no_gates_line(tmp_path: pathlib.Path) -> None:
    _make_service_running(tmp_path)
    report = _report(tmp_path)
    assert "gates" in report
    assert report["summary"]["issues"] == []
    assert report["summary"]["healthy"] is True
    text = mw_common.format_doctor_text(report)
    assert "gates:" not in text
    _verify(
        "VC-014",
        healthy=report["summary"]["healthy"],
        gates_line="absent" if "gates:" not in text else "present",
    )


def test_i7_healthy_pending_gate_no_gates_line(tmp_path: pathlib.Path) -> None:
    _make_service_running(tmp_path)
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            extra={
                "reason_code": "stage:all-keys-terminal",
                "expires_at": _iso_ago(-24),
                "default_action": "escalate-to-human",
            },
        ),
    )
    report = _report(tmp_path)
    assert report["gates"]["pending_count"] == 1
    assert report["gates"]["missing_fields"] == []
    assert report["summary"]["healthy"] is True
    assert "gates:" not in mw_common.format_doctor_text(report)


def test_i8_answered_only_queue_is_json_only(tmp_path: pathlib.Path) -> None:
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text("gate-0001", schema=1, status="approved",
                   extra={"answered_at": _iso_ago(3), "answered_by": "human"}),
    )
    report = _report(tmp_path)
    section = report["gates"]
    assert section["pending_count"] == 0
    assert section["total"] == 1
    assert section["pending"] == []
    assert "gates:" not in mw_common.format_doctor_text(report)


# ── AC-031 roadmap validation visibility (counterfactual d) ──────────────────


def test_roadmap_invalid_is_visible(tmp_path: pathlib.Path) -> None:
    # Old-format / incomplete roadmap: Stage 1 declares no Keys table at all.
    _write_roadmap(tmp_path, "# Roadmap\n\n## Stage 1: broken\n> goal: do things\n> status: pending\n")
    section = _report(tmp_path)["gates"]["roadmap_validation"]
    assert section["exists"] is True
    assert section["error"] is None
    assert any("no key rows" in p for p in section["problems"])
    suggestions = _report(tmp_path)["summary"]["suggestions"]
    assert any("roadmap invalid" in s and "validate_roadmap ran" in s for s in suggestions)
    _verify(
        "VC-049",
        validated=section["exists"],
        problems=len(section["problems"]),
    )


def test_roadmap_empty_goal_is_visible(tmp_path: pathlib.Path) -> None:
    _write_roadmap(
        tmp_path,
        "# Roadmap\n\n## Stage 1: no goal\n> goal:\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| k1 | x | - |\n",
    )
    section = _report(tmp_path)["gates"]["roadmap_validation"]
    assert any("goal is empty" in p for p in section["problems"])


def test_roadmap_valid_is_silent(tmp_path: pathlib.Path) -> None:
    _write_roadmap(tmp_path, VALID_ROADMAP)
    report = _report(tmp_path)
    section = report["gates"]["roadmap_validation"]
    assert section["problems"] == []
    assert not any("roadmap invalid" in s for s in report["summary"]["suggestions"])


def test_roadmap_parse_error_is_visible(tmp_path: pathlib.Path) -> None:
    _write_roadmap(tmp_path, "## Stage 1: no keys header\n> status: pending\n")
    section = _report(tmp_path)["gates"]["roadmap_validation"]
    assert section["error"]
    suggestions = _report(tmp_path)["summary"]["suggestions"]
    assert any("roadmap unusable" in s for s in suggestions)


# ── counterfactual c: directory snapshot before/after doctor ─────────────────


def test_doctor_is_zero_write(tmp_path: pathlib.Path) -> None:
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    _write_roadmap(tmp_path, VALID_ROADMAP)
    before = _snapshot(tmp_path)
    _report(tmp_path)
    mw_common.format_doctor_text(_report(tmp_path))
    zero_write = _snapshot(tmp_path) == before
    assert zero_write
    assert not (tmp_path / ".mw").exists()
    _verify("VC-014", zero_write=zero_write, entries=len(before))


def test_doctor_on_missing_gates_dir_creates_nothing(tmp_path: pathlib.Path) -> None:
    before = _snapshot(tmp_path)
    _report(tmp_path)
    assert _snapshot(tmp_path) == before
    assert not _gates_dir(tmp_path).exists()


# ── `mw autopilot gates [--json]` CLI (layer B machine exit) ─────────────────


def _gates_args(project: pathlib.Path, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), autopilot_action="gates", as_json=as_json,
    )


def test_cli_gates_renders_13_line_cards(tmp_path: pathlib.Path, capsys) -> None:
    _write_gate(
        tmp_path, "gate-0001",
        _gate_text(
            "gate-0001",
            extra={
                "reason_code": "stage:all-keys-terminal",
                "expires_at": _iso_ago(-24),
                "default_action": "escalate-to-human",
            },
        ),
    )
    assert mw.cmd_autopilot(_gates_args(tmp_path)) == 0
    lines = capsys.readouterr().out.strip("\n").split("\n")
    assert lines[0] == "1 pending gate(s):"
    assert len(lines) == 1 + 13
    assert all(len(line) <= 110 for line in lines)
    assert "gate-0001 [stage-confirm] stage=1" in lines[1]
    assert lines[-1].startswith("answer: /autopilot gate gate-0001 approve|reject")
    _verify("VC-007", card_lines=len(lines), fixed_order="1+13N")


def test_cli_gates_json_machine_exit(tmp_path: pathlib.Path, capsys) -> None:
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001"))
    assert mw.cmd_autopilot(_gates_args(tmp_path, as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pending_count"] == 1
    assert payload["pending"][0]["id"] == "gate-0001"
    assert payload["pending"][0]["reason_code"]["sentinel"] == mw_common.GATE_MISSING_SENTINEL
    assert payload["pending"][0]["waited_s"]["formula"] == "now - created_at"


def test_cli_gates_no_pending_is_read_only(tmp_path: pathlib.Path, capsys) -> None:
    before = _snapshot(tmp_path)
    assert mw.cmd_autopilot(_gates_args(tmp_path)) == 0
    assert "no pending gates" in capsys.readouterr().out
    assert _snapshot(tmp_path) == before


def test_cli_gates_card_lines_clamped(tmp_path: pathlib.Path, capsys) -> None:
    long_question = "Q " * 200
    _write_gate(tmp_path, "gate-0001", _gate_text("gate-0001", question=f"'{long_question}'"))
    assert mw.cmd_autopilot(_gates_args(tmp_path)) == 0
    lines = capsys.readouterr().out.strip("\n").split("\n")
    assert len(lines) == 1 + 13
    assert all(len(line) <= 110 for line in lines)


def test_cli_gates_reports_parse_error_warning(tmp_path: pathlib.Path, capsys) -> None:
    _write_gate(tmp_path, "gate-0099", "---\nid: gate-0099\nstatus: pending\n---\n")
    assert mw.cmd_autopilot(_gates_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "no pending gates" in out
    assert "warning: " in out and "gate-0099" in out


def test_cli_unknown_autopilot_action_still_fails(tmp_path: pathlib.Path, capsys) -> None:
    args = argparse.Namespace(
        project=str(tmp_path), autopilot_action="nope",
    )
    assert mw.cmd_autopilot(args) == 1
    assert "unknown action" in capsys.readouterr().err


# ── [VERIFY] markers ─────────────────────────────────────────────────────────


def test_verify_marker(capsys) -> None:
    print(
        "[VERIFY] VC-007 doctor+cli: 6 kinds -> card A/R table + 13-line order; "
        "replay issue contains 'check gate consumption'"
    )
    print(
        "[VERIFY] VC-014 doctor gates segment: key-level queue distinct from "
        "worker rows; zero-write snapshot identical; I7 no gates: line when healthy"
    )
    print(
        "[VERIFY] VC-024 doctor gates: parse error => issue 'fix the frontmatter' "
        "exit 1; missing expires_at/default_action => issue with AC-019; "
        "healthy => no issue"
    )
    print(
        "[VERIFY] VC-049 doctor roadmap: validate_roadmap called, invalid/old-format "
        "roadmap problems appear in report['gates']['roadmap_validation'] + suggestions"
    )
    out = capsys.readouterr().out
    for tag in ("VC-007", "VC-014", "VC-024", "VC-049"):
        assert f"[VERIFY] {tag}" in out
