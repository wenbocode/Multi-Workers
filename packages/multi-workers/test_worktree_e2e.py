"""test_worktree_e2e.py — AC-012 end to end (G2/G3/G4, T-W08).

The 2026-10-09 incident deleted 3,456 tracked files because bare
``git worktree remove --force`` traversed a ``<wt>/node_modules`` junction into
an ``<repo>/node_modules/@earendil-works/*`` workspace link and then into the
tracked package tree. AC-012 requires the machine-checked statement that the
guarded flow does not: build a worktree + link in ``%TEMP%``, clean it through
the new ``mw worktree rm`` transaction, and prove the main tree is
byte-for-byte unchanged while git never runs before the link is gone.

Two fixtures are built here (both entirely under ``%TEMP%``; every link target
is inside the fixture):

* the guarded fixture — real git repo ``<root>/main``, a worktree ``<root>/wt``
  created through ``worktree_cmd.cmd_worktree`` (``mw worktree add
  --link-deps``), the incident-shaped main-tree link
  ``main/node_modules/@earendil-works/pi-ai -> main/packages/x``, and an
  unregistered scan-root landmine ``<root>/landmine/node_modules``;
* the positive-control fixture — the same shape built with bare ``git worktree
  add`` + ``cmd /c mklink /J``, removed with bare ``git worktree remove
  --force`` so the incident is reproduced (tracked files and the link target are
  really deleted). Without this control "main tree unchanged" could be a vacuous
  pass.

Why the DI dispatch face and not ``python mw.py worktree ...`` as a subprocess:
``mw.py:_repo_root()`` (mw.py:4502) returns the *installed script's* repository
root, not ``cwd``, so the real CLI can never be pointed at a fixture — running it
here would drive ``git worktree add/remove`` against the real checkout, which is
forbidden. The ``cmd_worktree`` entry point is therefore called with
``repo_root``/``git``/``npm_hydrate`` injected (the same DI seam the CLI uses),
and ``npm_hydrate`` is a hard failure so no ``npm ci``/``npm install`` can run
(AGENTS hard rule). Cleanup goes through the real ``mw worktree rm`` six-step
transaction (``cmd_worktree`` rm action) with a recording git + a recording
unlink, which is exactly the seam AC-012 asks to instrument.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import worktree_cmd  # noqa: E402
import worktree_doctor  # noqa: E402
import worktree_registry  # noqa: E402

IS_WINDOWS = sys.platform == "win32"
PKG_DIR = pathlib.Path(__file__).resolve().parent

pytestmark = pytest.mark.skipif(
    not IS_WINDOWS, reason="directory junctions + cmd /c rmdir are Windows-only"
)

#: `%TEMP%` is 8.3 short-named on this machine; identity comparisons on link
#: paths must therefore tolerate the short/long spelling mix (spec pitfall 9).
#:
#: Domain (c) is depth-1 (`<root>/<worktree>/node_modules`), mirroring the real
#: corpus `%TEMP%\mwvg-t5\node_modules` with `%TEMP%` as the scan root. The
#: landmine is therefore `<root>/landmine/node_modules` (a `wt2` nesting would
#: need `<root>/landmine` as the scan root and could not be reached by the
#: `--worktree-scan-roots <root>` invocation AC-012 requires).
LANDMINE_REL = pathlib.Path("landmine") / "node_modules"


# ---------------------------------------------------------------------------
# fixture helpers (all targets inside the fixture, never the real checkout)
# ---------------------------------------------------------------------------

def _forbidden_hydrate(_target: pathlib.Path) -> bool:
    raise AssertionError(
        "npm hydration must never run in the AC-012 e2e (no npm install/npm ci)"
    )


def _init_repo(repo: pathlib.Path) -> None:
    """`git init` + one commit with `packages/x/f.txt` and `package.json`."""
    repo.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "wjg-e2e@example.invalid"],
        ["config", "user.name", "WJG E2E"],
        ["config", "commit.gpgsign", "false"],
    ):
        proc = mw._git(args, cwd=repo)
        assert proc.returncode == 0, proc.stderr
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "packages" / "x").mkdir(parents=True)
    (repo / "packages" / "x" / "f.txt").write_text("tracked-f\n", encoding="utf-8")
    (repo / "packages" / "x" / "index.js").write_text(
        "module.exports = 'real-dep';\n", encoding="utf-8"
    )
    (repo / "package.json").write_text(
        json.dumps({"name": "wjg-e2e", "version": "0.0.0", "private": True}),
        encoding="utf-8",
    )
    # The lockfile is the authority for "this in-repo link is a normal
    # workspace link": without it domain (b) would report
    # main/node_modules/@earendil-works/pi-ai (spec decision D-10).
    (repo / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "wjg-e2e",
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "wjg-e2e", "version": "0.0.0"},
                    "node_modules/@earendil-works/pi-ai": {
                        "link": True,
                        "resolved": "packages/x",
                    },
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert mw._git(["add", "-A"], cwd=repo).returncode == 0
    assert mw._git(["commit", "-q", "-m", "init"], cwd=repo).returncode == 0


def _make_link(link: pathlib.Path, target: pathlib.Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert os.path.isjunction(str(link))


def _build_main(root: pathlib.Path) -> pathlib.Path:
    """Real repo `root/main` with the incident double-layer link chain."""
    main = root / "main"
    _init_repo(main)
    (main / "node_modules" / "real-dep").mkdir(parents=True)
    (main / "node_modules" / "real-dep" / "index.js").write_text(
        "module.exports = 'real-dep';\n", encoding="utf-8"
    )
    # Layer 2: the workspace link the incident traversed into the tracked tree.
    _make_link(
        main / "node_modules" / "@earendil-works" / "pi-ai",
        main / "packages" / "x",
    )
    return main


def _add_landmine(root: pathlib.Path, main: pathlib.Path) -> pathlib.Path:
    """Unregistered `<root>/landmine/node_modules` -> main/node_modules."""
    link = root / LANDMINE_REL
    _make_link(link, main / "node_modules")
    return link


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ls_files(repo: pathlib.Path) -> list[str]:
    proc = mw._git(["--no-optional-locks", "ls-files", "-z"], cwd=repo)
    assert proc.returncode == 0, proc.stderr
    return [part for part in proc.stdout.split("\0") if part]


def _manifest(main: pathlib.Path) -> dict:
    """Tracked files (size/sha256/mtime_ns) + the link target content hash.

    `.git/` is git's own metadata and `.mw/` is the registry landing zone;
    AC-012 explicitly excludes both, so they are not part of this manifest.
    """
    manifest: dict = {}
    for rel in _ls_files(main):
        path = main / rel
        if path.is_file():
            stat = path.stat()
            manifest[rel] = {
                "size": stat.st_size,
                "sha256": _sha256(path),
                "mtime_ns": stat.st_mtime_ns,
            }
        else:
            manifest[rel] = {"missing": True}
    link_target = main / "node_modules" / "real-dep"
    if link_target.is_dir():
        for path in sorted(link_target.rglob("*")):
            if path.is_file():
                rel = path.relative_to(main).as_posix()
                stat = path.stat()
                manifest[rel] = {
                    "size": stat.st_size,
                    "sha256": _sha256(path),
                    "mtime_ns": stat.st_mtime_ns,
                }
    return manifest


def _rmdir_all_links(root: pathlib.Path) -> None:
    """`cmd /c rmdir <link>` (no /S) for every reparse point, never following it."""
    for dirpath, dirnames, _filenames in os.walk(
        root, topdown=True, onerror=lambda _exc: None
    ):
        for name in list(dirnames):
            candidate = pathlib.Path(dirpath) / name
            if os.path.isjunction(str(candidate)) or os.path.islink(str(candidate)):
                dirnames.remove(name)
                subprocess.run(
                    ["cmd", "/c", "rmdir", str(candidate)],
                    capture_output=True,
                    text=True,
                )


def _cleanup(root: pathlib.Path) -> None:
    if not root.exists():
        return
    _rmdir_all_links(root)
    mw._rmtree_robust(root)


class RecordingGit:
    """Delegates to real git; records every call and audits the remove boundary.

    On the `worktree remove --force` call the junction must already be gone —
    that in-callback assertion is the strongest form of "no caught mistake".
    """

    def __init__(self, link: pathlib.Path, events: list) -> None:
        self.link = pathlib.Path(link)
        self.events = events
        self.remove_checks: list[bool] = []

    def __call__(self, args, *, cwd=None, timeout=None):
        argv = tuple(args)
        self.events.append(("git", argv))
        if "remove" in argv:
            present = os.path.lexists(str(self.link))
            self.remove_checks.append(present)
            assert present is False, (
                f"zero-mis-release violation: git {' '.join(argv)} ran while "
                f"{self.link} still existed"
            )
        return mw._git(list(argv), cwd=cwd, timeout=timeout)


@pytest.fixture
def root(tmp_path: pathlib.Path):
    fixture_root = tmp_path / "root"
    try:
        yield fixture_root
    finally:
        _cleanup(fixture_root)


# ---------------------------------------------------------------------------
# AC-012: guarded flow keeps the main tree byte-for-byte identical
# ---------------------------------------------------------------------------

def test_e2e_ac012_guarded_cleanup_keeps_main_tree_unchanged(
    root: pathlib.Path, monkeypatch, capsys
) -> None:
    main = _build_main(root)
    landmine = _add_landmine(root, main)
    wt = root / "wt"

    # -- add via the DI dispatch face (mw worktree add --link-deps) ----------
    add_args = argparse.Namespace(
        worktree_action="add",
        path=str(wt),
        project=str(main),
        ref="HEAD",
        link_deps=True,
        dry_run=False,
        json=False,
    )
    assert worktree_cmd.cmd_worktree(
        add_args, repo_root=main, git=mw._git, npm_hydrate=_forbidden_hydrate
    ) == 0
    capsys.readouterr()
    assert os.path.isjunction(str(wt / "node_modules"))
    registry_before = worktree_registry.read_registry(main)
    assert len(registry_before) == 1
    assert os.path.normcase(registry_before[0]["link"]) == os.path.normcase(
        str(wt.resolve() / "node_modules")
    )

    manifest_before = _manifest(main)
    assert "packages/x/f.txt" in manifest_before
    assert manifest_before["node_modules/real-dep/index.js"]["sha256"] == _sha256(
        main / "node_modules" / "real-dep" / "index.js"
    )

    # -- D-12 end to end: the live registered wt link is normal, the
    #    unregistered landmine is still caught -----------------------------
    scan_roots = [str(root)]
    section_before = worktree_doctor.build_section(main, scan_roots=scan_roots)
    kinds_before = [entry["kind"] for entry in section_before["leftover"]]
    assert kinds_before == [worktree_doctor.SCAN_ROOT_KIND], section_before["leftover"]
    assert worktree_doctor._link_key(section_before["leftover"][0]["path"]) == (
        worktree_doctor._link_key(landmine)
    )
    assert section_before["count"] == 1

    # -- cleanup through the real `mw worktree rm` transaction, with the git
    #    and unlink calls recorded ------------------------------------------
    events: list = []
    real_unlink = worktree_cmd._unlink_reparse_point

    def recording_unlink(link: pathlib.Path) -> None:
        events.append(("unlink", str(link)))
        real_unlink(link)

    monkeypatch.setattr(worktree_cmd, "_unlink_reparse_point", recording_unlink)

    expected_unlinks = {
        worktree_doctor._link_key(link["path"])
        for link in worktree_cmd.enumerate_reparse_links(wt)
    }
    assert expected_unlinks == {worktree_doctor._link_key(wt / "node_modules")}

    recorder = RecordingGit(wt / "node_modules", events)
    rm_args = argparse.Namespace(
        worktree_action="rm", path=str(wt), project=str(main), json=False
    )
    assert worktree_cmd.cmd_worktree(
        rm_args, repo_root=main, git=recorder, npm_hydrate=_forbidden_hydrate
    ) == 0
    capsys.readouterr()

    # event order: unlink(s) strictly before `git worktree remove --force`
    git_removes = [
        index for index, event in enumerate(events)
        if event[0] == "git" and "remove" in event[1]
    ]
    unlink_indexes = [
        index for index, event in enumerate(events) if event[0] == "unlink"
    ]
    assert len(git_removes) == 1, events
    assert unlink_indexes, events
    assert git_removes[0] > max(unlink_indexes), events
    assert recorder.remove_checks == [False]
    unlinked_paths = {
        worktree_doctor._link_key(event[1])
        for event in events if event[0] == "unlink"
    }
    assert unlinked_paths == expected_unlinks

    # registry entry gone after the transaction
    assert worktree_registry.read_registry(main) == []
    assert not wt.exists()
    assert not os.path.lexists(str(wt / "node_modules"))

    # -- the machine criterion: tracked files + link target content identical
    manifest_after = _manifest(main)
    assert manifest_after == manifest_before, sorted(
        rel for rel in set(manifest_before) | set(manifest_after)
        if manifest_before.get(rel) != manifest_after.get(rel)
    )

    # -- mw doctor after cleanup: zero worktree findings ---------------------
    section_after = worktree_doctor.build_section(main)
    assert section_after["count"] == 0
    assert section_after["leftover"] == []

    doctor = subprocess.run(
        [sys.executable, "mw.py", "doctor", "--project", str(main), "--json"],
        cwd=str(PKG_DIR), capture_output=True, text=True,
    )
    report = json.loads(doctor.stdout)
    assert report["worktree_links"]["count"] == 0

    # Domain (c) with the same root: exactly the unregistered landmine, and the
    # removed `wt` link is not reported (it was unlinked by the rm transaction).
    scan_report_run = subprocess.run(
        [sys.executable, "mw.py", "doctor", "--project", str(main),
         "--worktree-scan-roots", str(root), "--json"],
        cwd=str(PKG_DIR), capture_output=True, text=True,
    )
    scan_report = json.loads(scan_report_run.stdout)["worktree_links"]
    assert len(scan_report["leftover"]) == 1, scan_report
    only = scan_report["leftover"][0]
    assert only["kind"] == worktree_doctor.SCAN_ROOT_KIND
    assert worktree_doctor._link_key(only["path"]) == worktree_doctor._link_key(landmine)
    assert f"{os.sep}wt{os.sep}" not in os.path.normcase(only["path"])


# ---------------------------------------------------------------------------
# Positive control: the fixture really can reproduce the incident
# ---------------------------------------------------------------------------

def test_e2e_ac012_positive_control_bare_remove_penetrates(root: pathlib.Path) -> None:
    """Bare `git worktree remove --force` on this fixture deletes tracked files
    and the link target — otherwise the guarded "unchanged" result is vacuous."""
    main = _build_main(root)
    wt = root / "wt"
    proc = mw._git(["worktree", "add", "--detach", str(wt), "HEAD"], cwd=main)
    assert proc.returncode == 0, proc.stderr
    _make_link(wt / "node_modules", main / "node_modules")

    manifest_before = _manifest(main)
    victim = main / "packages" / "x" / "f.txt"
    target_file = main / "node_modules" / "real-dep" / "index.js"
    assert victim.is_file()
    assert target_file.is_file()

    proc = mw._git(["worktree", "remove", "--force", str(wt)], cwd=main)
    assert proc.returncode == 0, proc.stderr

    manifest_after = _manifest(main)
    removed = sorted(
        rel for rel in manifest_before
        if manifest_after.get(rel) != manifest_before[rel]
    )
    # tracked files really vanished (the 2026-10-09 failure mode)
    assert "packages/x/f.txt" in removed, removed
    assert "packages/x/index.js" in removed, removed
    assert manifest_after["packages/x/f.txt"].get("missing") is True
    # the link target content really vanished
    assert "node_modules/real-dep/index.js" in removed, removed
    assert not victim.exists()
    assert not target_file.exists()
    assert not wt.exists()
