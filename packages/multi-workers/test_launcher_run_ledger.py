"""Launcher usage-ledger hooks (mw-usage-monitor T-02).

Every test redirects ``MW_USAGE_DIR`` at a ``tmp_path`` dir, so nothing ever
touches the host's real ``~/.mw/usage/runs.jsonl``, and no test starts a real
worker process: ``Popen`` (and, where needed, the model re-dispatch) is faked.

Covered (card T-02):

1. ``_build_command`` argv shape for pi / claude / codex + session-id placement;
2. ``start``/``end`` field completeness, ``run_id`` pairing and ``wall_s``;
3. the exit-3 re-dispatch writes ``end`` BEFORE the next run's ``start``;
4. the spawn-failure path writes ``spawn_failed`` (no pid, no wall);
5. fail-soft: an unusable ledger directory changes nothing about the spawn;
6. orphan reconcile writes ``end(reconciled=true)`` with the ``[END]`` exit or
   ``null`` (never 0).
"""

from __future__ import annotations

import json
import pathlib
import sys
import types
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import launcher  # noqa: E402
import mw_common  # noqa: E402
import usage  # noqa: E402

#: Envelope-compliant `coding` card (same shape the launcher's G-2 gate expects).
_COMPLIANT_TASK_MD = (
    "type: coding\n"
    "\n"
    "## 上下文\n"
    "\n"
    "背景：launcher 台账测试夹具。\n"
    "\n"
    "## 要求\n"
    "\n"
    "Do something useful. AC-001 判据成立。\n"
    "\n"
    "## 交付格式\n"
    "\n"
    "产物 report.md。\n"
    "\n"
    "## 写入允许面\n"
    "\n"
    "仅本任务目录。\n"
    "\n"
    "## 写入禁止面\n"
    "\n"
    "其他 key 与 packages/**。\n"
    "\n"
    "## 验收命令\n"
    "\n"
    "python -X utf8 -m pytest packages/multi-workers -q\n"
    "\n"
    "## 改动历史\n"
    "\n"
    "trace.log 写入事件。\n"
)

_HERMETIC_CONFIG = {
    "credentials": {
        "timi": {"sources": [{"env": "TIMI_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "ANTHROPIC_AUTH_TOKEN"}]},
    },
    "providers": {
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
        "claude-cli": {
            "port": 7003,
            "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_AUTH_TOKEN",
            "credential": "anthropic-auth",
        },
    },
}

_START_FIELDS = {
    "event",
    "run_id",
    "ts",
    "source",
    "project",
    "key",
    "task_key",
    "type",
    "role",
    "cli",
    "attribution",
    "session_id",
    "model",
    "model_source",
    "pid",
    "cwd",
}
_END_FIELDS = {"event", "run_id", "ts", "exit", "wall_s", "status", "reconciled"}


class _FakeProc:
    """Stand-in for `subprocess.Popen` (no process is ever started)."""

    def __init__(self, pid: int = 4242, returncode: int | None = None) -> None:
        self.pid = pid
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


@pytest.fixture()
def ledger_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    target = tmp_path / "machine-usage"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setattr(launcher, "_USAGE_RUNS", {})
    return target


@pytest.fixture()
def task_file(tmp_path: pathlib.Path) -> pathlib.Path:
    t = tmp_path / ".agenticdoc" / "test-key" / "workers" / "t001" / "task.md"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(_COMPLIANT_TASK_MD, encoding="utf-8")
    return t


@pytest.fixture()
def providers(tmp_path: pathlib.Path) -> dict:
    path = tmp_path / "providers.json"
    path.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return launcher._load_providers(path)


@pytest.fixture()
def queue_file(tmp_path: pathlib.Path) -> pathlib.Path:
    agentic = tmp_path / ".agenticdoc"
    agentic.mkdir(exist_ok=True)
    return agentic / "_workers.parallel"


@pytest.fixture(autouse=True)
def _timi_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")


def _entry(task_file: pathlib.Path, **overrides: str) -> dict[str, str]:
    entry = {
        "cli": "pi",
        "provider": "timi",
        "task_path": str(task_file),
        "task_key": "t001",
        "status": "pending",
        "dispatched_at": "2026-10-19T00:00:00+00:00",
        "updated_at": "2026-10-19T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


def _queue_row(queue_file: pathlib.Path, entry: dict[str, str]) -> None:
    queue_file.write_text(launcher._serialize_entry(entry) + "\n", encoding="utf-8")


def _fake_popen(monkeypatch: pytest.MonkeyPatch, procs: list[_FakeProc]) -> dict:
    """Patch Popen so each spawn returns the next fake proc; capture argv."""
    captured: dict = {"cmds": [], "cwd": []}
    pending = list(procs)

    def _popen(cmd, **kwargs):
        captured["cmds"].append(list(cmd))
        captured["cwd"].append(kwargs.get("cwd"))
        return pending.pop(0) if pending else _FakeProc()

    monkeypatch.setattr(launcher.subprocess, "Popen", _popen)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(pathlib.Path(name + ".CMD")))
    return captured


def _events(ledger_dir: pathlib.Path) -> list[dict]:
    path = ledger_dir / usage.LEDGER_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _end_marker(exit_code: int) -> str:
    return f"[END] 2026-10-19T09:00:00+00:00 exit={exit_code} elapsed=120s tools=5 phases=all"


# ── 1. argv shape: --session-id for pi/claude only ───────────────────────────


class TestSessionIdInArgv:
    def test_pi_carries_session_id_before_prompt(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        cmd = launcher._build_command(entry, session_id="mw-test-key-12-3")
        starter = launcher._starter_prompt(str(task_file))
        assert cmd == [
            "pi",
            "--provider",
            "timi",
            "--model",
            "glm-5.3",
            "--session-id",
            "mw-test-key-12-3",
            "-p",
            starter,
        ]
        # order semantics preserved: --model keeps its slot, -p stays last
        assert cmd[-1] == starter
        assert cmd.index("--model") < cmd.index("--session-id") < cmd.index("-p")

    def test_pi_generic_route_keeps_model_position(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "", "task_path": str(task_file), "model": "claude-x"}
        cmd = launcher._build_command(entry, session_id="sid")
        assert cmd[:4] == ["pi", "--model", "claude-x", "--session-id"]
        assert cmd[-1] == launcher._starter_prompt(str(task_file))

    def test_claude_carries_session_id(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "claude", "provider": "", "task_path": str(task_file), "model": "claude-y"}
        cmd = launcher._build_command(entry, session_id="0f0a2c34-0000-4000-8000-000000000000")
        assert cmd == [
            "claude",
            "--model",
            "claude-y",
            "--session-id",
            "0f0a2c34-0000-4000-8000-000000000000",
            "-p",
            launcher._starter_prompt(str(task_file)),
        ]

    def test_codex_ignores_session_id(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "codex", "provider": "", "task_path": str(task_file), "model": "gpt-x"}
        assert launcher._build_command(entry, session_id="sid") == [
            "codex",
            "exec",
            "-m",
            "gpt-x",
            launcher._starter_prompt(str(task_file)),
        ]

    def test_no_session_id_keeps_legacy_argv(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        assert "--session-id" not in launcher._build_command(entry)


class TestSessionIdAllocation:
    def test_pi_ids_are_unique_and_mw_prefixed(self, task_file: pathlib.Path) -> None:
        entry = _entry(task_file)
        first = launcher._usage_session_id(entry)
        second = launcher._usage_session_id(entry)
        assert first is not None and second is not None
        assert first.startswith("mw-test-key-")
        assert first != second  # same key, different seq: never resume an old file
        assert usage.SESSION_ID_RE.match(first)

    def test_claude_gets_uuid4(self, task_file: pathlib.Path) -> None:
        session_id = launcher._usage_session_id(_entry(task_file, cli="claude", provider=""))
        assert session_id is not None
        assert uuid.UUID(session_id).version == 4

    def test_codex_gets_nothing(self, task_file: pathlib.Path) -> None:
        assert launcher._usage_session_id(_entry(task_file, cli="codex", provider="")) is None


# ── 2. start/end pairing + wall clock ────────────────────────────────────────


class TestStartEndPairing:
    def test_spawn_then_reap_pairs_events_and_restores_wall(
        self,
        tmp_path: pathlib.Path,
        ledger_dir: pathlib.Path,
        task_file: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = _entry(task_file)
        _queue_row(queue_file, entry)
        proc = _FakeProc(pid=4242)
        _fake_popen(monkeypatch, [proc])
        clock = {"now": 1000.0}
        monkeypatch.setattr(launcher, "time", types.SimpleNamespace(time=lambda: clock["now"]))

        running: dict = {}
        launcher._spawn(entry, tmp_path, providers, running)
        assert running["t001"] is proc

        starts = _events(ledger_dir)
        assert len(starts) == 1 and starts[0]["event"] == "start"
        start = starts[0]
        assert _START_FIELDS <= set(start)
        assert start["key"] == "test-key"
        assert start["task_key"] == "t001"
        assert start["type"] == "coding"
        assert start["role"] == "coding"
        assert start["cli"] == "pi"
        assert start["attribution"] == "exact"
        assert start["pid"] == 4242
        assert start["project"] == str(tmp_path)
        assert start["cwd"] == str(tmp_path)
        assert start["model_source"]  # source of the resolved model is recorded
        assert start["session_id"].startswith("mw-test-key-")

        # 12.5s later the worker exits 0 and the next poll reaps it.
        clock["now"] = 1012.5
        proc.returncode = 0
        launcher._poll_once(tmp_path, providers, running, {}, [], None)
        ends = [event for event in _events(ledger_dir) if event["event"] == "end"]
        assert len(ends) == 1
        end = ends[0]
        assert _END_FIELDS <= set(end)
        assert end["run_id"] == start["run_id"]
        assert end["exit"] == 0
        assert end["status"] == "done"
        assert end["reconciled"] is False
        assert end["wall_s"] == pytest.approx(12.5)

        runs, meta = usage.load_runs(launcher._USAGE_EPOCH)
        assert meta["bad_lines"] == 0
        assert len(runs) == 1
        run = runs[0]
        assert run["run_id"] == start["run_id"]
        assert run["session_id"] == start["session_id"]
        assert run["wall_s"] == pytest.approx(12.5)
        assert run["exit"] == 0
        assert run["open_run"] is False and run["spawned"] is True

    def test_record_builders_are_pure_and_field_complete(self) -> None:
        start = launcher._usage_start_record(
            run_id="r1",
            ts="2026-10-19T00:00:00+00:00",
            key="k",
            task_key="tk",
            task_type="review",
            role="review",
            cli="claude",
            session_id="sid",
            model="claude/x",
            model_source="config:review",
            pid=7,
            cwd="/w",
            project="/p",
        )
        assert set(start) == _START_FIELDS
        assert start["attribution"] == "exact"

        codex = launcher._usage_start_record(
            run_id="r2",
            ts="t",
            key="k",
            task_key="tk",
            task_type="coding",
            role="coding",
            cli="codex",
            session_id=None,
            model="",
            model_source="default",
            pid=8,
            cwd="/w",
            project="/p",
        )
        assert codex["attribution"] == "unknown_cli"

        end = launcher._usage_end_record(
            run_id="r1", ts="t2", exit_code=None, wall_s=None, status="lost", reconciled=True
        )
        assert set(end) == _END_FIELDS
        assert end["exit"] is None and end["wall_s"] is None and end["reconciled"] is True


# ── 3. exit-3 re-dispatch: end before the next start ─────────────────────────


class TestExit3Redispatch:
    def test_end_is_written_before_the_next_start(
        self,
        tmp_path: pathlib.Path,
        ledger_dir: pathlib.Path,
        task_file: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = _entry(task_file)
        _queue_row(queue_file, entry)
        first = _FakeProc(pid=5001)
        second = _FakeProc(pid=5002)
        captured = _fake_popen(monkeypatch, [first, second])

        running: dict = {}
        launcher._spawn(entry, tmp_path, providers, running)

        def _redispatch(entry, project_dir, config, running_procs, log_handles) -> bool:
            launcher._spawn(entry, project_dir, config, running_procs, log_handles)
            return entry["task_key"] in running_procs

        monkeypatch.setattr(launcher, "_try_model_redispatch", _redispatch)

        first.returncode = 3
        launcher._poll_once(tmp_path, providers, running, {}, [], None)

        events = _events(ledger_dir)
        assert [event["event"] for event in events] == ["start", "end", "start"]
        assert events[0]["run_id"] == events[1]["run_id"]
        assert events[2]["run_id"] != events[1]["run_id"]
        assert events[1]["exit"] == 3
        assert events[1]["reconciled"] is False
        assert len(captured["cmds"]) == 2  # the task really was re-dispatched

        runs, meta = usage.load_runs(launcher._USAGE_EPOCH)
        assert meta["open_runs"] == 1  # the re-dispatched run is still open
        by_id = {run["run_id"]: run for run in runs}
        assert by_id[events[1]["run_id"]]["open_run"] is False
        assert by_id[events[1]["run_id"]]["exit"] == 3
        assert by_id[events[2]["run_id"]]["open_run"] is True


# ── 4. spawn failure ─────────────────────────────────────────────────────────


class TestSpawnFailed:
    def test_spawn_failure_writes_spawn_failed_without_pid_or_wall(
        self,
        tmp_path: pathlib.Path,
        ledger_dir: pathlib.Path,
        task_file: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TIMI_API_KEY", raising=False)
        entry = _entry(task_file)
        _queue_row(queue_file, entry)
        running: dict = {}
        launcher._spawn(entry, tmp_path, providers, running)
        assert running == {}

        events = _events(ledger_dir)
        assert len(events) == 1
        failed = events[0]
        assert failed["event"] == "spawn_failed"
        assert "pid" not in failed and "wall_s" not in failed
        assert failed["task_key"] == "t001"
        assert failed["key"] == "test-key"
        assert failed["cli"] == "pi"
        assert failed["attribution"] == "exact"
        assert "TIMI_API_KEY" in failed["reason"]

        runs, _meta = usage.load_runs(launcher._USAGE_EPOCH)
        assert len(runs) == 1
        assert runs[0]["status"] == "spawn_failed"
        assert runs[0]["spawned"] is False


# ── 5. fail-soft ledger ──────────────────────────────────────────────────────


class TestLedgerFailSoft:
    def test_unusable_ledger_dir_does_not_change_the_spawn(
        self,
        tmp_path: pathlib.Path,
        task_file: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv("MW_USAGE_DIR", str(blocker / "nested"))
        monkeypatch.setattr(launcher, "_USAGE_RUNS", {})

        entry = _entry(task_file)
        _queue_row(queue_file, entry)
        proc = _FakeProc(pid=6001)
        _fake_popen(monkeypatch, [proc])

        running: dict = {}
        launcher._spawn(entry, tmp_path, providers, running)  # must not raise

        assert running["t001"] is proc
        rows = launcher._parse_workers_file(queue_file)
        assert rows[0]["status"] == "running"
        assert "[mw usage]" in capsys.readouterr().err  # warned, not silent


# ── 6. orphan reconcile ──────────────────────────────────────────────────────


class TestReconcileEnd:
    def test_end_pairs_with_the_open_start_and_keeps_the_end_exit(
        self,
        tmp_path: pathlib.Path,
        ledger_dir: pathlib.Path,
        task_file: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = _entry(task_file)
        _queue_row(queue_file, entry)
        _fake_popen(monkeypatch, [_FakeProc(pid=7001)])
        launcher._spawn(entry, tmp_path, providers, {})
        start = _events(ledger_dir)[0]

        # A launcher restart: the in-memory run state is gone, the row is still
        # `running`, and the worker already wrote its [END] line.
        launcher._USAGE_RUNS.clear()
        (task_file.parent / "trace.log").write_text(_end_marker(0) + "\n", encoding="utf-8")

        launcher._reconcile_orphans(tmp_path, {})

        rows = launcher._parse_workers_file(queue_file)
        assert rows[0]["status"] == "done"
        ends = [event for event in _events(ledger_dir) if event["event"] == "end"]
        assert len(ends) == 1
        assert ends[0]["run_id"] == start["run_id"]  # paired, not a dangling end
        assert ends[0]["reconciled"] is True
        assert ends[0]["exit"] == 0

        runs, meta = usage.load_runs(launcher._USAGE_EPOCH)
        assert meta["open_runs"] == 0
        assert runs[0]["open_run"] is False
        assert runs[0]["reconciled"] is True
        assert runs[0]["exit"] == 0

    def test_end_without_end_marker_keeps_exit_null(
        self,
        tmp_path: pathlib.Path,
        ledger_dir: pathlib.Path,
        task_file: pathlib.Path,
        queue_file: pathlib.Path,
    ) -> None:
        entry = _entry(task_file, status="running")
        _queue_row(queue_file, entry)
        # output.md proves the terminal write path ran; no [END] line at all.
        (task_file.parent / "output.md").write_text("## 结论\nfailed\n", encoding="utf-8")

        launcher._reconcile_orphans(tmp_path, {})

        rows = launcher._parse_workers_file(queue_file)
        assert rows[0]["status"] == "failed"
        ends = [event for event in _events(ledger_dir) if event["event"] == "end"]
        assert len(ends) == 1
        assert ends[0]["reconciled"] is True
        assert ends[0]["exit"] is None  # AC-004/AC-013: unverified is never 0
        assert ends[0]["wall_s"] is None

        runs, _meta = usage.load_runs(launcher._USAGE_EPOCH)
        assert len(runs) == 1
        assert runs[0]["exit"] is None
        assert runs[0]["spawned"] is False  # no start event ever existed
        assert runs[0]["status"] == "failed"


# ── ledger writes stay off a real machine ledger in-process ──────────────────


def test_ledger_writes_disabled_without_usage_dir_in_pytest(
    tmp_path: pathlib.Path, task_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MW_USAGE_DIR", raising=False)
    assert launcher._usage_writes_enabled() is False
    # And the hook is a silent no-op instead of appending to ~/.mw/usage.
    assert launcher._usage_append({"event": "start", "run_id": "r", "ts": "t"}) is False
    monkeypatch.setenv("MW_USAGE_DIR", str(tmp_path / "usage"))
    assert launcher._usage_writes_enabled() is True


def test_owner_key_comes_from_the_task_path(task_file: pathlib.Path) -> None:
    fields = launcher._usage_common_fields(_entry(task_file), None)
    assert fields["key"] == "test-key"
    assert fields["task_key"] == "t001"
    assert fields["project"] == str(task_file.parents[4])
    assert mw_common.worker_owner_key(_entry(task_file)) == "test-key"
