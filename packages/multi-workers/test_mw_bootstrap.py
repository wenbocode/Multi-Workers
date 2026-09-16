"""Tests for `mw bootstrap` (fresh-machine one-shot, steps 1-8).

All externals are mocked: no npm/pip subprocess ever runs, no real repo state
is touched (repo_root is redirected to a tmp dir). These tests pin the step
sequence, the fail-fast gates, and the idempotent re-run behavior.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw


def _bootstrap_args(**overrides: object) -> argparse.Namespace:
    """The namespace _parse_args produces for `mw bootstrap` (defaults)."""
    base: dict[str, object] = {
        "project": None,
        "source": mw._DEFAULT_AGENTICTASK_REMOTE,
        "branch": mw._DEFAULT_AGENTICTASK_BRANCH,
        "fast": False,
        "no_start": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class _Recorder:
    """Collects (tag, detail) for every mocked extern call, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def note(self, tag: str, detail: str = "") -> None:
        self.calls.append((tag, detail))

    def tags(self) -> list[str]:
        return [tag for tag, _ in self.calls]


@pytest.fixture
def fake_machine(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> _Recorder:
    """A fully mocked machine around a tmp repo root + tmp project dir.

    - repo root redirected to tmp_path (real repo state untouched)
    - node/npm/git/pi resolved to fake paths; version probes succeed
    - credential route: timi available
    - cmd_setup / cmd_init / cmd_start / doctor_report stubbed to success
    - service considered already-started by default (skip start wait loop)
    """
    rec = _Recorder()

    repo = tmp_path / "repo"
    (repo / "packages" / "coding-agent" / "dist").mkdir(parents=True)
    (repo / "packages" / "coding-agent" / "dist" / "cli.js").write_text("// dist\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()

    monkeypatch.setattr(mw, "_repo_root", lambda: repo)

    fake_bins = {
        "node": str(tmp_path / "node.exe"),
        "npm": str(tmp_path / "npm.cmd"),
        "git": str(tmp_path / "git.exe"),
        "pi": str(tmp_path / "pi.CMD"),
    }
    monkeypatch.setattr(
        mw.shutil, "which", lambda name: fake_bins.get(name), raising=True,
    )

    def fake_run_stream(cmd: list[str], *, cwd: pathlib.Path) -> bool:
        exe = pathlib.Path(cmd[0]).stem  # npm / python
        rec.note("stream", f"{exe} {' '.join(cmd[1:3])} @ {pathlib.Path(cwd).name}")
        return True

    def fake_run_capture(cmd: list[str], *, timeout: float = 60.0) -> str | None:
        exe = pathlib.Path(cmd[0]).name.lower()
        if exe.startswith("node"):
            return "v22.19.0"
        if exe.startswith("pi"):
            return "0.99.0-test"
        return None

    monkeypatch.setattr(mw, "_run_stream", fake_run_stream)
    monkeypatch.setattr(mw, "_run_capture", fake_run_capture)

    monkeypatch.setattr(
        mw.mw_common, "load_providers", lambda path: {"providers": {}, "credentials": {}},
    )
    monkeypatch.setattr(
        mw.mw_common,
        "route_precheck",
        lambda config, env: {
            "routes": [{"route": "timi", "available": True, "missing": None, "source": "env"}],
            "all_missing": False,
        },
    )

    def fake_setup(a: argparse.Namespace) -> int:
        rec.note("setup", f"build={a.build} source={a.source}")
        return 0

    def fake_init(a: argparse.Namespace) -> int:
        rec.note("init", a.project)
        (pathlib.Path(a.project) / ".agents" / "skills" / "agentic-task").mkdir(
            parents=True, exist_ok=True,
        )
        (pathlib.Path(a.project) / ".agents" / "skills" / "agentic-task" / "SKILL.md").write_text(
            "# skill\n", encoding="utf-8",
        )
        return 0

    def fake_start(a: argparse.Namespace) -> int:
        rec.note("start", a.project)
        return 0

    monkeypatch.setattr(mw, "cmd_setup", fake_setup)
    monkeypatch.setattr(mw, "cmd_init", fake_init)
    monkeypatch.setattr(mw, "cmd_start", fake_start)

    # Step 4's link-target verification: by default the global package dir
    # "resolves" to the repo package (what a correct npm link means).
    monkeypatch.setattr(
        mw, "_global_pi_package_dir",
        lambda npm, repo_root: repo_root / "packages" / "coding-agent",
    )

    monkeypatch.setattr(mw, "_check_pid", lambda pid_path: 4242)
    monkeypatch.setattr(mw._ap_conductor, "conductor_status", lambda p: {"running": False})
    monkeypatch.setattr(
        mw.mw_common,
        "doctor_report",
        lambda project_dir, fix, config, stale_after_sec: {
            "service": {"running": True},
            "queue": {"stale_count": 0},
            "launcher_log": {},
            "target": None,
            "bundle": {},
            "orphan_proxy": {"detected": False, "ports": []},
            "worker_liveness": {},
            "credentials": {"routes": []},
            "conductor": {"running": False},
            "summary": {"healthy": True, "issues": [], "suggestions": []},
        },
    )
    monkeypatch.setattr(
        mw.mw_common, "format_doctor_text", lambda report: "[doctor] healthy",
    )

    rec.repo = repo  # type: ignore[attr-defined]
    rec.project = project  # type: ignore[attr-defined]
    return rec


class TestHappyPath:
    def test_full_bootstrap_sequence_fresh_machine(
        self, fake_machine: _Recorder, capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 0
        # Steps 1-8 all announced, in order (7 is skipped: service already
        # running on the fake machine — asserted separately below).
        out = capsys.readouterr().out
        steps = [line for line in out.splitlines() if "step " in line and "skipped" not in line]
        assert [s.split(":")[0].rsplit(" ", 1)[-1] for s in steps] == [
            "1/8", "2/8", "3/8", "4/8", "5/8", "6/8", "8/8",
        ]
        # Fresh machine (no node_modules) → npm ci; then build, link, setup, init.
        assert fake_machine.tags() == ["stream", "stream", "stream", "setup", "init"]
        assert fake_machine.calls[0][1].startswith("npm ci --ignore-scripts @ repo")
        assert fake_machine.calls[1][1].startswith("npm run build @ repo")
        assert fake_machine.calls[2][1].startswith("npm link @ coding-agent")
        # The already-running service (fake _check_pid) → step 7 skipped, not started.
        assert "start" not in fake_machine.tags()
        assert "skipped (already running (PID 4242))" in out
        assert "[doctor] healthy" in out

    def test_rerun_with_existing_node_modules_uses_npm_install(
        self, fake_machine: _Recorder,
    ) -> None:
        (fake_machine.repo / "node_modules").mkdir()
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 0
        assert fake_machine.calls[0][1].startswith("npm install --ignore-scripts @ repo")


class TestFastRerun:
    def test_fast_requires_prior_full_bootstrap(
        self, fake_machine: _Recorder, capsys: pytest.CaptureFixture[str],
    ) -> None:
        # No node_modules in the fake repo → nothing to fast-skip.
        rc = mw.cmd_bootstrap(_bootstrap_args(fast=True))
        assert rc == 1
        assert "--fast needs a previous full bootstrap" in capsys.readouterr().err

    def test_fast_skips_install_and_build_but_links_and_sets_up(
        self, fake_machine: _Recorder, capsys: pytest.CaptureFixture[str],
    ) -> None:
        (fake_machine.repo / "node_modules").mkdir()
        rc = mw.cmd_bootstrap(
            _bootstrap_args(fast=True, project=str(fake_machine.project)),
        )
        assert rc == 0
        # Only the npm link ran (no ci/install, no run build).
        streams = [d for t, d in fake_machine.calls if t == "stream"]
        assert streams == ["npm link @ coding-agent"]
        out = capsys.readouterr().out
        assert "step 2/8: skipped (--fast)" in out
        assert "step 3/8: skipped (--fast)" in out


    def test_no_credentials_warns_proceeds_and_skips_service_start(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Fresh machine before any auth configuration (~/.pi/agent/auth.json
        # does not exist yet): bootstrap must NOT abort — steps 2-6 are
        # credential-free, the service start is held back, and the doctor
        # verdict tolerates the expected service-not-running issue.
        monkeypatch.setattr(
            mw.mw_common,
            "route_precheck",
            lambda config, env: {
                "routes": [
                    {"route": "timi", "available": False,
                     "missing": "TIMI_API_KEY", "source": None},
                ],
                "all_missing": True,
            },
        )
        monkeypatch.setattr(mw, "_check_pid", lambda pid_path: None)
        base_doctor = {
            "service": {"running": False},
            "queue": {"stale_count": 0},
            "launcher_log": {},
            "target": None,
            "bundle": {},
            "orphan_proxy": {"detected": False, "ports": []},
            "worker_liveness": {},
            "credentials": {"routes": []},
            "conductor": {"running": False},
            "summary": {
                "healthy": False,
                "issues": ["mw service not running (workers will not be dispatched)"],
                "suggestions": [],
            },
        }
        monkeypatch.setattr(
            mw.mw_common, "doctor_report",
            lambda project_dir, fix, config, stale_after_sec: base_doctor,
        )
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 0
        # The install ran to completion: npm, build, link, setup, init — only
        # the service start is held back.
        assert fake_machine.tags() == ["stream", "stream", "stream", "setup", "init"]
        out = capsys.readouterr().out
        assert "Warning: no route has credentials yet" in out
        assert "auth.json" in out
        assert "step 7/8: skipped (no credential route configured" in out
        # Doctor's service-not-running issue did not fail the verdict.
        assert "finished with" not in out


class TestFailFastGates:
    def test_old_node_aborts(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            mw, "_run_capture", lambda cmd, *, timeout=60.0: "v18.0.0",
        )
        rc = mw.cmd_bootstrap(_bootstrap_args())
        assert rc == 1
        assert fake_machine.calls == []
        assert "node >=" in capsys.readouterr().err

    def test_missing_pi_after_link_fails(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            mw.shutil, "which", lambda name: None if name == "pi" else "x",
        )
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 1


class TestPiLinkVerification:
    def test_foreign_registry_install_rejected(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path,
    ) -> None:
        # A pre-existing registry install of the official package: the global
        # dir exists but is a plain directory, not a link to this repo.
        foreign = tmp_path / "global-npm" / "@earendil-works" / "pi-coding-agent"
        foreign.mkdir(parents=True)
        monkeypatch.setattr(
            mw, "_global_pi_package_dir", lambda npm, repo_root: foreign,
        )
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 1
        err = capsys.readouterr().err
        assert "not linked to this repo" in err
        assert "npm uninstall -g" in err

    def test_missing_global_package_rejected(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(mw, "_global_pi_package_dir", lambda npm, repo_root: None)
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 1
        assert "npm link did not install" in capsys.readouterr().err

    def test_link_target_ok_compares_realpaths(
        self, tmp_path: pathlib.Path,
    ) -> None:
        repo_pkg = tmp_path / "repo" / "packages" / "coding-agent"
        repo_pkg.mkdir(parents=True)
        other = tmp_path / "elsewhere"
        other.mkdir()
        assert mw._pi_link_target_ok(repo_pkg, repo_pkg)
        assert not mw._pi_link_target_ok(other, repo_pkg)

    def test_global_pi_package_dir_resolves_npm_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path,
    ) -> None:
        # repo with a package name; global root with the package present
        repo = tmp_path / "repo"
        (repo / "packages" / "coding-agent").mkdir(parents=True)
        (repo / "packages" / "coding-agent" / "package.json").write_text(
            '{"name": "@scope/pi-x"}', encoding="utf-8",
        )
        global_root = tmp_path / "global-nm"
        pkg_dir = global_root / "@scope" / "pi-x"
        pkg_dir.mkdir(parents=True)
        monkeypatch.setattr(
            mw, "_run_capture",
            lambda cmd, *, timeout=60.0: f"  {global_root}  \n",
        )
        assert mw._global_pi_package_dir("npm", repo) == pkg_dir

    def test_global_pi_package_dir_none_cases(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path,
    ) -> None:
        repo = tmp_path / "repo"  # no package.json → name fallback
        repo.mkdir()
        # npm root -g failed
        monkeypatch.setattr(mw, "_run_capture", lambda cmd, *, timeout=60.0: None)
        assert mw._global_pi_package_dir("npm", repo) is None
        # npm root -g ok but the package dir does not exist there
        empty_root = tmp_path / "empty-nm"
        empty_root.mkdir()
        monkeypatch.setattr(
            mw, "_run_capture", lambda cmd, *, timeout=60.0: str(empty_root),
        )
        assert mw._global_pi_package_dir("npm", repo) is None


class TestStartAndDoctor:
    def test_start_wait_loop_times_out(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(mw, "_check_pid", lambda pid_path: None)
        monkeypatch.setattr(mw.time, "sleep", lambda s: None)
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 1
        # start was attempted (fresh service), then the 30s wait failed.
        assert "start" in fake_machine.tags()
        assert "did not come up within 30s" in capsys.readouterr().err

    def test_no_start_tolerates_service_not_running_issue(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            mw.mw_common,
            "doctor_report",
            lambda project_dir, fix, config, stale_after_sec: {
                "service": {"running": False},
                "queue": {"stale_count": 0},
                "launcher_log": {},
                "target": None,
                "bundle": {},
                "orphan_proxy": {"detected": False, "ports": []},
                "worker_liveness": {},
                "credentials": {"routes": []},
                "conductor": {"running": False},
                "summary": {
                    "healthy": False,
                    "issues": ["mw service not running (workers will not be dispatched)"],
                    "suggestions": [],
                },
            },
        )
        rc = mw.cmd_bootstrap(
            _bootstrap_args(no_start=True, project=str(fake_machine.project)),
        )
        # The expected issue is filtered; bootstrap still succeeds.
        assert rc == 0
        out = capsys.readouterr().out
        assert "step 7/8: skipped (--no-start" in out

    def test_doctor_issue_fails_bootstrap(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = {
            "service": {"running": True},
            "queue": {"stale_count": 2},
            "launcher_log": {},
            "target": None,
            "bundle": {},
            "orphan_proxy": {"detected": False, "ports": []},
            "worker_liveness": {},
            "credentials": {"routes": []},
            "conductor": {"running": False},
            "summary": {"healthy": False, "issues": ["2 stale queue entries"], "suggestions": []},
        }
        monkeypatch.setattr(
            mw.mw_common, "doctor_report",
            lambda project_dir, fix, config, stale_after_sec: report,
        )
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 1

    def test_framework_missing_warns_but_succeeds(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def bare_init(a: argparse.Namespace) -> int:
            # Deliberately installs nothing: no .agents/skills/agentic-task.
            return 0

        monkeypatch.setattr(mw, "cmd_init", bare_init)
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 0
        assert "AgenticTask framework not installed" in capsys.readouterr().out

    def test_timi_route_missing_warns_at_the_end(
        self, fake_machine: _Recorder, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Another route is available (serve starts), but the default worker
        # route (timi) is not → warning, still exit 0.
        monkeypatch.setattr(
            mw.mw_common,
            "route_precheck",
            lambda config, env: {
                "routes": [
                    {"route": "claude", "available": True, "missing": None, "source": "env"},
                    {"route": "timi", "available": False, "missing": "TIMI_API_KEY", "source": None},
                ],
                "all_missing": False,
            },
        )
        rc = mw.cmd_bootstrap(_bootstrap_args(project=str(fake_machine.project)))
        assert rc == 0
        assert "TIMI_API_KEY is not set" in capsys.readouterr().out


class TestVersionHelpers:
    def test_version_tuple(self) -> None:
        assert mw._version_tuple("v22.19.0") == (22, 19, 0)
        assert mw._version_tuple("22.19.0") == (22, 19, 0)
        assert mw._version_tuple("garbage") is None

    def test_node_engine_min_reads_package_json(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"engines": {"node": ">=23.1.4"}}', encoding="utf-8",
        )
        assert mw._node_engine_min(tmp_path) == (23, 1, 4)

    def test_node_engine_min_falls_back(self, tmp_path: pathlib.Path) -> None:
        assert mw._node_engine_min(tmp_path) == mw._NODE_MIN_FALLBACK
