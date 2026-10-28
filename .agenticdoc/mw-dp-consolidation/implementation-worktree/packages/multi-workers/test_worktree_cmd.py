"""
test_worktree_cmd.py — `mw worktree` (G2, T-W02): the six-step rm transaction,
the D-1 three-way classification, the registry round-trip, and the `_npm_hydrate`
extraction from the bootstrap install vector.

Hermetic: every fixture lives under pytest's tmp_path (%TEMP%). Junction
targets are always inside the fixture; the real checkout is never touched.
Nothing here runs `npm ci`/`npm install` — `add` is exercised via `--dry-run`
or `--link-deps` (which never invokes npm).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import worktree_cmd
import worktree_registry


# ── fixture helpers ──────────────────────────────────────────────────────────


def _git_run(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


def _init_repo(repo: pathlib.Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    assert _git_run(repo, "init", "-q").returncode == 0
    assert _git_run(repo, "config", "user.email", "t@example.invalid").returncode == 0
    assert _git_run(repo, "config", "user.name", "T").returncode == 0
    assert _git_run(repo, "config", "commit.gpgsign", "false").returncode == 0
    (repo / "packages" / "ai").mkdir(parents=True)
    (repo / "packages" / "ai" / "f.txt").write_text("keep\n", encoding="utf-8")
    (repo / "packages" / "ai" / "g.txt").write_text("keep2\n", encoding="utf-8")
    assert _git_run(repo, "add", "-A").returncode == 0
    assert _git_run(repo, "commit", "-q", "-m", "init").returncode == 0


def _link_junction(link: pathlib.Path, target: pathlib.Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"mklink failed: {proc.stderr or proc.stdout}"


def _add_worktree(repo: pathlib.Path, wt: pathlib.Path) -> None:
    proc = mw._git(["worktree", "add", "--detach", str(wt), "HEAD"], cwd=repo)
    assert proc.returncode == 0, proc.stderr


def _remove_reparse_points(root: pathlib.Path) -> None:
    if not root.exists():
        return
    for link in worktree_cmd.enumerate_reparse_links(root):
        subprocess.run(["cmd", "/c", "rmdir", link["path"]], capture_output=True, text=True)


def _cleanup(root: pathlib.Path) -> None:
    """Unlink junctions first (never /S), then rmtree read-only-safe."""
    _remove_reparse_points(root)
    mw._rmtree_robust(root)


def _manifest(root: pathlib.Path) -> dict:
    """relpath -> sha256 (or LINK:<target>) of the working tree, .git excluded."""
    out: dict[str, str] = {}
    stack = [root]
    while stack:
        directory = stack.pop()
        for entry in os.scandir(directory):
            path = pathlib.Path(entry.path)
            if entry.name == ".git":
                continue
            if worktree_cmd._is_reparse_point(path):
                out[path.relative_to(root).as_posix()] = "LINK:" + str(os.readlink(path))
            elif entry.is_dir(follow_symlinks=False):
                stack.append(path)
            else:
                out[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    return out


class RecordingGit:
    """Delegates to real git but records argv and optionally fails `remove`."""

    def __init__(self, real, *, fail_on_remove: bool = False):
        self.real = real
        self.fail_on_remove = fail_on_remove
        self.calls: list[list[str]] = []

    def __call__(self, args, *, cwd=None, timeout=None):
        self.calls.append(list(args))
        if self.fail_on_remove and "remove" in args:
            return subprocess.CompletedProcess(["git", *args], 1, "", "forced failure")
        return self.real(args, cwd=cwd, timeout=timeout)


def _forbidden_hydrate(_target: pathlib.Path) -> bool:
    raise AssertionError("npm hydrate must not run in this test")


@pytest.fixture
def incident(tmp_path: pathlib.Path):
    """Fixture repository + linked worktree with the double-layer incident chain.

    A/node_modules/@earendil-works/pi-ai -> A/packages/ai   (workspace link)
    B/node_modules (junction)             -> A/node_modules   (risky shortcut)
    """
    repo = tmp_path / "A"
    _init_repo(repo)
    _link_junction(
        repo / "node_modules" / "@earendil-works" / "pi-ai", repo / "packages" / "ai"
    )
    wt = tmp_path / "B"
    _add_worktree(repo, wt)
    _link_junction(wt / "node_modules", repo / "node_modules")
    yield repo, wt
    _cleanup(tmp_path)


# ── pure classification (D-1) ────────────────────────────────────────────────


class TestClassification:
    def test_worktree_nested_in_repo(self, tmp_path: pathlib.Path) -> None:
        repo = (tmp_path / "repo").resolve()
        wt = (repo / ".worktrees" / "wt").resolve()
        classify = worktree_cmd.classify_link_target
        assert classify(repo / "packages" / "ai", repo_root=repo, worktree_root=wt) == "repo"
        assert classify(wt / "packages" / "ai", repo_root=repo, worktree_root=wt) == "worktree"
        assert classify(tmp_path / "elsewhere", repo_root=repo, worktree_root=wt) == "foreign"

    def test_worktree_outside_repo(self, tmp_path: pathlib.Path) -> None:
        repo = (tmp_path / "repo").resolve()
        wt = (tmp_path / "wt").resolve()
        classify = worktree_cmd.classify_link_target
        assert classify(repo / "node_modules", repo_root=repo, worktree_root=wt) == "repo"
        assert classify(wt / "node_modules", repo_root=repo, worktree_root=wt) == "worktree"
        assert classify(tmp_path / "out", repo_root=repo, worktree_root=wt) == "foreign"

    def test_worktree_subtree_wins_over_repo(self, tmp_path: pathlib.Path) -> None:
        # A worktree nested in the repo must not treat its own npm-ci self-link
        # as the dangerous main-tree case (D-1 rationale).
        repo = (tmp_path / "repo").resolve()
        wt = (repo / ".worktrees" / "wt").resolve()
        assert worktree_cmd.classify_link_target(
            wt / "packages" / "ai", repo_root=repo, worktree_root=wt
        ) == "worktree"

    def test_windows_long_path_prefix_and_case_insensitive(self, tmp_path: pathlib.Path) -> None:
        repo = (tmp_path / "Repo").resolve()
        raw = "\\\\?\\" + str(repo / "packages").upper()
        assert worktree_cmd.classify_link_target(
            raw, repo_root=repo, worktree_root=tmp_path / "wt"
        ) == "repo"

    def test_returns_only_the_three_labels(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "repo"
        wt = repo / "wt"
        assert worktree_cmd.classify_link_target(
            repo / "x", repo_root=repo, worktree_root=wt
        ) in {"repo", "worktree", "foreign"}

    def test_path_through_junction_alias_is_still_inside_repo(
        self, tmp_path: pathlib.Path
    ) -> None:
        # Regression: `%TEMP%` hands back 8.3 short names (WENBOZ~1) while a
        # junction may store the long (or short) spelling. normcase alone does
        # not equate them, so _norm must canonicalize via realpath (spec
        # pitfall 9). A junction alias resolves to the same canonical root.
        repo = tmp_path / "repo"
        (repo / "packages" / "ai").mkdir(parents=True)
        alias = tmp_path / "alias"
        _link_junction(alias, repo)
        try:
            assert worktree_cmd.classify_link_target(
                alias / "packages" / "ai", repo_root=repo, worktree_root=tmp_path / "wt"
            ) == "repo"
        finally:
            subprocess.run(["cmd", "/c", "rmdir", str(alias)], capture_output=True)


# ── registry ─────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_register_roundtrip_and_file_shape(self, tmp_path: pathlib.Path) -> None:
        project = tmp_path / "proj"
        entry = worktree_registry.register_link(
            project,
            link=str(tmp_path / "wt" / "node_modules"),
            target=str(tmp_path / "repo" / "node_modules"),
            worktree=str(tmp_path / "wt"),
            repo_root=str(tmp_path / "repo"),
            created_by="test-runner",
        )
        assert entry["target"] == str(tmp_path / "repo" / "node_modules")
        assert entry["created_at"]
        assert entry["created_by"] == "test-runner"
        path = worktree_registry.registry_path(project)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == worktree_registry.REGISTRY_VERSION
        assert len(data["entries"]) == 1
        assert worktree_registry.read_registry(project) == [entry]
        assert list(worktree_registry.iter_entries(project)) == [entry]
        assert worktree_registry.find_entry(project, entry["link"]) == entry
        # lock released and no stray tmp file
        assert not worktree_registry.registry_lock(project).exists()
        assert not pathlib.Path(str(path) + ".tmp").exists()

    def test_upsert_by_link_keeps_one_entry(self, tmp_path: pathlib.Path) -> None:
        project = tmp_path / "proj"
        link = str(tmp_path / "wt" / "node_modules")
        worktree_registry.register_link(
            project, link=link, target="C:/old", worktree=str(tmp_path / "wt"),
            repo_root=str(tmp_path / "repo"), created_by="a",
        )
        worktree_registry.register_link(
            project, link=link.upper(), target="C:/new", worktree=str(tmp_path / "wt"),
            repo_root=str(tmp_path / "repo"), created_by="b",
        )
        entries = worktree_registry.read_registry(project)
        assert len(entries) == 1
        assert entries[0]["target"] == "C:/new"
        assert entries[0]["created_by"] == "b"

    def test_unregister_is_idempotent(self, tmp_path: pathlib.Path) -> None:
        project = tmp_path / "proj"
        link = str(tmp_path / "wt" / "node_modules")
        worktree_registry.register_link(
            project, link=link, target="C:/t", worktree=str(tmp_path / "wt"),
            repo_root=str(tmp_path / "repo"), created_by="a",
        )
        assert worktree_registry.unregister_link(project, link) is True
        assert worktree_registry.read_registry(project) == []
        assert worktree_registry.unregister_link(project, link) is False

    def test_missing_registry_reads_empty(self, tmp_path: pathlib.Path) -> None:
        assert worktree_registry.read_registry(tmp_path / "nope") == []

    def test_corrupt_registry_fails_closed(self, tmp_path: pathlib.Path) -> None:
        project = tmp_path / "proj"
        path = worktree_registry.registry_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(worktree_registry.WorktreeRegistryError):
            worktree_registry.read_registry(project)

    def test_empty_required_field_rejected(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(worktree_registry.WorktreeRegistryError):
            worktree_registry.register_link(
                tmp_path / "proj", link=str(tmp_path / "l"), target="",
                worktree=str(tmp_path / "wt"), repo_root=str(tmp_path / "repo"),
                created_by="a",
            )

    def test_created_by_now_carries_pid_and_user(self) -> None:
        value = worktree_registry.created_by_now()
        assert value.startswith("mw worktree add --link-deps")
        assert str(os.getpid()) in value


# ── _npm_hydrate (bootstrap install vector, no regression) ───────────────────


class TestNpmHydrate:
    def _patch(self, monkeypatch, npm, result=True):
        calls: list[tuple[list[str], pathlib.Path]] = []
        monkeypatch.setattr(mw.shutil, "which", lambda name: npm if name == "npm" else None)
        monkeypatch.setattr(
            mw, "_run_stream",
            lambda cmd, *, cwd: (calls.append((list(cmd), cwd)), result)[1],
        )
        return calls

    def test_fresh_tree_uses_npm_ci(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        calls = self._patch(monkeypatch, "C:/npm.cmd")
        assert mw._npm_hydrate(tmp_path) is True
        # Exact vector of the bootstrap step-2 install_cmd (design D-6):
        # [npm, "install" if node_modules.is_dir() else "ci", "--ignore-scripts"]
        assert calls == [(["C:/npm.cmd", "ci", "--ignore-scripts"], tmp_path)]

    def test_existing_node_modules_uses_npm_install(
        self, tmp_path: pathlib.Path, monkeypatch
    ) -> None:
        (tmp_path / "node_modules").mkdir()
        calls = self._patch(monkeypatch, "C:/npm.cmd")
        assert mw._npm_hydrate(tmp_path) is True
        assert calls == [(["C:/npm.cmd", "install", "--ignore-scripts"], tmp_path)]

    def test_failure_propagates(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        self._patch(monkeypatch, "C:/npm.cmd", result=False)
        assert mw._npm_hydrate(tmp_path) is False

    def test_missing_npm_returns_false(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        calls = self._patch(monkeypatch, None)
        assert mw._npm_hydrate(tmp_path) is False
        assert calls == []

    def test_bootstrap_step2_delegates_to_npm_hydrate(self) -> None:
        # `cmd_bootstrap` must call the shared helper, not a private duplicate.
        source = pathlib.Path(mw.__file__).read_text(encoding="utf-8")
        bootstrap_body = source.split("def cmd_bootstrap")[1].split("\ndef ")[0]
        assert "if not _npm_hydrate(repo_root):" in bootstrap_body
        assert "install_cmd" not in bootstrap_body


# ── rm six steps ─────────────────────────────────────────────────────────────


class TestRemoveWorktree:
    def test_six_steps_ok_and_main_tree_untouched(self, incident) -> None:
        repo, wt = incident
        before_manifest = _manifest(repo)
        log_lines: list[str] = []
        result = worktree_cmd.remove_worktree(
            wt, repo_root=repo, project_dir=repo, git=mw._git, log=log_lines.append
        )

        assert result["ok"] is True
        assert result["abort_step"] is None
        assert [s["step"] for s in result["steps"]] == [1, 2, 3, 4, 5, 6]
        assert [s["name"] for s in result["steps"]] == [
            "enumerate", "validate", "unlink", "recheck", "remove", "report",
        ]
        assert all(s["ok"] for s in result["steps"])
        # step 2 ran before step 3: the frozen list carries a classification
        assert len(result["links"]) == 1
        assert result["links"][0]["link_type"] == "Junction"
        assert result["links"][0]["classification"] == "repo"
        assert len(result["unlinked"]) == 1
        assert result["main_tree_before"] == result["main_tree_after"]

        # AC-005: worktree gone, main tree byte-for-byte unchanged.
        assert not wt.exists()
        assert (repo / "packages" / "ai" / "f.txt").read_text(encoding="utf-8") == "keep\n"
        assert os.path.isjunction(repo / "node_modules" / "@earendil-works" / "pi-ai")
        assert _manifest(repo) == before_manifest

        text = "\n".join(log_lines)
        for step in range(1, 7):
            assert f"step {step}/6" in text

    def test_step2_foreign_aborts_with_zero_unlinks(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "x.txt").write_text("x", encoding="utf-8")
        wt = tmp_path / "B"
        _add_worktree(repo, wt)
        _link_junction(wt / "node_modules", repo / "node_modules")  # would pass
        _link_junction(wt / "foreign", outside)                     # fail-closed
        recording = RecordingGit(mw._git, fail_on_remove=True)

        log_lines: list[str] = []
        result = worktree_cmd.remove_worktree(
            wt, repo_root=repo, project_dir=repo, git=recording, log=log_lines.append
        )

        assert result["ok"] is False
        assert result["abort_step"] == 2
        assert result["unlinked"] == []
        assert {link["classification"] for link in result["links"]} == {"repo", "foreign"}
        assert os.path.isjunction(wt / "node_modules")
        assert os.path.isjunction(wt / "foreign")
        assert not any("remove" in call for call in recording.calls)
        text = "\n".join(log_lines)
        assert "ABORT at step 2/6" in text
        assert "未降级继续" in text
        assert 'cmd /c rmdir' in text
        _cleanup(tmp_path)

    def test_step3_unlink_failure_aborts_and_preserves_scene(self, incident) -> None:
        repo, wt = incident

        def boom(_link: pathlib.Path) -> None:
            raise worktree_cmd.WorktreeCommandError("injected unlink failure")

        recording = RecordingGit(mw._git, fail_on_remove=True)
        result = worktree_cmd.remove_worktree(
            wt, repo_root=repo, project_dir=repo, git=recording, unlink=boom,
            log=lambda _m: None,
        )
        assert result["abort_step"] == 3
        assert result["unlinked"] == []
        assert os.path.isjunction(wt / "node_modules")
        assert wt.exists()
        assert not any("remove" in call for call in recording.calls)

    def test_step4_recheck_failure_aborts_before_remove(
        self, incident, monkeypatch
    ) -> None:
        repo, wt = incident
        real_snapshot = worktree_cmd.snapshot_workspace_links
        calls = {"n": 0}

        def drifting_snapshot(root):
            calls["n"] += 1
            snapshot = real_snapshot(root)
            if calls["n"] == 2:
                snapshot = list(snapshot) + [{
                    "name": "injected", "path": "x", "link_type": None,
                    "target": None, "target_normalized": None,
                }]
            return snapshot

        monkeypatch.setattr(worktree_cmd, "snapshot_workspace_links", drifting_snapshot)
        recording = RecordingGit(mw._git, fail_on_remove=True)
        result = worktree_cmd.remove_worktree(
            wt, repo_root=repo, project_dir=repo, git=recording, log=lambda _m: None
        )
        assert result["abort_step"] == 4
        assert "changed" in result["error"]
        # no compensation write: the already-unlinked link stays unlinked,
        # the worktree itself is preserved (remove was never called).
        assert not os.path.lexists(wt / "node_modules")
        assert wt.exists()
        assert not any("remove" in call for call in recording.calls)

    def test_step5_remove_failure_aborts(self, incident) -> None:
        repo, wt = incident
        recording = RecordingGit(mw._git, fail_on_remove=True)
        result = worktree_cmd.remove_worktree(
            wt, repo_root=repo, project_dir=repo, git=recording, log=lambda _m: None
        )
        assert result["abort_step"] == 5
        assert "git worktree remove --force failed" in result["error"]
        assert wt.exists()

    def test_precondition_refuses_main_tree(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        result = worktree_cmd.remove_worktree(
            repo, repo_root=repo, project_dir=repo, git=mw._git, log=lambda _m: None
        )
        assert result["ok"] is False
        assert result["abort_step"] is None  # precondition, not one of the six
        assert result["steps"] == []
        _cleanup(tmp_path)

    def test_precondition_refuses_non_worktree(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        plain = tmp_path / "plain"
        plain.mkdir()
        result = worktree_cmd.remove_worktree(
            plain, repo_root=repo, project_dir=repo, git=mw._git, log=lambda _m: None
        )
        assert result["ok"] is False
        assert result["abort_step"] is None
        _cleanup(tmp_path)

    def test_unlinks_registered_entry(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        wt = tmp_path / "B"
        _add_worktree(repo, wt)
        _link_junction(wt / "node_modules", repo / "node_modules")
        worktree_registry.register_link(
            repo, link=str(wt / "node_modules"), target=str(repo / "node_modules"),
            worktree=str(wt), repo_root=str(repo), created_by="test",
        )
        result = worktree_cmd.remove_worktree(
            wt, repo_root=repo, project_dir=repo, git=mw._git, log=lambda _m: None
        )
        assert result["ok"] is True
        assert result["registry_unregistered"] == [str(wt / "node_modules")]
        assert worktree_registry.read_registry(repo) == []
        _cleanup(tmp_path)


def test_positive_control_unsafe_remove_penetrates(tmp_path: pathlib.Path) -> None:
    """The fixture really does reproduce the incident: without the six steps,
    `git worktree remove --force` follows the junction chain and deletes the
    main tree's tracked files."""
    repo = tmp_path / "A"
    _init_repo(repo)
    _link_junction(
        repo / "node_modules" / "@earendil-works" / "pi-ai", repo / "packages" / "ai"
    )
    wt = tmp_path / "B"
    _add_worktree(repo, wt)
    _link_junction(wt / "node_modules", repo / "node_modules")
    victim = repo / "packages" / "ai" / "f.txt"
    assert victim.exists()

    proc = mw._git(["worktree", "remove", "--force", str(wt)], cwd=repo)
    assert proc.returncode == 0, proc.stderr
    assert not victim.exists(), (
        "positive control void: git did not follow the junction on this platform"
    )
    _cleanup(tmp_path)


# ── add ──────────────────────────────────────────────────────────────────────


class TestAddWorktree:
    def test_dry_run_writes_nothing(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        wt = tmp_path / "B"
        result = worktree_cmd.add_worktree(
            wt, repo_root=repo, project_dir=repo, git=mw._git,
            npm_hydrate=_forbidden_hydrate, link_deps=True, dry_run=True,
            log=lambda _m: None,
        )
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert not wt.exists()
        assert not os.path.lexists(wt)
        assert not worktree_registry.registry_path(repo).exists()
        assert any("mklink" in line for line in result["planned"])
        _cleanup(tmp_path)

    def test_default_add_hydrates_and_creates_no_link(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        wt = tmp_path / "B"
        hydrated: list[pathlib.Path] = []

        def hydrate(target: pathlib.Path) -> bool:
            hydrated.append(target)
            return True

        result = worktree_cmd.add_worktree(
            wt, repo_root=repo, project_dir=repo, git=mw._git, npm_hydrate=hydrate,
            log=lambda _m: None,
        )
        assert result["ok"] is True
        assert hydrated == [wt.resolve()]
        assert not os.path.lexists(wt / "node_modules")
        assert not worktree_registry.registry_path(repo).exists()
        _cleanup(tmp_path)

    def test_link_deps_creates_junction_registers_then_rm_unregisters(
        self, tmp_path: pathlib.Path
    ) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        wt = tmp_path / "B"
        result = worktree_cmd.add_worktree(
            wt, repo_root=repo, project_dir=repo, git=mw._git,
            npm_hydrate=_forbidden_hydrate, link_deps=True, log=lambda _m: None,
        )
        assert result["ok"] is True
        assert os.path.isjunction(wt / "node_modules")
        entries = worktree_registry.read_registry(repo)
        assert len(entries) == 1
        assert entries[0]["target"] == str((repo / "node_modules").resolve())
        assert entries[0]["created_at"]
        assert entries[0]["created_by"]
        assert result["registered"] == entries[0]

        rm = worktree_cmd.remove_worktree(
            wt, repo_root=repo, project_dir=repo, git=mw._git, log=lambda _m: None
        )
        assert rm["ok"] is True
        assert worktree_registry.read_registry(repo) == []
        _cleanup(tmp_path)

    def test_add_refuses_existing_path(self, tmp_path: pathlib.Path) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        wt = tmp_path / "B"
        wt.mkdir()
        result = worktree_cmd.add_worktree(
            wt, repo_root=repo, project_dir=repo, git=mw._git,
            npm_hydrate=_forbidden_hydrate, log=lambda _m: None,
        )
        assert result["ok"] is False
        assert "already exists" in result["error"]
        _cleanup(tmp_path)


# ── CLI + JSON contract ──────────────────────────────────────────────────────


class TestCliJson:
    def test_list_json_fields(self, tmp_path: pathlib.Path, capsys) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        link = str(tmp_path / "wt" / "node_modules")
        worktree_registry.register_link(
            repo, link=link, target=str(repo / "node_modules"), worktree=str(tmp_path / "wt"),
            repo_root=str(repo), created_by="test",
        )
        args = argparse.Namespace(worktree_action="list", project=str(repo), json=True)
        rc = worktree_cmd.cmd_worktree(
            args, repo_root=repo, git=mw._git, npm_hydrate=_forbidden_hydrate
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert rc == 0
        assert data["action"] == "list"
        assert data["count"] == 1
        assert data["registry"][0]["link"] == link
        assert data["worktree_count"] >= 1
        assert data["ok"] is True
        _cleanup(tmp_path)

    def test_rm_json_six_step_report(self, incident, capsys) -> None:
        repo, wt = incident
        args = argparse.Namespace(
            worktree_action="rm", path=str(wt), project=str(repo), json=True
        )
        rc = worktree_cmd.cmd_worktree(
            args, repo_root=repo, git=mw._git, npm_hydrate=_forbidden_hydrate
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert rc == 0
        assert data["ok"] is True
        assert data["abort_step"] is None
        assert [s["step"] for s in data["steps"]] == [1, 2, 3, 4, 5, 6]
        assert data["links"][0]["classification"] == "repo"
        assert data["main_tree_before"] == data["main_tree_after"]
        # JSON mode keeps stdout parseable: progress went to stderr.
        assert "step 1/6" in captured.err

    def test_rm_json_abort_report(self, tmp_path: pathlib.Path, capsys) -> None:
        repo = tmp_path / "A"
        _init_repo(repo)
        outside = tmp_path / "outside"
        outside.mkdir()
        wt = tmp_path / "B"
        _add_worktree(repo, wt)
        _link_junction(wt / "foreign", outside)
        args = argparse.Namespace(
            worktree_action="rm", path=str(wt), project=str(repo), json=True
        )
        rc = worktree_cmd.cmd_worktree(
            args, repo_root=repo, git=mw._git, npm_hydrate=_forbidden_hydrate
        )
        data = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert data["abort_step"] == 2
        assert data["unlinked"] == []
        _cleanup(tmp_path)

    def test_parser_contract(self, monkeypatch) -> None:
        monkeypatch.setattr(
            sys, "argv",
            ["mw.py", "worktree", "add", "X", "--link-deps", "--dry-run", "--json",
             "--ref", "main", "--project", "P"],
        )
        args = mw._parse_args()
        assert args.subcommand == "worktree"
        assert args.worktree_action == "add"
        assert args.path == "X"
        assert args.link_deps and args.dry_run and args.json
        assert args.ref == "main"
        assert args.project == "P"

    def test_rm_has_no_step_skipping_switch(self, monkeypatch) -> None:
        for flag in ("--force", "--continue", "--dry-run"):
            monkeypatch.setattr(
                sys, "argv", ["mw.py", "worktree", "rm", "X", flag]
            )
            with pytest.raises(SystemExit):
                mw._parse_args()

    def test_dispatch_registers_worktree(self) -> None:
        source = pathlib.Path(mw.__file__).read_text(encoding="utf-8")
        assert '"worktree": cmd_worktree' in source
