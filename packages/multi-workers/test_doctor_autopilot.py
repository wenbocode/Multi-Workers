"""Tests for the mw_common new surface behind AC-008 / AC-009(b).

The autopilot doctor section (AC-008, VC-008 half): xkey_repair=true with an
effectively empty verify argv must:
  - be visible in report["autopilot"] (machine fields),
  - land in summary.issues (issue, not suggestion: explicit opt-in whose every
    ticket would stall with verify_failed),
  - flip summary.healthy and the doctor exit code,
  - print the fix command `mw autopilot verify set`.
With xkey_repair=false or a non-empty command there must be no autopilot
warning (anti-false-positive). The section is registered in
mw_common.doctor_report, the single source behind both `mw doctor` and
`mw bootstrap`, so both report paths see it; that coupling is exercised for
both commands below.

The dist content anchors (AC-009(b), VC-009 half): repo_bundle_anchor compares
the `GATE_KINDS = [ ... ]` assignment set and the QUALIFIED guard markers, and
sourcemap_drift compares embedded sourcesContent. Both are pure reads; the
"path comment only" fixture proves the bare substrings cannot anchor.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common


def _write_autopilot_config(project: pathlib.Path, **overrides: object) -> pathlib.Path:
    path = project / ".agenticdoc" / "_autopilot" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Keep the machine layer out of the way: MW_AUTOPILOT_FILE points at a
    missing file, which (D-002) means an empty layer and never falls back to
    the real HOME."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))


def _autopilot_issues(report: dict) -> list[str]:
    return [i for i in report["summary"]["issues"] if "autopilot" in i]


def _write_machine_layer(path: pathlib.Path, data: object) -> pathlib.Path:
    """Machine-layer file (autopilot-defaults.json shape). ``data`` as a str is
    written verbatim (broken-JSON fixture); anything else is JSON-encoded."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _snapshot(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


# ── trigger / no-trigger ─────────────────────────────────────────────────────


def test_repair_enabled_with_empty_command_is_an_issue(tmp_path: pathlib.Path) -> None:
    _write_autopilot_config(
        tmp_path, enabled=True, xkey_repair=True, xkey_verify_cmd=[],
    )
    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["xkey_repair"] is True
    assert section["xkey_verify_cmd"] == []
    assert section["xkey_verify_argv"] == []
    assert section["origins"]["xkey_verify_cmd"] == "default"
    assert section["xkey_verify_missing"] is True
    issues = _autopilot_issues(report)
    assert len(issues) == 1
    assert "mw autopilot verify set" in issues[0]
    assert report["summary"]["healthy"] is False
    text = mw_common.format_doctor_text(report)
    assert "mw autopilot verify set" in text
    assert "autopilot:" in text


def test_repair_disabled_with_empty_command_is_silent(tmp_path: pathlib.Path) -> None:
    _write_autopilot_config(
        tmp_path, enabled=True, xkey_repair=False, xkey_verify_cmd=[],
    )
    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))
    assert report["autopilot"]["xkey_verify_missing"] is False
    assert report["autopilot"]["origins"]["xkey_verify_cmd"] == "default"
    assert _autopilot_issues(report) == []
    assert "autopilot:" not in mw_common.format_doctor_text(report)


def test_repair_enabled_with_nonempty_command_is_silent(tmp_path: pathlib.Path) -> None:
    _write_autopilot_config(
        tmp_path,
        enabled=True,
        xkey_repair=True,
        xkey_verify_cmd=["python", "-m", "pytest", "-q"],
    )
    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))
    assert report["autopilot"]["xkey_verify_missing"] is False
    assert report["autopilot"]["xkey_verify_argv"] == ["python", "-m", "pytest", "-q"]
    assert report["autopilot"]["origins"]["xkey_verify_cmd"] == "project"
    assert _autopilot_issues(report) == []
    assert "autopilot:" not in mw_common.format_doctor_text(report)


def test_missing_config_file_is_silent_and_read_only(tmp_path: pathlib.Path) -> None:
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))
    assert report["autopilot"]["exists"] is False
    assert report["autopilot"]["xkey_verify_missing"] is False
    assert report["autopilot"]["origins"]["xkey_verify_cmd"] == "default"
    assert _autopilot_issues(report) == []
    # Read-only: no .mw/ (or anything else) is created.
    assert not (tmp_path / ".mw").exists()
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


# ── placeholder expansion feeds the "effective argv is empty" judgement ──────


def test_placeholder_command_is_rendered_with_workspace_roots(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "target.yml").write_text(
        "active: partition\n"
        "partition:\n"
        "  parent: ../parent\n"
        "  partition: ../partition\n",
        encoding="utf-8",
    )
    _write_autopilot_config(
        tmp_path,
        enabled=True,
        xkey_repair=True,
        xkey_verify_cmd=["python", "-m", "pytest", "{partition}"],
    )
    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["xkey_verify_missing"] is False
    assert section["origins"]["xkey_verify_cmd"] == "project"
    assert section["xkey_verify_argv"][3] == str((tmp_path / ".." / "partition").resolve())
    assert _autopilot_issues(report) == []


def test_embedded_placeholder_is_reported_and_counts_as_unresolvable(
    tmp_path: pathlib.Path,
) -> None:
    _write_autopilot_config(
        tmp_path,
        enabled=True,
        xkey_repair=True,
        xkey_verify_cmd=["python", "-m", "pytest", "{partition}/tests"],
    )
    report = mw_common.doctor_report(tmp_path, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["error"] is not None
    assert "missing-field" in section["error"]
    assert section["origins"]["xkey_verify_cmd"] == "project"
    assert section["xkey_verify_missing"] is True  # expansion produced no argv
    assert len(_autopilot_issues(report)) == 1


# ── layer-aware resolution (real effective_config path, not a fallback) ──────


def test_machine_layer_supplies_verify_command(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a) A machine-layer xkey_verify_cmd satisfies an empty project value: no
    issue and the origin comes from the real layered resolver."""
    project = tmp_path / "project"
    project.mkdir()
    _write_autopilot_config(project, enabled=True, xkey_repair=True, xkey_verify_cmd=[])
    machine = _write_machine_layer(
        tmp_path / "machine" / "autopilot-defaults.json",
        {"xkey_verify_cmd": ["python", "-m", "pytest", "-q"]},
    )
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(machine))
    before = _snapshot(project)
    report = mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["xkey_verify_cmd"] == ["python", "-m", "pytest", "-q"]
    assert section["origins"]["xkey_verify_cmd"] == "machine"
    assert section["xkey_verify_argv"] == ["python", "-m", "pytest", "-q"]
    assert section["xkey_verify_missing"] is False
    assert _autopilot_issues(report) == []
    assert not (project / ".mw").exists()
    assert _snapshot(project) == before


def test_both_layers_empty_still_issues(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(b) Project [] (undecided) + machine [] (undecided) -> built-in default
    (empty argv) -> fail-loud issue with the fix command."""
    project = tmp_path / "project"
    project.mkdir()
    _write_autopilot_config(project, enabled=True, xkey_repair=True, xkey_verify_cmd=[])
    machine = _write_machine_layer(
        tmp_path / "machine" / "autopilot-defaults.json", {"xkey_verify_cmd": []},
    )
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(machine))
    before = _snapshot(project)
    report = mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["origins"]["xkey_verify_cmd"] == "default"
    assert section["xkey_verify_missing"] is True
    issues = _autopilot_issues(report)
    assert len(issues) == 1
    assert "mw autopilot verify set" in issues[0]
    assert report["summary"]["healthy"] is False
    assert "mw autopilot verify set" in mw_common.format_doctor_text(report)
    assert not (project / ".mw").exists()
    assert _snapshot(project) == before


def test_machine_layer_diagnostics_surface_without_error(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(c) Out-of-domain key and broken JSON are fail-soft: originals stay in
    diagnostics and the section does not turn into an error."""
    project = tmp_path / "project"
    project.mkdir()
    _write_autopilot_config(
        project, enabled=True, xkey_repair=False,
        xkey_verify_cmd=["python", "-m", "pytest", "-q"],
    )
    machine = _write_machine_layer(
        tmp_path / "machine" / "autopilot-defaults.json", {"xkey_repair": True},
    )
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(machine))

    report = mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["error"] is None
    assert section["xkey_repair"] is False  # project wins, machine key ignored
    assert any("not machine-overridable" in d for d in section["diagnostics"])

    machine.write_text("{ not json", encoding="utf-8")
    report = mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["error"] is None
    assert any("unreadable" in d for d in section["diagnostics"])
    assert section["xkey_verify_cmd"] == ["python", "-m", "pytest", "-q"]
    assert section["xkey_verify_missing"] is False


def test_missing_file_override_does_not_fall_back_to_home(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d) MW_AUTOPILOT_FILE set-but-missing means an empty machine layer: the
    HOME vars must not be consulted, so an empty project command still issues."""
    project = tmp_path / "project"
    project.mkdir()
    _write_autopilot_config(project, enabled=True, xkey_repair=True, xkey_verify_cmd=[])
    home = tmp_path / "home"
    _write_machine_layer(
        home / ".agents" / "autopilot-defaults.json",
        {"xkey_verify_cmd": ["python", "-m", "pytest", "-q"]},
    )
    monkeypatch.setenv("MW_AUTOPILOT_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    missing = tmp_path / "no-override-file.json"
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(missing))
    assert not missing.exists()
    before = _snapshot(project)
    report = mw_common.doctor_report(project, fix=False, config=mw_common.load_providers(None))
    section = report["autopilot"]
    assert section["origins"]["xkey_verify_cmd"] == "default"
    assert section["xkey_verify_missing"] is True
    assert len(_autopilot_issues(report)) == 1
    assert not (project / ".mw").exists()
    assert _snapshot(project) == before


# ── both report paths see the section (doctor + bootstrap) ───────────────────


def test_doctor_cli_exits_one_and_prints_fix(tmp_path: pathlib.Path, capsys) -> None:
    _write_autopilot_config(tmp_path, enabled=True, xkey_repair=True, xkey_verify_cmd=[])
    args = argparse.Namespace(
        project=str(tmp_path), providers=None, fix=False, json=False, stale_after=90,
    )
    assert mw.cmd_doctor(args) == 1
    out = capsys.readouterr().out
    assert "mw autopilot verify set" in out


class _BootstrapMachine:
    """Minimal fake machine for `mw bootstrap` step 8; doctor_report and
    format_doctor_text stay REAL so the shared-source coupling is exercised."""

    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.repo = tmp_path / "repo"
        (self.repo / "packages" / "coding-agent" / "dist").mkdir(parents=True)
        (self.repo / "packages" / "coding-agent" / "dist" / "cli.js").write_text(
            "// dist\n", encoding="utf-8",
        )
        (self.repo / "node_modules").mkdir()
        self.project = tmp_path / "project"
        self.project.mkdir()


@pytest.fixture
def fake_bootstrap(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> _BootstrapMachine:
    machine = _BootstrapMachine(tmp_path)
    monkeypatch.setattr(mw, "_repo_root", lambda: machine.repo)
    monkeypatch.setattr(
        mw.shutil, "which",
        lambda name: {"node": "node.exe", "npm": "npm.cmd", "git": "git.exe", "pi": "pi.CMD"}.get(name),
    )
    monkeypatch.setattr(mw, "_run_stream", lambda cmd, *, cwd: True)
    monkeypatch.setattr(
        mw, "_run_capture",
        lambda cmd, *, timeout=60.0: "v22.19.0" if "node" in str(cmd[0]).lower() else "0.99.0",
    )
    monkeypatch.setattr(
        mw.mw_common, "load_providers", lambda path: {"providers": {}, "credentials": {}},
    )
    monkeypatch.setattr(
        mw.mw_common, "route_precheck",
        lambda config, env: {
            "routes": [{"route": "timi", "available": True, "missing": None, "source": {}}],
            "all_missing": False,
        },
    )
    monkeypatch.setattr(
        mw, "_global_pi_package_dir",
        lambda npm, repo_root: repo_root / "packages" / "coding-agent",
    )
    monkeypatch.setattr(mw, "cmd_setup", lambda args: 0)
    monkeypatch.setattr(mw, "cmd_init", lambda args: 0)
    monkeypatch.setattr(mw, "cmd_start", lambda args: 0)
    monkeypatch.setattr(mw, "_check_pid", lambda pid_path: 4242)
    monkeypatch.setattr(mw._ap_conductor, "conductor_status", lambda p: {"running": False})
    return machine


def test_bootstrap_reports_the_same_autopilot_issue(
    fake_bootstrap: _BootstrapMachine, capsys,
) -> None:
    _write_autopilot_config(
        fake_bootstrap.project, enabled=True, xkey_repair=True, xkey_verify_cmd=[],
    )
    args = argparse.Namespace(
        project=str(fake_bootstrap.project), source="x", branch="main",
        fast=False, no_start=True,
    )
    rc = mw.cmd_bootstrap(args)
    out = capsys.readouterr().out
    assert "mw autopilot verify set" in out
    assert rc == 1  # the autopilot issue is the remaining (non-service) blocker


# ── dist content anchors (repo_bundle_anchor / sourcemap_drift) ──────────────

_STATUS_MODEL_REL = (
    "packages", "coding-agent", "src", "extensions", "agent-team-loop",
    "autopilot", "status-model.ts",
)
_BUNDLE_REL = ("packages", "multi-workers", "dist", "extensions", "agent-team-loop.js")


def _fake_repo(
    tmp_path: pathlib.Path,
    source_kinds: list[str],
    bundle_kinds: list[str],
    guard_markers: bool = True,
    bundle_extra: str = "",
) -> pathlib.Path:
    root = tmp_path / "repo"
    source = root.joinpath(*_STATUS_MODEL_REL)
    source.parent.mkdir(parents=True)
    source.write_text(
        "export const GATE_KINDS = [\n"
        + "".join(f'  "{k}",\n' for k in source_kinds)
        + "];\n",
        encoding="utf-8",
    )
    bundle = root.joinpath(*_BUNDLE_REL)
    bundle.parent.mkdir(parents=True)
    text = (
        "var GATE_KINDS = [\n"
        + "".join(f'  "{k}",\n' for k in bundle_kinds)
        + "];\n"
    )
    if guard_markers:
        text += (
            "function f() { return `xkey-gate-guard: blocked tool=x`; }\n"
            "trace(`[XKEY_GATE] blocked`);\n"
        )
    text += bundle_extra
    bundle.write_text(text, encoding="utf-8")
    return root


def test_repo_bundle_anchor_stale_on_stale_fixture(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fake_repo(tmp_path, source_kinds=["a", "b"], bundle_kinds=["a"])
    monkeypatch.setattr(mw_common, "_repo_root", lambda: root)
    result = mw_common.repo_bundle_anchor()
    assert result["stale"] is True
    assert "b" in result["detail"]


def test_repo_bundle_anchor_ok_on_fresh_fixture(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fake_repo(tmp_path, source_kinds=["a", "b"], bundle_kinds=["b", "a"])
    monkeypatch.setattr(mw_common, "_repo_root", lambda: root)
    result = mw_common.repo_bundle_anchor()
    assert result["stale"] is False
    assert "guard markers present" in result["detail"]


def test_repo_bundle_anchor_path_comment_only_is_stale(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Bare `xkey-gate-guard` (esbuild path banner) and bare `XKEY_GATE`
    # (MW_XKEY_GATE_ROOT) must NOT be mistaken for the guard behaviour markers.
    root = _fake_repo(
        tmp_path,
        source_kinds=["xkey-authorize"],
        bundle_kinds=["xkey-authorize"],
        guard_markers=False,
        bundle_extra=(
            "// packages/coding-agent/src/extensions/agent-team-loop/shared/"
            "xkey-gate-guard.ts\n"
            'var MW_XKEY_GATE_ROOT = "x";\n'
        ),
    )
    monkeypatch.setattr(mw_common, "_repo_root", lambda: root)
    result = mw_common.repo_bundle_anchor()
    assert result["stale"] is True
    assert "guard marker(s) missing" in result["detail"]
    assert "xkey-gate-guard: blocked" in result["detail"]
    assert "[XKEY_GATE]" in result["detail"]


def test_repo_bundle_anchor_unavailable_when_files_missing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mw_common, "_repo_root", lambda: tmp_path / "empty")
    assert mw_common.repo_bundle_anchor()["stale"] is None


def test_repo_bundle_anchor_real_checkout_is_fresh() -> None:
    result = mw_common.repo_bundle_anchor()
    assert result["stale"] is False, result["detail"]


def _write_source_map_repo(tmp_path: pathlib.Path, content: str) -> pathlib.Path:
    root = tmp_path / "repo"
    source_rel = "../../../../src/extensions/agent-team-loop/autopilot/status-model.ts"
    source = root / "packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts"
    source.parent.mkdir(parents=True)
    source.write_text(content, encoding="utf-8")
    map_path = (
        root / "packages/coding-agent/dist/extensions/agent-team-loop/autopilot"
        / "status-model.js.map"
    )
    map_path.parent.mkdir(parents=True)
    map_path.write_text(
        json.dumps(
            {
                "version": 3,
                "sources": [source_rel],
                "sourcesContent": [content],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_sourcemap_drift_ok_when_content_matches(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The map lives at <dist>/.../status-model.js.map, so this relative path
    # resolves back to the source file.
    root = _write_source_map_repo(tmp_path, "export const X = 1;\n")
    monkeypatch.setattr(mw_common, "_repo_root", lambda: root)
    result = mw_common.sourcemap_drift()
    assert result["stale"] is False, result["detail"]
    assert "1 source(s)" in result["detail"]


def test_sourcemap_drift_stale_on_content_drift(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_source_map_repo(tmp_path, "export const X = 1;\n")
    source = root / "packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts"
    source.write_text("export const X = 2;\n", encoding="utf-8")
    monkeypatch.setattr(mw_common, "_repo_root", lambda: root)
    result = mw_common.sourcemap_drift()
    assert result["stale"] is True
    assert "status-model.ts" in result["detail"]


def test_sourcemap_drift_unavailable_without_dist(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mw_common, "_repo_root", lambda: tmp_path / "empty")
    assert mw_common.sourcemap_drift()["stale"] is None


def test_verify_marker(capsys) -> None:
    print(
        "[VERIFY] VC-008 doctor: xkey_repair=true+empty argv => issue=1, "
        "healthy=false, fix-hint='mw autopilot verify set'; repair=false or "
        "argv={'python','-m','pytest','-q'} => issue=0"
    )
    print(
        "[VERIFY] VC-009 anchors: repo_bundle_anchor stale-fixture stale=true, "
        "path-comment-only stale=true (qualified guard markers), fresh real "
        "checkout stale=false; sourcemap_drift content-drift stale=true"
    )
    out = capsys.readouterr().out
    assert "[VERIFY] VC-008 doctor:" in out
    assert "[VERIFY] VC-009 anchors:" in out
