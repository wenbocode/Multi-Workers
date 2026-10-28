"""test_autopilot_done_contract_guard.py - G3 done-gate wiring + prompt lock.

Key mw-gate-verdict-hardening, task T-10 (AC-010 / AC-011 / AC-012 / AC-013;
VC-013 / VC-014 / VC-015 / VC-016).

The decision logic itself lives in `autopilot/contract_guard.py` and is covered
by `test_autopilot_contract_guard.py` (T-04). This file covers the conductor
wiring that T-10 owns:

  - VC-013: `_repair_prompt` / `_phase_writer_prompt` / `_fix_writer_prompt`
    each carry the SAME hard-constraint literal verbatim.
  - VC-014: `_done_transaction` refuses (fail-closed) a frozen AC/VC change
    with no approval record, emits the machine-classified `contract-refused`
    event, raises a `contract-unauthorized` stall gate, and writes no terminal
    artifact; an approved `authorizes: ["contract-change"]` gate lets it pass.
  - VC-015: a prose note / pending / rejected / wrong-key gate never authorizes
    at the done boundary.
  - VC-016: no freeze sidecar => the guard is a no-op (historical keys behave
    exactly as before).
  - field materialization: `_gate_default_fields` / `_stamp_gate_defaults`
    write `authorizes: []` into every new gate (without touching `create()`).
  - reason_code closed set + independent recomputation (no reason drift).
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config, conductor, contract_guard, gates, roadmap, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


_KEY = "k1"

SPEC = (
    "# Spec\n\n"
    "## 3. Acceptance Criteria\n\n"
    "| AC ID | 判据 |\n"
    "|---|---|\n"
    "| AC-001 | first contract text, locked |\n"
    "| AC-002 | second contract text, locked |\n"
)
DESIGN = (
    "# Design\n\n"
    "## §7 Verification Contract\n\n"
    "VC-001: first assertion text\n"
    "       Layer: L0   Output: [VERIFY] VC-001: one=true   Source: AC-001\n"
    "VC-002: second assertion text\n"
    "       Layer: L1   Output: [VERIFY] VC-002: two=true   Source: AC-002\n"
)
L3_MEETS = (
    "# L3 Report\n\n"
    "## Quality Gate Report\n\n"
    "| VC | verdict | evidence |\n"
    "|----|---------|----------|\n"
    "| VC-001 | PASS | evidence/runs/a.md |\n"
    "\n"
    "## Achieved\n\n"
    + (
        "达成摘要：本 key 完成了全部任务书列出的交付物，验证套件全绿，"
        "证据链闭合无缺口，目标收益如 spec 所述已经落地，遗留问题仅在文档层面。"
        * 4
    )
    + "\n"
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    (ap / "_roadmap.md").write_text(
        "# Roadmap\n"
        "> generated_at: t\n"
        "> goal_mtime: 1\n"
        "\n"
        "## Stage 1: work\n"
        "> goal: deliver\n"
        "> status: running\n"
        f"> key-status: {_KEY}=running\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        f"| {_KEY} | worker | - |\n",
        encoding="utf-8",
    )
    # phase column = `verify` so `_done_transaction` reads a non-DONE key.
    (tmp_path / ".agenticdoc" / "_index.parallel").write_text(
        f"| {_KEY} | active | verify | — | - | d | 2026-09-10T00:00:00 |\n",
        encoding="utf-8",
    )
    key_dir = tmp_path / ".agenticdoc" / _KEY
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "spec.md").write_text(SPEC, encoding="utf-8", newline="\n")
    (key_dir / "design.md").write_text(DESIGN, encoding="utf-8", newline="\n")
    return tmp_path


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _l3_output(project: pathlib.Path) -> pathlib.Path:
    out = (
        project / ".agenticdoc" / _KEY
        / "workers" / f"ap-{_KEY}-l3-a1" / "output.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(L3_MEETS, encoding="utf-8", newline="\n")
    return out


def _set_index_phase_file(project: pathlib.Path, key: str, phase: str) -> None:
    ipath = project / ".agenticdoc" / "_index.parallel"
    lines = []
    for line in ipath.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| {key} |"):
            cols = [c.strip() for c in line.strip("|").split("|")]
            cols[2] = phase
            line = "| " + " | ".join(cols) + " |"
        lines.append(line)
    ipath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fake_advance(project: pathlib.Path):
    """Gate-validating advance fake: mirrors the real three-artifact checks."""
    calls: list[tuple[str, str]] = []

    def fake_advance(key: str, phase: str, root, summary=None):
        calls.append((key, phase))
        if phase != "done":
            return 0, "advanced", ""
        key_dir = pathlib.Path(root) / ".agenticdoc" / key
        achieved = key_dir / "achieved.md"
        pm_state = key_dir / "pm-state.md"
        qg = list((key_dir / "evidence").glob("quality-gate-report-*.md"))
        if (
            not achieved.is_file() or achieved.stat().st_size < 200
            or not pm_state.is_file() or "PASS" not in pm_state.read_text(encoding="utf-8")
            or not qg
        ):
            return 1, "", "done gate failed (三件套)"
        _set_index_phase_file(project, key, "DONE")
        return 0, "advanced", ""

    return fake_advance, calls


def _gate_file(
    gates_dir: pathlib.Path,
    gate_id: str,
    *,
    key: str,
    status: str,
    authorizes: list[str] | None = None,
    note: str | None = None,
) -> pathlib.Path:
    lines = [
        "---",
        f"id: {gate_id}",
        "kind: stalled",
        "stage: 1",
        f"key: {key}",
        "created_at: 2026-10-10T08:00:00+00:00",
        "created_by: conductor",
        "question: proceed?",
        "context_refs: []",
        f"status: {status}",
        "answered_at:",
        "answered_by:",
        "note:",
    ]
    if note is not None:
        lines[-1] = f"note: '{note}'"
    if authorizes is not None:
        lines.append("authorizes: '" + json.dumps(authorizes) + "'")
    lines.append("---")
    gates_dir.mkdir(parents=True, exist_ok=True)
    path = gates_dir / f"{gate_id}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _freeze_and_rewrite(project: pathlib.Path) -> None:
    """Freeze the contract, then rewrite one AC body (a frozen-text change)."""
    key_dir = project / ".agenticdoc" / _KEY
    contract_guard.freeze_contract(key_dir, _KEY, SPEC, DESIGN)
    (key_dir / "spec.md").write_text(
        SPEC.replace("first contract text, locked", "first contract text, rewritten"),
        encoding="utf-8",
        newline="\n",
    )


# ── VC-013: one literal, three prompts ────────────────────────────────────────


def test_vc013_three_prompts_carry_the_same_constraint_verbatim() -> None:
    prompts = {
        "repair": conductor._repair_prompt(
            _KEY, 1, f".agenticdoc/{_KEY}/workers/ap-{_KEY}-l3-a1/report.md"
        ),
        "phase-writer": conductor._phase_writer_prompt(_KEY, "design", "plan"),
        "fix-writer": conductor._fix_writer_prompt(
            _KEY, "design", "plan",
            [{"item": "gap", "rule": "r1"}], pathlib.Path("."), 1,
        ),
    }
    assert len(prompts) == 3
    for name, text in prompts.items():
        assert conductor._CONTRACT_CONSTRAINT in text, name
        assert text.count(conductor._CONTRACT_CONSTRAINT) == 1, name
        assert text.rstrip("\n").endswith(conductor._CONTRACT_CONSTRAINT), name
    _verify("VC-013", prompts=len(prompts), verbatim="true")


def test_vc013_constraint_is_a_standalone_literal_outside_contract_guard() -> None:
    """The constraint is T-10's own string, not re-exported from T-04."""
    guard_src = pathlib.Path(contract_guard.__file__).read_text(encoding="utf-8")
    assert conductor._CONTRACT_CONSTRAINT not in guard_src
    assert "硬约束" not in guard_src


# ── VC-014: done is refused, machine-classified, and no terminal write ────────


def test_vc014_done_refused_without_approval_and_classified(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _freeze_and_rewrite(project)
    # E2-shaped prose note: approved, but no machine authorizes field.
    _gate_file(
        project / ".agenticdoc" / "_autopilot" / "gates",
        "gate-0001", key=_KEY, status="approved",
        note="放宽的是验证方式与文档同步，contract-change 属可修范围",
    )
    fake_advance, calls = _fake_advance(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    l3_out = _l3_output(project)

    verdict, err = conductor._done_transaction(project, st, _KEY, l3_out)

    assert verdict == "gated" and err == ""
    assert calls == []  # advance never ran: no terminal write
    key_dir = project / ".agenticdoc" / _KEY
    assert not list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    assert not (key_dir / "pm-state.md").exists()
    assert not (key_dir / "l3-verdict.txt").exists()

    refused = [e for e in _events(project) if e["ev"] == "contract-refused"]
    assert len(refused) == 1, refused
    data = refused[0]["data"]
    assert data["changed_ids"] == ["AC-001"]
    assert data["freeze_rel"] == f".agenticdoc/{_KEY}/evidence/contract-freeze.json"
    assert data["carrier"] is None

    stalled = [
        g for g in gates.enumerate(conductor.gates_dir(project))
        if g.reason_code == "contract-unauthorized"
    ]
    assert len(stalled) == 1, stalled
    gate = stalled[0]
    assert gate.kind == "stalled" and gate.status == "pending"
    # independent recomputation stays consistent (no stalled-reason-drift)
    assert conductor._stall_family(gate) == "l3"
    cause = conductor.recompute_stall_cause(project, gate)
    assert cause == "contract-unauthorized", cause
    _verify(
        "VC-014", refused="true", changed_ids=len(data["changed_ids"]),
        classified="true",
    )


def test_vc014_approved_authorizing_gate_allows_done(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _freeze_and_rewrite(project)
    _gate_file(
        project / ".agenticdoc" / "_autopilot" / "gates",
        "gate-0001", key=_KEY, status="approved",
        authorizes=["contract-change"],
    )
    fake_advance, calls = _fake_advance(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    l3_out = _l3_output(project)

    verdict, err = conductor._done_transaction(project, st, _KEY, l3_out)

    assert verdict == "advanced", (verdict, err)
    assert calls == [(_KEY, "done")]
    assert not [e for e in _events(project) if e["ev"] == "contract-refused"]
    assert list(
        (project / ".agenticdoc" / _KEY / "evidence").glob("quality-gate-report-*.md")
    )
    _verify("VC-014-carrier", authorized="true", carrier="gate-0001")


@pytest.mark.parametrize(
    "gate_id,status,key,authorizes,note",
    [
        ("gate-0001", "pending", _KEY, ["contract-change"], None),
        ("gate-0002", "rejected", _KEY, ["contract-change"], None),
        ("gate-0003", "approved", "other-key", ["contract-change"], None),
        ("gate-0004", "approved", _KEY, ["retry"], None),
        ("gate-0005", "approved", _KEY, None, "contract-change 属可修范围"),
    ],
)
def test_vc015_no_non_machine_or_non_scoped_record_authorizes_done(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    gate_id: str,
    status: str,
    key: str,
    authorizes: list[str] | None,
    note: str | None,
) -> None:
    project = _project(tmp_path)
    _freeze_and_rewrite(project)
    _gate_file(
        project / ".agenticdoc" / "_autopilot" / "gates",
        gate_id, key=key, status=status, authorizes=authorizes, note=note,
    )
    fake_advance, calls = _fake_advance(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)

    verdict, _err = conductor._done_transaction(project, st, _KEY, _l3_output(project))

    assert verdict == "gated", (gate_id, verdict, status, authorizes, note)
    assert calls == []
    assert [e for e in _events(project) if e["ev"] == "contract-refused"]
    _verify("VC-015", gate=gate_id, authorized="false")


# The E2 incident shape (read-only reference 2026-10-09):
# `H:\git\E2Feature\.agenticdoc\_autopilot\gates\gate-0014.md` - kind stalled,
# status approved, answered_by wenbozhou, and a prose note that was treated as
# the authorization for a design.md AC/VC rewrite. No `authorizes` field.
_E2_GATE_0014_NOTE = (
    "方案 A 人工介入后重试。L3 三轮判 below 且失败项为真实缺陷而非机械误判"
    "（37 PASS / 5 FAIL）：VC-001 parent db shm/wal 导致白名单外 delta、VC-002 7 "
    "个受保护 eval 导出哈希漂移、VC-033 未限定 K5 E2E 仍 exit 1、VC-037/039 "
    "spec 降标未同步 design/ER。放宽的是验证方式与文档同步，属可修范围；"
    "若下一轮仍同 5 项，则转 closed-legacy 加四态登记。"
)


def test_vc015_e2feature_gate_0014_shape_is_not_an_authorization(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact prose-note carrier from the E2 incident does not authorize."""
    project = _project(tmp_path)
    _freeze_and_rewrite(project)
    gate_path = _gate_file(
        project / ".agenticdoc" / "_autopilot" / "gates",
        "gate-0014", key=_KEY, status="approved", note=_E2_GATE_0014_NOTE,
    )
    parsed = gates.parse(gate_path)
    assert parsed.authorizes is None
    fake_advance, calls = _fake_advance(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)

    verdict, _err = conductor._done_transaction(project, st, _KEY, _l3_output(project))

    assert verdict == "gated"
    assert calls == []
    refused = [e for e in _events(project) if e["ev"] == "contract-refused"]
    assert refused and refused[0]["data"]["carrier"] is None
    _verify("VC-015", gate="gate-0014-shape", authorized="false")


# ── VC-016 / AC-013: no freeze => no-op for historical keys ──────────────────


def test_ac013_no_freeze_is_a_noop_for_the_done_transaction(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / _KEY
    # Even with the AC body rewritten, no freeze means no identity anchor.
    (key_dir / "spec.md").write_text(
        SPEC.replace("first contract text, locked", "unrelated rewrite"),
        encoding="utf-8",
        newline="\n",
    )
    fake_advance, calls = _fake_advance(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)

    verdict, err = conductor._done_transaction(project, st, _KEY, _l3_output(project))

    assert verdict == "advanced", (verdict, err)
    assert calls == [(_KEY, "done")]
    assert not [e for e in _events(project) if e["ev"] == "contract-refused"]
    assert not [
        g for g in gates.enumerate(conductor.gates_dir(project)) if g.kind == "stalled"
    ]
    _verify("VC-016", freeze="absent", refused="false")


def test_ac013_done_refused_does_not_fire_when_frozen_text_is_unchanged(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / _KEY
    contract_guard.freeze_contract(key_dir, _KEY, SPEC, DESIGN)  # no rewrite
    fake_advance, calls = _fake_advance(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)

    verdict, err = conductor._done_transaction(project, st, _KEY, _l3_output(project))

    assert verdict == "advanced", (verdict, err)
    assert calls == [(_KEY, "done")]


# ── field materialization ─────────────────────────────────────────────────────


def test_new_gate_materializes_an_empty_authorizes_field(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    st = _state(project)
    path = conductor._create_gate(project, st, "stalled", "q?", key=_KEY)
    assert path is not None
    gate = gates.parse(path)
    assert gate.authorizes == []
    raw = path.read_text(encoding="utf-8")
    assert "\nauthorizes: []\n" in raw
    # gates.create() itself is untouched (13 keys, no authorizes)
    create_path = gates.create(
        project / "other-gates", "stalled", "q2?", [], stage=1, key=_KEY
    )
    create_lines = create_path.read_text(encoding="utf-8").splitlines()
    end = create_lines.index("---", 1)
    keys = [ln.split(":", 1)[0] for ln in create_lines[1:end] if not ln.startswith(" ")]
    assert len(keys) == 13 and "authorizes" not in keys
    _verify("VC-016-materialize", stamped_authorizes="[]", create_keys=len(keys))


def test_gate_default_fields_includes_authorizes(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    create_path = gates.create(
        project / "g", "stalled", "q?", [], stage=1, key=_KEY
    )
    fields = conductor._gate_default_fields(create_path)
    assert fields["authorizes"] == "[]"
    assert fields["default_action"] == conductor.GATE_DEFAULT_ACTION


# ── reason_code closed set ────────────────────────────────────────────────────


def test_contract_unauthorized_is_in_the_reason_code_closed_set() -> None:
    assert "contract-unauthorized" in conductor.STALL_REASON_CODES
    assert "contract-unauthorized" in conductor.REASON_CODES
    assert len(conductor.STALL_REASON_CODES) == 14
    assert set(conductor.STALL_REASON_CODES) <= conductor.REASON_CODES


def test_stalled_gate_lookup_and_roadmap_round_trip(tmp_path: pathlib.Path) -> None:
    """The refusal path actually froze the key (roadmap says stalled)."""
    project = _project(tmp_path)
    _freeze_and_rewrite(project)
    st = _state(project)
    conductor.mark_stalled(
        project, st, _KEY, "AC/VC changed without authorization",
        reason_code="contract-unauthorized",
    )
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status[_KEY] == "stalled"
