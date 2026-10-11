"""test_autopilot_contract_freeze.py - G3 anchor establishment (T-23).

Key mw-gate-verdict-hardening, task T-23 / AC-025 / VC-047. T-04 built the
freeze library and T-10 the done-gate consumer, but nothing in production ever
CREATED the sidecar, so `evaluate` always read `no_anchor` and G3 never fired.
This file locks the missing producer: the design/plan acceptance boundaries
freeze AC/VC once, and the explicit `mw autopilot contract-freeze` CLI anchors
what first-sight could not (historical keys are never backfilled).

Covered:
  - VC-047 first-sight: design freezes ONLY the AC block; plan adds the VC
    block with the AC block byte-identical; a repeat tick does not rewrite and
    emits exactly two `contract-frozen` events; a later AC rewrite makes
    `contract_guard.evaluate` refuse (G3 live).
  - No retroactive anchor for tasks/execute/verify/done/empty phases, and no
    anchor (no error) when the boundary artifact is absent.
  - `contract-frozen` is admitted in the timeline vocabulary.
  - The freeze write failure degrades into a `contract-frozen` event without
    breaking the tick.
  - The CLI: missing blocks filled; unchanged blocks left untouched; changed
    blocks refused (exit 1) without `--force` and re-frozen with it (replaced
    ids + old/new sha printed); `--block ac` leaves the VC block `skipped`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402  (module under test: the CLI)
from autopilot import config, conductor, contract_guard, timeline  # noqa: E402

MW_PY = pathlib.Path(__file__).parent / "mw.py"

SPEC = (
    "# Spec\n\n## 3. Acceptance Criteria\n\n"
    "| AC ID | 判据 |\n|---|---|\n"
    "| AC-001 | first ac text, locked |\n"
    "| AC-002 | second ac text, locked |\n"
)
DESIGN = (
    "# Design\n\n## §7 Verification Contract\n\n"
    "VC-001: first vc assertion\n"
    "       Layer: L0   Output: [VERIFY] VC-001: one=true   Source: AC-001\n"
    "VC-002: second vc assertion\n"
    "       Layer: L1   Output: [VERIFY] VC-002: two=true   Source: AC-002\n"
)


@pytest.fixture(autouse=True)
def _isolate_orchestrate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The freeze step runs before orchestrate, which needs a roadmap/workers
    fixture this card does not own. Keep the rest of the tick a no-op so these
    cases exercise exactly the anchor producer."""
    monkeypatch.setattr(conductor, "orchestrate", lambda root, st: None)


# ── fixtures / helpers ────────────────────────────────────────────────────────

def _base_project(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text("# Goal\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    return tmp_path


def _index_row(key: str, phase: str) -> str:
    return f"| {key} | active | {phase} | — | - | desc | 2026-10-10T00:00:00 |\n"


def _project(
    tmp_path: pathlib.Path,
    phase: str,
    *,
    key: str = "k1",
    spec: str = SPEC,
    design: str = DESIGN,
    write_spec: bool = True,
    write_design: bool = True,
) -> tuple[pathlib.Path, pathlib.Path]:
    project = _base_project(tmp_path)
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row(key, phase), encoding="utf-8"
    )
    key_dir = project / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    if write_spec:
        (key_dir / "spec.md").write_text(spec, encoding="utf-8", newline="\n")
    if write_design:
        (key_dir / "design.md").write_text(design, encoding="utf-8", newline="\n")
    return project, key_dir


def _set_phase(project: pathlib.Path, key: str, phase: str) -> None:
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row(key, phase), encoding="utf-8"
    )


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _frozen_events(project: pathlib.Path) -> list[dict]:
    return [e for e in _events(project) if e["ev"] == "contract-frozen"]


def _file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rewrite_first_ac(key_dir: pathlib.Path) -> None:
    (key_dir / "spec.md").write_text(
        SPEC.replace("first ac text, locked", "first ac text, REWRITTEN"),
        encoding="utf-8",
        newline="\n",
    )


def _freeze_args(
    project: pathlib.Path,
    key: str,
    *,
    block: str = "all",
    force: bool = False,
    as_json: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        autopilot_action="contract-freeze",
        key=key,
        block=block,
        force=force,
        as_json=as_json,
    )


def _run_freeze_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["MW_AUTOPILOT_FILE"] = str(pathlib.Path(argv[argv.index("--project") + 1]) / "none.json")
    env.pop("MW_AUTOPILOT_HOME", None)
    return subprocess.run(
        [sys.executable, str(MW_PY), "autopilot", "contract-freeze", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        timeout=60,
        env=env,
    )


# ── VC-047: first-sight establish AC then VC, never rewrite ────────────────────

def test_vc047_first_sight_freezes_ac_then_vc_and_never_rewrites(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path, "DESIGN")
    st = _state(project)
    assert conductor.tick(project, st) == "ok"

    freeze_path = contract_guard.freeze_path(key_dir)
    assert freeze_path.is_file()
    first = contract_guard.read_freeze(key_dir)
    assert first is not None
    assert sorted(first["spec"]) == ["AC-001", "AC-002"]
    assert first["design"] == {}  # ONLY the AC block at the design boundary
    spec_block = json.dumps(first["spec"], ensure_ascii=False, sort_keys=True)
    sha_after_design = _file_sha(freeze_path)
    frozen_after_design = _frozen_events(project)
    assert len(frozen_after_design) == 1
    assert frozen_after_design[0]["key"] == "k1"
    assert frozen_after_design[0]["data"] == {
        "block": "ac",
        "phase": "design",
        "source": "conductor-first-sight",
        "freeze_rel": ".agenticdoc/k1/evidence/contract-freeze.json",
        "ids": ["AC-001", "AC-002"],
    }

    # design -> plan: the VC block joins and the AC block stays byte-identical.
    _set_phase(project, "k1", "PLAN")
    assert conductor.tick(project, st) == "ok"
    second = contract_guard.read_freeze(key_dir)
    assert sorted(second["design"]) == ["VC-001", "VC-002"]
    assert sorted(second["spec"]) == ["AC-001", "AC-002"]
    assert json.dumps(second["spec"], ensure_ascii=False, sort_keys=True) == spec_block
    sha_after_plan = _file_sha(freeze_path)
    assert sha_after_plan != sha_after_design  # the VC block was added

    # A repeat tick at plan never rewrites and never re-emits. Cross a clock
    # second first so a hypothetical rewrite (fresh `frozen_at`) would change
    # the file sha - the assertion must be able to see a rewrite at all.
    time.sleep(1.05)
    assert conductor.tick(project, st) == "ok"
    assert _file_sha(freeze_path) == sha_after_plan
    assert [e["data"]["block"] for e in _frozen_events(project)] == ["ac", "vc"]

    # G3 is live: the done guard refuses an unauthorized AC rewrite.
    _rewrite_first_ac(key_dir)
    verdict = contract_guard.evaluate(key_dir, conductor.gates_dir(project), key="k1")
    assert verdict.ok is False
    assert verdict.no_anchor is False
    assert "AC-001" in verdict.changed_ids
    print(
        "[VERIFY] VC-047: ac_first=true vc_added=true spec_bytes_stable=true "
        "repeat_sha_stable=true events=2 refused=true"
    )


def test_vc047_no_retroactive_anchor_for_later_phases(tmp_path: pathlib.Path) -> None:
    for index, phase in enumerate(("TASKS", "EXECUTE", "VERIFY", "DONE", "")):
        root = tmp_path / f"case{index}"
        root.mkdir()
        project, key_dir = _project(root, phase)
        st = _state(project)
        assert conductor.tick(project, st) == "ok", phase
        assert not contract_guard.freeze_path(key_dir).exists(), phase
        assert _frozen_events(project) == [], phase
    print("[VERIFY] VC-047: no_retro_phases=tasks,execute,verify,done,empty")


def test_phase_design_without_spec_does_not_anchor_or_raise(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path, "DESIGN", write_spec=False)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    assert not contract_guard.freeze_path(key_dir).exists()
    assert _frozen_events(project) == []
    print("[VERIFY] VC-047: missing_spec_no_anchor=true no_raise=true")


def test_contract_frozen_event_is_admitted() -> None:
    assert "contract-frozen" in timeline.EVENT_TYPES
    print("[VERIFY] VC-047: vocabulary_admitted=true")


def test_freeze_write_failure_degrades_without_breaking_tick(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, key_dir = _project(tmp_path, "DESIGN")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected freeze write failure")

    monkeypatch.setattr(contract_guard, "write_freeze", boom)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    degraded = _frozen_events(project)
    assert len(degraded) == 1
    assert "freeze failed" in degraded[0]["detail"]
    assert degraded[0]["data"]["block"] == "ac"
    assert not contract_guard.freeze_path(key_dir).exists()
    print("[VERIFY] VC-047: write_failure_degraded=true tick_status=ok")


# ── CLI: missing / unchanged / changed / --force / --block ─────────────────────

def test_cli_fills_missing_blocks(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    project, key_dir = _project(tmp_path, "PLAN")
    assert mw.cmd_autopilot(_freeze_args(project, "k1", as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["key"] == "k1"
    assert payload["freeze_rel"] == ".agenticdoc/k1/evidence/contract-freeze.json"
    assert payload["blocks"]["ac"] == {"status": "written", "ids": ["AC-001", "AC-002"]}
    assert payload["blocks"]["vc"] == {"status": "written", "ids": ["VC-001", "VC-002"]}
    frozen = contract_guard.read_freeze(key_dir)
    assert sorted(frozen["spec"]) == ["AC-001", "AC-002"]
    assert sorted(frozen["design"]) == ["VC-001", "VC-002"]
    print("[VERIFY] AC-025: cli_missing_filled=true both_blocks=true")


def test_cli_unchanged_block_is_left_untouched(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, key_dir = _project(tmp_path, "PLAN")
    contract_guard.freeze_contract(key_dir, "k1", SPEC, DESIGN)
    freeze_path = contract_guard.freeze_path(key_dir)
    before = _file_sha(freeze_path)
    assert mw.cmd_autopilot(_freeze_args(project, "k1", as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["blocks"]["ac"]["status"] == "unchanged"
    assert payload["blocks"]["vc"]["status"] == "unchanged"
    assert _file_sha(freeze_path) == before  # zero write
    print("[VERIFY] AC-025: cli_unchanged_skipped=true sha_stable=true")


def test_cli_changed_block_refused_without_force(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, key_dir = _project(tmp_path, "PLAN")
    contract_guard.freeze_contract(key_dir, "k1", SPEC, DESIGN)
    freeze_path = contract_guard.freeze_path(key_dir)
    before = _file_sha(freeze_path)
    _rewrite_first_ac(key_dir)

    assert mw.cmd_autopilot(_freeze_args(project, "k1", as_json=True)) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["blocks"]["ac"] == {"status": "refused", "ids": ["AC-001"]}
    assert payload["blocks"]["vc"]["status"] == "unchanged"
    assert _file_sha(freeze_path) == before  # a refusal writes nothing

    # The text path says what to do about it.
    assert mw.cmd_autopilot(_freeze_args(project, "k1")) == 1
    text = capsys.readouterr().out
    assert "ac refused" in text and "replaced=AC-001" in text and "--force" in text
    print("[VERIFY] AC-025: cli_changed_refused=true exit=1 replaced=AC-001")


def test_cli_force_refreezes_and_prints_shas(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, key_dir = _project(tmp_path, "PLAN")
    contract_guard.freeze_contract(key_dir, "k1", SPEC, DESIGN)
    old = contract_guard.read_freeze(key_dir)
    _rewrite_first_ac(key_dir)

    assert mw.cmd_autopilot(_freeze_args(project, "k1", force=True)) == 0
    text = capsys.readouterr().out
    assert "ac written" in text and "replaced=AC-001" in text
    assert "old_sha=" in text and "new_sha=" in text
    new = contract_guard.read_freeze(key_dir)
    assert new["spec"]["AC-001"] != old["spec"]["AC-001"]
    assert new["spec"]["AC-002"] == old["spec"]["AC-002"]  # other ids kept
    # The re-freeze moves the anchor to the current text (no longer refused).
    verdict = contract_guard.evaluate(key_dir, conductor.gates_dir(project), key="k1")
    assert verdict.ok is True and verdict.no_anchor is False
    print("[VERIFY] AC-025: cli_force_refrozen=true shas_printed=true anchor_moved=true")


def test_cli_block_scope_marks_other_block_skipped(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, key_dir = _project(tmp_path, "PLAN")
    assert mw.cmd_autopilot(_freeze_args(project, "k1", block="ac", as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["blocks"]["ac"]["status"] == "written"
    assert payload["blocks"]["vc"] == {"status": "skipped", "ids": []}
    frozen = contract_guard.read_freeze(key_dir)
    assert sorted(frozen["spec"]) == ["AC-001", "AC-002"]
    assert frozen["design"] == {}
    print("[VERIFY] AC-025: block_scope=ac vc_skipped=true")


def test_cli_subprocess_json_and_argparse(tmp_path: pathlib.Path) -> None:
    # `--key` is mandatory: no batch write of a whole project.
    missing_key = _run_freeze_cli("--project", str(tmp_path), "--json")
    assert missing_key.returncode == 2

    project, _key_dir = _project(tmp_path, "PLAN")
    result = _run_freeze_cli("--project", str(project), "--key", "k1", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["blocks"]["ac"]["status"] == "written"
    assert payload["blocks"]["vc"]["status"] == "written"
    assert str(project) not in json.dumps(payload)  # project-relative payload
    print("[VERIFY] AC-025: cli_key_required=true json_relative=true")


# ── first-sight x CLI: historical key anchored only by the CLI ─────────────────

def test_execute_key_without_sidecar_is_anchored_only_by_cli(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path, "EXECUTE")
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    assert not contract_guard.freeze_path(key_dir).exists()  # no backfill

    assert mw.cmd_autopilot(_freeze_args(project, "k1")) == 0
    frozen = contract_guard.read_freeze(key_dir)
    assert sorted(frozen["spec"]) == ["AC-001", "AC-002"]
    assert sorted(frozen["design"]) == ["VC-001", "VC-002"]
    print("[VERIFY] AC-025: execute_key_cli_only=true")
