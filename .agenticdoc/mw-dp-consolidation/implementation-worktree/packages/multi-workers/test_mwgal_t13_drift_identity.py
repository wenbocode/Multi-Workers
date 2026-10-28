"""
test_mwgal_t13_drift_identity.py — serve code identity + drift self-check
(T-13 / AC-005, AC-006).

Covers:
  * `serve.meta` identity fields (schema / full-OID commit / dirty /
    code_mtime_ms / code_digest / version / written_at_ms) + atomic write.
  * The runtime code set and its sha256 digest: directory-level `test` skip,
    delete-visibility, touch-invisibility.
  * `serve_code_verdict()` matrix: fresh / content-changed / head-moved /
    history-only (digest equal, commit moved) / schema-stale capability /
    dirty-is-not-drift / cross-tree / undecidable fail-open.
  * Full-OID commit collection without the short-OID trap.
  * The double-channel drift alarm (`stderr` + timeline `config`) and its
    `(code_dir, meta_commit, head_commit, serve_pid)` rate limit.
  * Fresh-process-side entries as subprocesses: `mw status` and
    `mw doctor --json` (drift => issue => exit 1, TS `doctorMw`-compatible).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw

_MW_PY = pathlib.Path(__file__).parent / "mw.py"
_HAS_GIT = shutil.which("git") is not None


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_tree(root: pathlib.Path, *, files: dict[str, str] | None = None) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in (files or {"runtime.py": "x = 1\n"}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def _write_meta(project: pathlib.Path, **over: object) -> dict:
    (project / ".mw").mkdir(parents=True, exist_ok=True)
    meta = {
        "pid": os.getpid(),
        "started_at_ms": int((time.time() - 3600) * 1000),
        "code_dir": str(project.parent / "code"),
        "schema": mw.SERVE_META_SCHEMA,
    }
    meta.update(over)
    (project / ".mw" / "serve.meta").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _git_repo(root: pathlib.Path) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t.local"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "runtime.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "seed"], check=True, capture_output=True)
    return root


# ── serve.meta identity ──────────────────────────────────────────────────────

class TestServeMetaIdentity:
    def test_write_serve_meta_shape_and_atomic(self, tmp_path: pathlib.Path) -> None:
        mw._write_serve_meta(tmp_path)
        p = tmp_path / ".mw" / "serve.meta"
        meta = json.loads(p.read_text(encoding="utf-8"))
        assert meta["pid"] == os.getpid()
        assert meta["schema"] == mw.SERVE_META_SCHEMA
        assert meta["code_dir"] == str(mw._SCRIPT_DIR)
        for key in ("commit", "dirty_tracked", "dirty_untracked", "code_mtime_ms",
                    "code_digest", "version", "written_at_ms"):
            assert key in meta, key
        # Atomic write leaves no partial ".tmp" sibling.
        assert not (tmp_path / ".mw" / "serve.meta.tmp").exists()
        # Legacy fields are still present (old TS readers keep working).
        assert isinstance(meta["started_at_ms"], int)

    def test_remove_serve_meta_clears_tmp(self, tmp_path: pathlib.Path) -> None:
        mw._write_serve_meta(tmp_path)
        (tmp_path / ".mw" / "serve.meta.tmp").write_text("partial", encoding="utf-8")
        mw._remove_serve_meta(tmp_path)
        assert not (tmp_path / ".mw" / "serve.meta").exists()
        assert not (tmp_path / ".mw" / "serve.meta.tmp").exists()

    def test_identity_collection_is_fail_open_without_git(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulate "no git binary": every git call fails cleanly.
        monkeypatch.setattr(
            mw, "_git",
            lambda *a, **k: subprocess.CompletedProcess(["git"], 1, "", "not found"),
        )
        tree = _make_tree(tmp_path / "tree")
        identity = mw._serve_meta_identity(tree)
        assert identity["commit"] is None
        assert identity["dirty_tracked"] is None
        assert identity["dirty_untracked"] is None
        assert isinstance(identity["code_digest"], str)
        mw._write_serve_meta(tmp_path / "proj", identity)
        meta = json.loads((tmp_path / "proj" / ".mw" / "serve.meta").read_text(encoding="utf-8"))
        assert meta["commit"] is None

    @pytest.mark.skipif(not _HAS_GIT, reason="git not available")
    def test_identity_records_full_oid_not_short(self, tmp_path: pathlib.Path) -> None:
        repo = _git_repo(tmp_path / "repo")
        identity = mw._serve_meta_identity(repo)
        oid = identity["commit"]
        assert isinstance(oid, str) and len(oid) == 40
        assert oid == mw._git_head_oid(repo)
        # The short form must never be what is recorded: it is a different
        # string by construction (dynamic length), and comparing it to a full
        # OID would be a permanent false drift.
        short = mw._git_head_short(repo)
        if short is not None:
            assert short != oid
        assert identity["dirty_tracked"] == 0 and identity["dirty_untracked"] == 0


# ── runtime code set + digest ────────────────────────────────────────────────

class TestRuntimeDigest:
    def test_skip_set_includes_test_directory(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code")
        (tree / "test").mkdir()
        (tree / "test" / "fixture.json").write_text("{}", encoding="utf-8")
        runtime_mtime = (tree / "runtime.py").stat().st_mtime
        fixture_mtime = runtime_mtime + 10_000
        os.utime(tree / "test" / "fixture.json", (fixture_mtime, fixture_mtime))
        # The fixture must be invisible to both the mtime baseline and the digest.
        assert mw._mw_code_newest_mtime(tree) == pytest.approx(runtime_mtime)
        rels = {p.relative_to(tree).as_posix() for p in mw._runtime_code_files(tree)}
        assert rels == {"runtime.py"}

    def test_digest_stable_on_touch_and_changes_on_delete(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code", files={"runtime.py": "x = 1\n", "conf.json": "{}\n"})
        before = mw._runtime_digest(tree)
        # touch-only (content identical) must NOT read as drift.
        os.utime(tree / "runtime.py", (time.time() + 5, time.time() + 5))
        assert mw._runtime_digest(tree) == before
        assert mw._runtime_digest(tree).startswith("sha256:")
        # Deleting a runtime file is invisible to mtime but visible to digest.
        deleted_mtime = tree / "conf.json"
        (tmp_path / "conf.json").write_text("{}", encoding="utf-8")
        deleted_mtime.unlink()
        assert mw._runtime_digest(tree) != before

    def test_digest_none_for_empty_tree(self, tmp_path: pathlib.Path) -> None:
        tree = tmp_path / "empty"
        tree.mkdir()
        assert mw._runtime_digest(tree) is None


# ── verdict matrix ───────────────────────────────────────────────────────────

class TestServeCodeVerdict:
    def test_fresh_when_digest_matches(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code")
        project = tmp_path / "proj"
        digest = mw._runtime_digest(tree)
        _write_meta(project, code_digest=digest, code_mtime_ms=int(time.time() * 1000))
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "fresh" and v["restart_required"] is False
        assert "fresh" in v["detail"]

    def test_content_changed_is_drift_with_expected_actual_and_age(
        self, tmp_path: pathlib.Path
    ) -> None:
        tree = _make_tree(tmp_path / "code")
        past = time.time() - 7200
        os.utime(tree / "runtime.py", (past, past))
        project = tmp_path / "proj"
        _write_meta(
            project,
            code_digest="sha256:" + "0" * 64,
            code_mtime_ms=int((time.time() - 7200) * 1000),
            commit="a" * 40,
        )
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "drift" and v["reason"] == "content-changed"
        assert v["restart_required"] is True
        assert v["expected_commit"] == "a" * 40
        assert v["drift_age_s"] is not None and v["drift_age_s"] > 3600
        assert "expected commit=" + "a" * 40 in v["detail"]
        assert "fix: /mw restart" in v["detail"]

    @pytest.mark.skipif(not _HAS_GIT, reason="git not available")
    def test_content_changed_reports_real_expected_actual_pair(self, tmp_path: pathlib.Path) -> None:
        tree = _git_repo(tmp_path / "code")
        project = tmp_path / "proj"
        head = mw._git_head_oid(tree)
        _write_meta(
            project,
            code_digest="sha256:" + "0" * 64,
            code_mtime_ms=int((time.time() - 7200) * 1000),
            commit=head,
        )
        v = mw.serve_code_verdict(project)
        assert v["expected_commit"] == head and v["actual_commit"] == head
        assert f"expected commit={head}" in v["detail"]

    def test_delete_only_visible_to_digest(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code", files={"runtime.py": "x\n", "other.py": "y\n"})
        project = tmp_path / "proj"
        digest = mw._runtime_digest(tree)
        mtime_ms = int(mw._mw_code_newest_mtime(tree) * 1000)
        _write_meta(project, code_digest=digest, code_mtime_ms=mtime_ms)
        (tree / "other.py").unlink()
        # mtime judge would see nothing new; digest judge must catch the delete.
        assert mw._mw_code_newest_mtime(tree) == pytest.approx(mtime_ms / 1000)
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "drift" and v["reason"] == "content-changed"

    @pytest.mark.skipif(not _HAS_GIT, reason="git not available")
    def test_history_only_when_commit_moves_but_digest_matches(self, tmp_path: pathlib.Path) -> None:
        tree = _git_repo(tmp_path / "code")
        project = tmp_path / "proj"
        _write_meta(
            project,
            code_digest=mw._runtime_digest(tree),
            code_mtime_ms=int(time.time() * 1000),
            commit="a" * 40,
        )
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "history-only" and v["restart_required"] is False
        assert v["actual_commit"] and v["actual_commit"] != "a" * 40
        assert "history-only" in v["detail"]

    @pytest.mark.skipif(not _HAS_GIT, reason="git not available")
    def test_legacy_meta_commit_drift_alerts(self, tmp_path: pathlib.Path) -> None:
        tree = _git_repo(tmp_path / "code")
        project = tmp_path / "proj"
        # Legacy meta: no schema/digest, only a recorded commit (AC-005 literal).
        _write_meta(
            project,
            schema=0,
            code_digest=None,
            code_mtime_ms=int(time.time() * 1000),
            commit="b" * 40,
        )
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "drift" and v["reason"] == "head-moved"
        assert v["upper_bound"] is True

    def test_legacy_meta_mtime_drift_alerts(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code")
        project = tmp_path / "proj"
        _write_meta(project, schema=0, code_digest=None, code_mtime_ms=int((time.time() - 3600) * 1000))
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "drift" and v["reason"] == "content-changed"

    def test_dirty_workspace_is_not_drift(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code")
        project = tmp_path / "proj"
        _write_meta(
            project,
            code_digest=mw._runtime_digest(tree),
            code_mtime_ms=int(time.time() * 1000),
            commit="c" * 40,
            dirty_tracked=11,
            dirty_untracked=9,
        )
        v = mw.serve_code_verdict(project)
        assert v["verdict"] in ("fresh", "history-only")
        assert v["restart_required"] is False

    def test_schema_stale_means_must_restart(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code")
        project = tmp_path / "proj"
        _write_meta(
            project,
            schema=0,
            code_digest=mw._runtime_digest(tree),
            code_mtime_ms=int(time.time() * 1000),
        )
        v = mw.serve_code_verdict(project, checker_dir=tree)
        assert v["verdict"] == "drift" and v["reason"] == "schema-stale"
        assert v["restart_required"] is True
        assert "CAPABILITY DRIFT" in v["detail"]

    def test_cross_tree_capability_is_unknown_not_guessed(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "code")
        project = tmp_path / "proj"
        _write_meta(
            project,
            schema=1,
            code_digest=mw._runtime_digest(tree),
            code_mtime_ms=int(time.time() * 1000),
        )
        # Baseline tree (meta.code_dir) is NOT the checker's tree: content can
        # still be judged fresh, but capability must stay unknown.
        v = mw.serve_code_verdict(project, checker_dir=tmp_path / "elsewhere")
        assert v["same_tree"] is False
        assert v["verdict"] == "fresh"

    def test_meta_missing_and_code_dir_missing_are_undecidable(self, tmp_path: pathlib.Path) -> None:
        project = tmp_path / "proj"
        (project / ".mw").mkdir(parents=True)
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "undecidable" and v["reason"] == "meta-missing"
        _write_meta(project, code_dir=str(tmp_path / "nope"))
        v = mw.serve_code_verdict(project)
        assert v["verdict"] == "undecidable" and v["reason"] == "code-dir-missing"

    def test_legacy_meta_without_code_dir_falls_back_to_checker(self, tmp_path: pathlib.Path) -> None:
        tree = _make_tree(tmp_path / "checker")
        project = tmp_path / "proj"
        _write_meta(project, schema=0, code_dir=None, code_mtime_ms=int(time.time() * 1000))
        v = mw.serve_code_verdict(project, checker_dir=tree)
        assert v["tree"] == str(tree)
        assert v["verdict"] in ("fresh", "drift")


# ── ordering: identity collection precedes the PID file ─────────────────────

_T13_PROVIDERS = {
    "credentials": {"timi": {"sources": [{"env": "T13_TEST_KEY"}]}},
    "providers": {"timi": {"api_key_env": "T13_TEST_KEY", "credential": "timi"}},
}


def test_serve_identity_collected_before_pid_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-13 requirement 2: the identity probe (which spawns git) must run BEFORE
    `_write_pid`, so a hung git can never leave "PID present, service not up"."""
    proj = tmp_path / "proj"
    proj.mkdir()
    providers = tmp_path / "providers.json"
    providers.write_text(json.dumps(_T13_PROVIDERS), encoding="utf-8")
    monkeypatch.setenv("T13_TEST_KEY", "x")

    events: list[str] = []
    monkeypatch.setattr(
        mw,
        "_serve_meta_identity",
        lambda *a, **k: events.append("identity") or {"schema": mw.SERVE_META_SCHEMA},
    )
    monkeypatch.setattr(mw, "_write_pid", lambda p: events.append("pid"))
    # Keep the meta on disk for the post-run assertion (serve removes it in its
    # finally block on exit).
    monkeypatch.setattr(mw, "_remove_serve_meta", lambda p: None)

    class _Proc:
        pid = 4321
        returncode = None

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            pass

    monkeypatch.setattr(mw.subprocess, "Popen", lambda *a, **k: _Proc())
    monkeypatch.setattr(mw.time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt()))

    args = argparse.Namespace(
        project=str(proj), pi_port=1, claude_port=2, poll_interval=1,
        max_workers=None, providers=str(providers), deepseek_port=None,
    )
    assert mw.cmd_serve(args) == 0  # KeyboardInterrupt => intentional stop
    assert events.index("identity") < events.index("pid")
    meta = json.loads((proj / ".mw" / "serve.meta").read_text(encoding="utf-8"))
    assert meta["schema"] == mw.SERVE_META_SCHEMA


# ── full-OID collection without subprocess ───────────────────────────────────

@pytest.mark.skipif(not _HAS_GIT, reason="git not available")
def test_head_oid_pure_file_read_without_spawning_git(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path / "repo")
    expected = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    def _boom(*a, **k):
        raise AssertionError("git must not be spawned when the ref file is readable")

    monkeypatch.setattr(mw, "_git", _boom)
    assert mw._git_head_oid(repo) == expected


def test_git_dirty_counts_none_when_git_fails(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mw, "_git",
        lambda *a, **k: subprocess.CompletedProcess(["git"], 128, "", "boom"),
    )
    assert mw._git_dirty_counts(tmp_path) is None


# ── double-channel alarm + rate limit ────────────────────────────────────────

class TestDriftAlarm:
    def _drift_project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        tree = _make_tree(tmp_path / "code")
        project = tmp_path / "proj"
        _write_meta(
            project,
            code_digest="sha256:" + "1" * 64,
            code_mtime_ms=int((time.time() - 3600) * 1000),
            commit="d" * 40,
        )
        return project

    def test_emits_once_on_both_channels(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = self._drift_project(tmp_path)
        seen: set = set()
        mw._report_serve_code_drift(project, seen)
        mw._report_serve_code_drift(project, seen)  # same key => suppressed
        err = capsys.readouterr().err
        assert err.count("STALE CODE") == 1
        assert "fix: /mw restart" in err
        tl = project / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
        assert tl.is_file()
        events = [json.loads(line) for line in tl.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(events) == 1
        assert events[0]["ev"] == "config"
        assert "STALE CODE" in events[0]["detail"]

    def test_fresh_emits_nothing(self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
        tree = _make_tree(tmp_path / "code")
        project = tmp_path / "proj"
        _write_meta(
            project,
            code_digest=mw._runtime_digest(tree),
            code_mtime_ms=int(time.time() * 1000),
        )
        mw._report_serve_code_drift(project, set())
        assert capsys.readouterr().err == ""
        assert not (project / ".agenticdoc" / "_autopilot" / "timeline.jsonl").exists()


# ── fresh-process-side CLI entries ───────────────────────────────────────────

class TestFreshProcessEntries:
    def _world(self, tmp_path: pathlib.Path, *, stale: bool) -> pathlib.Path:
        project = tmp_path / "proj"
        (project / ".mw").mkdir(parents=True)
        # Legacy meta (no digest/schema) + a code tree whose mtime is either
        # newer than the recorded start (stale) or older (fresh).
        tree = project / "code"
        tree.mkdir()
        (tree / "runtime.py").write_text("x\n", encoding="utf-8")
        mtime = time.time() - 60 if stale else time.time() - 7200
        os.utime(tree / "runtime.py", (mtime, mtime))
        (project / ".mw" / "mw.pid").write_text(str(os.getpid()), encoding="utf-8")
        (project / ".mw" / "serve.meta").write_text(
            json.dumps({
                "pid": os.getpid(),
                "started_at_ms": int((time.time() - 3600) * 1000),
                "code_dir": str(tree),
            }),
            encoding="utf-8",
        )
        return project

    def _run(self, *args: str, project: pathlib.Path) -> subprocess.CompletedProcess:
        env = {**os.environ, mw_common_agent_dir(project): str(project / "pi-agent")}
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(_MW_PY), *args, f"--project={project}"],
            capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace", env=env,
        )

    def test_status_entry(self, tmp_path: pathlib.Path) -> None:
        stale = self._world(tmp_path / "s", stale=True)
        res = self._run("status", project=stale)
        assert res.returncode == 0, res.stderr
        assert "serve code: STALE CODE" in res.stdout
        assert "fix: /mw restart" in res.stdout

        fresh = self._world(tmp_path / "f", stale=False)
        res = self._run("status", project=fresh)
        assert res.returncode == 0
        assert "serve code: fresh" in res.stdout

    def test_doctor_entry_drift_is_issue_and_exit_one(self, tmp_path: pathlib.Path) -> None:
        stale = self._world(tmp_path / "s", stale=True)
        res = self._run("doctor", "--json", project=stale)
        assert res.returncode == 1, (res.returncode, res.stdout, res.stderr)
        report = json.loads(res.stdout)
        assert report["serve_code"]["verdict"] == "drift"
        assert report["serve_code"]["restart_required"] is True
        assert report["summary"]["healthy"] is False
        assert any("STALE CODE" in i for i in report["summary"]["issues"])

    def test_doctor_entry_fresh_stays_healthy(self, tmp_path: pathlib.Path) -> None:
        fresh = self._world(tmp_path / "f", stale=False)
        res = self._run("doctor", "--json", project=fresh)
        report = json.loads(res.stdout)
        assert report["serve_code"]["verdict"] in ("fresh", "history-only")
        assert not any("STALE CODE" in i for i in report["summary"]["issues"])


def mw_common_agent_dir(project: pathlib.Path) -> str:
    """Name of the env var that scopes doctor's pi-shell section to a tmp dir."""
    import mw_common

    return mw_common.AGENT_DIR_ENV


# ── optional OS probe ────────────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform not in ("win32", "linux"), reason="no OS probe on this platform")
def test_process_start_ms_probe() -> None:
    got = mw.process_start_ms(os.getpid())
    assert got is not None
    assert abs(got - time.time() * 1000) < 300_000
    assert mw.process_start_ms(0) is None
