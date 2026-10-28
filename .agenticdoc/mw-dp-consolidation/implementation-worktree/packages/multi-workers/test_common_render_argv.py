"""Tests for mw_common.render_argv / workspace_root (AC-014, VC-014).

render_argv is the fail-closed, element-wise verification argv renderer: the
token set is the workspace mode's root tokens plus {control} (verify-only), a
placeholder must occupy a whole argv element, and undefined/unconfigured
tokens raise TargetConfigError("missing-field") with the original element in
the message. The toolchain renderer is deliberately NOT refactored; its
cross-language parity set (test_common_target_config.py) is the guard proving
that (VC-014), so this file also pins the shared partition token-name helper
that keeps both "defines:" lists identical.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from mw_common import (
    TargetConfigError,
    _partition_token_names,
    load_target_config,
    render_argv,
    render_toolchain_command,
    workspace_root,
)


def _partition_config(control="C", parent="P", partition="R", roots=None) -> dict:
    return {
        "mode": "partition",
        "control_root": control,
        "game_root": None,
        "engine_root": None,
        "parent_root": parent,
        "partition_root": partition,
        "roots": {} if roots is None else roots,
        "uproject": None,
    }


def _dual_config(control="C", game="G", engine="E", uproject=None) -> dict:
    return {
        "mode": "dual",
        "control_root": control,
        "game_root": game,
        "engine_root": engine,
        "parent_root": None,
        "partition_root": None,
        "roots": None,
        "uproject": uproject,
    }


def _single_config(control="C", uproject=None) -> dict:
    # single/legacy: game_root == control_root (legacy mode uses the same set).
    return {
        "mode": "legacy",
        "control_root": control,
        "game_root": control,
        "engine_root": None,
        "parent_root": None,
        "partition_root": None,
        "roots": None,
        "uproject": uproject,
    }


# ── truth table ───────────────────────────────────────────────────────────────


def test_no_token_elements_pass_through_verbatim() -> None:
    cmd = ["python", "-m", "pytest", "-q", "-x", "--maxfail=1"]
    out = render_argv(cmd, _partition_config())
    assert out == cmd
    assert out is not cmd  # a fresh list; the template is never mutated


def test_partition_mode_root_tokens() -> None:
    cfg = _partition_config(
        control="C:/control", parent="E:/parent", partition="H:/partition",
        roots={"tests": "H:/partition/tests", "docs": "H:/partition/docs"},
    )
    assert render_argv(
        ["python", "-m", "pytest", "{control}", "{parent}", "{partition}",
         "{tests}", "{docs}"],
        cfg,
    ) == [
        "python", "-m", "pytest", "C:/control", "E:/parent", "H:/partition",
        "H:/partition/tests", "H:/partition/docs",
    ]


def test_dual_mode_root_tokens(tmp_path: pathlib.Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    (game / "Main.uproject").write_text("{}", encoding="utf-8")
    cfg = _dual_config(control="C", game=str(game), engine="E")
    out = render_argv(["{control}", "{game}", "{engine}", "{uproject}"], cfg)
    assert out[0] == "C"
    assert out[1] == str(game)
    assert out[2] == "E"
    assert out[3].endswith("Main.uproject")


def test_single_legacy_mode_root_tokens() -> None:
    cfg = _single_config(control="C:/control")
    assert render_argv(["{control}", "{game}", "literal"], cfg) == [
        "C:/control", "C:/control", "literal",
    ]


@pytest.mark.parametrize(
    "cfg_factory, cmd, token",
    [
        (_partition_config, ["{game}"], "{game}"),  # dual token in partition
        (_partition_config, ["{python}"], "{python}"),  # never provided
        (lambda: _dual_config(engine=None), ["{engine}"], "{engine}"),
        (_single_config, ["{engine}"], "{engine}"),
        (lambda: _dual_config(), ["{python}"], "{python}"),
        (_single_config, ["{python}"], "{python}"),
    ],
)
def test_undefined_or_unconfigured_token_fails_closed(cfg_factory, cmd, token) -> None:
    with pytest.raises(TargetConfigError) as excinfo:
        render_argv(cmd, cfg_factory())
    assert excinfo.value.kind == "missing-field"
    message = str(excinfo.value)
    assert token in message
    assert cmd[0] in message  # the original element is carried verbatim


@pytest.mark.parametrize("element", ["{partition}/tests", "a{b}", "{a}{b}", "x{control}"])
def test_embedded_placeholder_fails_closed_with_element(element: str) -> None:
    with pytest.raises(TargetConfigError) as excinfo:
        render_argv(["ok", element], _partition_config())
    assert excinfo.value.kind == "missing-field"
    assert element in str(excinfo.value)
    assert "whole argv element" in str(excinfo.value)


def test_partition_defines_list_includes_control_and_roots() -> None:
    cfg = _partition_config(roots={"b": "B", "a": "A"})
    with pytest.raises(TargetConfigError) as excinfo:
        render_argv(["{nope}"], cfg)
    message = str(excinfo.value)
    assert "{control}" in message
    assert "{parent}" in message
    assert "{partition}" in message
    assert "{a}" in message and "{b}" in message


def test_uproject_missing_fails_closed_as_uproject_error(tmp_path: pathlib.Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with pytest.raises(TargetConfigError) as excinfo:
        render_argv(["{uproject}"], _dual_config(game=str(game)))
    assert excinfo.value.kind == "ambiguous-uproject"  # discover_uproject contract


# ── workspace_root truth table (AC-013 helper half) ──────────────────────────


def test_workspace_root_mode_dispatch() -> None:
    partition = _partition_config(control="C", parent="P", partition="R")
    assert workspace_root(partition) == "R"
    assert workspace_root(_dual_config(control="C", game="G")) == "G"
    assert workspace_root(_single_config(control="C")) == "C"
    # explicit single mode (v2 active: single) behaves like legacy
    single = _single_config(control="C")
    single["mode"] = "single"
    assert workspace_root(single) == "C"


# ── integration with load_target_config (real target.yml shape) ─────────────


def test_render_argv_over_loaded_partition_target(tmp_path: pathlib.Path) -> None:
    control = tmp_path / "control"
    (control / ".agenticdoc").mkdir(parents=True)
    (control / ".agenticdoc" / "target.yml").write_text(
        "active: partition\n"
        "partition:\n"
        "  parent: ../parent\n"
        "  partition: ../partition\n"
        "  roots:\n"
        "    tests: ../partition/tests\n",
        encoding="utf-8",
    )
    cfg = load_target_config(control, env={})
    assert cfg["mode"] == "partition"
    assert workspace_root(cfg) == cfg["partition_root"]
    rendered = render_argv(["python", "-m", "pytest", "{partition}", "{control}"], cfg)
    assert rendered[3] == cfg["partition_root"]
    assert rendered[4] == cfg["control_root"]


# ── the extraction guard: toolchain behaviour is unchanged (VC-014) ──────────


def test_partition_token_names_helper_matches_toolchain_defines() -> None:
    roots = {"zz": "Z", "aa": "A"}
    assert _partition_token_names(roots) == ["{parent}", "{partition}", "{aa}", "{zz}"]
    with pytest.raises(TargetConfigError) as excinfo:
        render_toolchain_command("{nope}", _partition_config(roots=roots))
    message = str(excinfo.value)
    assert "(partition mode defines: {parent}, {partition}, {aa}, {zz})" in message
    assert "toolchain command references undefined placeholder '{nope}'" in message


def test_render_argv_truth_table_marker(capsys) -> None:
    print(
        "[VERIFY] VC-014 render_argv: partition control/parent/partition/roots=ok; "
        "dual game/engine/uproject/control=ok; single control/game=ok; "
        "embedded {partition}/tests,a{b}=fail-closed; undefined {game}/{engine}/"
        "{python}=fail-closed; workspace_root partition/dual/single=R/G/C"
    )
    out = capsys.readouterr().out
    assert "[VERIFY] VC-014 render_argv:" in out
