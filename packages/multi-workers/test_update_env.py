"""
test_update_env.py — mw update-env (incremental self-check over UPDATE.md anchors).

Covers the check helpers, the full _check_update_env report against a
fabricated hermetic world (tmp git repos, monkeypatched module state), the
--apply execution order, and the cmd-level JSON/text output.
No network, no real clones, no real builds.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common


# ── git fixtures ─────────────────────────────────────────────────────────────

def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _git_out(repo: pathlib.Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _git_init(repo: pathlib.Path, *, bare: bool = False) -> pathlib.Path:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init"] + (["--bare"] if bare else []),
        cwd=str(repo), check=True, capture_output=True, text=True,
    )
    # Pin the branch name regardless of the machine's init.defaultBranch.
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", "refs/heads/master"],
        cwd=str(repo), check=True, capture_output=True, text=True,
    )
    return repo


def _make_framework_source(path: pathlib.Path) -> pathlib.Path:
    """A minimal framework source repo: install.py + claude/{commands,...},
    committed, clean."""
    _git_init(path)
    _git(path, "config", "user.email", "t@t.local")
    _git(path, "config", "user.name", "t")
    (path / "install.py").write_text("# installer\n", encoding="utf-8")
    for sub in mw._CLAUDE_ADAPTER_DIRS:
        d = path / "claude" / sub
        d.mkdir(parents=True)
        (d / f"{sub}.md").write_text(f"# {sub}\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "seed")
    return path


def _publish(origin: pathlib.Path, source: pathlib.Path) -> None:
    """Point source at the bare origin and push master."""
    _git(source, "remote", "add", "origin", str(origin))
    _git(source, "push", "origin", "master")


def _make_project(project: pathlib.Path, source: pathlib.Path, *, clone: pathlib.Path) -> None:
    """An initialized mw project whose framework install matches source."""
    (project / ".agenticdoc").mkdir(parents=True)
    (project / ".agenticdoc" / "_index.md").write_text("# idx\n", encoding="utf-8")
    (project / ".mw").mkdir()
    (project / ".mw" / "serve.meta").write_text(
        json.dumps({"pid": 12345, "started_at_ms": int((time.time() + 3600) * 1000),
                    "code_dir": "fake"}),
        encoding="utf-8",
    )
    clone.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", str(source), str(clone)],
        check=True, capture_output=True, text=True,
    )
    for sub in mw._CLAUDE_ADAPTER_DIRS:
        dst = project / ".claude" / sub
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.mkdir(exist_ok=True)
        (dst / f"{sub}.md").write_text((source / "claude" / sub / f"{sub}.md").read_text(encoding="utf-8"), encoding="utf-8")
    (project / ".agentic-framework").write_text(
        f"framework=AgenticTask\nrepo={source}\ncommit={_git_out(source, 'rev-parse', '--short', 'HEAD')}\n",
        encoding="utf-8",
    )


# ── unit: helpers ────────────────────────────────────────────────────────────

class TestHelpers:
    def test_mw_code_newest_mtime_skip_rules(self, tmp_path, monkeypatch):
        for name in ("runtime.py", "conf.json"):
            (tmp_path / name).write_text("x", encoding="utf-8")
        # all of these must be skipped: test_*, _*, __pycache__/, dist/, .tmp/
        for name in ("test_x.py", "_priv.py", "notes.txt"):
            (tmp_path / name).write_text("x", encoding="utf-8")
        for sub in ("__pycache__", "dist", ".tmp"):
            d = tmp_path / sub
            d.mkdir()
            (d / f"{sub}_mod.py").write_text("x", encoding="utf-8")
        monkeypatch.setattr(mw, "_SCRIPT_DIR", tmp_path)
        got = mw._mw_code_newest_mtime()
        assert got is not None
        assert tmp_path.joinpath("runtime.py").stat().st_mtime == pytest.approx(got, abs=1.0)

    def test_newest_file_mtime_empty(self, tmp_path):
        assert mw._newest_file_mtime(tmp_path) is None

    def test_git_dirty_counts(self, tmp_path):
        repo = _make_framework_source(tmp_path / "repo")
        assert mw._git_dirty(repo) == (0, 0)
        (repo / "install.py").write_text("# changed\n", encoding="utf-8")
        (repo / "stray.md").write_text("x", encoding="utf-8")
        assert mw._git_dirty(repo) == (1, 1)

    def test_git_dirty_paths_sees_staged_and_untracked(self, tmp_path):
        repo = _make_framework_source(tmp_path / "repo")
        target = repo / "packages" / "ai" / "src" / "x.ts"
        target.parent.mkdir(parents=True)
        target.write_text("x\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "src")
        assert mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS) == []
        # unstaged change → tracked by the pathspec
        target.write_text("changed\n", encoding="utf-8")
        assert any("x.ts" in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))
        # staged change (git diff --quiet would miss this) still shows
        _git(repo, "add", "-A")
        assert any("x.ts" in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))
        # untracked file inside the guarded paths is seen
        (repo / "packages" / "ai" / "src" / "new.ts").write_text("x\n", encoding="utf-8")
        assert any("new.ts" in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))
        # a change outside the guarded paths is ignored
        (repo / "install.py").write_text("# dirty\n", encoding="utf-8")
        assert all("install.py" not in ln for ln in mw._git_dirty_paths(repo, mw._BOOTSTRAP_DIRTY_PATHS))

    def test_git_dirty_paths_none_for_non_git_dir(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert mw._git_dirty_paths(plain, mw._BOOTSTRAP_DIRTY_PATHS) is None

    def test_update_git_counts_behind_and_ahead(self, tmp_path):
        origin = _git_init(tmp_path / "origin.git", bare=True)
        seed = _make_framework_source(tmp_path / "seed")
        _publish(origin, seed)
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True, text=True)
        assert mw._update_git_counts(clone) == {"behind": 0, "ahead": 0}
        # push a new commit from seed → clone falls behind
        (seed / "install.py").write_text("# v2\n", encoding="utf-8")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-m", "v2")
        _git(seed, "push", "origin", "master")
        # counts read LOCAL refs — the clone must fetch to see the new commit
        # (exactly what `mw update-env --fetch` does)
        _git(clone, "fetch", "origin")
        assert mw._update_git_counts(clone) == {"behind": 1, "ahead": 0}
        # local commit in clone → diverged
        (clone / "local.md").write_text("x", encoding="utf-8")
        _git(clone, "config", "user.email", "t@t.local")
        _git(clone, "config", "user.name", "t")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-m", "local")
        assert mw._update_git_counts(clone) == {"behind": 1, "ahead": 1}

    def test_claude_adapter_drift(self, tmp_path):
        source = _make_framework_source(tmp_path / "source")
        project = tmp_path / "project"
        _make_project(project, source, clone=tmp_path / "clone")
        assert mw._claude_adapter_drift(project, source) == 0
        # modify one file, delete one, add one extra → 3
        (project / ".claude" / "commands" / "commands.md").write_text("# changed\n", encoding="utf-8")
        (project / ".claude" / "skills" / "skills.md").unlink()
        (project / ".claude" / "agents" / "extra.md").write_text("x", encoding="utf-8")
        assert mw._claude_adapter_drift(project, source) == 3

    def test_read_framework_manifest(self, tmp_path):
        (tmp_path / ".agentic-framework").write_text(
            "framework=AgenticTask\nrepo=C:/x\ncommit=abc1234\n", encoding="utf-8",
        )
        assert mw._read_framework_manifest(tmp_path) == {
            "framework": "AgenticTask", "repo": "C:/x", "commit": "abc1234",
        }
        assert mw._read_framework_manifest(tmp_path / "missing") == {}


# ── integration: _check_update_env against a fabricated world ────────────────

def _patch_world(monkeypatch, tmp_path, *, source: pathlib.Path, code_dir: pathlib.Path,
                 repo_root: pathlib.Path, bundle_stale: bool):
    monkeypatch.setattr(mw, "_checkout_framework_dir", lambda: source)
    monkeypatch.setattr(mw, "_TMP_AGENTICTASK", tmp_path / "no-cache")
    monkeypatch.setattr(mw, "_SCRIPT_DIR", code_dir)
    monkeypatch.setattr(mw, "_repo_root", lambda: repo_root)
    # A1b/A2b anchors resolve the repo root through mw_common, not mw.
    monkeypatch.setattr(mw_common, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(mw, "_check_pid", lambda _p: 12345)
    monkeypatch.setattr(mw_common, "_doctor_bundle", lambda: {
        "available": True, "source_available": True, "stale": bundle_stale,
        "global_bundle_mtime": "2026-09-21T10:00:00", "source_newest_mtime": "2026-09-21T11:00:00",
    })


def _world(tmp_path, monkeypatch, *, bundle_stale=False, dist_stale=False):
    source = _make_framework_source(tmp_path / "fw-source")
    project = tmp_path / "project"
    _make_project(project, source, clone=project / ".agents" / "skills" / "agentic-task")
    code_dir = tmp_path / "mwcode"
    code_dir.mkdir()
    (code_dir / "runtime.py").write_text("x", encoding="utf-8")
    repo_root = tmp_path / "repo-root"
    src_dir = repo_root / "packages" / "coding-agent" / "src"
    dist_dir = repo_root / "packages" / "coding-agent" / "dist"
    src_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)
    (src_dir / "core.ts").write_text("x", encoding="utf-8")
    dist_file = dist_dir / "core.js"
    dist_file.write_text("x", encoding="utf-8")
    if dist_stale:
        # The staleness check has a 2s slack — backdate the dist file instead
        # of racing the clock.
        past = time.time() - 10
        os.utime(dist_file, (past, past))
    _patch_world(monkeypatch, tmp_path, source=source, code_dir=code_dir,
                 repo_root=repo_root, bundle_stale=bundle_stale)
    return project, source


def _write_repo_bundle_fixture(
    repo_root: pathlib.Path,
    *,
    source_kinds: tuple[str, ...] = ("stage-confirm", "xkey-authorize"),
    bundle_kinds: tuple[str, ...] | None = None,
    guards: bool = True,
) -> None:
    """A1b fixture: the status-model.ts source plus the tracked repo bundle.
    Defaults match on both sides; callers override one side to create drift."""
    src = (repo_root / "packages" / "coding-agent" / "src" / "extensions"
           / "agent-team-loop" / "autopilot" / "status-model.ts")
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        "export const GATE_KINDS = ["
        + ", ".join(f'"{k}"' for k in source_kinds) + "] as const;\n",
        encoding="utf-8",
    )
    kinds = source_kinds if bundle_kinds is None else bundle_kinds
    bundle = (repo_root / "packages" / "multi-workers" / "dist" / "extensions"
              / "agent-team-loop.js")
    bundle.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "var GATE_KINDS = [" + ", ".join(f'"{k}"' for k in kinds) + "];",
        # esbuild's module banner: a path comment only, never a guard behaviour
        # marker — a bare `xkey-gate-guard` search would false-positive here.
        "// packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts",
    ]
    if guards:
        lines.append("const blocked = `xkey-gate-guard: blocked`;")
        lines.append("const trace = `[XKEY_GATE] blocked tool`;")
    bundle.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_sourcemap_fixture(repo_root: pathlib.Path, *, drifted: bool = False) -> None:
    """A2b fixture: one dist *.map embedding its source, next to the source."""
    src = repo_root / "packages" / "coding-agent" / "src" / "mod.ts"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("export const x = 1;\n", encoding="utf-8")
    embedded = "export const x = 2;   // stale build\n" if drifted else src.read_text(encoding="utf-8")
    map_path = repo_root / "packages" / "coding-agent" / "dist" / "mod.js.map"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        json.dumps({"version": 3, "sources": ["../src/mod.ts"], "sourcesContent": [embedded]}),
        encoding="utf-8",
    )


class TestCheckUpdateEnv:
    def test_healthy_world(self, tmp_path, monkeypatch):
        project, _source = _world(tmp_path, monkeypatch)
        report = mw._check_update_env(project)
        by_id = {c["id"]: c for c in report["checks"]}
        assert by_id["bundle"]["status"] == "ok"
        assert by_id["pi-dist"]["status"] == "ok"
        assert by_id["tmp-cache"]["status"] == "skip"
        assert by_id["serve"]["status"] == "ok"
        assert by_id["skill-clone"]["status"] == "ok"
        assert by_id["claude-adapters"]["status"] == "ok"
        assert by_id["manifest"]["status"] == "ok"
        assert by_id["legacy-patterns"]["status"] == "ok"
        assert report["summary"]["healthy"] is True

    def test_repo_bundle_content_anchor_fresh_and_stale(self, tmp_path, monkeypatch):
        project, _source = _world(tmp_path, monkeypatch)
        repo_root = tmp_path / "repo-root"
        _write_repo_bundle_fixture(repo_root)
        by_id = {c["id"]: c for c in mw._check_update_env(project)["checks"]}
        assert by_id["repo-bundle"]["status"] == "ok"
        # bundle lost a kind and both guard behaviour markers → stale, auto
        _write_repo_bundle_fixture(repo_root, bundle_kinds=("stage-confirm",), guards=False)
        report = mw._check_update_env(project)
        by_id = {c["id"]: c for c in report["checks"]}
        check = by_id["repo-bundle"]
        assert check["status"] == "stale" and check["auto"] is True
        assert "missing xkey-authorize" in check["detail"]
        assert "xkey-gate-guard: blocked" in check["detail"]
        assert report["summary"]["healthy"] is False

    def test_repo_bundle_anchor_ignores_path_comment_only(self, tmp_path, monkeypatch):
        """Mandated counterexample: the only xkey-gate-guard mention is the
        esbuild path banner, so the (qualified) guard criterion must stay red."""
        project, _source = _world(tmp_path, monkeypatch)
        _write_repo_bundle_fixture(tmp_path / "repo-root", guards=False)
        by_id = {c["id"]: c for c in mw._check_update_env(project)["checks"]}
        check = by_id["repo-bundle"]
        assert check["status"] == "stale"
        assert "guard marker(s) missing" in check["detail"]

    def test_repo_bundle_anchor_unjudgeable_is_not_ok(self, tmp_path, monkeypatch):
        project, _source = _world(tmp_path, monkeypatch)  # no fixture files
        by_id = {c["id"]: c for c in mw._check_update_env(project)["checks"]}
        assert by_id["repo-bundle"]["status"] == "info"
        assert by_id["repo-bundle"]["status"] != "ok"

    def test_sourcemap_content_anchor_fresh_and_stale(self, tmp_path, monkeypatch):
        project, _source = _world(tmp_path, monkeypatch)
        repo_root = tmp_path / "repo-root"
        _write_sourcemap_fixture(repo_root, drifted=False)
        by_id = {c["id"]: c for c in mw._check_update_env(project)["checks"]}
        assert by_id["pi-dist-content"]["status"] == "ok"
        _write_sourcemap_fixture(repo_root, drifted=True)
        report = mw._check_update_env(project)
        by_id = {c["id"]: c for c in report["checks"]}
        check = by_id["pi-dist-content"]
        assert check["status"] == "stale" and check["auto"] is True
        assert "mod.ts" in check["detail"]
        assert report["summary"]["healthy"] is False

    def test_sourcemap_anchor_flags_historical_181a75332_shape(self, tmp_path, monkeypatch):
        """A2b must be red on the exact 181a75332 shape: the tracked dist map
        embeds a status-model source without xkey-authorize while the current
        source has it. Read from git objects — no build."""
        repo = pathlib.Path(mw.__file__).resolve().parents[2]
        rel = ("packages/coding-agent/dist/extensions/agent-team-loop/"
               "autopilot/status-model.js.map")
        shown = subprocess.run(["git", "-C", str(repo), "show", f"181a75332:{rel}"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
        if shown.returncode != 0 or not shown.stdout:
            pytest.skip("181a75332 map unavailable in this checkout")
        old_map = json.loads(shown.stdout)
        src_rel = ("packages/coding-agent/src/extensions/agent-team-loop/"
                   "autopilot/status-model.ts")
        current = (repo / src_rel).read_text(encoding="utf-8")
        assert "xkey-authorize" in current
        fixture = tmp_path / "historical-root"
        (fixture / rel).parent.mkdir(parents=True)
        (fixture / rel).write_text(json.dumps(old_map), encoding="utf-8")
        (fixture / src_rel).parent.mkdir(parents=True, exist_ok=True)
        (fixture / src_rel).write_text(current, encoding="utf-8")
        monkeypatch.setattr(mw_common, "_repo_root", lambda: fixture)
        result = mw_common.sourcemap_drift()
        assert result["stale"] is True
        assert "status-model.ts" in result["detail"]

    def test_stale_world(self, tmp_path, monkeypatch):
        project, source = _world(tmp_path, monkeypatch, bundle_stale=True, dist_stale=True)
        # serve started in the past → stale
        (project / ".mw" / "serve.meta").write_text(
            json.dumps({"pid": 12345, "started_at_ms": int((time.time() - 3600) * 1000)}),
            encoding="utf-8",
        )
        # claude drift + manifest mismatch + dirty source repo
        (project / ".claude" / "commands" / "commands.md").write_text("# changed\n", encoding="utf-8")
        (project / ".agentic-framework").write_text("framework=AgenticTask\ncommit=0000000\n", encoding="utf-8")
        (source / "install.py").write_text("# dirty\n", encoding="utf-8")
        report = mw._check_update_env(project)
        by_id = {c["id"]: c for c in report["checks"]}
        assert by_id["bundle"]["status"] == "stale" and by_id["bundle"]["auto"] is True
        assert by_id["pi-dist"]["status"] == "stale" and by_id["pi-dist"]["auto"] is True
        assert by_id["serve"]["status"] == "stale" and by_id["serve"]["auto"] is True
        assert by_id["claude-adapters"]["status"] == "stale" and by_id["claude-adapters"]["auto"] is True
        assert by_id["manifest"]["status"] == "stale" and by_id["manifest"]["auto"] is True
        assert by_id["framework-source"]["status"] == "warn"
        assert report["summary"]["healthy"] is False

    def test_uninitialized_project(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty-project"
        empty.mkdir()
        source = _make_framework_source(tmp_path / "fw-source")
        code_dir = tmp_path / "mwcode"
        code_dir.mkdir()
        (code_dir / "runtime.py").write_text("x", encoding="utf-8")
        repo_root = tmp_path / "repo-root"
        _patch_world(monkeypatch, tmp_path, source=source, code_dir=code_dir,
                     repo_root=repo_root, bundle_stale=False)
        report = mw._check_update_env(empty)
        by_id = {c["id"]: c for c in report["checks"]}
        assert by_id["project"]["status"] == "info"
        assert by_id["serve"]["status"] == "info"
        assert "skill-clone" not in by_id
        assert report["summary"]["healthy"] is True  # info/skip are not issues

    def test_clone_behind_origin_is_stale_auto(self, tmp_path, monkeypatch):
        origin = _git_init(tmp_path / "origin.git", bare=True)
        source = _make_framework_source(tmp_path / "fw-source")
        _publish(origin, source)
        project = tmp_path / "project"
        clone = project / ".agents" / "skills" / "agentic-task"
        _make_project(project, source, clone=clone)
        # source pushes a new commit → the installed clone falls behind
        (source / "install.py").write_text("# v2\n", encoding="utf-8")
        _git(source, "add", "-A")
        _git(source, "commit", "-m", "v2")
        _git(source, "push", "origin", "master")
        _git(clone, "fetch", "origin")  # counts use local origin refs
        # manifest must still match, else that check also goes stale (fine, but assert precisely)
        code_dir = tmp_path / "mwcode"
        code_dir.mkdir()
        (code_dir / "runtime.py").write_text("x", encoding="utf-8")
        repo_root = tmp_path / "repo-root"
        _patch_world(monkeypatch, tmp_path, source=source, code_dir=code_dir,
                     repo_root=repo_root, bundle_stale=False)
        report = mw._check_update_env(project)
        by_id = {c["id"]: c for c in report["checks"]}
        assert by_id["skill-clone"]["status"] == "stale" and by_id["skill-clone"]["auto"] is True


# ── apply: execution order + manual notes ────────────────────────────────────

class TestApplyUpdateEnv:
    def _report(self, *stale_ids: str) -> dict:
        checks = [
            {"id": cid, "layer": "project" if cid in ("serve", "skill-clone", "claude-adapters", "manifest") else "machine",
             "status": "stale" if cid in stale_ids else "ok", "detail": "d", "fix": "f",
             "auto": True}
            for cid in ("repo-bundle", "bundle", "pi-dist", "pi-dist-content", "tmp-cache",
                        "serve", "skill-clone", "claude-adapters", "manifest")
        ]
        return {"checks": checks, "summary": {"ok": 0, "stale": len(stale_ids), "warn": 0, "healthy": False}}

    def test_order_and_manual_notes(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(mw, "_build_bundle", lambda: calls.append("build") or (True, "built"))
        monkeypatch.setattr(mw, "_deploy_bundle", lambda no_dist: calls.append("deploy") or 0)
        monkeypatch.setattr(mw, "_pull_agentictask", lambda remote, *, force, branch: calls.append("pull") or (True, "ok"))
        monkeypatch.setattr(mw, "_resolve_framework_source_readonly", lambda: tmp_path)
        monkeypatch.setattr(mw, "_install_framework", lambda p, *, source: calls.append("install") or (True, "installed"))
        monkeypatch.setattr(mw, "_stop_serve", lambda p: calls.append("stop") or True)
        monkeypatch.setattr(mw, "cmd_start", lambda a: calls.append("start"))
        applied, manual = mw._apply_update_env(tmp_path, self._report(
            "bundle", "tmp-cache", "skill-clone", "serve"))
        assert calls == ["build", "deploy", "pull", "install", "stop", "start"]
        assert len(applied) == 4
        assert any("重启 pi 窗口" in m for m in manual)
        assert any("/reload" in m for m in manual)

    def test_s1_build_failure_skips_deploy(self, tmp_path, monkeypatch):
        # The fail-open fix: a failed rebuild must never fall through to deploy.
        calls = []
        monkeypatch.setattr(mw, "_build_bundle", lambda: calls.append("build") or (False, "boom"))
        monkeypatch.setattr(mw, "_deploy_bundle", lambda no_dist: calls.append("deploy") or 0)
        applied, manual = mw._apply_update_env(tmp_path, self._report("bundle"))
        assert calls == ["build"]
        assert applied == []
        assert any("失败" in m for m in manual)

    def test_s1_deploy_failure_goes_manual(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mw, "_build_bundle", lambda: (True, "built"))
        monkeypatch.setattr(mw, "_deploy_bundle", lambda no_dist: 1)
        applied, manual = mw._apply_update_env(tmp_path, self._report("bundle"))
        assert applied == []
        assert any("失败" in m for m in manual)

    def test_s1_repo_bundle_stale_triggers_rebuild(self, tmp_path, monkeypatch):
        # A1b alone (global bundle/dist mtimes ok) must still rebuild + deploy.
        calls = []
        monkeypatch.setattr(mw, "_build_bundle", lambda: calls.append("build") or (True, "built"))
        monkeypatch.setattr(mw, "_deploy_bundle", lambda no_dist: calls.append("deploy") or 0)
        applied, manual = mw._apply_update_env(tmp_path, self._report("repo-bundle"))
        assert calls == ["build", "deploy"]
        assert applied == ["bundle+dist 重建并全局重装"]

    def test_no_action_when_healthy(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(mw, "_build_bundle", lambda: calls.append("build") or (True, "built"))
        monkeypatch.setattr(mw, "_deploy_bundle", lambda no_dist: calls.append("deploy") or 0)
        applied, manual = mw._apply_update_env(tmp_path, self._report())
        assert applied == [] and manual == []
        assert calls == []


# ── cmd: JSON/text output + exit codes ───────────────────────────────────────

class TestCmdUpdateEnv:
    def _args(self, project: pathlib.Path, **kw) -> argparse.Namespace:
        base = {"project": str(project), "apply": False, "json": False, "fetch": False}
        base.update(kw)
        return argparse.Namespace(**base)

    def test_json_output_and_exit_zero_when_healthy(self, tmp_path, monkeypatch, capsys):
        project, _ = _world(tmp_path, monkeypatch)
        rc = mw.cmd_update_env(self._args(project, json=True))
        out = capsys.readouterr().out
        report = json.loads(out)
        assert rc == 0
        assert report["summary"]["healthy"] is True
        assert report["manual"] == []
        assert report["applied"] == []

    def test_text_output_and_exit_one_when_stale(self, tmp_path, monkeypatch, capsys):
        project, _ = _world(tmp_path, monkeypatch, bundle_stale=True)
        rc = mw.cmd_update_env(self._args(project))
        out = capsys.readouterr().out
        assert rc == 1
        assert "STALE" in out
        assert "bundle" in out
        assert "--apply" in out  # the hint line
