"""Exercise dual skill installation through the real mw target and partition CLI."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import dual_skills


@pytest.fixture
def roots(tmp_path):
    control, game, engine = (tmp_path / name for name in ("control", "game", "engine"))
    for root in (control, game, engine):
        root.mkdir()
    return control, game, engine


def _cli(control, command, action, *args, expected=0):
    env = os.environ.copy()
    for name in ("MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-B", str(Path(__file__).with_name("mw.py")), command, action,
         "--project", str(control), *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", env={**env, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == expected, result.stdout + result.stderr
    return result


def _assert_payload(project):
    for path in dual_skills.SOURCE.rglob("*"):
        if path.is_file():
            installed = project / dual_skills.SLOT / path.relative_to(dual_skills.SOURCE)
            assert installed.read_bytes() == path.read_bytes()


def test_target_lifecycle_installs_only_active_roots(roots):
    control, game, engine = roots
    (control / ".agenticdoc").mkdir()
    (control / ".agenticdoc" / "target.yml").write_text("active: single\n", encoding="utf-8")
    _cli(control, "target", "skills-sync")
    assert not (control / ".agents").exists()
    _cli(control, "target", "set", "--game", game, "--engine", engine)
    for project in (control, game):
        _assert_payload(project)
    assert not list(engine.iterdir())

    installed = game / dual_skills.SLOT / "SKILL.md"
    first_mtime = installed.stat().st_mtime_ns
    _cli(control, "target", "skills-sync")
    assert installed.stat().st_mtime_ns == first_mtime

    _cli(control, "target", "off")
    assert not any((project / dual_skills.SLOT).exists() for project in (control, game))
    _cli(control, "target", "on")
    for project in (control, game):
        _assert_payload(project)
    _cli(control, "target", "clear")
    assert not any((project / dual_skills.SLOT).exists() for project in (control, game))


def test_retarget_and_switch_to_partition_preserve_project_changes(roots, tmp_path):
    control, game, engine = roots
    _cli(control, "target", "set", "--game", game)
    custom = control / dual_skills.SLOT / "SKILL.md"
    custom.write_text("Project adaptation", encoding="utf-8")
    new_game = tmp_path / "new-game"
    partition = tmp_path / "partition"
    new_game.mkdir()
    partition.mkdir()
    _cli(control, "target", "set", "--game", new_game)
    assert not (game / dual_skills.SLOT).exists()
    _assert_payload(new_game)
    _cli(control, "partition", "set", "--parent", engine, "--partition", partition)
    assert custom.read_text(encoding="utf-8") == "Project adaptation"
    assert not (new_game / dual_skills.SLOT).exists()
    assert not (partition / ".agents").exists()


def test_blocked_install_retries_and_preserves_custom_skill(roots):
    control, game, _ = roots
    blocked = game / dual_skills.SLOT
    blocked.parent.mkdir(parents=True)
    blocked.write_text("owned by the project", encoding="utf-8")
    result = _cli(control, "target", "set", "--game", game, expected=1)
    assert "skill slot is occupied" in result.stderr
    assert blocked.read_text(encoding="utf-8") == "owned by the project"
    blocked.unlink()
    blocked.mkdir()
    custom = blocked / "SKILL.md"
    custom.write_text("project skill", encoding="utf-8")
    _cli(control, "target", "skills-sync")
    _assert_payload(control)
    _cli(control, "target", "clear")
    assert custom.read_text(encoding="utf-8") == "project skill"


def test_sync_can_upgrade_unchanged_release_copy(roots, tmp_path, monkeypatch):
    control, game, _ = roots
    _cli(control, "target", "set", "--game", game)
    new_release = tmp_path / "new-release"
    shutil.copytree(dual_skills.SOURCE, new_release)
    new_skill = new_release / "SKILL.md"
    new_skill.write_bytes(new_skill.read_bytes() + b"\nNew release.\n")
    monkeypatch.setattr(dual_skills, "SOURCE", new_release)
    for name in ("MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"):
        monkeypatch.delenv(name, raising=False)
    assert dual_skills.sync(control) == 0
    for project in (control, game):
        _assert_payload(project)


def test_two_control_roots_do_not_share_ownership(roots, tmp_path):
    control, game, _ = roots
    other_control = tmp_path / "other-control"
    other_control.mkdir()
    _cli(control, "target", "set", "--game", game)
    result = _cli(other_control, "target", "set", "--game", game, expected=1)
    assert "skill is managed by" in result.stderr
    _cli(other_control, "target", "clear")
    _assert_payload(game)
    _cli(control, "target", "clear")
    assert not (game / dual_skills.SLOT).exists()
