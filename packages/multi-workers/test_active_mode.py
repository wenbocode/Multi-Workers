"""
test_active_mode.py — mw-target-partition rule-table tests (T-01, spec §1.5,
AC-017, VC-017).

Two layers:
1. Shared parameterized table test/fixtures/active-mode-table.json — the
   full enumeration of file shape × active value × EP/ET state for
   mw_common._decide_active_mode, rows 2-12 (the TS runner in
   packages/coding-agent/test/extensions/agent-team-loop-active-mode.test.ts
   executes the SAME table: the JSON is the parity contract).
2. Entry-level unit tests for the two rows the pure inputs cannot express:
   row 1 (mixed format) and row 4 (missing mode block), driven through
   load_target_config. Rows 5-12 are additionally covered end-to-end by the
   target-config-cases fixtures.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from mw_common import (
    ENV_PARTITION_PARENT,
    ENV_PARTITION_ROOT,
    _decide_active_mode,
    load_target_config,
    TargetConfigError,
)

_TABLE_PATH = pathlib.Path(__file__).parent / "test" / "fixtures" / "active-mode-table.json"
_TABLE = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
CASES = _TABLE["cases"]
_ENV_KEYS = ("MW_PARTITION_PARENT", "MW_PARTITION_ROOT", "MW_TARGET_GAME", "MW_TARGET_ENGINE")


def test_table_shape_lock() -> None:
    """The shared table is the frozen enumeration: 112 cases, rows 2-12 all
    present (row 1/4 are not pure-function inputs — see module docstring)."""
    assert len(CASES) == 112, f"expected 112 table cases, found {len(CASES)}"
    rows = sorted({case["row"] for case in CASES})
    assert rows == [2, 3, 5, 6, 7, 8, 9, 10, 11, 12], rows


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[case["id"] for case in CASES],
)
def test_decide_active_mode_table(case: dict) -> None:
    """Every rule-table input combination hits the expected row (priority
    order) with the expected mode/block or error kind + message elements."""
    env = case["env"]
    expect = case["expect"]
    try:
        result = _decide_active_mode(
            case["file_shape"],
            case["active"],
            env.get("MW_PARTITION_PARENT"),
            env.get("MW_PARTITION_ROOT"),
            env.get("MW_TARGET_GAME"),
            env.get("MW_TARGET_ENGINE"),
        )
    except TargetConfigError as e:
        error = expect.get("error")
        assert error is not None, f"{case['id']}: unexpected error: {e.kind}: {e}"
        assert e.kind == error["kind"], f"{case['id']}: kind {e.kind} != {error['kind']}"
        for part in error["contains"]:
            assert part in str(e), f"{case['id']}: {part!r} not in {e}"
    else:
        assert "error" not in expect, f"{case['id']}: expected error, got {result}"
        assert result == {"mode": expect["mode"], "block": expect["block"]}, case["id"]


def test_decide_active_mode_table_markers() -> None:
    rows = {case["row"] for case in CASES}
    print(f"[PARITY] active-mode table cases={len(CASES)} rows={sorted(rows)}")
    print("[VERIFY] VC-017: table=rows-2-12 (rows 1/4 via entry tests + fixtures), parity=py-side")


# ── rows not expressible as pure inputs (entry-level, AC-017) ─────────────────


def _write_yml(control: pathlib.Path, text: str) -> None:
    (control / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (control / ".agenticdoc" / "target.yml").write_text(text, encoding="utf-8")


def test_row1_mixed_format_fails_closed(tmp_path: pathlib.Path) -> None:
    """Row 1: `active:` key together with any v1 top-level field is a
    mixed-format error naming both shapes (fixture case 018 mirrors this)."""
    control = tmp_path / "control"
    control.mkdir()
    _write_yml(control, "active: partition\nmode: dual\ngame: ./game\n")
    with pytest.raises(TargetConfigError) as ei:
        load_target_config(control, env={})
    assert ei.value.kind == "invalid-config"
    message = str(ei.value)
    for part in ("mixed", "v2", "v1"):
        assert part in message, part


def test_row4_missing_partition_block_fails_closed(tmp_path: pathlib.Path) -> None:
    """Row 4: active names a mode whose block is missing — error carries the
    block name (fixture cases 020/039 mirror both variants)."""
    control = tmp_path / "control"
    control.mkdir()
    _write_yml(control, "active: partition\ndual:\n  game: ./game\n")
    with pytest.raises(TargetConfigError) as ei:
        load_target_config(control, env={})
    assert ei.value.kind == "invalid-config"
    assert "partition" in str(ei.value)
    assert "missing" in str(ei.value)


def test_row4_missing_dual_block_fails_closed(tmp_path: pathlib.Path) -> None:
    control = tmp_path / "control"
    control.mkdir()
    _write_yml(control, "active: dual\n")
    with pytest.raises(TargetConfigError) as ei:
        load_target_config(control, env={})
    assert ei.value.kind == "invalid-config"
    assert "dual" in str(ei.value)
    assert "missing" in str(ei.value)


def test_row5_blocks_parked_not_validated(tmp_path: pathlib.Path) -> None:
    """Row 5: active single parks the mode blocks — content that would be a
    whitelist violation if parsed must not raise (AC-017)."""
    control = tmp_path / "control"
    control.mkdir()
    _write_yml(
        control,
        "active: single\ndual:\n  game: ./game\n  parent: ../oops\npartition:\n  parent: ../p\n  partition: ./q\n",
    )
    config = load_target_config(control, env={})
    assert config["mode"] == "single"
    assert config["source"] == "target-yml"
    assert config["game_root"] == config["control_root"]
    assert config["roots"] is None


def test_row9_env_partition_activation(tmp_path: pathlib.Path) -> None:
    """Row 9: no file + both partition env vars → partition, source=env."""
    control = tmp_path / "control"
    control.mkdir()
    config = load_target_config(
        control,
        env={ENV_PARTITION_PARENT: "../parentproj", ENV_PARTITION_ROOT: "./frag"},
    )
    assert config["mode"] == "partition"
    assert config["source"] == "env"
    assert config["parent_root"] == str((control / "../parentproj").resolve())
    assert config["partition_root"] == str((control / "frag").resolve())
    assert config["game_root"] is None
    assert config["roots"] == {}
