"""Tests for `tree_watch` (G4: AC-010 collapse, AC-011 dangling junction).

Every fixture lives under `%TEMP%` (via `tempfile.mkdtemp`); the real tree is
never touched and no destructive git command runs anywhere. Junctions are
created with `cmd /c mklink /J` and always point at a target inside the fixture
directory (spec pit 16).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import tree_watch  # noqa: E402
import launcher  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _git(repo: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _commit(repo: pathlib.Path, paths: list[str], message: str) -> None:
    _git(repo, "add", *paths)
    _git(repo, "commit", "-q", "-m", message)


def _write_files(repo: pathlib.Path, rel_dir: str, count: int, content: str = "x") -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for index in range(count):
        path = repo / rel_dir / f"f{index:05d}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        out.append(path)
    return out


def _is_reparse(path: str) -> bool:
    return os.path.isjunction(path) or os.path.islink(path)


def _cleanup(base: pathlib.Path) -> None:
    """Remove junctions first (`os.rmdir`, never `/S`) then the tree."""
    for dirpath, dirnames, _filenames in os.walk(base, topdown=True):
        for name in list(dirnames):
            candidate = os.path.join(dirpath, name)
            if _is_reparse(candidate):
                dirnames.remove(name)
                try:
                    os.rmdir(candidate)
                except OSError:
                    pass
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def repo() -> pathlib.Path:
    base = pathlib.Path(tempfile.mkdtemp(prefix="wjg-tw-"))
    root = base / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "wjg@test.invalid")
    _git(root, "config", "user.name", "wjg")
    yield root
    _cleanup(base)


def _mklink(repo: pathlib.Path, name: str, target: pathlib.Path, scope: str | None = None) -> pathlib.Path:
    parent = repo / "node_modules"
    if scope is not None:
        parent = parent / scope
    parent.mkdir(parents=True, exist_ok=True)
    link = parent / name
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert os.path.isjunction(link)
    return link


# ---------------------------------------------------------------------------
# Threshold / path surface
# ---------------------------------------------------------------------------

def test_collapse_threshold_formula() -> None:
    # max(20, round-half-up(1% * non_dist_tracked)); the spec example is 2,756 -> 28.
    assert tree_watch.collapse_threshold(2756) == 28
    assert tree_watch.collapse_threshold(2822) == 28  # current repo base
    assert tree_watch.collapse_threshold(2850) == 29
    assert tree_watch.collapse_threshold(0) == 20
    assert tree_watch.collapse_threshold(1500) == 20
    assert tree_watch.collapse_threshold(2800) == 28


def test_dist_path_surface() -> None:
    assert tree_watch.is_dist_path("packages/foo/dist/index.js")
    assert tree_watch.is_dist_path("a/dist/b/c.js")
    assert tree_watch.is_dist_path("dist/x.js")  # root-level dist/ is a component too
    assert not tree_watch.is_dist_path("packages/foo/src/index.ts")
    assert not tree_watch.is_dist_path("packages/foo/distfile.js")


# ---------------------------------------------------------------------------
# Criterion 1: collapse (AC-010)
# ---------------------------------------------------------------------------

def test_collapse_triggers(repo: pathlib.Path) -> None:
    files = _write_files(repo, "src", 600)
    _git(repo, "add", "src")

    before = tree_watch.sample_once(repo)
    assert before["tracked_non_dist"] == 600
    assert before["deleted_non_dist"] == 0
    assert before["threshold"] == 20

    for path in files[:300]:
        path.unlink()
    after = tree_watch.sample_once(repo)
    assert after["deleted_non_dist"] == 300

    verdict = tree_watch.evaluate(before, after)
    assert verdict["collapse"] is True
    assert verdict["delta"] == 300
    assert any("collapse" in line for line in verdict["alarms"])
    assert verdict["events"][0]["kind"] == "collapse"
    # The index total is unchanged (pit 6): the criterion is the delta, not the total.
    assert after["tracked_non_dist"] == 600


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_collapse_event_carries_same_window_link_delta(repo: pathlib.Path) -> None:
    """AC-010 action (3) (T-W09): the collapse event records the same-window
    junction-inventory delta - nonzero when a link is removed in the window,
    zero when the inventory is untouched."""
    files = _write_files(repo, "src", 400)
    _git(repo, "add", "src")
    target = repo / "targets" / "pkg"
    target.mkdir(parents=True)
    link = _mklink(repo, "pkg", target)

    before = tree_watch.sample_once(repo)
    assert any(item["path"] == str(link) for item in before["links"])
    os.rmdir(link)
    for path in files[:100]:
        path.unlink()
    after = tree_watch.sample_once(repo)

    verdict = tree_watch.evaluate(before, after)
    assert verdict["collapse"] is True
    collapse = next(item for item in verdict["events"] if item["kind"] == "collapse")
    assert collapse["link_delta"] == {"removed": 1, "changed": 0, "added": 0}
    assert collapse["ts"] == after["ts"]

    # Reverse direction: the next collapse window leaves the inventory intact.
    _mklink(repo, "pkg", target)
    before2 = tree_watch.sample_once(repo)
    for path in files[100:200]:
        path.unlink()
    after2 = tree_watch.sample_once(repo)

    verdict2 = tree_watch.evaluate(before2, after2)
    assert verdict2["collapse"] is True
    collapse2 = next(item for item in verdict2["events"] if item["kind"] == "collapse")
    assert collapse2["link_delta"] == {"removed": 0, "changed": 0, "added": 0}


def test_single_file_edit_does_not_trigger(repo: pathlib.Path) -> None:
    files = _write_files(repo, "src", 200)
    _git(repo, "add", "src")
    before = tree_watch.sample_once(repo)

    files[7].write_text("edited content", encoding="utf-8")
    after = tree_watch.sample_once(repo)

    assert after["deleted_non_dist"] == 0
    verdict = tree_watch.evaluate(before, after)
    assert verdict["collapse"] is False
    assert verdict["alarms"] == []


def test_git_rm_does_not_trigger(repo: pathlib.Path) -> None:
    _write_files(repo, "pkg", 120)
    _commit(repo, ["pkg"], "add pkg")
    before = tree_watch.sample_once(repo)
    assert before["tracked_non_dist"] == 120

    _git(repo, "rm", "-r", "-q", "pkg")
    after = tree_watch.sample_once(repo)

    # `git rm` updates the index and the disk together: -d stays 0.
    assert after["deleted_non_dist"] == 0
    assert tree_watch.evaluate(before, after)["collapse"] is False


def test_dist_clean_does_not_trigger(repo: pathlib.Path) -> None:
    dist_files = _write_files(repo, "packages/foo/dist", 80)
    _write_files(repo, "packages/foo/src", 1)
    _git(repo, "add", "packages")
    before = tree_watch.sample_once(repo)
    assert before["tracked_non_dist"] == 1

    # "npm run clean --workspaces" analogue: dist files vanish from disk only.
    for path in dist_files:
        path.unlink()
    after = tree_watch.sample_once(repo)

    assert after["deleted_total"] == 80  # git ls-files -d still reports them
    assert after["deleted_non_dist"] == 0  # ... but the path surface excludes dist
    assert tree_watch.evaluate(before, after)["collapse"] is False


def test_collapse_requires_two_samples(repo: pathlib.Path) -> None:
    """A first sample has no baseline: a large deleted count must not alarm."""
    files = _write_files(repo, "src", 300)
    _git(repo, "add", "src")
    for path in files[:200]:
        path.unlink()
    sample = tree_watch.sample_once(repo)
    assert sample["deleted_non_dist"] == 200
    verdict = tree_watch.evaluate({}, sample)
    assert verdict["delta"] is None
    assert verdict["collapse"] is False


def test_sample_once_is_read_only(repo: pathlib.Path) -> None:
    _write_files(repo, "src", 5)
    _git(repo, "add", "src")
    tree_watch.sample_once(repo)
    assert not tree_watch.state_path(repo).exists()


# ---------------------------------------------------------------------------
# Criterion 2: dangling junction (AC-011)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_good_junction_does_not_trigger(repo: pathlib.Path) -> None:
    target = repo / "targets" / "goodpkg"
    target.mkdir(parents=True)
    (target / "index.js").write_text("ok", encoding="utf-8")
    link = _mklink(repo, "goodpkg", target, scope="@earendil-works")

    sample = tree_watch.sample_once(repo)
    entry = next(item for item in sample["links"] if item["path"] == str(link))
    assert entry["link_type"] == "Junction"
    assert entry["target_exists"] is True

    verdict = tree_watch.evaluate({}, sample)
    assert verdict["broken_links"] == []
    assert verdict["alarms"] == []


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_broken_junction_triggers(repo: pathlib.Path) -> None:
    target = repo / "targets" / "badpkg"
    target.mkdir(parents=True)
    link = _mklink(repo, "badpkg", target)

    # `exists` follows the link and is True while the target is there.
    assert os.path.exists(str(link))
    shutil.rmtree(target)
    assert not os.path.exists(str(link))  # broken junction (pit 8)
    assert os.path.lexists(str(link))
    assert os.path.isjunction(str(link))

    sample = tree_watch.sample_once(repo)
    entry = next(item for item in sample["links"] if item["path"] == str(link))
    assert entry["target_exists"] is False

    verdict = tree_watch.evaluate({}, sample)
    assert [item["path"] for item in verdict["broken_links"]] == [str(link)]
    assert any("broken-link" in line and str(link) in line for line in verdict["alarms"])


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_real_directory_and_inventory_change(repo: pathlib.Path) -> None:
    target = repo / "targets" / "pkg"
    target.mkdir(parents=True)
    link = _mklink(repo, "pkg", target)
    (repo / "node_modules" / "plaindir").mkdir(parents=True, exist_ok=True)

    sample = tree_watch.sample_once(repo)
    assert all(item["path"] != str(repo / "node_modules" / "plaindir") for item in sample["links"])

    # Inventory migration: a previously present link that is now gone alarms.
    verdict = tree_watch.evaluate({}, sample)
    assert verdict["alarms"] == []
    os.rmdir(link)
    after = tree_watch.sample_once(repo)
    verdict2 = tree_watch.evaluate(sample, after)
    assert any(item["kind"] == "link-removed" for item in verdict2["events"])
    assert any("link-inventory" in line for line in verdict2["alarms"])


# ---------------------------------------------------------------------------
# Cadence / disable switch
# ---------------------------------------------------------------------------

def test_watch_disabled_by_env_zero_no_git_child(repo: pathlib.Path, monkeypatch) -> None:
    assert tree_watch.watch_interval_polls(5, {"PI_TREE_WATCH_SEC": "0"}) == 0

    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("PI_TREE_WATCH_SEC=0 must not spawn git")

    monkeypatch.setattr(tree_watch.subprocess, "run", _explode)
    watcher = tree_watch.TreeWatch(repo, 5, env={"PI_TREE_WATCH_SEC": "0"})
    assert watcher.enabled is False
    for _ in range(20):
        assert watcher.tick() is None
    assert not tree_watch.state_path(repo).exists()


def test_default_cadence_is_six_polls(repo: pathlib.Path, monkeypatch) -> None:
    calls: list[pathlib.Path] = []

    def _record(root):
        calls.append(root)
        return {
            "ts": 1.0, "iso": "x", "root": str(root),
            "tracked_total": 0, "tracked_non_dist": 0,
            "deleted_total": 0, "deleted_non_dist": 0,
            "deleted_paths": [], "threshold": 20, "links": [],
        }

    monkeypatch.setattr(tree_watch, "sample_once", _record)
    watcher = tree_watch.TreeWatch(repo, 5, env={})
    assert watcher.interval_polls == 6
    for _ in range(5):
        assert watcher.tick() is None
    assert calls == []
    verdict = watcher.tick()
    assert len(calls) == 1
    assert verdict is not None
    # State file was written through tmp + os.replace, no tmp left behind.
    state = tree_watch.read_state(repo)
    assert state["version"] == tree_watch.STATE_VERSION
    assert not (tree_watch.state_path(repo).parent / f"{tree_watch.STATE_FILE_NAME}.tmp{os.getpid()}").exists()


def test_sample_failure_logs_and_skips(repo: pathlib.Path, monkeypatch, capsys) -> None:
    def _boom(root):
        raise tree_watch.TreeWatchError("git is unhappy")

    monkeypatch.setattr(tree_watch, "sample_once", _boom)
    watcher = tree_watch.TreeWatch(repo, 5, env={"PI_TREE_WATCH_SEC": "5"})
    assert watcher.sample_and_record() is None
    assert not tree_watch.state_path(repo).exists()
    err = capsys.readouterr().err
    assert "[TREE-WATCH] sample skipped" in err


# ---------------------------------------------------------------------------
# Launcher hook (thin: emit alarms, never break the poll)
# ---------------------------------------------------------------------------

def test_poll_once_emits_tree_watch_alarms(repo: pathlib.Path, capsys) -> None:
    class _FakeWatch:
        def tick(self):
            return {"alarms": ["[TREE-WATCH] collapse: delta=300"]}

    launcher._poll_once(repo, {"providers": {}}, {}, {}, [], 1, _FakeWatch())
    assert "[launcher] [TREE-WATCH] collapse: delta=300" in capsys.readouterr().err


def test_poll_once_without_watcher_still_works(repo: pathlib.Path) -> None:
    # The 6-positional-argument call is the existing contract for direct callers.
    launcher._poll_once(repo, {"providers": {}}, {}, {}, [], 1)


def test_poll_once_survives_watcher_error(repo: pathlib.Path, capsys) -> None:
    class _BoomWatch:
        def tick(self):
            raise RuntimeError("sampler exploded")

    launcher._poll_once(repo, {"providers": {}}, {}, {}, [], 1, _BoomWatch())
    assert "tree watch error (continuing)" in capsys.readouterr().err


def test_pi_tree_watch_sec_overrides_interval() -> None:
    assert tree_watch.watch_interval_polls(5, {"PI_TREE_WATCH_SEC": "30"}) == 6
    assert tree_watch.watch_interval_polls(5, {"PI_TREE_WATCH_SEC": "90"}) == 18
    assert tree_watch.watch_interval_polls(5, {"PI_TREE_WATCH_SEC": "1"}) == 1
    assert tree_watch.watch_interval_polls(5, {"PI_TREE_WATCH_SEC": "garbage"}) == 6


def test_state_roundtrip(repo: pathlib.Path) -> None:
    sample = {
        "ts": 12.0, "iso": "iso", "root": str(repo),
        "tracked_total": 10, "tracked_non_dist": 5,
        "deleted_total": 3, "deleted_non_dist": 3,
        "deleted_paths": ["a", "b", "c"], "threshold": 20, "links": [],
    }
    verdict = tree_watch.evaluate({}, sample)
    tree_watch.write_state(repo, sample, verdict)
    state = json.loads(tree_watch.state_path(repo).read_text(encoding="utf-8"))
    assert state["deleted_non_dist"] == 3
    assert state["links"] == []
    assert tree_watch.read_state(repo)["version"] == 1
    # Corrupt state is a missing baseline, not a crash.
    tree_watch.state_path(repo).write_text("{not json", encoding="utf-8")
    assert tree_watch.read_state(repo) == {}
