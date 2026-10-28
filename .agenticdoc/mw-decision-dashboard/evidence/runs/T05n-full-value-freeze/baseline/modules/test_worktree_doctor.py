"""Tests for `worktree_doctor` (G3: AC-009 leftover junctions).

Every fixture lives under `%TEMP%` (`tempfile.mkdtemp` / pytest `tmp_path`);
junction targets are always inside the fixture and the real checkout is only
read (scandir/lstat/readlink + one read-only `mw doctor` run). Junctions are
created with `cmd /c mklink /J` on Windows and removed with `cmd /c rmdir`
(never `/S`), matching `test_tree_watch.py` / `test_worktree_cmd.py`.

Coverage maps to the task's six required groups: domain (a) registry
leftover/stale, domain (b) repo-local subtraction, the `\\\\?\\` prefix
regression, domain (c) opt-in scan roots (+budget), the clean-fixture reverse
control, and the circular-import regression.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import mw_common  # noqa: E402
import worktree_doctor  # noqa: E402
import worktree_registry  # noqa: E402

IS_WINDOWS = sys.platform == "win32"
PKG_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _is_reparse(path: object) -> bool:
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None and isjunction(str(path)):
        return True
    return os.path.islink(str(path))


def _make_link(link: pathlib.Path, target: pathlib.Path) -> None:
    """Directory link, target forced to stay inside the fixture."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS:
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, (proc.stderr or proc.stdout)
    else:
        os.symlink(str(target), str(link), target_is_directory=True)
    assert os.path.lexists(str(link))


def _remove_link(link: pathlib.Path) -> None:
    if not os.path.lexists(str(link)):
        return
    if IS_WINDOWS:
        subprocess.run(["cmd", "/c", "rmdir", str(link)], capture_output=True, text=True)
    else:
        os.unlink(str(link))


def _cleanup(base: pathlib.Path) -> None:
    """Unlink reparse points first (never /S), then rmtree the fixture."""
    for dirpath, dirnames, _filenames in os.walk(base, topdown=True):
        for name in list(dirnames):
            candidate = pathlib.Path(dirpath) / name
            if _is_reparse(candidate):
                dirnames.remove(name)
                try:
                    os.rmdir(str(candidate))
                except OSError:
                    pass
    shutil.rmtree(base, ignore_errors=True)


def _snapshot(root: pathlib.Path) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        for name in list(dirnames):
            candidate = pathlib.Path(dirpath) / name
            if _is_reparse(candidate):
                out.append(os.path.relpath(str(candidate), str(root)))
                dirnames.remove(name)
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), str(root)))
    return sorted(out)


def _write_lockfile(repo: pathlib.Path, link_rels: list[str]) -> None:
    packages: dict = {"": {"name": "wjg-fixture"}}
    for rel in link_rels:
        packages[rel] = {"link": True}
    payload = {"name": "wjg-fixture", "lockfileVersion": 3, "packages": packages}
    (repo / "package-lock.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


@pytest.fixture
def fixture() -> pathlib.Path:
    base = pathlib.Path(tempfile.mkdtemp(prefix="wjg-w03-"))
    try:
        yield base
    finally:
        _cleanup(base)


@pytest.fixture
def repo(fixture: pathlib.Path) -> pathlib.Path:
    """A bare repo root with a real `node_modules` and a real package dir."""
    root = fixture / "repo"
    (root / "node_modules").mkdir(parents=True)
    (root / "packages" / "ai").mkdir(parents=True)
    (root / "packages" / "ai" / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Domain (a): registry
# ---------------------------------------------------------------------------

def test_registry_leftover_then_stale_entry(fixture: pathlib.Path, repo: pathlib.Path) -> None:
    target = repo / "node_modules"
    # Link lives outside the worktree root so the worktree can be removed while
    # the link survives (the exact "link present, worktree gone" shape).
    link = fixture / "links" / "node_modules"
    _make_link(link, target)
    worktree = fixture / "wt"
    worktree.mkdir()

    worktree_registry.register_link(
        repo,
        link=str(link),
        target=str(target),
        worktree=str(worktree),
        repo_root=str(repo),
        created_by="wjg-test",
    )

    # Link on disk + worktree on disk -> silent (no false positive).
    healthy = worktree_doctor.build_section(repo)
    assert healthy["count"] == 0
    assert healthy["domains"]["registry"] == 1

    # Worktree gone, link still on disk -> leftover.
    worktree.rmdir()
    leftover = worktree_doctor.build_section(repo)
    assert leftover["count"] == 1
    assert leftover["stale_entries"] == []
    entry = leftover["leftover"][0]
    assert entry["kind"] == worktree_doctor.REGISTRY_LEFTOVER_KIND
    assert entry["path"] == str(link)
    assert entry["target"] == str(target)
    assert entry["worktree"] == str(worktree)

    # Link gone too -> the same registered entry becomes a stale-entry.
    _remove_link(link)
    stale = worktree_doctor.build_section(repo)
    assert stale["leftover"] == []
    assert stale["count"] == 1
    entry = stale["stale_entries"][0]
    assert entry["kind"] == worktree_doctor.REGISTRY_STALE_KIND
    assert entry["path"] == str(link)
    assert entry["worktree"] == str(worktree)


def test_registry_absent_is_silent(tmp_path: pathlib.Path) -> None:
    section = worktree_doctor.build_section(tmp_path)
    assert section["count"] == 0
    assert section["domains"]["registry"] == 0
    assert section["scanned"]["registry_error"] is None
    assert section["registry_path"] == str(worktree_registry.registry_path(tmp_path))


# ---------------------------------------------------------------------------
# Domain (b): repo-local top level
# ---------------------------------------------------------------------------

def test_repo_local_leftover_and_expected_set_subtraction(repo: pathlib.Path) -> None:
    target = repo / "packages" / "ai"
    expected_link = repo / "node_modules" / "pi-ai"
    unexpected_link = repo / "node_modules" / "leftover-pkg"
    _make_link(expected_link, target)
    _make_link(unexpected_link, target)
    _write_lockfile(repo, ["node_modules/pi-ai"])

    section = worktree_doctor.build_section(repo)
    assert section["domains"]["repo_local"] == 2
    assert section["scanned"]["expected_links"] == 1
    assert section["count"] == 1
    entry = section["leftover"][0]
    assert entry["kind"] == worktree_doctor.REPO_LOCAL_KIND
    assert entry["path"] == str(unexpected_link)
    assert entry["target"] == str(target)
    assert entry["worktree"] is None

    # Adding the second link to the lockfile expected set makes it silent.
    _write_lockfile(repo, ["node_modules/pi-ai", "node_modules/leftover-pkg"])
    assert worktree_doctor.build_section(repo)["count"] == 0


def test_repo_local_target_outside_repo_is_not_reported(
    fixture: pathlib.Path, repo: pathlib.Path
) -> None:
    outside = fixture / "elsewhere"
    outside.mkdir()
    link = repo / "node_modules" / "foreign"
    _make_link(link, outside)
    section = worktree_doctor.build_section(repo)
    # Domain (b) only reports links whose target lands inside the repo.
    assert section["count"] == 0
    assert section["domains"]["repo_local"] == 1


def test_repo_local_short_vs_long_name_alias(repo: pathlib.Path) -> None:
    """`mw.py` resolves `--project` (8.3 short name -> long) while a junction
    target keeps its creation spelling; the section must still match."""
    target = repo / "packages" / "ai"
    link = repo / "node_modules" / "alias-pkg"
    _make_link(link, target)
    _write_lockfile(repo, [])

    section = worktree_doctor.build_section(pathlib.Path(str(repo)).resolve())
    assert section["count"] == 1
    found = section["leftover"][0]
    assert os.path.realpath(found["path"]) == os.path.realpath(str(link))
    assert os.path.normcase(os.path.realpath(found["target"])) == os.path.normcase(
        os.path.realpath(str(target))
    )


@pytest.mark.skipif(not IS_WINDOWS, reason="junction prefix semantics are Windows-only")
def test_repo_local_prefix_strip_regression(repo: pathlib.Path) -> None:
    """The raw junction target carries `\\\\?\\`; the section must still see it
    as inside the repo (PM-measured trap: 5/5 links looked 'outside' before the
    prefix was stripped)."""
    target = repo / "packages" / "ai"
    link = repo / "node_modules" / "pi-ai"
    _make_link(link, target)

    raw = os.readlink(str(link))
    assert raw.startswith("\\\\?\\"), raw
    _write_lockfile(repo, [])  # empty expected set -> the link must be reported

    section = worktree_doctor.build_section(repo)
    assert section["count"] == 1
    entry = section["leftover"][0]
    assert entry["path"] == str(link)
    assert not entry["target"].startswith("\\\\?\\")
    assert os.path.normcase(entry["target"]) == os.path.normcase(str(target))


# ---------------------------------------------------------------------------
# Domain (c): opt-in scan roots
# ---------------------------------------------------------------------------

def test_scan_roots_default_off_then_on(fixture: pathlib.Path, repo: pathlib.Path) -> None:
    scan_root = fixture / "temp-root"
    landing = scan_root / "mwvg-t5"
    link = landing / "node_modules"
    _make_link(link, repo / "node_modules")
    # A worktree whose node_modules points somewhere else must stay silent.
    foreign_wt = scan_root / "other-wt"
    foreign_target = fixture / "external-node-modules"
    foreign_target.mkdir()
    _make_link(foreign_wt / "node_modules", foreign_target)

    # Default off: the landmine is invisible.
    assert worktree_doctor.build_section(repo)["count"] == 0

    section = worktree_doctor.build_section(repo, scan_roots=[str(scan_root)])
    assert section["count"] == 1
    assert section["domains"]["scan_roots"] == 2
    assert section["scanned"]["truncated"] is False
    entry = section["leftover"][0]
    assert entry["kind"] == worktree_doctor.SCAN_ROOT_KIND
    assert entry["path"] == str(link)
    assert entry["target"] == str(repo / "node_modules")
    assert entry["worktree"] == str(landing)


def test_scan_roots_skips_live_registered_worktree(
    fixture: pathlib.Path, repo: pathlib.Path
) -> None:
    """D-12: a registered link whose worktree still exists is the normal state of
    a live worktree -> domain (c) must stay silent (no false positive)."""
    scan_root = fixture / "temp-root"
    link = scan_root / "wt" / "node_modules"
    _make_link(link, repo / "node_modules")
    worktree_registry.register_link(
        repo,
        link=str(link),
        target=str(repo / "node_modules"),
        worktree=str(link.parent),
        repo_root=str(repo),
        created_by="wjg-d12",
    )

    section = worktree_doctor.build_section(repo, scan_roots=[str(scan_root)])
    assert section["domains"]["scan_roots"] == 1
    assert section["leftover"] == []
    assert section["count"] == 0
    assert section["stale_entries"] == []


def test_scan_roots_reports_link_whose_registered_worktree_vanished(
    fixture: pathlib.Path, repo: pathlib.Path
) -> None:
    """D-12 reverse control (the mwvg-t5 shape): the registered ``worktree``
    field is gone while the link survives -> domain (c) must still catch it.

    The link path stays fixed at ``<scan_root>/wt/node_modules``; only the
    registry's ``worktree`` directory is removed (it is a separate path, the
    same layout `test_registry_leftover_then_stale_entry` uses, because a link
    nested in its own worktree cannot outlive that worktree).
    """
    scan_root = fixture / "temp-root"
    link = scan_root / "wt" / "node_modules"
    _make_link(link, repo / "node_modules")
    worktree = fixture / "registered-wt"
    worktree.mkdir()
    worktree_registry.register_link(
        repo,
        link=str(link),
        target=str(repo / "node_modules"),
        worktree=str(worktree),
        repo_root=str(repo),
        created_by="wjg-d12",
    )

    before = worktree_doctor.build_section(repo, scan_roots=[str(scan_root)])
    assert before["leftover"] == [], "a live registered worktree must not be reported"

    # Simulate `%TEMP%\mwvg-t5`: the worktree directory is removed, the link
    # stays on disk. Domain (a) also reports the now-leftover registry entry;
    # the point here is that domain (c) is no longer suppressed by D-12.
    worktree.rmdir()
    section = worktree_doctor.build_section(repo, scan_roots=[str(scan_root)])
    scan_entries = [
        entry for entry in section["leftover"]
        if entry["kind"] == worktree_doctor.SCAN_ROOT_KIND
    ]
    assert len(scan_entries) == 1
    entry = scan_entries[0]
    assert entry["path"] == str(link)
    assert entry["target"] == str(repo / "node_modules")
    assert entry["worktree"] == str(link.parent)
    assert worktree_doctor.REGISTRY_LEFTOVER_KIND in {
        item["kind"] for item in section["leftover"]
    }


def test_scan_roots_budget_truncates(fixture: pathlib.Path, repo: pathlib.Path) -> None:
    scan_root = fixture / "temp-root"
    for index in range(3):
        _make_link(scan_root / f"wt-{index}" / "node_modules", repo / "node_modules")

    section = worktree_doctor.build_section(
        repo, scan_roots=[str(scan_root)], entry_budget=2
    )
    assert section["domains"]["scan_roots"] == 2
    assert section["scanned"]["entries_visited"] == 2
    assert section["scanned"]["truncated"] is True
    assert len(section["leftover"]) <= 2
    assert section["scanned"]["budget"] == 2


# ---------------------------------------------------------------------------
# Reverse control: clean fixture
# ---------------------------------------------------------------------------

def _doctor_args(project: pathlib.Path, scan_roots: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), providers=None, fix=False, json=False,
        stale_after=90, worktree_scan_roots=scan_roots,
    )


def test_clean_fixture_zero_findings_zero_lines_rc_unchanged(
    fixture: pathlib.Path, repo: pathlib.Path, capsys
) -> None:
    _make_link(repo / "node_modules" / "pi-ai", repo / "packages" / "ai")
    _write_lockfile(repo, ["node_modules/pi-ai"])

    section = worktree_doctor.build_section(repo)
    assert section["count"] == 0
    assert section["scanned"]["expected_links"] == 1
    assert section["scanned"]["repo_local_links"] == 1

    report = mw_common.doctor_report(
        repo, fix=False, config=mw_common.load_providers(None)
    )
    assert report["worktree_links"]["count"] == 0
    assert not [issue for issue in report["summary"]["issues"] if "worktree" in issue]
    text = mw_common.format_doctor_text(report)
    assert "worktree_links" not in text

    # rc is driven by summary.healthy only; the (empty) section must not move it.
    rc_off = mw.cmd_doctor(_doctor_args(repo))
    out_off = capsys.readouterr().out
    empty_root = fixture / "empty-root"
    empty_root.mkdir()
    rc_on = mw.cmd_doctor(_doctor_args(repo, scan_roots=str(empty_root)))
    out_on = capsys.readouterr().out
    assert rc_off == rc_on
    assert "worktree_links" not in out_off
    assert "worktree_links" not in out_on


def test_build_section_is_read_only(fixture: pathlib.Path, repo: pathlib.Path) -> None:
    _make_link(repo / "node_modules" / "pi-ai", repo / "packages" / "ai")
    _write_lockfile(repo, ["node_modules/pi-ai"])
    scan_root = fixture / "temp-root"
    _make_link(scan_root / "wt" / "node_modules", repo / "node_modules")

    before = _snapshot(fixture)
    worktree_doctor.build_section(repo, scan_roots=[str(scan_root)])
    assert _snapshot(fixture) == before
    assert not (repo / ".mw").exists()


# ---------------------------------------------------------------------------
# Circular import + this-repo reverse control
# ---------------------------------------------------------------------------

def test_no_import_cycle() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", "import mw_common; print('cycle-ok')"],
        cwd=str(PKG_DIR), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "cycle-ok" in proc.stdout


@pytest.mark.skipif(not IS_WINDOWS, reason="this repo's links are Windows junctions")
def test_this_repo_reports_no_worktree_links() -> None:
    """Reverse control on the real checkout: 14 expected == 14 on disk -> no
    leftover, no issue, no text line, rc unchanged (read-only)."""
    section = worktree_doctor.build_section(REPO_ROOT)
    assert section["count"] == 0
    assert section["leftover"] == []
    assert section["stale_entries"] == []
    assert section["scanned"]["expected_links"] == section["scanned"]["repo_local_links"]

    text_run = subprocess.run(
        [sys.executable, "mw.py", "doctor", "--project", str(REPO_ROOT)],
        cwd=str(PKG_DIR), capture_output=True, text=True,
    )
    assert "worktree_links" not in text_run.stdout

    json_run = subprocess.run(
        [sys.executable, "mw.py", "doctor", "--project", str(REPO_ROOT), "--json"],
        cwd=str(PKG_DIR), capture_output=True, text=True,
    )
    report = json.loads(json_run.stdout)
    assert report["worktree_links"]["count"] == 0
    assert not [issue for issue in report["summary"]["issues"] if "worktree" in issue]
    assert json_run.returncode == (0 if report["summary"]["healthy"] else 1)


# ---------------------------------------------------------------------------
# AC-015: a corrupt registry must be visible (issue + text line + rc)
# ---------------------------------------------------------------------------

def _make_service_running(project: pathlib.Path) -> None:
    """A live PID removes the 'service not running' issue, so the registry
    finding is the only variable in `summary.healthy` / rc."""
    (project / ".mw").mkdir(parents=True, exist_ok=True)
    mw_common.pid_file(project).write_text(str(os.getpid()), encoding="utf-8")


def test_corrupt_registry_visible_healthy_registry_silent(
    fixture: pathlib.Path, repo: pathlib.Path, capsys
) -> None:
    """AC-015 (D-14): the registry read error used to be folded into the
    section and then ignored by both the issue and text faces (silent on a
    broken registry). Reverse control inside the same fixture: before the file
    is corrupted there is no new issue, no new line, and rc stays 0.
    """
    _make_service_running(repo)
    registry = worktree_registry.registry_path(repo)

    # Healthy (absent) registry -> zero findings, zero registry lines, rc 0.
    assert worktree_doctor.build_section(repo)["registry_error"] is None
    healthy = mw_common.doctor_report(repo, fix=False, config=mw_common.load_providers(None))
    assert healthy["worktree_links"]["registry_error"] is None
    assert not [i for i in healthy["summary"]["issues"] if "registry" in i]
    healthy_text = mw_common.format_doctor_text(healthy)
    assert "REGISTRY-ERROR" not in healthy_text
    rc_healthy = mw.cmd_doctor(_doctor_args(repo))
    healthy_out = capsys.readouterr().out
    assert rc_healthy == 0, healthy["summary"]["issues"]
    assert "REGISTRY-ERROR" not in healthy_out

    # Corrupt registry -> issue (+path) and a text line even though count == 0.
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("{ not json", encoding="utf-8")
    section = worktree_doctor.build_section(repo)
    assert section["count"] == 0
    assert section["registry_error"]
    assert section["scanned"]["registry_error"] == section["registry_error"]

    corrupt = mw_common.doctor_report(repo, fix=False, config=mw_common.load_providers(None))
    issues = [
        i for i in corrupt["summary"]["issues"]
        if i.startswith("worktree-registry-error:")
    ]
    assert len(issues) == 1
    assert str(registry) in issues[0]
    assert "could not be read" in issues[0]
    assert corrupt["summary"]["healthy"] is False
    text = mw_common.format_doctor_text(corrupt)
    assert "worktree_links: REGISTRY-ERROR" in text
    assert str(registry) in text

    rc_corrupt = mw.cmd_doctor(_doctor_args(repo))
    corrupt_out = capsys.readouterr().out
    assert rc_corrupt == 1
    assert "REGISTRY-ERROR" in corrupt_out
    assert rc_healthy != rc_corrupt

    # A healthy registry file (valid empty payload) turns it green again.
    registry.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    assert worktree_doctor.build_section(repo)["registry_error"] is None
    assert mw.cmd_doctor(_doctor_args(repo)) == rc_healthy
    assert "REGISTRY-ERROR" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# AC-015 / D-17: a dangling registry link must be visible too
# ---------------------------------------------------------------------------

def test_dangling_registry_link_is_visible(
    fixture: pathlib.Path, repo: pathlib.Path, capsys
) -> None:
    """D-17: `.mw/worktree-registry.json` as a junction/symlink to a removed
    target has `lexists` True and `exists` False. `read_registry` used to gate on
    `exists()`, so this shape folded into "no registry" and was the one silent
    shape among the bad-registry corpus. With `lexists` the dangling link
    reaches `read_text`, raises (OSError), and becomes a visible finding. The
    shape is self-proved: lexists True and exists False, else skip (never a
    fake green).
    """
    _make_service_running(repo)
    registry = worktree_registry.registry_path(repo)
    target = fixture / "nonexistent-target"
    _make_link(registry, target)
    assert os.path.lexists(str(registry)) is True
    if registry.exists():  # pragma: no cover - depends on the platform's link
        pytest.skip("registry link resolves on this platform; dangling shape N/A")
    assert registry.exists() is False

    # The gate no longer returns []: the read fails closed.
    with pytest.raises(worktree_registry.WorktreeRegistryError):
        worktree_registry.read_registry(repo)

    section = worktree_doctor.build_section(repo)
    assert section["count"] == 0
    assert section["registry_error"]
    assert section["scanned"]["registry_error"] == section["registry_error"]

    report = mw_common.doctor_report(repo, fix=False, config=mw_common.load_providers(None))
    issues = [
        i for i in report["summary"]["issues"]
        if i.startswith("worktree-registry-error:")
    ]
    assert len(issues) == 1
    assert str(registry) in issues[0]
    assert report["summary"]["healthy"] is False
    text = mw_common.format_doctor_text(report)
    assert "worktree_links: REGISTRY-ERROR" in text
    assert str(registry) in text

    rc = mw.cmd_doctor(_doctor_args(repo))
    out = capsys.readouterr().out
    assert rc == 1
    assert "REGISTRY-ERROR" in out

    _remove_link(registry)
    assert os.path.lexists(str(registry)) is False


def test_registry_missing_and_healthy_are_silent_reverse_controls(
    repo: pathlib.Path, capsys
) -> None:
    """D-17 reverse controls: a genuinely absent registry and a healthy empty
    registry both add zero lines and leave rc unchanged (the dangling-link fix
    must not turn normal states red)."""
    _make_service_running(repo)
    registry = worktree_registry.registry_path(repo)

    # Absent file: missing-file fast path still returns [] (no read attempt).
    assert worktree_registry.read_registry(repo) == []
    assert worktree_doctor.build_section(repo)["registry_error"] is None
    rc_absent = mw.cmd_doctor(_doctor_args(repo))
    out_absent = capsys.readouterr().out
    assert rc_absent == 0
    assert "REGISTRY-ERROR" not in out_absent
    assert "worktree_links" not in out_absent

    # Healthy registry: same zero findings, same rc.
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    assert worktree_registry.read_registry(repo) == []
    assert worktree_doctor.build_section(repo)["registry_error"] is None
    rc_healthy = mw.cmd_doctor(_doctor_args(repo))
    out_healthy = capsys.readouterr().out
    assert rc_healthy == rc_absent
    assert "REGISTRY-ERROR" not in out_healthy
    assert "worktree_links" not in out_healthy
