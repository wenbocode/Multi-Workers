"""
test_runtime_scan_pruning.py — deterministic regression for runtime code scanning.

Covers:
  * excluded directories are pruned before `os.scandir` ever enters them;
  * runtime file set, mtime and digest ignore changes under excluded directories;
  * directory symlinks are not followed, while file symlinks keep their old
    place in the runtime file set.
No wall-clock thresholds: the directory visits are observed directly.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw


_SKIP_DIRS = ("__pycache__", "dist", ".tmp", "test")
_RUNTIME_FILES = (
    "runtime.py",
    "conf.json",
    "pkg/module.py",
    "pkg/nested/deep.json",
)
_FILTERED_FILES = (
    "test_x.py",
    "_priv.py",
    "notes.txt",
    "pkg/test_helper.py",
    "pkg/_private.json",
    "pkg/module.txt",
)
_BASE_MTIME = 1_700_000_000
_FUTURE_MTIME = _BASE_MTIME + 10_000


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _canonical(value: object) -> str:
    if isinstance(value, int):
        return f"fd:{value}"
    raw = os.fspath(value)
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    return os.path.normcase(os.path.realpath(raw))


def _make_tree(root: pathlib.Path) -> tuple[set[str], list[pathlib.Path]]:
    root.mkdir()
    for rel in _RUNTIME_FILES + _FILTERED_FILES:
        _write(root / rel, "x = 1\n")
    for rel in _RUNTIME_FILES:
        os.utime(root / rel, (_BASE_MTIME, _BASE_MTIME))

    excluded_files: list[pathlib.Path] = []
    for parent in (root, root / "pkg"):
        for name in _SKIP_DIRS:
            excluded = parent / name
            inner = excluded / "inner"
            paths = (excluded / "ignored.py", inner / "ignored.json")
            for path in paths:
                _write(path, "ignored = 1\n")
                os.utime(path, (_FUTURE_MTIME, _FUTURE_MTIME))
                excluded_files.append(path)
    return set(_RUNTIME_FILES), excluded_files


def _relative_files(tree: pathlib.Path) -> set[str]:
    return {p.relative_to(tree).as_posix() for p in mw._runtime_code_files(tree)}


def _scandir_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    real_scandir = os.scandir
    visited: list[str] = []

    def spy(path="."):
        visited.append(_canonical(path))
        return real_scandir(path)

    monkeypatch.setattr(mw.os, "scandir", spy)
    return visited


def test_excluded_directories_are_pruned_before_scandir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = tmp_path / "code"
    expected, _ = _make_tree(tree)
    visited = _scandir_spy(monkeypatch)

    assert _relative_files(tree) == expected
    for ordinary in (tree, tree / "pkg", tree / "pkg" / "nested"):
        assert _canonical(ordinary) in visited
    for parent in (tree, tree / "pkg"):
        for name in _SKIP_DIRS:
            excluded = parent / name
            assert _canonical(excluded) not in visited, f"scanned excluded dir: {excluded}"
            assert _canonical(excluded / "inner") not in visited


def test_excluded_changes_leave_runtime_file_set_mtime_and_digest_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    tree = tmp_path / "code"
    expected, excluded_files = _make_tree(tree)
    runtime = tree / "runtime.py"
    later = _FUTURE_MTIME + 10_000
    for path in excluded_files:
        os.utime(path, (later, later))

    assert _relative_files(tree) == expected
    assert mw._mw_code_newest_mtime(tree) == pytest.approx(_BASE_MTIME, abs=2.0)
    digest = mw._runtime_digest(tree)
    assert digest is not None and digest.startswith("sha256:")

    for path in excluded_files:
        path.write_text("changed excluded content\n", encoding="utf-8")
        os.utime(path, (later + 10_000, later + 10_000))
    assert _relative_files(tree) == expected
    assert mw._mw_code_newest_mtime(tree) == pytest.approx(_BASE_MTIME, abs=2.0)
    assert mw._runtime_digest(tree) == digest

    # Existing identity semantics: a touch changes the mtime baseline only;
    # a content change is visible to the digest.
    os.utime(runtime, (later, later))
    assert mw._mw_code_newest_mtime(tree) == pytest.approx(later, abs=2.0)
    assert mw._runtime_digest(tree) == digest
    runtime.write_text("x = 2\n", encoding="utf-8")
    assert mw._runtime_digest(tree) != digest


def test_directory_symlinks_are_not_followed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = tmp_path / "code"
    tree.mkdir()
    _write(tree / "runtime.py", "x = 1\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside / "payload.json", "{}\n")
    _write(outside / "hidden.py", "hidden = 1\n")
    try:
        (tree / "linked_dir").symlink_to(outside, target_is_directory=True)
        (tree / "linked.json").symlink_to(outside / "payload.json")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    visited = _scandir_spy(monkeypatch)
    assert _relative_files(tree) == {"runtime.py", "linked.json"}
    assert _canonical(tree) in visited
    assert _canonical(outside) not in visited
