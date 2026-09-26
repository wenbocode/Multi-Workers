"""
test_mw_build.py — `mw build --install` dist-sync + dirty-tree guard behavior.

The npm global `pi` links to packages/coding-agent, so the runtime executes the
repo's dist. `--install` must therefore also rebuild dist (opt out: --no-dist);
a failing dist rebuild fails the whole build AND must not touch the global copy
(partial-deploy guard). It must also refuse to compile uncommitted
packages/coding-agent/src changes into tracked artifacts unless --allow-dirty
is given, and `mw bootstrap` must guard the wider packages/*/src surface.
"""
import argparse
import pathlib
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw


def _args(install: bool, no_dist: bool = False, allow_dirty: bool = False) -> SimpleNamespace:
    return SimpleNamespace(install=install, no_dist=no_dist, allow_dirty=allow_dirty)


def _patch_build_env(tmp_path, monkeypatch, dist_result=(True, "dist rebuilt"),
                     dirty=None, patch_dirty=True):
    """Point the bundle/install plumbing at a tmp dir; record dist rebuilds."""
    bundle = tmp_path / "agent-team-loop.js"
    bundle.write_text("export default function activate() {}\n", encoding="utf-8")
    monkeypatch.setattr(mw, "_build_bundle", lambda: (True, "built ok"))
    monkeypatch.setattr(mw, "_bundle_path", lambda: bundle)
    monkeypatch.setattr(mw, "_global_ext_dir", lambda: tmp_path / "ext")
    monkeypatch.setattr(mw, "_write_mw_py_path", lambda: None)
    if patch_dirty:
        monkeypatch.setattr(mw, "_git_dirty_paths", lambda repo, paths: dirty)
    rebuilt: list[int] = []

    def fake_rebuild():
        rebuilt.append(1)
        return dist_result

    monkeypatch.setattr(mw, "_rebuild_pi_dist", fake_rebuild)
    return rebuilt


def test_install_rebuilds_dist(tmp_path, monkeypatch, capsys):
    rebuilt = _patch_build_env(tmp_path, monkeypatch)
    assert mw.cmd_build(_args(install=True)) == 0
    assert rebuilt == [1]
    out = capsys.readouterr().out
    assert "dist rebuilt" in out
    assert (tmp_path / "ext" / "agent-team-loop.js").exists()


def test_install_dist_failure_fails_the_build_and_leaves_global_untouched(
    tmp_path, monkeypatch, capsys,
):
    """AC-009(c): the dist rebuild runs before the global copy, so a failed
    rebuild leaves the old global bundle in place (no partial deploy)."""
    _patch_build_env(tmp_path, monkeypatch, dist_result=(False, "boom: tsgo failed"))
    assert mw.cmd_build(_args(install=True)) == 1
    assert "boom: tsgo failed" in capsys.readouterr().err
    assert not (tmp_path / "ext" / "agent-team-loop.js").exists()


def test_no_dist_skips_rebuild(tmp_path, monkeypatch, capsys):
    rebuilt = _patch_build_env(tmp_path, monkeypatch)
    assert mw.cmd_build(_args(install=True, no_dist=True)) == 0
    assert rebuilt == []
    assert "--no-dist" in capsys.readouterr().out


def test_plain_build_never_touches_dist(tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "_build_bundle", lambda: (True, "built ok"))
    monkeypatch.setattr(mw, "_bundle_path", lambda: tmp_path / "b.js")

    def boom():
        raise AssertionError("dist rebuild must not run without --install")

    monkeypatch.setattr(mw, "_rebuild_pi_dist", boom)
    assert mw.cmd_build(_args(install=False)) == 0


# ── dirty-tree guard (AC-009(d)) ─────────────────────────────────────────────

def _make_git_repo(tmp_path) -> tuple[pathlib.Path, pathlib.Path]:
    """A tmp git repo with a committed packages/ai/src/x.ts; returns it."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*a: str) -> None:
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)

    g("init")
    g("config", "user.email", "t@t.local")
    g("config", "user.name", "t")
    target = repo / "packages" / "ai" / "src" / "x.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export const x = 1;\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-m", "seed")
    return repo, target


def test_install_refuses_dirty_src_and_does_not_build(tmp_path, monkeypatch, capsys):
    built: list[int] = []
    deployed: list[int] = []
    monkeypatch.setattr(mw, "_build_bundle", lambda: built.append(1) or (True, "ok"))
    monkeypatch.setattr(mw, "_deploy_bundle", lambda no_dist: deployed.append(1) or 0)
    dirty_line = " M packages/coding-agent/src/extensions/agent-team-loop/index.ts"
    monkeypatch.setattr(mw, "_git_dirty_paths", lambda repo, paths: [dirty_line])
    assert mw.cmd_build(_args(install=True)) == 1
    assert built == []  # refused before building anything
    assert deployed == []
    err = capsys.readouterr().err
    assert dirty_line in err
    assert "未提交" in err
    assert "--allow-dirty" in err


def test_install_allow_dirty_bypasses_and_declares(tmp_path, monkeypatch, capsys):
    dirty = ["?? packages/coding-agent/src/extensions/agent-team-loop/new-mod.ts"]
    rebuilt = _patch_build_env(tmp_path, monkeypatch, dirty=dirty)
    assert mw.cmd_build(_args(install=True, allow_dirty=True)) == 0
    assert rebuilt == [1]
    assert "已按脏树构建，产物可能含未提交源码" in capsys.readouterr().out


def test_install_non_git_tree_skips_the_guard(tmp_path, monkeypatch):
    # The real _git_dirty_paths returns None when there is no .git: nothing to
    # commit, so the guard is skipped (this is what keeps bootstrap tests green).
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    monkeypatch.setattr(mw, "_repo_root", lambda: repo)
    _patch_build_env(tmp_path, monkeypatch, patch_dirty=False)
    assert mw._git_dirty_paths(repo, mw._BUILD_DIRTY_PATHS) is None
    assert mw.cmd_build(_args(install=True)) == 0


def test_git_dirty_paths_sees_staged_and_untracked(tmp_path):
    repo, target = _make_git_repo(tmp_path)
    assert mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS) == []
    target.write_text("export const x = 2;\n", encoding="utf-8")  # unstaged
    assert any("x.ts" in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True, text=True)
    assert any("x.ts" in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))
    # untracked file inside the guarded paths is seen too
    (repo / "packages" / "ai" / "src" / "new.ts").write_text("x\n", encoding="utf-8")
    assert any("new.ts" in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))
    # a change outside the guarded paths is ignored
    (repo / "install.py").write_text("# dirty\n", encoding="utf-8")
    assert all("install.py" not in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))


def test_git_dirty_paths_none_for_non_git_dir(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert mw._git_dirty_paths(plain, mw._BOOTSTRAP_DIRTY_PATHS) is None


def test_bootstrap_dirty_guard_blocks_then_allows(tmp_path, capsys):
    repo, target = _make_git_repo(tmp_path)
    assert mw._bootstrap_dirty_guard(repo, allow_dirty=False) is True
    target.write_text("export const x = 3;\n", encoding="utf-8")
    assert mw._bootstrap_dirty_guard(repo, allow_dirty=False) is False
    err = capsys.readouterr().err
    assert "packages/*/src/**" in err
    assert "--allow-dirty" in err
    assert mw._bootstrap_dirty_guard(repo, allow_dirty=True) is True
    assert "已按脏树构建" in capsys.readouterr().out


def test_bootstrap_refuses_dirty_src_before_running_build(tmp_path, monkeypatch, capsys):
    repo, target = _make_git_repo(tmp_path)
    target.write_text("export const x = 9;\n", encoding="utf-8")
    monkeypatch.setattr(mw, "_repo_root", lambda: repo)
    monkeypatch.setattr(
        mw.shutil, "which",
        lambda name: f"/fake/{name}" if name in ("node", "npm", "git") else None,
    )
    monkeypatch.setattr(mw, "_run_capture", lambda cmd, *, timeout=60.0: "v99.0.0")
    monkeypatch.setattr(mw.mw_common, "load_providers", lambda path: {})
    monkeypatch.setattr(
        mw.mw_common, "route_precheck",
        lambda config, env: {
            "routes": [{"route": "timi", "available": True, "missing": None, "source": "env"}],
            "all_missing": False,
        },
    )
    streams: list[list[str]] = []
    monkeypatch.setattr(mw, "_run_stream", lambda cmd, *, cwd: streams.append(list(cmd)) or True)
    args = argparse.Namespace(
        project=None, source="x", branch="master", fast=False, no_start=True,
        allow_dirty=False,
    )
    assert mw.cmd_bootstrap(args) == 1
    assert not any("build" in " ".join(cmd) for cmd in streams)
    assert "packages/*/src/**" in capsys.readouterr().err
