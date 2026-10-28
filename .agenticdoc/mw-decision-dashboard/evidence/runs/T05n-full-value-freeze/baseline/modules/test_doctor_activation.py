"""Tests for the AC-016 activation self-check (mw-worktree-junction-guard
T-W13, extended by T-W16 / D-18 to a multi-marker set).

`mw doctor` must be able to report that the G1 reparse-point removal guard is
not deployed to the runtime pi loads: the two bundles the runtime can pick up
(`packages/multi-workers/dist/extensions/agent-team-loop.js` and
``<PI_CODING_AGENT_DIR|~/.pi/agent>/extensions/agent-team-loop.js``) are probed
for the guard's own capability literals (`mw_common.ACTIVATION_MARKERS`), and
anything that is absent, marker-less or unreadable is an issue (`mw build`
for the staging copy, `mw build --install` for the installed one).

D-18: the markers are judged independently - `reparse-point` (the decision
vocabulary) and `user_bash` (the G6/AC-014 hook) - so deleting just the
`pi.on("user_bash")` hook is a finding even though the decision marker
survives. `has_marker` is True only when every marker is present, and the
issue/text faces name the missing marker(s).

Every fixture lives under `%TEMP%` (`tmp_path`); the bundle paths are injected
so the real checkout and the real ``~/.pi`` are never read. The reverse control
is a project with marker-carrying fixture bundles: zero new issues, zero new
text lines, unchanged rc.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import mw_common  # noqa: E402

MARKERS = mw_common.ACTIVATION_MARKERS
FIX = "mw build --install"
FIX_DIST = "mw build"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _doctor_args(project: pathlib.Path, *, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), providers=None, fix=False, json=as_json,
        stale_after=90, worktree_scan_roots=None,
    )


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal project with a live PID so the activation findings are the
    only variable in `summary.healthy` / rc."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".mw").mkdir()
    mw_common.pid_file(project).write_text(str(os.getpid()), encoding="utf-8")
    return project


def _bundle(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _markers_text(*present: str) -> str:
    """Bundle body carrying exactly the given markers."""
    return "".join(f"var x = '{marker}';\n" for marker in present)


def _report(project: pathlib.Path) -> dict:
    return mw_common.doctor_report(
        project, fix=False, config=mw_common.load_providers(None)
    )


def _activation_issues(report: dict) -> list[str]:
    return [i for i in report["summary"]["issues"] if i.startswith("guard-not-deployed:")]


def _inject(monkeypatch, *paths: pathlib.Path) -> None:
    """Point the doctor at fixture bundles (bypasses the checkout scope gate)."""
    monkeypatch.setattr(
        mw_common, "_activation_bundle_paths", lambda project_dir: list(paths)
    )


# ---------------------------------------------------------------------------
# Pure scan: markers present / absent / missing file / unreadable
# ---------------------------------------------------------------------------

def test_scan_all_markers_present_is_ok(tmp_path: pathlib.Path) -> None:
    a = _bundle(tmp_path / "dist.js", _markers_text(*MARKERS))
    b = _bundle(tmp_path / "global.js", "".join(f"// {m}\n" for m in MARKERS))
    section = mw_common._activation_scan([a, b])
    assert section["applicable"] is True
    assert section["markers"] == list(MARKERS)
    assert section["ok"] is True
    assert section["missing"] == []
    assert [entry["has_marker"] for entry in section["checked"]] == [True, True]
    assert [entry["missing_markers"] for entry in section["checked"]] == [[], []]


def test_scan_marker_absent_is_a_finding(tmp_path: pathlib.Path) -> None:
    present = _bundle(tmp_path / "dist.js", _markers_text(*MARKERS))
    absent = _bundle(tmp_path / "global.js", _markers_text(MARKERS[0]))
    section = mw_common._activation_scan([present, absent])
    assert section["ok"] is False
    assert section["missing"] == [str(absent)]
    entries = {entry["path"]: entry for entry in section["checked"]}
    assert entries[str(absent)]["exists"] is True
    assert entries[str(absent)]["has_marker"] is False
    assert entries[str(absent)]["missing_markers"] == [MARKERS[1]]
    assert entries[str(absent)]["markers"][MARKERS[0]] is True
    assert entries[str(absent)]["markers"][MARKERS[1]] is False
    assert entries[str(absent)]["error"] is None


def test_scan_missing_file_is_a_finding(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "gone.js"
    section = mw_common._activation_scan([missing])
    assert section["ok"] is False
    entry = section["checked"][0]
    assert entry["exists"] is False
    assert entry["has_marker"] is None
    assert entry["missing_markers"] == []
    assert entry["error"] == "file missing"


def test_scan_unreadable_does_not_raise(tmp_path: pathlib.Path) -> None:
    # A directory where the bundle should be -> IsADirectoryError (OSError).
    as_dir = tmp_path / "dir.js"
    as_dir.mkdir()
    section = mw_common._activation_scan([as_dir])
    assert section["ok"] is False
    entry = section["checked"][0]
    assert entry["exists"] is True
    assert entry["has_marker"] is None  # "cannot confirm", not "deployed"
    assert entry["error"]


def test_scan_invalid_encoding_does_not_raise(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.js"
    bad.write_bytes(b"\xff\xfe\x00not utf-8\xff")
    section = mw_common._activation_scan([bad])
    assert section["ok"] is False
    entry = section["checked"][0]
    assert entry["has_marker"] is None
    assert entry["error"]


# ---------------------------------------------------------------------------
# Doctor assembly: issue + text face
# ---------------------------------------------------------------------------

def test_missing_marker_is_an_issue_with_path_and_fix(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    absent = _bundle(tmp_path / "global.js", "var basis = 'resolved';\n")
    _inject(monkeypatch, absent)

    report = _report(project)
    assert report["activation"]["applicable"] is True
    issues = _activation_issues(report)
    assert len(issues) == 1
    assert str(absent) in issues[0]
    assert FIX in issues[0]
    # D-18: both missing markers are named.
    for marker in MARKERS:
        assert f"'{marker}'" in issues[0]
    assert report["summary"]["healthy"] is False

    text = mw_common.format_doctor_text(report)
    for marker in MARKERS:
        assert f"activation: MARKER-ABSENT '{marker}' {absent} - run '{FIX}'" in text


def test_missing_bundle_file_is_an_issue_with_fix(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    missing = tmp_path / "never-built.js"
    _inject(monkeypatch, missing)

    report = _report(project)
    issues = _activation_issues(report)
    assert len(issues) == 1
    assert str(missing) in issues[0]
    assert "bundle file missing" in issues[0]
    assert FIX in issues[0]
    assert f"activation: MISSING {missing} - run '{FIX}'" in mw_common.format_doctor_text(report)


def test_unreadable_bundle_is_reported_verbatim(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    bad = tmp_path / "bad.js"
    bad.write_bytes(b"\xff\xfe\x00not utf-8\xff")
    _inject(monkeypatch, bad)

    report = _report(project)  # must not raise
    issues = _activation_issues(report)
    assert len(issues) == 1
    assert "unverifiable" in issues[0]
    assert str(bad) in issues[0]
    text = mw_common.format_doctor_text(report)
    assert "activation: UNVERIFIABLE" in text
    assert "MARKER-ABSENT" not in text  # never disguised as "present"


# ---------------------------------------------------------------------------
# Scope gate + reverse control (rc)
# ---------------------------------------------------------------------------

def test_scope_gate_skips_projects_without_the_extension_source(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.delenv(mw_common.AGENT_DIR_ENV, raising=False)
    # No `packages/coding-agent/src/extensions/agent-team-loop` -> not applicable,
    # regardless of the real machine's bundle state.
    assert mw_common._activation_bundle_paths(project) is None
    report = _report(project)
    assert report["activation"]["applicable"] is False
    assert _activation_issues(report) == []
    assert "activation:" not in mw_common.format_doctor_text(report)


def test_two_marked_bundles_are_silent_and_rc_unchanged(
    tmp_path: pathlib.Path, monkeypatch, capsys
) -> None:
    project = _project(tmp_path)
    monkeypatch.setenv(mw_common.AGENT_DIR_ENV, str(tmp_path / "pi-agent"))
    good = [
        _bundle(tmp_path / "dist.js", _markers_text(*MARKERS)),
        _bundle(tmp_path / "global.js", _markers_text(*MARKERS)),
    ]
    _inject(monkeypatch, *good)

    report = _report(project)
    assert report["activation"]["ok"] is True
    assert _activation_issues(report) == []
    assert report["summary"]["issues"] == []
    assert report["summary"]["healthy"] is True
    assert "activation:" not in mw_common.format_doctor_text(report)

    rc_good = mw.cmd_doctor(_doctor_args(project))
    assert rc_good == 0, capsys.readouterr().out
    assert "activation:" not in capsys.readouterr().out

    # Same project, all markers removed -> new issue + rc flip (the non-hollow
    # counterfactual: the check can actually turn red and back to green).
    _inject(monkeypatch, _bundle(tmp_path / "global.js", "var basis = 'resolved';\n"))
    rc_bad = mw.cmd_doctor(_doctor_args(project))
    out_bad = capsys.readouterr().out
    assert rc_bad == 1
    assert "guard-not-deployed:" in out_bad
    assert "activation:" in out_bad
    assert rc_good != rc_bad

    # Restore the markers: the check turns green again with no code change.
    _bundle(tmp_path / "global.js", _markers_text(*MARKERS))
    _inject(monkeypatch, *good)
    assert mw.cmd_doctor(_doctor_args(project)) == rc_good


# ---------------------------------------------------------------------------
# D-18: per-marker independence (only user_bash / only reparse-point / both)
# ---------------------------------------------------------------------------

def test_only_user_bash_missing_names_that_marker(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Dropping the G6 `pi.on("user_bash")` hook must be visible even though the
    `reparse-point` decision marker survives."""
    project = _project(tmp_path)
    bundle = _bundle(tmp_path / "global.js", _markers_text("reparse-point"))
    _inject(monkeypatch, bundle)

    report = _report(project)
    issues = _activation_issues(report)
    assert len(issues) == 1
    assert str(bundle) in issues[0]
    assert "'user_bash'" in issues[0]
    assert "'reparse-point'" not in issues[0]
    assert "capability marker(s) absent" in issues[0]
    assert report["summary"]["healthy"] is False

    text = mw_common.format_doctor_text(report)
    assert f"activation: MARKER-ABSENT 'user_bash' {bundle} - run '{FIX}'" in text
    assert "MARKER-ABSENT 'reparse-point'" not in text


def test_only_reparse_point_missing_names_that_marker(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    bundle = _bundle(tmp_path / "global.js", _markers_text("user_bash"))
    _inject(monkeypatch, bundle)

    report = _report(project)
    issues = _activation_issues(report)
    assert len(issues) == 1
    assert str(bundle) in issues[0]
    assert "'reparse-point'" in issues[0]
    assert "'user_bash'" not in issues[0]

    text = mw_common.format_doctor_text(report)
    assert f"activation: MARKER-ABSENT 'reparse-point' {bundle} - run '{FIX}'" in text
    assert "MARKER-ABSENT 'user_bash'" not in text


def test_both_markers_missing_names_both(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    bundle = _bundle(tmp_path / "global.js", "var basis = 'resolved';\n")
    _inject(monkeypatch, bundle)

    report = _report(project)
    issues = _activation_issues(report)
    assert len(issues) == 1
    for marker in MARKERS:
        assert f"'{marker}'" in issues[0]

    text = mw_common.format_doctor_text(report)
    for marker in MARKERS:
        assert f"activation: MARKER-ABSENT '{marker}' {bundle} - run '{FIX}'" in text


def test_both_markers_present_reverse_control_rc_unchanged(
    tmp_path: pathlib.Path, monkeypatch, capsys
) -> None:
    project = _project(tmp_path)
    monkeypatch.setenv(mw_common.AGENT_DIR_ENV, str(tmp_path / "pi-agent"))
    bundle = _bundle(tmp_path / "global.js", _markers_text(*MARKERS))
    _inject(monkeypatch, bundle)

    report = _report(project)
    entry = report["activation"]["checked"][0]
    assert entry["has_marker"] is True
    assert entry["missing_markers"] == []
    assert all(entry["markers"][marker] is True for marker in MARKERS)
    assert _activation_issues(report) == []
    assert report["summary"]["healthy"] is True

    rc = mw.cmd_doctor(_doctor_args(project))
    assert rc == 0, capsys.readouterr().out
    assert "activation:" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# D-18 C9: the two copies have different roles, so different fix directives
# ---------------------------------------------------------------------------

def test_dist_and_installed_copies_carry_role_specific_wording(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    body = "var basis = 'resolved';\n"

    dist = _bundle(
        tmp_path / "packages" / "multi-workers" / "dist" / "extensions"
        / "agent-team-loop.js",
        body,
    )
    _inject(monkeypatch, dist)
    report = _report(project)
    issues = _activation_issues(report)
    assert len(issues) == 1
    assert "build artifact" in issues[0]
    assert "pi does not load this copy" in issues[0]
    assert f"run '{FIX_DIST}'" in issues[0]
    assert f"run '{FIX}'" not in issues[0]
    assert (
        f"activation: MARKER-ABSENT 'user_bash' {dist} - run '{FIX_DIST}'"
        in mw_common.format_doctor_text(report)
    )

    installed = _bundle(
        tmp_path / "pi-agent" / "extensions" / "agent-team-loop.js", body
    )
    _inject(monkeypatch, installed)
    report = _report(project)
    issues = _activation_issues(report)
    assert len(issues) == 1
    assert "installed bundle pi actually loads" in issues[0]
    assert f"run '{FIX}'" in issues[0]
    assert (
        f"activation: MARKER-ABSENT 'user_bash' {installed} - run '{FIX}'"
        in mw_common.format_doctor_text(report)
    )
