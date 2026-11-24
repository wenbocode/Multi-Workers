"""test_additional_write_roots.py — dual additional write roots (Python side).

Card: `.agenticdoc/mw-dual-additional-write-roots/tasks/t-002-python-cli.md`
(key mw-dual-additional-write-roots, AC-001/AC-002, design D-001..D-005).

The Python half of the contract:

* config parsing — v1 flat top level, canonical `dual.additional_write_roots`,
  v2 top-level read-side compatibility, undeclared/`[]` no-op, mode gates,
  relative/null/non-list/non-string/duplicate/nested/overlap rejection, env
  overlay against the final roots, junction-as-root rejection;
* host write face — `write_face_roots()` and `parse_workspace_write_face()`
  accept declared external paths and keep the existing rejection codes;
* profile / `mw target show` / doctor probe fingerprint — conditional only;
* `mw target off|clear` and `mw partition set|on|clear` — promote a top-level
  declaration into the `dual:` block before writing, or fail closed with zero
  writes; the v1 -> v2 migration keeps the declaration inside the dual block.

Run: cd packages/multi-workers; python -X utf8 -m pytest test/test_additional_write_roots.py -q
"""
import argparse
import ctypes
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import mw  # noqa: E402
import mw_common as mc  # noqa: E402
from autopilot import dispatch  # noqa: E402
from test_target_baseline import DUAL_YML, GOLDEN_DIR  # noqa: E402

_ENV_KEYS = (
    mc.ENV_TARGET_GAME,
    mc.ENV_TARGET_ENGINE,
    mc.ENV_PARTITION_PARENT,
    mc.ENV_PARTITION_ROOT,
)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)


# ── fixtures / helpers ───────────────────────────────────────────────────────


def _root(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    path = tmp_path / name
    path.mkdir()
    return path


def _write_yml(control: pathlib.Path, text: str) -> pathlib.Path:
    yml = mc.target_yml_path(control)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(text, encoding="utf-8", newline="\n")
    return yml


def _dual_top(control: pathlib.Path, game: pathlib.Path, engine: pathlib.Path,
              extra: pathlib.Path) -> str:
    return (
        "mode: dual\n"
        f"game: '{game}'\n"
        f"engine: '{engine}'\n"
        "additional_write_roots:\n"
        f"  - '{extra}'\n"
    )


def _dual_top_v2(game: pathlib.Path, engine: pathlib.Path, extra: pathlib.Path) -> str:
    return (
        "active: dual\n"
        "additional_write_roots:\n"
        f"  - '{extra}'\n"
        "dual:\n"
        f"  game: '{game}'\n"
        f"  engine: '{engine}'\n"
    )


def _dual_block_v2(game: pathlib.Path, engine: pathlib.Path, extra: pathlib.Path) -> str:
    return (
        "active: dual\n"
        "dual:\n"
        f"  game: '{game}'\n"
        f"  engine: '{engine}'\n"
        "  additional_write_roots:\n"
        f"    - '{extra}'\n"
    )


def _expect_invalid(control: pathlib.Path, contains: tuple[str, ...] = ()) -> str:
    with pytest.raises(mc.TargetConfigError) as ei:
        mc.load_target_config(control, env={})
    assert ei.value.kind == "invalid-config", str(ei.value)
    message = str(ei.value)
    for part in contains:
        assert part in message, f"{part!r} not in {message!r}"
    return message


def _junction(link: pathlib.Path, target: pathlib.Path) -> None:
    """Real Windows junction (mklink /J); directory symlink elsewhere."""
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True
        )
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


def _unlink_junction(link: pathlib.Path) -> None:
    """Remove a junction itself — never recurse into its target (P-027)."""
    try:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()
    except OSError:
        pass


def _short_path(path: pathlib.Path) -> str:
    if os.name != "nt":
        pytest.skip("8.3 short names are a Windows feature")
    buf = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 32768)
    if not size:
        pytest.skip("GetShortPathNameW returned no short name")
    return buf.value


# ── config shape ─────────────────────────────────────────────────────────────


def test_config_shape_accepts_v1_flat_v2_block_and_v2_top_level(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    want = [str(extra.resolve())]
    for text in (
        _dual_top(control, game, engine, extra),
        _dual_top_v2(game, engine, extra),
        _dual_block_v2(game, engine, extra),
    ):
        _write_yml(control, text)
        config = mc.load_target_config(control, env={})
        assert config["mode"] == "dual"
        assert config["additional_write_roots"] == want
    print("[VERIFY] VC-001/002/003 config-shape accepts v1-flat/v2-block/v2-top-level")


def test_config_shape_undeclared_and_empty_list_add_no_field(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    undeclared = (
        "active: dual\n"
        "dual:\n"
        f"  game: '{game}'\n"
        f"  engine: '{engine}'\n"
    )
    for text in (
        undeclared,
        undeclared + "  additional_write_roots: []\n",
        "active: dual\n"
        "additional_write_roots: []\n"
        f"dual:\n  game: '{game}'\n  engine: '{engine}'\n",
    ):
        _write_yml(control, text)
        config = mc.load_target_config(control, env={})
        assert "additional_write_roots" not in config
    # Row 5: a parked dual block is not parsed — even an invalid declaration
    # in it must not change the single-mode result.
    _write_yml(
        control,
        "active: single\n"
        "dual:\n"
        f"  game: '{game}'\n"
        "  additional_write_roots:\n"
        "    - 'relative/saved'\n",
    )
    parked = mc.load_target_config(control, env={})
    assert parked["mode"] == "single"
    assert "additional_write_roots" not in parked
    print("[VERIFY] VC-006 undeclared/[]/parked-dual add no field")


def test_config_shape_rejects_top_level_in_single_and_partition(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra, parent, part = (
        _root(tmp_path, name) for name in ("control", "game", "engine", "saved", "parent", "part")
    )
    _write_yml(
        control,
        "active: single\n"
        "additional_write_roots:\n"
        f"  - '{extra}'\n"
        "dual:\n"
        f"  game: '{game}'\n"
        f"  engine: '{engine}'\n",
    )
    _expect_invalid(control, ("additional_write_roots", "active: dual", "single"))
    _write_yml(
        control,
        "active: partition\n"
        "additional_write_roots:\n"
        f"  - '{extra}'\n"
        "partition:\n"
        f"  parent: '{parent}'\n"
        f"  partition: '{part}'\n"
        "dual:\n"
        f"  game: '{game}'\n",
    )
    _expect_invalid(control, ("additional_write_roots", "active: dual", "partition"))
    # v1 single / no game: the declaration is not mode-scoped to dual either.
    _write_yml(
        control,
        "mode: single\n"
        "additional_write_roots:\n"
        f"  - '{extra}'\n",
    )
    _expect_invalid(control, ("additional_write_roots", "dual", "single"))
    _write_yml(control, "additional_write_roots:\n  - 'D:/nowhere'\n")
    _expect_invalid(control, ("additional_write_roots", "dual", "single"))
    print("[VERIFY] VC-004 top-level declaration rejected outside dual")


def test_config_shape_rejects_both_declarations(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    _write_yml(
        control,
        "active: dual\n"
        "additional_write_roots:\n"
        f"  - '{extra}'\n"
        "dual:\n"
        f"  game: '{game}'\n"
        f"  engine: '{engine}'\n"
        "  additional_write_roots:\n"
        f"    - '{extra}'\n",
    )
    _expect_invalid(control, ("additional_write_roots", "top level", "'dual' block", "exactly one"))
    print("[VERIFY] VC-003 both placements rejected")


def test_config_shape_rejects_relative_null_non_list_and_non_string(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    header = f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n"
    cases = (
        ("relative", "additional_write_roots:\n  - 'Saved'\n", ("absolute", "additional_write_roots")),
        ("null", "additional_write_roots:\n", ("empty value", "additional_write_roots")),
        ("non-list", f"additional_write_roots: '{extra}'\n", ("list", "additional_write_roots")),
        ("non-string", "additional_write_roots:\n  - 42\n", ("non-empty string",)),
        ("empty-string", "additional_write_roots:\n  - ''\n", ("non-empty string",)),
    )
    for name, block, contains in cases:
        _write_yml(control, header + block)
        _expect_invalid(control, contains)
        assert not (control / "Saved").exists(), name
    print("[VERIFY] VC-005 relative/null/non-list/non-string rejected")


def test_config_shape_rejects_duplicates_nested_and_root_overlap(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    nested_extra = extra / "child"
    nested_extra.mkdir()
    inside_game = game / "sub"
    header = f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n"
    cases = (
        ("duplicate-separator", f"  - '{extra}'\n  - '{extra}{os.sep}'\n", "duplicates"),
        ("duplicate-case", f"  - '{extra}'\n  - '{str(extra).upper()}'\n", "duplicates"),
        ("nested-pair", f"  - '{extra}'\n  - '{nested_extra}'\n", "nested"),
        ("equals-control", f"  - '{control}'\n", "control"),
        ("inside-game", f"  - '{inside_game}'\n", "game"),
        ("equals-engine", f"  - '{engine}'\n", "engine"),
        ("contains-control", f"  - '{control.parent}'\n", "control"),
    )
    for _name, body, contains in cases:
        _write_yml(control, header + "additional_write_roots:\n" + body)
        _expect_invalid(control, ("additional_write_roots", contains))
    print("[VERIFY] VC-005 duplicate/nested/control-game-engine overlap rejected")


def test_config_shape_env_overlay_is_checked_against_final_roots(tmp_path: pathlib.Path) -> None:
    control, game, extra, other_game = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "saved"), _root(tmp_path, "other-game"),
    )
    _write_yml(control, _dual_top(control, game, game, extra))
    # MW_TARGET_GAME points at a directory that contains the declared root.
    with pytest.raises(mc.TargetConfigError) as ei:
        mc.load_target_config(control, env={mc.ENV_TARGET_GAME: str(tmp_path)})
    assert ei.value.kind == "invalid-config"
    assert "game" in str(ei.value) and "additional_write_roots" in str(ei.value)
    # MW_TARGET_ENGINE equals the declared root.
    with pytest.raises(mc.TargetConfigError) as ei:
        mc.load_target_config(control, env={mc.ENV_TARGET_ENGINE: str(extra)})
    assert ei.value.kind == "invalid-config"
    assert "engine" in str(ei.value)
    # A final game root outside the declaration stays accepted.
    config = mc.load_target_config(control, env={mc.ENV_TARGET_GAME: str(other_game)})
    assert config["game_root"] == str(other_game.resolve())
    assert config["additional_write_roots"] == [str(extra.resolve())]
    print("[VERIFY] VC-006 env overlay validated on final roots")


def test_config_shape_normalizes_short_long_and_case_spellings(tmp_path: pathlib.Path) -> None:
    control, game = _root(tmp_path, "control"), _root(tmp_path, "game")
    extra = _root(tmp_path, "saved")
    want = str(extra.resolve())
    spellings = [str(extra), str(extra.resolve())]
    if os.name == "nt":
        spellings += [str(extra).upper(), str(extra) + os.sep, _short_path(extra)]
    for spelling in spellings:
        _write_yml(
            control,
            f"mode: dual\ngame: '{game}'\nadditional_write_roots:\n  - '{spelling}'\n",
        )
        config = mc.load_target_config(control, env={})
        assert config["additional_write_roots"] == [want], spelling
    print("[VERIFY] VC-017 short/long/case spellings normalize to one root")


def test_config_shape_junction_root_to_engine_and_game_is_rejected(tmp_path: pathlib.Path) -> None:
    control, game, engine = _root(tmp_path, "control"), _root(tmp_path, "game"), _root(tmp_path, "engine")
    base = pathlib.Path(tempfile.mkdtemp(prefix="mw-additional-roots-junction-"))
    to_engine, to_game = base / "engine-link", base / "game-link"
    try:
        _junction(to_engine, engine)
        _junction(to_game, game)
        for link, label in ((to_engine, "engine"), (to_game, "game")):
            _write_yml(
                control,
                f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n"
                f"additional_write_roots:\n  - '{link}'\n",
            )
            _expect_invalid(control, ("additional_write_roots", label))
    finally:
        _unlink_junction(to_engine)
        _unlink_junction(to_game)
        shutil.rmtree(base, ignore_errors=True)
    print("[VERIFY] VC-016 junction root to Engine/Game rejected (real %TEMP% junction)")


# ── dispatch / write face ────────────────────────────────────────────────────


def test_dispatch_write_face_roots_appends_extras_only_in_dual(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra, parent, part = (
        _root(tmp_path, name) for name in ("control", "game", "engine", "saved", "parent", "part")
    )
    _write_yml(control, _dual_block_v2(game, engine, extra))
    dual = mc.load_target_config(control, env={})
    assert dispatch.write_face_roots(control, dual) == [
        str(control.resolve()), str(game.resolve()), str(engine.resolve()), str(extra.resolve()),
    ]
    _write_yml(control, f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n")
    undeclared = mc.load_target_config(control, env={})
    assert dispatch.write_face_roots(control, undeclared) == [
        str(control.resolve()), str(game.resolve()), str(engine.resolve()),
    ]
    _write_yml(control, "active: single\n")
    assert dispatch.write_face_roots(control, mc.load_target_config(control, env={})) is None
    _write_yml(
        control,
        "active: partition\n"
        "partition:\n"
        f"  parent: '{parent}'\n"
        f"  partition: '{part}'\n",
    )
    partition = mc.load_target_config(control, env={})
    assert "additional_write_roots" not in partition
    assert dispatch.write_face_roots(control, partition) == [
        str(control.resolve()), str(part.resolve()), str(parent.resolve()),
    ]
    print("[VERIFY] VC-008 write_face_roots appends extras (single None, partition unchanged)")


def test_dispatch_accepts_declared_external_and_junction_rejection_codes(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra, outside = (
        _root(tmp_path, name) for name in ("control", "game", "engine", "saved", "outside")
    )
    _write_yml(control, _dual_block_v2(game, engine, extra))
    config = mc.load_target_config(control, env={})
    entry = str(extra / "src" / "a.cpp")
    face = dispatch.parse_workspace_write_face(
        control, f"write_face: '{entry}'\n", config
    )
    assert face.allow_entries == (entry.replace("\\", "/"),), face

    outside_entry = str(outside / "src" / "a.cpp")
    refused = dispatch.parse_workspace_write_face(
        control, f"write_face: '{outside_entry}'\n", config
    )
    assert getattr(refused, "code", None) == "write-face-outside-base", refused

    escape_entry = str(extra) + "/../outside.cpp"
    refused = dispatch.parse_workspace_write_face(
        control, f"write_face: '{escape_entry}'\n", config
    )
    assert getattr(refused, "code", None) == "write-face-escape", refused

    link = extra / "engine-link"
    _junction(link, engine)
    try:
        refused = dispatch.parse_workspace_write_face(
            control, f"write_face: '{link / 'Logs' / 'run.txt'}'\n", config
        )
        assert getattr(refused, "code", None) == "write-face-read-only", refused
    finally:
        _unlink_junction(link)
    print("[VERIFY] VC-009/016 declared external allowed; outside/escape/read-only preserved")


# ── profile / show / fingerprint ────────────────────────────────────────────


def test_profile_and_show_render_extra_roots_conditionally(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    _write_yml(control, _dual_block_v2(game, engine, extra))
    config = mc.load_target_config(control, env={})
    lines = mc.render_dual_profile_md(config).splitlines()
    expected_root = str(extra.resolve())
    index = lines.index(f"Engine root: {engine.resolve()}")
    assert lines[index + 1] == "Additional write roots:"
    assert lines[index + 2] == f"- {expected_root}"

    mw._print_target_summary(config)
    out = capsys.readouterr().out
    assert f"[mw target] additional write root: {expected_root}" in out.splitlines()

    _write_yml(control, f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n")
    plain = mc.load_target_config(control, env={})
    assert "Additional write roots:" not in mc.render_dual_profile_md(plain)
    mw._print_target_summary(plain)
    assert "additional write root" not in capsys.readouterr().out
    print("[VERIFY] VC-010/012 profile and target show render conditionally")


def test_target_show_golden_is_byte_stable_without_declaration(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    control = _root(tmp_path, "control")
    (control / "game").mkdir()
    (control / "game" / "MyGame.uproject").write_text("{}", encoding="utf-8")
    (control / "engine").mkdir()
    (control / "docs").mkdir()
    (control / "docs" / "contract-notes.md").write_text("# contract notes\n", encoding="utf-8")
    _write_yml(control, DUAL_YML)
    config = mc.load_target_config(control, env={})
    assert "additional_write_roots" not in config
    assert len(mc.render_dual_profile_md(config).splitlines()) == 33
    assert mw._target_show(control) == 0
    actual = capsys.readouterr().out.replace(str(control.resolve()), "<CTRL>")
    golden = json.loads((GOLDEN_DIR / "dual.json").read_text(encoding="utf-8"))
    expected = golden["e_target_show_stdout"].replace("\r\n", "\n")
    assert actual.replace("\r\n", "\n") == expected
    print("[VERIFY] VC-010/022 undeclared profile/show byte-stable")


def test_probe_fingerprint_moves_only_when_declared(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    _write_yml(control, f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n")
    plain = mc.load_target_config(control, env={})
    plain_fingerprint = json.loads(mc._probe_fingerprint(plain))
    assert [key for key, _ in plain_fingerprint["roots"]] == ["engine", "game", "parent", "partition"]

    _write_yml(control, _dual_block_v2(game, engine, extra))
    declared = mc.load_target_config(control, env={})
    declared_fingerprint = json.loads(mc._probe_fingerprint(declared))
    assert ["additional:0", str(extra.resolve())] in declared_fingerprint["roots"]
    assert mc._probe_fingerprint(declared) != mc._probe_fingerprint(plain)

    # doctor `config` section keeps the frozen key set in both shapes.
    _write_yml(control, f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n")
    bare_keys = sorted(mc._doctor_target(control)["config"])
    _write_yml(control, _dual_block_v2(game, engine, extra))
    declared_keys = sorted(mc._doctor_target(control)["config"])
    assert declared_keys == bare_keys
    print("[VERIFY] VC-011 fingerprint moves only with a declaration; doctor keys frozen")


# ── CLI promote / fail-closed / migration ───────────────────────────────────


def _partition_args(project: pathlib.Path, parent: pathlib.Path) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), partition_action="set",
        parent=str(parent), partition=str(project), root=None, vcs=None,
    )


def test_cli_target_off_promotes_top_level_roots_into_dual_block(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra = (
        _root(tmp_path, "control"), _root(tmp_path, "game"),
        _root(tmp_path, "engine"), _root(tmp_path, "saved"),
    )
    yml = _write_yml(
        control,
        "# hand header\n"
        "active: dual\n"
        "additional_write_roots:\n"
        "  # keep this comment\n"
        f"  - '{extra}'\n"
        f"dual:\n  game: '{game}'\n  engine: '{engine}'\n",
    )
    assert mw._target_off(control) == 0
    text = yml.read_text(encoding="utf-8")
    assert "# hand header" in text
    assert "# keep this comment" in text
    assert any(line.startswith("additional_write_roots:") for line in text.splitlines()) is False
    raw = mc._tc_read_target_yml(str(control))
    assert raw["active"] == "single"
    assert raw["dual"]["additional_write_roots"] == [str(extra.resolve())]
    config = mc.load_target_config(control, env={})
    assert config["mode"] == "single"
    print("[VERIFY] VC-012 target off promotes before writing; config re-readable")


def test_cli_target_off_and_partition_set_fail_closed_on_bad_layouts(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra, parent, part = (
        _root(tmp_path, name)
        for name in ("control", "game", "engine", "saved", "parent", "part")
    )
    both = _write_yml(
        control,
        "active: dual\n"
        "additional_write_roots:\n"
        f"  - '{extra}'\n"
        f"dual:\n  game: '{game}'\n  engine: '{engine}'\n"
        "  additional_write_roots:\n"
        f"    - '{extra}'\n",
    )
    before = both.read_bytes()
    assert mw._target_off(control) == 1
    assert both.read_bytes() == before
    assert mw._partition_set(control, _partition_args(control, parent)) == 1
    assert both.read_bytes() == before

    flow = _write_yml(
        control,
        f"active: dual\nadditional_write_roots: ['{extra}']\n"
        f"dual:\n  game: '{game}'\n  engine: '{engine}'\n"
        f"partition:\n  parent: '{parent}'\n  partition: '{part}'\n",
    )
    before = flow.read_bytes()
    assert mw._target_clear(control) == 1
    assert flow.read_bytes() == before
    assert mw._partition_on(control) == 1
    assert flow.read_bytes() == before
    assert mw._partition_clear(control) == 1
    assert flow.read_bytes() == before

    missing = _write_yml(
        control,
        f"active: dual\nadditional_write_roots:\n  - '{extra}'\n"
        f"partition:\n  parent: '{parent}'\n  partition: '{part}'\n",
    )
    before = missing.read_bytes()
    assert mw._target_off(control) == 1
    assert missing.read_bytes() == before
    assert mw._partition_on(control) == 1
    assert missing.read_bytes() == before
    assert mw._partition_clear(control) == 1
    assert missing.read_bytes() == before
    assert mw._target_clear(control) == 1
    assert missing.read_bytes() == before
    print("[VERIFY] VC-012 unsupported layouts fail closed with zero writes")


def test_cli_clear_promotes_then_removes_the_block(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra, parent, part = (
        _root(tmp_path, name) for name in ("control", "game", "engine", "saved", "parent", "part")
    )
    yml = _write_yml(
        control,
        f"active: dual\nadditional_write_roots:\n  - '{extra}'\n"
        f"dual:\n  game: '{game}'\n  engine: '{engine}'\n"
        f"partition:\n  parent: '{parent}'\n  partition: '{part}'\n",
    )
    assert mw._target_clear(control) == 0
    text = yml.read_text(encoding="utf-8")
    assert "dual:" not in text
    assert "additional_write_roots" not in text
    assert mc.load_target_config(control, env={})["mode"] == "single"

    _write_yml(
        control,
        f"active: partition\nadditional_write_roots:\n  - '{extra}'\n"
        f"dual:\n  game: '{game}'\n  engine: '{engine}'\n"
        f"partition:\n  parent: '{parent}'\n  partition: '{part}'\n",
    )
    assert mw._partition_clear(control) == 0
    text = yml.read_text(encoding="utf-8")
    assert "partition:" not in text
    raw = mc._tc_read_target_yml(str(control))
    assert raw["active"] == "single"
    assert raw["dual"]["additional_write_roots"] == [str(extra.resolve())]
    assert mc.load_target_config(control, env={})["mode"] == "single"
    print("[VERIFY] VC-012 clear promotes/removes without leaving an unscoped declaration")


def test_cli_partition_set_promotes_v2_and_migrates_v1(tmp_path: pathlib.Path) -> None:
    control, game, engine, extra, parent, part = (
        _root(tmp_path, name) for name in ("control", "game", "engine", "saved", "parent", "part")
    )
    yml = _write_yml(control, _dual_top_v2(game, engine, extra))
    args = argparse.Namespace(
        project=str(control), partition_action="set",
        parent=str(parent), partition=str(part), root=None, vcs=None,
    )
    assert mw._partition_set(control, args) == 0
    raw = mc._tc_read_target_yml(str(control))
    assert raw["active"] == "partition"
    assert "additional_write_roots" not in raw
    assert raw["dual"]["additional_write_roots"] == [str(extra.resolve())]
    assert mc.load_target_config(control, env={})["mode"] == "partition"

    # v1 -> v2 migration keeps the declaration inside the generated block.
    control_v1 = _root(tmp_path, "control-v1")
    yml_v1 = _write_yml(control_v1, _dual_top(control_v1, game, engine, extra))
    args_v1 = argparse.Namespace(
        project=str(control_v1), partition_action="set",
        parent=str(parent), partition=str(part), root=None, vcs=None,
    )
    assert mw._partition_set(control_v1, args_v1) == 0
    migrated = mc._tc_read_target_yml(str(control_v1))
    assert migrated["active"] == "partition"
    assert migrated["dual"]["additional_write_roots"] == [str(extra.resolve())]
    assert yml_v1.with_name("target.yml.bak").exists()
    assert mc.load_target_config(control_v1, env={})["mode"] == "partition"
    print("[VERIFY] VC-012 partition set promotes v2 and migrates v1 declarations")


def test_cli_partition_on_promotes_and_target_on_keeps_block_declaration(
    tmp_path: pathlib.Path,
) -> None:
    control, game, engine, extra, parent, part = (
        _root(tmp_path, name) for name in ("control", "game", "engine", "saved", "parent", "part")
    )
    _write_yml(
        control,
        f"active: single\nadditional_write_roots:\n  - '{extra}'\n"
        f"dual:\n  game: '{game}'\n  engine: '{engine}'\n"
        f"partition:\n  parent: '{parent}'\n  partition: '{part}'\n",
    )
    assert mw._partition_on(control) == 0
    raw = mc._tc_read_target_yml(str(control))
    assert raw["active"] == "partition"
    assert raw["dual"]["additional_write_roots"] == [str(extra.resolve())]
    assert mc.load_target_config(control, env={})["mode"] == "partition"

    # `mw target on` never leaves dual: the canonical block declaration stays.
    _write_yml(control, _dual_block_v2(game, engine, extra))
    assert mw._target_on(control) == 0
    raw = mc._tc_read_target_yml(str(control))
    assert raw["active"] == "dual"
    assert raw["dual"]["additional_write_roots"] == [str(extra.resolve())]
    config = mc.load_target_config(control, env={})
    assert config["mode"] == "dual"
    assert config["additional_write_roots"] == [str(extra.resolve())]

    # `mw target set` edits bootstrap scalars only; the hand-written section
    # inside the dual block survives and the config stays loadable.
    assert mw.cmd_target(
        argparse.Namespace(
            project=str(control), target_action="set", game=str(game),
            engine=str(engine), vcs="git", uproject=None,
        )
    ) == 0
    raw = mc._tc_read_target_yml(str(control))
    assert raw["dual"]["additional_write_roots"] == [str(extra.resolve())]
    assert mc.load_target_config(control, env={})["additional_write_roots"] == [
        str(extra.resolve())
    ]
    print("[VERIFY] VC-012 partition on promotes; target on/set keep the block declaration")
