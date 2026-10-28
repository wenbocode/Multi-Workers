"""
test_mw_target.py — `mw target set/clear/show` + doctor target section tests
(mw-dual-workspace Task 003, AC-005, VC-010).

VC-010 observable: set→resolve(game), clear→resolve(single); write scope is
target.yml only (full-tree snapshot before/after); the repo's coding-agent
dist bundle mtimes are untouched (no rebuild on mode switch).
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
    ENV_TARGET_ENGINE,
    ENV_TARGET_GAME,
    load_target_config,
    target_yml_path,
    toolchain_probe_path,
)

_DIST_DIR = pathlib.Path(__file__).parent.parent / "coding-agent" / "dist"


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_TARGET_GAME, raising=False)
    monkeypatch.delenv(ENV_TARGET_ENGINE, raising=False)


def _set_args(project: pathlib.Path, game: pathlib.Path, **kw: str | None) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        target_action="set",
        game=str(game),
        engine=kw.get("engine"),
        vcs=kw.get("vcs"),
        uproject=kw.get("uproject"),
    )


def _action_args(project: pathlib.Path, action: str) -> argparse.Namespace:
    return argparse.Namespace(project=str(project), target_action=action)


def _snapshot(root: pathlib.Path) -> dict[str, tuple[int, int]]:
    """{relative path: (mtime_ns, size)} for every file under root."""
    snap: dict[str, tuple[int, int]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            snap[str(p.relative_to(root)).replace("\\", "/")] = (st.st_mtime_ns, st.st_size)
    return snap


def _diff_snapshots(before: dict, after: dict) -> tuple[set, set, set]:
    changed = {k for k in before.keys() & after.keys() if before[k] != after[k]}
    added = set(after) - set(before)
    removed = set(before) - set(after)
    return changed, added, removed


# ── target set / clear / show ─────────────────────────────────────────────────


def test_set_creates_template_and_resolves_dual(tmp_path: pathlib.Path) -> None:
    project, game = tmp_path / "control", tmp_path / "game"
    project.mkdir()
    game.mkdir()
    assert mw.cmd_target(_set_args(project, game)) == 0
    yml = target_yml_path(project)
    assert yml.exists()
    config = load_target_config(project)
    assert config["mode"] == "dual"
    assert config["game_root"] == str(game.resolve())
    print("[VERIFY] VC-010: dual-root=game")


def test_set_existing_file_line_updates_preserve_sections(tmp_path: pathlib.Path) -> None:
    project, game, new_game = tmp_path / "control", tmp_path / "game", tmp_path / "game2"
    for d in (project, game, new_game):
        d.mkdir()
    yml = target_yml_path(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    original = (
        "# hand-maintained header comment\n"
        "mode: dual\n"
        f"game: '{game}'\n"
        "toolchain:\n"
        "  build: 'build {game}'  # keep this comment\n"
        "ignore:\n"
        "  deny_globs:\n"
        '    - "**/*.uasset"\n'
    )
    yml.write_text(original, encoding="utf-8")

    rc = mw.cmd_target(
        argparse.Namespace(
            project=str(project), target_action="set", game=str(new_game),
            engine=None, vcs="p4", uproject=None,
        )
    )
    assert rc == 0
    text = yml.read_text(encoding="utf-8")
    assert f"game: '{new_game.resolve()}'" in text
    assert f"game: '{game.resolve()}'" not in text  # old game line replaced (exact quote boundary)
    assert "# hand-maintained header comment" in text
    assert "  build: 'build {game}'  # keep this comment" in text
    assert '    - "**/*.uasset"' in text
    assert "vcs: p4" in text
    config = load_target_config(project)
    assert config["game_root"] == str(new_game.resolve())
    assert config["ignore"]["deny_globs"] == ["**/*.uasset"]
    assert config["toolchain"]["build"] == "build {game}"


def test_clear_returns_single(tmp_path: pathlib.Path) -> None:
    project, game = tmp_path / "control", tmp_path / "game"
    project.mkdir()
    game.mkdir()
    assert mw.cmd_target(_set_args(project, game)) == 0
    assert mw.cmd_target(_action_args(project, "clear")) == 0
    assert not target_yml_path(project).exists()
    config = load_target_config(project)
    assert config["mode"] == "single"
    assert config["game_root"] == config["control_root"]
    print("[VERIFY] VC-010: single-root=control")


def test_write_scope_is_target_yml_only(tmp_path: pathlib.Path) -> None:
    """VC-010: set/clear touch nothing but .agenticdoc/target.yml, and the
    coding-agent dist bundle mtimes are unchanged (no rebuild on switch)."""
    project, game = tmp_path / "control", tmp_path / "game"
    project.mkdir()
    game.mkdir()
    # noise files that must never be touched
    (project / "README.md").write_text("keep", encoding="utf-8")
    (project / ".agenticdoc").mkdir()
    (project / ".agenticdoc" / "_index.parallel").write_text("", encoding="utf-8")

    dist_before = _snapshot(_DIST_DIR) if _DIST_DIR.is_dir() else None
    tree_before = _snapshot(project)

    assert mw.cmd_target(_set_args(project, game)) == 0
    tree_after_set = _snapshot(project)
    changed, added, removed = _diff_snapshots(tree_before, tree_after_set)
    assert changed == set() and removed == set()
    assert added == {".agenticdoc/target.yml"}, f"unexpected writes: {added}"

    assert mw.cmd_target(_action_args(project, "clear")) == 0
    tree_after_clear = _snapshot(project)
    changed, added, removed = _diff_snapshots(tree_after_set, tree_after_clear)
    assert changed == set() and added == set()
    assert removed == {".agenticdoc/target.yml"}, f"unexpected deletions: {removed}"

    if dist_before is not None:
        assert _snapshot(_DIST_DIR) == dist_before
        print("[VERIFY] VC-010: write-scope=target-yml-only dist-mtime-unchanged=true")
    else:
        print("[VERIFY] VC-010: write-scope=target-yml-only dist-mtime-unchanged=skipped(no dist)")


def test_set_missing_game_fails_closed(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "control"
    project.mkdir()
    rc = mw.cmd_target(_set_args(project, tmp_path / "nope"))
    assert rc == 1
    assert not target_yml_path(project).exists()


def test_set_validates_engine_and_uproject(tmp_path: pathlib.Path) -> None:
    project, game = tmp_path / "control", tmp_path / "game"
    project.mkdir()
    game.mkdir()
    (game / "Main.uproject").write_text("{}", encoding="utf-8")
    rc = mw.cmd_target(
        argparse.Namespace(
            project=str(project), target_action="set", game=str(game),
            engine=str(tmp_path / "missing-engine"), vcs=None, uproject=None,
        )
    )
    assert rc == 1
    rc = mw.cmd_target(
        argparse.Namespace(
            project=str(project), target_action="set", game=str(game),
            engine=None, vcs=None, uproject="Nope.uproject",
        )
    )
    assert rc == 1
    # uproject must exist to be accepted
    rc = mw.cmd_target(
        argparse.Namespace(
            project=str(project), target_action="set", game=str(game),
            engine=None, vcs=None, uproject="Main.uproject",
        )
    )
    assert rc == 0
    config = load_target_config(project)
    assert config["uproject"] == "Main.uproject"


def test_show_prints_resolved_config(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, game = tmp_path / "control", tmp_path / "game"
    project.mkdir()
    game.mkdir()
    (game / "Proj.uproject").write_text("{}", encoding="utf-8")
    assert mw.cmd_target(_set_args(project, game)) == 0
    capsys.readouterr()
    assert mw.cmd_target(_action_args(project, "show")) == 0
    out = capsys.readouterr().out
    assert "mode: dual" in out
    assert str(game.resolve()) in out


def test_show_fail_closed_on_broken_config(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "control"
    project.mkdir()
    yml = target_yml_path(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text("mode: [unclosed\n", encoding="utf-8")
    assert mw.cmd_target(_action_args(project, "show")) == 1
    assert "invalid-yaml" in capsys.readouterr().err


# ── doctor: target section + toolchain probe cache ────────────────────────────


def _doctor(project: pathlib.Path) -> dict:
    return mw_common.doctor_report(project, config=mw_common.load_providers(None))


def test_doctor_target_section_probes_and_caches(tmp_path: pathlib.Path) -> None:
    project, game, engine = tmp_path / "control", tmp_path / "game", tmp_path / "engine"
    for d in (project, game, engine):
        d.mkdir()
    (game / "Proj.uproject").write_text("{}", encoding="utf-8")
    yml = target_yml_path(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(
        f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n"
        "toolchain:\n  build: 'b {uproject}'\n",
        encoding="utf-8",
    )

    report = _doctor(project)
    target = report["target"]
    assert target["config"]["mode"] == "dual"
    assert target["probe_cache"] == "probed"
    assert [(c["name"], c["ok"]) for c in target["checks"]] == [
        ("game_root", True), ("engine_root", True), ("uproject", True),
    ]
    cache = toolchain_probe_path(project)
    assert cache.exists()
    first_mtime = cache.stat().st_mtime_ns

    # Second doctor run reuses the fresh cache (no rewrite, no re-probe).
    report2 = _doctor(project)
    assert report2["target"]["probe_cache"] == "fresh"
    assert cache.stat().st_mtime_ns == first_mtime

    # summary healthy: no target-related issues (service may be down — unrelated)
    assert not any("target" in i for i in report2["summary"]["issues"])

    # target.yml rewritten → cache stale → re-probe
    yml.write_text(
        f"mode: dual\ngame: '{game}'\nengine: '{engine}'\n"
        "toolchain:\n  build: 'b {uproject}'\n",
        encoding="utf-8",
    )
    report3 = _doctor(project)
    assert report3["target"]["probe_cache"] == "probed"


def test_doctor_target_single_default_has_no_checks(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "control"
    project.mkdir()
    report = _doctor(project)
    target = report["target"]
    assert target["config"]["mode"] == "single"
    assert target["config"]["source"] == "default"
    assert target["checks"] is None
    # service-not-running is unrelated; target must contribute no issues
    assert not any("target" in i for i in report["summary"]["issues"])


def test_doctor_target_error_is_issue(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "control"
    project.mkdir()
    yml = target_yml_path(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text("mode: dual\n", encoding="utf-8")  # dual without game
    report = _doctor(project)
    assert any("target config error" in i for i in report["summary"]["issues"])
    text = mw_common.format_doctor_text(report)
    assert "target: ERROR" in text


def test_doctor_target_probe_failure_is_issue(tmp_path: pathlib.Path) -> None:
    project, game = tmp_path / "control", tmp_path / "game"
    project.mkdir()
    game.mkdir()  # exists now, deleted before doctor → probe failure
    yml = target_yml_path(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(f"mode: dual\ngame: '{game}'\n", encoding="utf-8")
    import shutil

    shutil.rmtree(game)
    report = _doctor(project)
    assert any("target toolchain check failed: game_root" in i for i in report["summary"]["issues"])
