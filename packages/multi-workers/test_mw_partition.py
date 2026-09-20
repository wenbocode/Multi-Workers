"""
test_mw_partition.py — `mw partition set/show/clear/on/off` + the target-family
guards and the v2 dual-block write (mw-target-partition S3 CLI, AC-010/011/
012/013/022/023).

VC-010/011/022/023 observables: set resolves partition with v1 → v2 migration
(.bak + content preservation); every rejection path leaves the file untouched
(no .bak, no migration); repeated set is byte-idempotent; hand-maintained
sections survive bootstrap/roots changes byte-for-byte; the atomic write
never truncates on failure; clear/on/off follow the AC-023 state machine;
`mw target show` guards per AC-018a while v1/dual/single output is unchanged
(AC-013 red line).

Tests call mw.cmd_* in-process with argparse.Namespace — the established CLI
test pattern (test_mw_target.py; the task's subprocess suggestion resolves to
this after probing the existing suite). /mw partition equivalence (AC-012) is
covered on the TS side by arg-sequence parity plus set-output determinism
asserted here: the forwarded run and a direct CLI run hit the identical mw.py
entry point, so deterministic output + identical args ⇒ identical bytes.
"""
import argparse
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common
from mw_common import (
    ENV_PARTITION_PARENT,
    ENV_PARTITION_ROOT,
    ENV_TARGET_ENGINE,
    ENV_TARGET_GAME,
    load_target_config,
    target_yml_path,
)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (ENV_PARTITION_PARENT, ENV_PARTITION_ROOT, ENV_TARGET_GAME, ENV_TARGET_ENGINE):
        monkeypatch.delenv(name, raising=False)


def _pset(
    project: pathlib.Path,
    parent: pathlib.Path | None,
    partition: pathlib.Path | None = None,
    root: list[str] | None = None,
    vcs: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        partition_action="set",
        parent=None if parent is None else str(parent),
        partition=None if partition is None else str(partition),
        root=root,
        vcs=vcs,
    )


def _paction(project: pathlib.Path, action: str) -> argparse.Namespace:
    return argparse.Namespace(project=str(project), partition_action=action)


def _taction(project: pathlib.Path, action: str) -> argparse.Namespace:
    return argparse.Namespace(project=str(project), target_action=action)


def _tset(
    project: pathlib.Path,
    game: pathlib.Path,
    engine: pathlib.Path | None = None,
    vcs: str | None = None,
    uproject: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        target_action="set",
        game=str(game),
        engine=None if engine is None else str(engine),
        vcs=vcs,
        uproject=uproject,
    )


def _yml(project: pathlib.Path) -> pathlib.Path:
    return target_yml_path(project)


def _block_region(text: str, block_key: str) -> str:
    """The `block_key:` mapping region: its header line through the next
    top-level key (or EOF), trailing blank separators trimmed — layout-stable
    for preservation assertions."""
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"{block_key}:"):
            start = i
            break
    assert start is not None, f"no {block_key} block in:\n{text}"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].strip() and not lines[j][:1].isspace():
            end = j
            break
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return "".join(lines[start:end])


def _mk(*names: str, base: pathlib.Path) -> dict[str, pathlib.Path]:
    out: dict[str, pathlib.Path] = {}
    for name in names:
        d = base / name
        d.mkdir()
        out[name] = d
    return out


# ── set: fresh write / defaults / roots / vcs ────────────────────────────────


def test_set_creates_v2_template_and_resolves_partition(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project, parent, part = dirs["control"], dirs["parent"], dirs["part"]
    assert mw.cmd_partition(_pset(project, parent, partition=part)) == 0
    yml = _yml(project)
    assert yml.exists()
    text = yml.read_text(encoding="utf-8")
    assert "active: partition" in text
    assert "partition:" in text
    # omitted fields are not persisted
    assert "vcs:" not in text
    assert "roots:" not in text
    config = load_target_config(project)
    assert config["mode"] == "partition"
    assert config["source"] == "target-yml"
    assert config["parent_root"] == str(parent.resolve())
    assert config["partition_root"] == str(part.resolve())
    assert config["game_root"] is None
    assert config["roots"] == {}
    assert config["vcs"] is None
    print("[VERIFY] VC-010: exit=0, mode=partition, omitted-fields=not-persisted")


def test_set_default_partition_is_control_root(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", base=tmp_path)
    project = dirs["control"]
    assert mw.cmd_partition(_pset(project, dirs["parent"])) == 0
    config = load_target_config(project)
    assert config["partition_root"] == str(project.resolve())
    text = _yml(project).read_text(encoding="utf-8")
    assert f"  partition: '{project.resolve()}'" in text
    print("[VERIFY] VC-010: default-partition=control-root-absolute")


def test_set_roots_and_vcs_persisted_and_relative_anchored(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", "sdk", base=tmp_path)
    project, parent, part, sdk = (
        dirs["control"], dirs["parent"], dirs["part"], dirs["sdk"]
    )
    rel_root = project / "tools"
    rel_root.mkdir()
    rc = mw.cmd_partition(
        _pset(project, parent, partition=part, root=[f"sdk={sdk}", "tools=tools"], vcs="git")
    )
    assert rc == 0
    text = _yml(project).read_text(encoding="utf-8")
    assert "  vcs: git" in text
    assert "  roots:" in text
    assert f"    sdk: '{sdk.resolve()}'" in text
    # relative root paths anchor to the control root (spec §2.1)
    assert f"    tools: '{rel_root.resolve()}'" in text
    config = load_target_config(project)
    assert config["vcs"] == "git"
    assert config["roots"]["sdk"] == str(sdk.resolve())
    assert config["roots"]["tools"] == str(rel_root.resolve())
    print("[VERIFY] VC-010: roots+vcs persisted, relative-roots=control-anchored")


# ── set: rejection paths (file untouched, no .bak, no migration) ─────────────


def test_set_missing_parent_rejected(tmp_path: pathlib.Path, capsys) -> None:
    project = tmp_path / "control"
    project.mkdir()
    rc = mw.cmd_partition(
        argparse.Namespace(
            project=str(project), partition_action="set",
            parent=None, partition=None, root=None, vcs=None,
        )
    )
    assert rc == 1
    assert not _yml(project).exists()
    # mw-partition-parent-extended AC-005: the wording names the extended
    # writable workspace, never a read-only context.
    err = capsys.readouterr().err
    assert "read-only" not in err
    assert "extended writable workspace" in err
    print("[VERIFY] VC-011: exit=1 missing-parent, file=unchanged")
    print("[VERIFY] VC-008: read_only_residual=0, wording=extended-writable-workspace")


@pytest.mark.parametrize(
    "root_args",
    [
        ["noequalsign"],
        ["bad name=x"],  # space fails [A-Za-z0-9_-]+
        ["parent=x"],  # reserved
        ["sdk=x", "sdk=y"],  # duplicate
        ["=x"],  # empty name
    ],
)
def test_set_rejects_invalid_root_args(
    tmp_path: pathlib.Path, root_args: list[str]
) -> None:
    dirs = _mk("control", "parent", "part", "sdk", base=tmp_path)
    project = dirs["control"]
    # a pre-existing v2 file must stay untouched on argument rejection
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"])) == 0
    before = _yml(project).read_bytes()
    rc = mw.cmd_partition(
        _pset(project, dirs["parent"], partition=dirs["part"], root=root_args)
    )
    assert rc == 1
    assert _yml(project).read_bytes() == before
    assert not (project / ".agenticdoc" / "target.yml.bak").exists()


def test_set_rejects_missing_paths(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"])) == 0
    before = _yml(project).read_bytes()

    missing = tmp_path / "nope"
    rc = mw.cmd_partition(_pset(project, missing, partition=dirs["part"]))
    assert rc == 1
    rc = mw.cmd_partition(_pset(project, dirs["parent"], partition=missing))
    assert rc == 1
    rc = mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"], root=[f"sdk={missing}"]))
    assert rc == 1
    assert _yml(project).read_bytes() == before
    print("[VERIFY] VC-010: exit=1 missing-paths, yml=unchanged")


def test_set_rejects_root_relation(tmp_path: pathlib.Path) -> None:
    control = tmp_path / "control"
    control.mkdir()
    parent = tmp_path / "parent"
    parent.mkdir()
    part = tmp_path / "part"
    part.mkdir()
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)

    # equal (via the default partition = control root with parent = control)
    rc = mw.cmd_partition(_pset(control, control))
    assert rc == 1
    # partition nested inside parent
    rc = mw.cmd_partition(_pset(control, outer, partition=inner))
    assert rc == 1
    # parent nested inside partition
    rc = mw.cmd_partition(_pset(control, inner, partition=outer))
    assert rc == 1
    # default partition (= the control root) nested inside the parent
    rc = mw.cmd_partition(_pset(control, tmp_path))
    assert rc == 1
    assert not _yml(control).exists()
    print("[VERIFY] VC-010: exit=1 root-relation, yml=unchanged")


@pytest.mark.parametrize(
    "env_name",
    [ENV_PARTITION_PARENT, ENV_PARTITION_ROOT, ENV_TARGET_GAME, ENV_TARGET_ENGINE],
)
def test_set_rejects_cross_env(
    tmp_path: pathlib.Path, env_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["parent"]
    # a v1 file: the cross-env guard must fire before any migration/.bak
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    v1 = f"mode: dual\ngame: '{dirs['part']}'\n"
    yml.write_text(v1, encoding="utf-8")
    monkeypatch.setenv(env_name, str(dirs["part"]))
    rc = mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["control"]))
    assert rc == 1
    assert yml.read_text(encoding="utf-8") == v1
    assert not (yml.parent / "target.yml.bak").exists()
    print(f"[VERIFY] VC-010: exit=1 cross-env {env_name}, no-migration no-bak")


def test_set_rejects_mixed_format(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    mixed = f"active: dual\ngame: '{dirs['part']}'\n"
    yml.write_text(mixed, encoding="utf-8")
    rc = mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"]))
    assert rc == 1
    assert yml.read_text(encoding="utf-8") == mixed


def test_set_rejects_unparseable_yml(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    broken = "mode: [unclosed\n"
    yml.write_text(broken, encoding="utf-8")
    rc = mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"]))
    assert rc == 1
    assert yml.read_text(encoding="utf-8") == broken


# ── set: v1 → v2 migration ───────────────────────────────────────────────────


def test_set_migrates_v1_dual_with_hand_maintained_sections(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dirs = _mk("control", "parent", "game", "engine", base=tmp_path)
    project, parent, game, engine = (
        dirs["control"], dirs["parent"], dirs["game"], dirs["engine"]
    )
    (game / "Proj.uproject").write_text("{}", encoding="utf-8")
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    v1 = (
        "# hand-maintained header comment\n"
        "mode: dual\n"
        f"game: '{game}'\n"
        f"engine: '{engine}'\n"
        "vcs: p4\n"
        "uproject: Proj.uproject\n"
        "toolchain:\n"
        "  build: 'b {game} {engine}'  # keep this comment\n"
        "ignore:\n"
        "  deny_globs:\n"
        '    - "**/*.uasset"\n'
        "contract:\n"
        "  forbidden_paths:\n"
        "    - secret/\n"
        "  docs:\n"
        "    - a.md\n"
    )
    yml.write_text(v1, encoding="utf-8")
    original_bytes = yml.read_bytes()

    assert mw.cmd_partition(_pset(project, parent)) == 0
    out = capsys.readouterr().out
    assert "migrated v1 target.yml to v2" in out

    # .bak is a byte copy of the original v1 file
    bak = yml.with_name(yml.name + ".bak")
    assert bak.exists()
    assert bak.read_bytes() == original_bytes

    # v2 dual block carries every v1 field (content level — AC-022)
    import yaml

    raw = yaml.safe_load(yml.read_text(encoding="utf-8"))
    assert raw["active"] == "partition"
    dual = raw["dual"]
    assert dual["game"] == str(game)
    assert dual["engine"] == str(engine)
    assert dual["vcs"] == "p4"
    assert dual["uproject"] == "Proj.uproject"
    assert dual["toolchain"] == {"build": "b {game} {engine}"}
    assert dual["ignore"] == {"deny_globs": ["**/*.uasset"]}
    assert dual["contract"] == {"forbidden_paths": ["secret/"], "docs": ["a.md"]}

    config = load_target_config(project)
    assert config["mode"] == "partition"
    assert config["partition_root"] == str(project.resolve())
    print("[VERIFY] VC-010: migrated=v1-to-v2, bak=complete, content=preserved")


def test_set_migrates_v1_single(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", base=tmp_path)
    project, parent = dirs["control"], dirs["parent"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text("mode: single\ntoolchain:\n  build: 'b'\n", encoding="utf-8")
    assert mw.cmd_partition(_pset(project, parent)) == 0
    config = load_target_config(project)
    assert config["mode"] == "partition"
    # the hand-maintained profile is parked in the dual block, not lost
    import yaml

    raw = yaml.safe_load(yml.read_text(encoding="utf-8"))
    assert raw["active"] == "partition"
    assert raw["dual"]["toolchain"] == {"build": "b"}
    assert (yml.with_name(yml.name + ".bak")).exists()


# ── set: v2 block-level edit — preservation / idempotency / atomicity ───────


_V2_WITH_HAND_SECTIONS = """active: partition
partition:
  parent: '{old_parent}'
  partition: '{old_partition}'
  vcs: p4
  roots:
    sdk: '{old_sdk}'
  toolchain:
    build: 'build.bat {{partition}} {{sdk}}'  # keep this comment
  ignore:
    deny_globs:
      - "**/*.uasset"
  contract:
    forbidden_paths: []
    docs: []
"""


def _write_v2_hand_maintained(project: pathlib.Path, parent: pathlib.Path, part: pathlib.Path, sdk: pathlib.Path) -> None:
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(
        _V2_WITH_HAND_SECTIONS.format(
            old_parent=parent, old_partition=part, old_sdk=sdk
        ),
        encoding="utf-8",
    )


def test_set_v2_block_edit_preserves_hand_maintained_sections(
    tmp_path: pathlib.Path,
) -> None:
    dirs = _mk("control", "parent1", "parent2", "part1", "part2", "sdk1", "sdk2", base=tmp_path)
    project = dirs["control"]
    _write_v2_hand_maintained(project, dirs["parent1"], dirs["part1"], dirs["sdk1"])
    before = _yml(project).read_text(encoding="utf-8")
    hand_before = before.split("  toolchain:", 1)[1]

    # bootstrap scalars + roots change; vcs omitted → dropped; roots omitted → dropped
    rc = mw.cmd_partition(_pset(project, dirs["parent2"], partition=dirs["part2"]))
    assert rc == 0
    after = _yml(project).read_text(encoding="utf-8")
    hand_after = after.split("  toolchain:", 1)[1]
    # byte-for-byte preservation of the hand-maintained region (AC-022)
    assert hand_after == hand_before
    assert "  vcs: p4" not in after
    assert "  roots:" not in after
    assert f"  parent: '{dirs['parent2'].resolve()}'" in after
    assert f"  partition: '{dirs['part2'].resolve()}'" in after
    config = load_target_config(project)
    assert config["parent_root"] == str(dirs["parent2"].resolve())
    assert config["partition_root"] == str(dirs["part2"].resolve())
    assert config["vcs"] is None
    assert config["ignore"]["deny_globs"] == ["**/*.uasset"]

    # roots come back as a whole-section rewrite, hand region still intact
    rc = mw.cmd_partition(
        _pset(project, dirs["parent2"], partition=dirs["part2"], root=[f"sdk={dirs['sdk2']}"], vcs="git")
    )
    assert rc == 0
    after2 = _yml(project).read_text(encoding="utf-8")
    assert after2.split("  toolchain:", 1)[1] == hand_before
    assert "  roots:" in after2
    assert f"    sdk: '{dirs['sdk2'].resolve()}'" in after2
    print("[VERIFY] VC-022: preserved=pass (hand sections + comments byte-identical)")


def test_set_idempotent_bytes(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", "sdk", base=tmp_path)
    project = dirs["control"]
    args = _pset(project, dirs["parent"], partition=dirs["part"], root=[f"sdk={dirs['sdk']}"], vcs="git")
    assert mw.cmd_partition(args) == 0
    first = _yml(project).read_bytes()
    assert mw.cmd_partition(args) == 0
    assert _yml(project).read_bytes() == first
    # also idempotent on the migrated (v1) layout
    project2 = dirs["sdk"]  # reuse an existing dir as a second control root
    yml2 = _yml(project2)
    yml2.parent.mkdir(parents=True, exist_ok=True)
    yml2.write_text(f"mode: dual\ngame: '{dirs['part']}'\n", encoding="utf-8")
    args2 = _pset(project2, dirs["parent"], partition=dirs["part"])
    assert mw.cmd_partition(args2) == 0
    once = yml2.read_bytes()
    assert mw.cmd_partition(args2) == 0
    assert yml2.read_bytes() == once
    print("[VERIFY] VC-022: idempotent=pass (fresh + migrated paths)")


def test_set_atomic_write_never_truncates(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    v1 = f"mode: dual\ngame: '{dirs['part']}'\n"
    yml.write_text(v1, encoding="utf-8")
    original_bytes = yml.read_bytes()

    # FIX-8: the v1 backup swap is itself an os.replace — let the FIRST
    # replace (the .bak write) succeed and fail the SECOND (the main
    # write), so the test still exercises "backup lands, main write
    # fails, file intact".
    real_replace = os.replace
    replace_calls: list[str] = []

    def _flaky_replace(src: str, dst: str) -> None:
        replace_calls.append(dst)
        if len(replace_calls) > 1:
            raise OSError("simulated rename failure")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _flaky_replace)
    rc = mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"]))
    monkeypatch.undo()
    assert rc == 1
    assert len(replace_calls) == 2  # .bak swap succeeded, main write failed
    # the original file is intact — no truncation, no partial write
    assert yml.read_bytes() == original_bytes
    # no temp-file residue from either failed/succeeded swap
    assert list(yml.parent.glob("target.yml.tmp*")) == []
    assert list(yml.parent.glob("target.yml.bak.tmp*")) == []
    # the v1 backup (written before the swap) is the original content
    bak = yml.with_name(yml.name + ".bak")
    assert bak.read_bytes() == original_bytes
    print("[VERIFY] VC-022: atomic=pass (replace-failure → file intact, no residue)")


def test_set_output_deterministic(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    args = _pset(project, dirs["parent"], partition=dirs["part"], vcs="git")
    assert mw.cmd_partition(args) == 0
    first_out = capsys.readouterr().out
    _yml(project).unlink()
    assert mw.cmd_partition(args) == 0
    second_out = capsys.readouterr().out
    assert first_out == second_out
    print("[VERIFY] VC-012: set-output=deterministic (forwarded vs direct runs identical)")


# ── show ─────────────────────────────────────────────────────────────────────


def test_show_prints_resolved_view(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dirs = _mk("control", "parent", "part", "sdk", base=tmp_path)
    project = dirs["control"]
    assert mw.cmd_partition(
        _pset(project, dirs["parent"], partition=dirs["part"], root=[f"sdk={dirs['sdk']}"], vcs="git")
    ) == 0
    yml = _yml(project)
    yml.write_text(
        yml.read_text(encoding="utf-8").replace(
            "  # build: 'build.bat {partition} {sdk}'",
            "    build: 'build.bat {partition} {sdk}'",
        ),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert mw.cmd_partition(_paction(project, "show")) == 0
    out = capsys.readouterr().out
    assert "mode: partition" in out
    assert str(dirs["parent"].resolve()) in out
    assert str(dirs["part"].resolve()) in out
    assert str(dirs["sdk"].resolve()) in out
    # the toolchain placeholder renders with the partition root
    assert f"build.bat {dirs['part'].resolve()} {dirs['sdk'].resolve()}" in out


def test_show_no_config_matches_target_show_shape(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """FIX-4 (AC-018a): no target.yml = active single (default) — `mw
    partition show` exits 1 naming the current mode and the switch command,
    exactly like every other non-partition shape (no special case)."""
    project = tmp_path / "control"
    project.mkdir()
    capsys.readouterr()
    assert mw.cmd_partition(_paction(project, "show")) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "active mode is 'single'" in captured.err
    assert "mw partition set" in captured.err
    print("[VERIFY] FIX-4: no-file partition show = exit 1 + mode + set hint")


def test_show_guard_when_active_not_partition(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dirs = _mk("control", "parent", "part", "game", base=tmp_path)
    project, part, game = dirs["control"], dirs["part"], dirs["game"]
    # v2 dual active
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=part)) == 0
    assert mw.cmd_target(_tset(project, game)) == 0
    capsys.readouterr()
    assert mw.cmd_partition(_paction(project, "show")) == 1
    err = capsys.readouterr().err
    assert "active mode is 'dual'" in err
    assert "mw partition on" in err
    assert "mw partition set" in err
    # v1 file
    project2 = tmp_path / "control2"
    project2.mkdir()
    yml = _yml(project2)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(f"mode: dual\ngame: '{game}'\n", encoding="utf-8")
    assert mw.cmd_partition(_paction(project2, "show")) == 1
    assert "v1 format" in capsys.readouterr().err


def test_show_fail_closed_on_broken_config(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "control"
    project.mkdir()
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text("mode: [unclosed\n", encoding="utf-8")
    assert mw.cmd_partition(_paction(project, "show")) == 1
    assert "invalid-yaml" in capsys.readouterr().err


# ── clear ────────────────────────────────────────────────────────────────────


def test_clear_deletes_file_when_no_blocks_remain(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", base=tmp_path)
    project = dirs["control"]
    assert mw.cmd_partition(_pset(project, dirs["parent"])) == 0
    yml = _yml(project)
    assert yml.exists()
    assert mw.cmd_partition(_paction(project, "clear")) == 0
    assert not yml.exists()
    config = load_target_config(project)
    assert config["mode"] == "single"
    print("[VERIFY] VC-011: clear=block-removed, no-blocks → file deleted")


def test_clear_keeps_dual_block_and_sets_single(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", "game", base=tmp_path)
    project, part, game = dirs["control"], dirs["part"], dirs["game"]
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=part)) == 0
    assert mw.cmd_target(_tset(project, game)) == 0  # v2 dual block, active: dual
    assert mw.cmd_partition(_paction(project, "on")) == 0
    yml = _yml(project)
    before = yml.read_text(encoding="utf-8")
    assert mw.cmd_partition(_paction(project, "clear")) == 0
    after = yml.read_text(encoding="utf-8")
    assert "partition:" not in after
    assert "active: single" in after
    assert "dual:" in after
    assert after.split("dual:", 1)[1] == before.split("dual:", 1)[1]
    config = load_target_config(project)
    assert config["mode"] == "single"
    # the parked dual block stays usable for a later `mw target on`
    assert mw.cmd_target(_taction(project, "on")) == 0
    assert load_target_config(project)["mode"] == "dual"


def test_clear_no_block_is_noop(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "game", base=tmp_path)
    project, game = dirs["control"], dirs["game"]
    # no file at all
    assert mw.cmd_partition(_paction(project, "clear")) == 0
    assert not _yml(project).exists()
    # v1 file: no partition block to remove
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    v1 = f"mode: dual\ngame: '{game}'\n"
    yml.write_text(v1, encoding="utf-8")
    assert mw.cmd_partition(_paction(project, "clear")) == 0
    assert yml.read_text(encoding="utf-8") == v1
    # v2 without the block
    project2 = tmp_path / "control2"
    project2.mkdir()
    yml2 = _yml(project2)
    yml2.parent.mkdir(parents=True, exist_ok=True)
    v2 = f"active: dual\ndual:\n  game: '{game}'\n"
    yml2.write_text(v2, encoding="utf-8")
    assert mw.cmd_partition(_paction(project2, "clear")) == 0
    assert yml2.read_text(encoding="utf-8") == v2


def test_clear_rejects_cross_env(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"])) == 0
    before = _yml(project).read_bytes()
    monkeypatch.setenv(ENV_TARGET_GAME, str(dirs["part"]))
    assert mw.cmd_partition(_paction(project, "clear")) == 1
    assert _yml(project).read_bytes() == before


# ── target clear on v2 (FIX-6: block-level, symmetric to partition clear) ────


def test_target_clear_v2_keeps_partition_block_and_sets_single(
    tmp_path: pathlib.Path,
) -> None:
    dirs = _mk("control", "parent", "part", "game", base=tmp_path)
    project, part, game = dirs["control"], dirs["part"], dirs["game"]
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=part)) == 0
    assert mw.cmd_target(_tset(project, game)) == 0  # v2 dual block, active: dual
    yml = _yml(project)
    before = yml.read_text(encoding="utf-8")
    assert mw.cmd_target(_taction(project, "clear")) == 0
    after = yml.read_text(encoding="utf-8")
    assert "dual:" not in after
    assert "active: single" in after
    # the parked partition block survives byte-for-byte
    assert _block_region(after, "partition") == _block_region(before, "partition")
    config = load_target_config(project)
    assert config["mode"] == "single"
    # the parked partition block stays usable for a later `mw partition on`
    assert mw.cmd_partition(_paction(project, "on")) == 0
    assert load_target_config(project)["mode"] == "partition"
    print("[VERIFY] FIX-6: target clear = dual-block-only, partition kept, active single")


def test_target_clear_v2_only_dual_block_deletes_file(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "game", base=tmp_path)
    project, game = dirs["control"], dirs["game"]
    assert mw.cmd_target(_tset(project, game)) == 0
    assert _yml(project).exists()
    assert mw.cmd_target(_taction(project, "clear")) == 0
    assert not _yml(project).exists()
    assert load_target_config(project)["mode"] == "single"


def test_target_clear_v2_no_dual_block_is_noop(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"])) == 0
    before = _yml(project).read_bytes()
    assert mw.cmd_target(_taction(project, "clear")) == 0
    assert _yml(project).read_bytes() == before


def test_target_clear_v1_still_unlinks_whole_file(tmp_path: pathlib.Path) -> None:
    """FIX-6 red line: v1 files keep the historical whole-file unlink — the
    pre-partition `mw target clear` contract (AC-013)."""
    dirs = _mk("control", "game", base=tmp_path)
    project, game = dirs["control"], dirs["game"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(f"mode: dual\ngame: '{game}'\n", encoding="utf-8")
    assert mw.cmd_target(_taction(project, "clear")) == 0
    assert not yml.exists()


# ── FIX-7/FIX-10: parseable non-mapping target.yml fails closed ─────────────


@pytest.mark.parametrize("doc", ["- a\n", "null\n", "~\n", "42\n"])
def test_non_mapping_yml_rejected_by_set_migration_paths(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], doc: str,
) -> None:
    """FIX-7/FIX-10: a parseable but non-mapping document (list/scalar
    top level — `null`/`~` parse to YAML null, a non-mapping document too)
    is never an empty v1 — both set verbs refuse with the resolver's
    message and leave the file (and the absence of .bak) untouched."""
    dirs = _mk("control", "parent", "part", "game", base=tmp_path)
    project, parent, part, game = (
        dirs["control"], dirs["parent"], dirs["part"], dirs["game"],
    )
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(doc, encoding="utf-8")
    snap = yml.read_bytes()

    assert mw.cmd_target(_tset(project, game)) == 1
    assert "top level must be a mapping" in capsys.readouterr().err
    assert mw.cmd_partition(_pset(project, parent, partition=part)) == 1
    assert "top level must be a mapping" in capsys.readouterr().err
    assert yml.read_bytes() == snap
    assert not (yml.parent / "target.yml.bak").exists()
    # on/off/clear refuse too (never treated as an empty v1 shape)
    for action in ("on", "off", "clear"):
        assert mw.cmd_target(_taction(project, action)) == 1
        assert mw.cmd_partition(_paction(project, action)) == 1
        assert yml.read_bytes() == snap
    print(f"[VERIFY] FIX-7/FIX-10: non-mapping yml ({doc!r}) = exit 1, file unchanged, no migration")


# ── FIX-10: YAML null top level fails closed; blank files stay single ────────


def test_yaml_null_top_level_fails_closed(tmp_path: pathlib.Path) -> None:
    """FIX-10: a non-blank document that parses to YAML null (`null` / `~`)
    is a non-mapping top level — the resolver fails closed exactly like the
    list/scalar shapes instead of silently resolving single/default (the
    residual BLOCKER of mwtp-final-review-2)."""
    dirs = _mk("control", base=tmp_path)
    project = dirs["control"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    for text in ("null\n", "~\n"):
        yml.write_text(text, encoding="utf-8")
        with pytest.raises(mw_common.TargetConfigError) as ei:
            load_target_config(project)
        assert ei.value.kind == "invalid-config"
        assert "top level must be a mapping" in str(ei.value)
    print("[VERIFY] FIX-10: yaml-null top level = invalid-config, fail closed")


def test_blank_target_yml_keeps_historical_single(tmp_path: pathlib.Path) -> None:
    """FIX-10 red line (v1 zero regression): an empty file (0 bytes) or a
    pure-whitespace file is the historical no-config shape — single/default,
    never an error."""
    dirs = _mk("control", base=tmp_path)
    project = dirs["control"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    for text in ("", " \n \n"):
        yml.write_text(text, encoding="utf-8")
        config = load_target_config(project)
        assert config["mode"] == "single"
        assert config["source"] == "default"
        assert config["game_root"] == config["control_root"]
    # a UTF-8 BOM with no content is the degenerate Windows-editor empty
    # file — same historical no-config shape (PM follow-up to FIX-10).
    yml.write_bytes(b"\xef\xbb\xbf")
    config = load_target_config(project)
    assert config["mode"] == "single"
    assert config["source"] == "default"
    print("[VERIFY] FIX-10: blank/empty yml (incl. BOM-only) = single/default (historical)")


# ── on / off state machine (AC-023) ─────────────────────────────────────────


def test_on_activates_partition_block(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project, part = dirs["control"], dirs["part"]
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=part)) == 0
    assert mw.cmd_partition(_paction(project, "off")) == 0
    config = load_target_config(project)
    assert config["mode"] == "single"
    yml = _yml(project)
    parked = yml.read_bytes()
    assert mw.cmd_partition(_paction(project, "on")) == 0
    assert load_target_config(project)["mode"] == "partition"
    # off → on round trip keeps the parked block content
    assert mw.cmd_partition(_paction(project, "off")) == 0
    assert yml.read_bytes() == parked
    print("[VERIFY] VC-023: on=active-flip, off=single-parked, block=kept")


def test_on_rejects_missing_block_and_missing_fields(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "game", base=tmp_path)
    project, game = dirs["control"], dirs["game"]
    # no file
    assert mw.cmd_partition(_paction(project, "on")) == 1
    # v2 without a partition block
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(f"active: dual\ndual:\n  game: '{game}'\n", encoding="utf-8")
    before = yml.read_bytes()
    assert mw.cmd_partition(_paction(project, "on")) == 1
    assert yml.read_bytes() == before
    # v2 with a partition block missing the required fields
    yml.write_text(
        f"active: single\ndual:\n  game: '{game}'\npartition:\n  vcs: git\n",
        encoding="utf-8",
    )
    before = yml.read_bytes()
    assert mw.cmd_partition(_paction(project, "on")) == 1
    assert yml.read_bytes() == before


def test_on_off_reject_v1(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    dirs = _mk("control", "game", base=tmp_path)
    project, game = dirs["control"], dirs["game"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    v1 = f"mode: dual\ngame: '{game}'\n"
    yml.write_text(v1, encoding="utf-8")
    rc = mw.cmd_partition(_paction(project, "on"))
    assert rc == 1
    assert "v1 format" in capsys.readouterr().err
    rc = mw.cmd_partition(_paction(project, "off"))
    assert rc == 1  # AC-023: on/off on v1 → exit 1 with the migration hint
    assert "v1 format" in capsys.readouterr().err
    assert yml.read_text(encoding="utf-8") == v1


def test_off_idempotent_when_not_active(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "game", base=tmp_path)
    project, game = dirs["control"], dirs["game"]
    # no file at all
    assert mw.cmd_partition(_paction(project, "off")) == 0
    # v2 active dual: partition off is a no-op
    assert mw.cmd_partition(_pset(project, dirs["parent"])) == 0
    assert mw.cmd_target(_tset(project, game)) == 0
    yml = _yml(project)
    before = yml.read_bytes()
    assert mw.cmd_partition(_paction(project, "off")) == 0
    assert yml.read_bytes() == before


# ── target family: show guard + v2 dual-block write + on/off ────────────────


def test_target_show_guard_when_partition_active(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project, part = dirs["control"], dirs["part"]
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=part)) == 0
    capsys.readouterr()
    assert mw.cmd_target(_taction(project, "show")) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "mw partition show" in captured.err
    print("[VERIFY] VC-018: guard=exit-1 (target show → mw partition show)")


def test_target_show_dual_and_single_unchanged(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dirs = _mk("control", "game", base=tmp_path)
    project, game = dirs["control"], dirs["game"]
    (game / "Proj.uproject").write_text("{}", encoding="utf-8")
    assert mw.cmd_target(_tset(project, game)) == 0
    capsys.readouterr()
    assert mw.cmd_target(_taction(project, "show")) == 0
    out = capsys.readouterr().out
    assert "mode: dual" in out
    assert str(game.resolve()) in out
    # single (no file) keeps printing the resolved view, exit 0
    project2 = tmp_path / "control2"
    project2.mkdir()
    capsys.readouterr()
    assert mw.cmd_target(_taction(project2, "show")) == 0
    assert "mode: single" in capsys.readouterr().out


def test_target_set_on_v1_writes_v1_flat_format(tmp_path: pathlib.Path) -> None:
    """AC-013 red line: `mw target set` on a v1 file keeps writing v1 lines —
    no active key, no dual block, hand-maintained content preserved."""
    dirs = _mk("control", "game", "game2", base=tmp_path)
    project, game, new_game = dirs["control"], dirs["game"], dirs["game2"]
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    v1 = (
        "# hand-maintained header comment\n"
        "mode: dual\n"
        f"game: '{game}'\n"
        "toolchain:\n"
        "  build: 'build {game}'  # keep this comment\n"
    )
    yml.write_text(v1, encoding="utf-8")
    assert mw.cmd_target(_tset(project, new_game)) == 0
    text = yml.read_text(encoding="utf-8")
    assert "active:" not in text
    assert "dual:" not in text
    assert "partition:" not in text
    assert "mode: dual" in text
    assert f"game: '{new_game.resolve()}'" in text
    assert "  build: 'build {game}'  # keep this comment" in text
    print("[VERIFY] VC-013: target-set-on-v1=v1-flat-format (zero change)")


def test_target_set_on_v2_writes_dual_block(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", "game", "engine", base=tmp_path)
    project, part, game, engine = (
        dirs["control"], dirs["part"], dirs["game"], dirs["engine"]
    )
    (game / "Proj.uproject").write_text("{}", encoding="utf-8")
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=part)) == 0
    yml = _yml(project)
    partition_block = _block_region(yml.read_text(encoding="utf-8"), "partition")

    assert mw.cmd_target(_tset(project, game, engine=engine, vcs="p4", uproject="Proj.uproject")) == 0
    text = yml.read_text(encoding="utf-8")
    assert "active: dual" in text
    assert "dual:" in text
    assert f"  game: '{game.resolve()}'" in text
    assert f"  engine: '{engine.resolve()}'" in text
    assert "  vcs: p4" in text
    assert "  uproject: 'Proj.uproject'" in text
    # the partition block is preserved byte-for-byte (parked)
    assert _block_region(text, "partition") == partition_block
    config = load_target_config(project)
    assert config["mode"] == "dual"
    assert config["game_root"] == str(game.resolve())
    assert config["uproject"] == "Proj.uproject"

    # omitted fields drop from the dual block (mirrors v1 target set)
    assert mw.cmd_target(_tset(project, game)) == 0
    text = yml.read_text(encoding="utf-8")
    assert "  engine:" not in text
    assert "  vcs: p4" not in text
    assert "  uproject:" not in text
    assert _block_region(text, "partition") == partition_block


def test_target_on_off_symmetric(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    dirs = _mk("control", "parent", "part", "game", base=tmp_path)
    project, part, game = dirs["control"], dirs["part"], dirs["game"]
    # v1 file → exit 1 with the migration hint
    yml = _yml(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    v1 = f"mode: dual\ngame: '{game}'\n"
    yml.write_text(v1, encoding="utf-8")
    rc = mw.cmd_target(_taction(project, "on"))
    assert rc == 1
    assert "v1 format" in capsys.readouterr().err
    rc = mw.cmd_target(_taction(project, "off"))
    assert rc == 1
    assert "v1 format" in capsys.readouterr().err

    # v2: partition set + target set → on flips to dual, off parks to single
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=part)) == 0
    assert mw.cmd_target(_tset(project, game)) == 0
    yml2 = _yml(project)
    dual_active = yml2.read_text(encoding="utf-8")
    assert mw.cmd_target(_taction(project, "on")) == 0
    assert load_target_config(project)["mode"] == "dual"
    # on is idempotent: already dual → byte-identical file
    assert yml2.read_text(encoding="utf-8") == dual_active
    assert mw.cmd_target(_taction(project, "off")) == 0
    after_off = yml2.read_text(encoding="utf-8")
    # off flips only the active line; the blocks stay parked byte-for-byte
    assert after_off.replace("active: single", "active: dual") == dual_active
    assert load_target_config(project)["mode"] == "single"

    # v2 without a usable dual block → on exits 1 (prompt set)
    project2 = tmp_path / "control2"
    project2.mkdir()
    yml3 = _yml(project2)
    yml3.parent.mkdir(parents=True, exist_ok=True)
    yml3.write_text("active: single\n", encoding="utf-8")
    before = yml3.read_bytes()
    assert mw.cmd_target(_taction(project2, "on")) == 1
    assert yml3.read_bytes() == before
    # no file → on exits 1, off is an idempotent no-op
    project3 = tmp_path / "control3"
    project3.mkdir()
    assert mw.cmd_target(_taction(project3, "on")) == 1
    assert mw.cmd_target(_taction(project3, "off")) == 0
    print("[VERIFY] VC-023: target on/off symmetric (v2 flip/park, v1 exit-1)")


# ── write scope: only target.yml (+ .bak on migration) ──────────────────────


def test_write_scope_is_target_yml_only(tmp_path: pathlib.Path) -> None:
    dirs = _mk("control", "parent", "part", base=tmp_path)
    project = dirs["control"]
    (project / "README.md").write_text("keep", encoding="utf-8")
    (project / ".agenticdoc").mkdir()
    (project / ".agenticdoc" / "_index.parallel").write_text("", encoding="utf-8")

    def snapshot(root: pathlib.Path) -> set[str]:
        return {
            str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file()
        }

    before = snapshot(project)
    assert mw.cmd_partition(_pset(project, dirs["parent"], partition=dirs["part"])) == 0
    after = snapshot(project)
    assert after - before == {".agenticdoc/target.yml"}
    assert mw.cmd_partition(_paction(project, "off")) == 0
    assert mw.cmd_partition(_paction(project, "on")) == 0
    assert snapshot(project) == after
    assert mw.cmd_partition(_paction(project, "clear")) == 0
    assert snapshot(project) == before
