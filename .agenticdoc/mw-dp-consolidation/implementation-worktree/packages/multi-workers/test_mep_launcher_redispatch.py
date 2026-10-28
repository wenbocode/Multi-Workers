"""T-06 (mw-model-error-perception) — launcher two-stage model re-dispatch.

Covers AC-008/AC-009 after the D3 revision (T-03b): a worker `exit 3` first
gets SAME-MODEL process retries (budget `PI_WORKER_MODEL_ERR_MAX`, default 2,
0 = skip) whose state lives in `trace.log`, and only when that budget is spent
does the configured `fallback_models` chain advance. The mechanism is exercised
through the real `launcher._try_model_redispatch` / `_poll_once` reap branch
with a faked `_spawn` / `subprocess.Popen`; no pi process, credential, or
network is ever used.
"""
import json
import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher


# ── hermetic fixtures ──────────────────────────────────────────────────────────

_HERMETIC_CONFIG = {
    "credentials": {
        "anthropic": {"sources": [{"env": "ANTHROPIC_API_KEY"}]},
        "deepseek": {"sources": [{"env": "DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [{"env": "TIMI_API_KEY"}]},
    },
    "providers": {
        "claude": {
            "port": 7001, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_API_KEY", "credential": "anthropic",
        },
        "deepseek": {
            "port": 7004, "base_url_env": "DEEPSEEK_BASE_URL",
            "api_key_env": "DEEPSEEK_API_KEY", "credential": "deepseek",
        },
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
    },
}

_MAIN = "timi/glm-5.3"
_SPARE = "timi/glm-5.4"


def _make_project(
    root: pathlib.Path,
    fallbacks: dict | None = None,
    *,
    key: str = "t001",
    task_type: str = "coding",
    task_model: str = _MAIN,
) -> pathlib.Path:
    task_dir = root / ".agenticdoc" / "test-key" / "workers" / key
    task_dir.mkdir(parents=True, exist_ok=True)
    body = f"type: {task_type}\n"
    if task_model:
        body += f"model: {task_model}\n"
    body += "do it\n"
    (task_dir / "task.md").write_text(body, encoding="utf-8")
    _write_run_json(task_dir, "failed", model_exhausted=True)
    if fallbacks is not None:
        (root / ".mw").mkdir(exist_ok=True)
        (root / ".mw" / "dispatch.yml").write_text(
            yaml.safe_dump({"fallback_models": fallbacks}, allow_unicode=True),
            encoding="utf-8",
        )
    return task_dir


def _write_run_json(task_dir: pathlib.Path, status: str, **overrides) -> pathlib.Path:
    record = {
        "schema": 1,
        "task_key": task_dir.name,
        "run_id": f"{task_dir.name}@2026-10-15T00:00:00.000Z",
        "owner_key": "test-key",
        "kind": "coding",
        "status": status,
        "started_at": "2026-10-15T00:00:00.000Z",
        "artifacts": [],
    }
    record.update(overrides)
    path = task_dir / "run.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _entry(task_dir: pathlib.Path, **overrides) -> dict[str, str]:
    entry = {
        "cli": "pi",
        "provider": "timi",
        "task_path": str(task_dir / "task.md"),
        "task_key": task_dir.name,
        "status": "running",
        "dispatched_at": "2026-10-15T00:00:00+00:00",
        "updated_at": "2026-10-15T00:00:00+00:00",
        "model": _MAIN,
    }
    entry.update(overrides)
    return entry


def _write_queue(root: pathlib.Path, entries: list[dict[str, str]]) -> pathlib.Path:
    queue = root / ".agenticdoc" / "_workers.parallel"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("\n".join(launcher._serialize_entry(e) for e in entries) + "\n", encoding="utf-8")
    return queue


def _trace(task_dir: pathlib.Path) -> str:
    path = task_dir / "trace.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _append_trace(task_dir: pathlib.Path, line: str) -> None:
    with (task_dir / "trace.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


class _SpawnRecorder:
    """Fake ``launcher._spawn``: records kwargs and re-occupies the slot."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, entry, project_dir, config, running_procs, log_handles=None, **kwargs):  # noqa: ANN001
        self.calls.append({"entry": entry, "kwargs": kwargs})
        running_procs[entry["task_key"]] = object()

    @property
    def overrides(self) -> list[str | None]:
        return [call["kwargs"].get("model_override") for call in self.calls]


class _FinishedProc:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode


class _FakeProc:
    returncode = None

    def poll(self):
        return None


def _redispatch(root: pathlib.Path, entry: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> tuple[bool, _SpawnRecorder]:
    recorder = _SpawnRecorder()
    monkeypatch.setattr(launcher, "_spawn", recorder)
    result = launcher._try_model_redispatch(entry, root, _HERMETIC_CONFIG, {}, None)
    return result, recorder


def _emit_verify(capsys: pytest.CaptureFixture[str], line: str) -> None:
    with capsys.disabled():
        print(line, flush=True)


# ── trace-derived budgets ──────────────────────────────────────────────────────


class TestTraceDerivedBudgets:
    def test_retry_count_is_per_model_and_restart_safe(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path)
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:00+00:00 model={_MAIN} attempt=1")
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:01+00:00 model={_MAIN} attempt=2")
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:02+00:00 model={_SPARE} attempt=1")
        entry = _entry(task_dir)
        assert launcher._model_retry_count(entry, _MAIN) == 2
        assert launcher._model_retry_count(entry, _SPARE) == 1
        assert launcher._model_retry_count(entry, "timi/never") == 0

    def test_highest_attempt_wins(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path)
        _append_trace(task_dir, f"[MODEL_RETRY] x model={_MAIN} attempt=2")
        _append_trace(task_dir, f"[MODEL_RETRY] x model={_MAIN} attempt=1")  # out of order
        entry = _entry(task_dir)
        assert launcher._model_retry_count(entry, _MAIN) == 2

    def test_fallback_history_sorted_by_attempt(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path)
        _append_trace(task_dir, f"[MODEL_FALLBACK] x from={_MAIN} to=timi/b attempt=2")
        _append_trace(task_dir, f"[MODEL_FALLBACK] x from={_MAIN} to=timi/a attempt=1")
        entry = _entry(task_dir)
        assert launcher._model_fallback_history(entry) == [(1, "timi/a"), (2, "timi/b")]

    def test_model_err_max_default_zero_and_invalid(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
        assert launcher._model_err_max() == 2
        monkeypatch.setenv("PI_WORKER_MODEL_ERR_MAX", "0")
        assert launcher._model_err_max() == 0

        monkeypatch.setattr(launcher, "_MODEL_ERR_MAX_WARNED", False)
        monkeypatch.setenv("PI_WORKER_MODEL_ERR_MAX", "not-an-int")
        assert launcher._model_err_max() == 2
        err = capsys.readouterr().err
        assert "invalid" in err and "not-an-int" in err


# ── stage 1: same-model retry budget ───────────────────────────────────────────


class TestSameModelRetry:
    def test_first_exit3_retries_the_same_model(self, tmp_path: pathlib.Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        run_before = (task_dir / "run.json").read_bytes()

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is True
        assert len(recorder.calls) == 1
        kwargs = recorder.calls[0]["kwargs"]
        # `--model` unchanged: model_override=None means _spawn resolves the
        # entry again (task.md model: timi/glm-5.3); INDEX/TRIED unchanged.
        assert kwargs["model_override"] is None
        assert kwargs["fallback_index"] == 0
        assert kwargs["tried_models"] == []
        assert kwargs["main_model"] == _MAIN
        assert recorder.calls[0]["entry"]["task_key"] == "t001"  # same task_key
        assert (task_dir / "run.json").read_bytes() == run_before  # launcher never writes the product
        assert "[MODEL_RETRY]" in _trace(task_dir)
        assert f"model={_MAIN} attempt=1" in _trace(task_dir)
        assert "[MODEL_FALLBACK]" not in _trace(task_dir)

    def test_second_exit3_spends_the_last_budget_attempt(self, tmp_path: pathlib.Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:00+00:00 model={_MAIN} attempt=1")

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is True
        assert recorder.overrides == [None]
        assert f"model={_MAIN} attempt=2" in _trace(task_dir)
        assert "[MODEL_FALLBACK]" not in _trace(task_dir)

    def test_budget_exhausts_then_the_chain_advances(self, tmp_path: pathlib.Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:00+00:00 model={_MAIN} attempt=1")
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:01+00:00 model={_MAIN} attempt=2")

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is True
        assert recorder.overrides == [_SPARE]
        kwargs = recorder.calls[0]["kwargs"]
        assert kwargs["fallback_index"] == 1
        assert kwargs["tried_models"] == [_MAIN]
        assert kwargs["main_model"] == _MAIN
        trace = _trace(task_dir)
        assert f"[MODEL_FALLBACK] " in trace
        assert f"from={_MAIN} to={_SPARE} attempt=1" in trace

    def test_budget_zero_goes_straight_to_the_chain(self, tmp_path: pathlib.Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.setenv("PI_WORKER_MODEL_ERR_MAX", "0")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is True
        assert recorder.overrides == [_SPARE]
        assert "[MODEL_RETRY]" not in _trace(task_dir)
        assert f"to={_SPARE} attempt=1" in _trace(task_dir)

    def test_each_model_carries_its_own_budget(self, tmp_path: pathlib.Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        # The chain already advanced to the spare; the spare itself has spent 1.
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:00+00:00 model={_MAIN} attempt=1")
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:01+00:00 model={_MAIN} attempt=2")
        _append_trace(task_dir, f"[MODEL_FALLBACK] 2026-10-15T00:00:02+00:00 from={_MAIN} to={_SPARE} attempt=1")
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:03+00:00 model={_SPARE} attempt=1")

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is True
        assert recorder.overrides == [_SPARE]  # retry the spare, not the main model
        assert f"model={_SPARE} attempt=2" in _trace(task_dir)

    def test_total_attempts_are_bounded_by_budget_and_chain(self, tmp_path: pathlib.Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        recorder = _SpawnRecorder()
        monkeypatch.setattr(launcher, "_spawn", recorder)
        entry = _entry(task_dir)

        results = [
            launcher._try_model_redispatch(entry, tmp_path, _HERMETIC_CONFIG, {}, None)
            for _ in range(6)
        ]

        # (budget 2 + 1 initial) x (main + one spare) = 4 spawns, plus the
        # initial-budget retries: 2 main retries + 1 fallback + 2 spare retries.
        assert results == [True, True, True, True, True, False]
        assert len(recorder.calls) == 5
        trace = _trace(task_dir)
        assert trace.count(f"[MODEL_RETRY]") == 4
        assert trace.count("[MODEL_FALLBACK]") == 1


# ── stage 2: fallback chain (precheck / exhaustion) ────────────────────────────


class TestFallbackChain:
    def test_precheck_failure_skips_and_continues(self, tmp_path: pathlib.Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.setenv("PI_WORKER_MODEL_ERR_MAX", "0")
        # `zai` has no declared route in the hermetic config -> skip; timi is usable.
        task_dir = _make_project(tmp_path, {"coding": ["zai/glm-x", _SPARE]})

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is True
        assert recorder.overrides == [_SPARE]
        trace = _trace(task_dir)
        assert "[MODEL_FALLBACK-SKIP]" in trace and "candidate=zai/glm-x" in trace
        assert f"to={_SPARE} attempt=2" in trace  # chain slot 2 (slot 1 was skipped)

    def test_precheck_failure_on_every_candidate_is_exhaustion(self, tmp_path: pathlib.Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PI_WORKER_MODEL_ERR_MAX", "0")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        task_dir = _make_project(tmp_path, {"coding": ["zai/glm-x", "claude/claude-sonnet-5"]})

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is False
        assert recorder.calls == []
        trace = _trace(task_dir)
        assert trace.count("[MODEL_FALLBACK-SKIP]") == 2
        assert "[MODEL_FALLBACK] " not in trace

    def test_chain_already_consumed_returns_false(self, tmp_path: pathlib.Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        monkeypatch.setenv("PI_WORKER_MODEL_ERR_MAX", "0")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        _append_trace(task_dir, f"[MODEL_FALLBACK] 2026-10-15T00:00:00+00:00 from={_MAIN} to={_SPARE} attempt=1")

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is False and recorder.calls == []

    def test_no_fallback_returns_false_once_the_budget_is_spent(self, tmp_path: pathlib.Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
        task_dir = _make_project(tmp_path, None)
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:00+00:00 model={_MAIN} attempt=1")
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:01+00:00 model={_MAIN} attempt=2")

        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)

        assert result is False and recorder.calls == []
        assert "[MODEL_FALLBACK]" not in _trace(task_dir)

    def test_requires_run_json_confirmation(self, tmp_path: pathlib.Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        _write_run_json(task_dir, "failed")  # no model_exhausted marker
        result, recorder = _redispatch(tmp_path, _entry(task_dir), monkeypatch)
        assert result is False and recorder.calls == []

    def test_non_pi_entry_is_not_redispatched(self, tmp_path: pathlib.Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        result, recorder = _redispatch(tmp_path, _entry(task_dir, cli="claude"), monkeypatch)
        assert result is False and recorder.calls == []


# ── env injection: PI_WORKER_FALLBACK_MODELS / _INDEX / _TRIED ──────────────────


class TestFallbackEnvInjection:
    def test_unit_format(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path, {"coding": [_SPARE, "claude/claude-sonnet-5"]})
        entry = _entry(task_dir)
        env: dict[str, str] = {}
        launcher.inject_fallback_env(env, entry, tmp_path, main_value=_MAIN)
        assert env["PI_WORKER_FALLBACK_MODELS"] == f"{_SPARE},claude/claude-sonnet-5"
        assert env["PI_WORKER_FALLBACK_INDEX"] == "0"
        assert env["PI_WORKER_TRIED_MODELS"] == ""

    def test_unit_index_and_tried(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        entry = _entry(task_dir)
        env: dict[str, str] = {}
        launcher.inject_fallback_env(
            env, entry, tmp_path, main_value=_MAIN, index=1, tried=[_MAIN, "timi/old"],
        )
        assert env["PI_WORKER_FALLBACK_MODELS"] == _SPARE
        assert env["PI_WORKER_FALLBACK_INDEX"] == "1"
        assert env["PI_WORKER_TRIED_MODELS"] == f"{_MAIN},timi/old"

    def test_main_model_is_stripped_from_the_chain(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path, {"coding": [_MAIN, _SPARE]})
        env: dict[str, str] = {}
        launcher.inject_fallback_env(env, _entry(task_dir), tmp_path, main_value=_MAIN)
        assert env["PI_WORKER_FALLBACK_MODELS"] == _SPARE

    def test_no_chain_clears_stale_markers(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path, None)
        env = {
            "PI_WORKER_FALLBACK_MODELS": "stale",
            "PI_WORKER_FALLBACK_INDEX": "9",
            "PI_WORKER_TRIED_MODELS": "stale",
        }
        launcher.inject_fallback_env(env, _entry(task_dir), tmp_path, main_value=_MAIN)
        assert "PI_WORKER_FALLBACK_MODELS" not in env
        assert "PI_WORKER_FALLBACK_INDEX" not in env
        assert "PI_WORKER_TRIED_MODELS" not in env

    def test_role_bucket_is_honoured(self, tmp_path: pathlib.Path) -> None:
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]}, task_type="phase-writer")
        env: dict[str, str] = {}
        launcher.inject_fallback_env(env, _entry(task_dir), tmp_path, main_value=_MAIN)
        assert env["PI_WORKER_FALLBACK_MODELS"] == _SPARE

    def test_real_spawn_injects_the_env_and_the_model_flag(self, tmp_path: pathlib.Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE, "claude/claude-sonnet-5"]})
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured: dict = {}

        def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN202
            captured["cmd"] = cmd
            captured["env"] = kwargs["env"]
            return _FakeProc()

        monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
        (tmp_path / ".agenticdoc").mkdir(exist_ok=True)
        _write_queue(tmp_path, [_entry(task_dir, status="pending")])

        launcher._spawn(
            _entry(task_dir, status="pending"), tmp_path, _HERMETIC_CONFIG, {}, None,
            model_override=_SPARE, fallback_index=1, tried_models=[_MAIN], main_model=_MAIN,
        )

        env = captured["env"]
        assert env["PI_WORKER_FALLBACK_MODELS"] == f"{_SPARE},claude/claude-sonnet-5"
        assert env["PI_WORKER_FALLBACK_INDEX"] == "1"
        assert env["PI_WORKER_TRIED_MODELS"] == _MAIN
        assert _SPARE.split("/")[1] in " ".join(captured["cmd"])

    def test_same_model_retry_keeps_the_model_flag(self, tmp_path: pathlib.Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured: dict = {}

        def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN202
            captured["cmd"] = cmd
            return _FakeProc()

        monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
        (tmp_path / ".agenticdoc").mkdir(exist_ok=True)
        _write_queue(tmp_path, [_entry(task_dir, status="pending")])

        launcher._spawn(
            _entry(task_dir, status="pending"), tmp_path, _HERMETIC_CONFIG, {}, None,
            model_override=None, fallback_index=0, tried_models=[], main_model=_MAIN,
        )
        assert _MAIN.split("/")[1] in " ".join(captured["cmd"])
        assert _SPARE.split("/")[1] not in " ".join(captured["cmd"])


# ── reap integration: slot reuse / terminal statuses ───────────────────────────


def _poll(root: pathlib.Path, entry: dict[str, str], returncode: int,
          monkeypatch: pytest.MonkeyPatch, *, budget: str | None = None,
          pending_queue: list | None = None) -> tuple[dict, _SpawnRecorder]:
    if budget is None:
        monkeypatch.delenv("PI_WORKER_MODEL_ERR_MAX", raising=False)
    else:
        monkeypatch.setenv("PI_WORKER_MODEL_ERR_MAX", budget)
    recorder = _SpawnRecorder()
    monkeypatch.setattr(launcher, "_spawn", recorder)
    running = {entry["task_key"]: _FinishedProc(returncode)}
    launcher._poll_once(root, _HERMETIC_CONFIG, running, {}, pending_queue if pending_queue is not None else [], 2)
    return running, recorder


class TestPollReapIntegration:
    def test_exit3_redispatches_without_draining_the_pending_queue(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        entry = _entry(task_dir)
        queue = _write_queue(tmp_path, [entry])
        run_before = (task_dir / "run.json").read_bytes()
        parked = _entry(task_dir, task_key="t999", status="pending")

        running, recorder = _poll(tmp_path, entry, 3, monkeypatch, pending_queue=[parked])

        # The slot is re-occupied by the re-dispatch: pending drain is skipped.
        assert running.keys() == {"t001"}
        assert recorder.overrides == [None]
        assert [e["task_key"] for e in launcher._parse_workers_file(queue)] == ["t001"]
        assert {e["task_key"]: e["status"] for e in launcher._parse_workers_file(queue)}["t001"] == "running"
        # No extra quota: exactly one queue row, no ack/resume-credit side file.
        assert not (tmp_path / ".agenticdoc" / "_workers.acked").exists()
        assert (task_dir / "run.json").read_bytes() == run_before

    def test_chain_exhausted_lands_failed(self, tmp_path: pathlib.Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        _append_trace(task_dir, f"[MODEL_FALLBACK] 2026-10-15T00:00:00+00:00 from={_MAIN} to={_SPARE} attempt=1")
        entry = _entry(task_dir)
        queue = _write_queue(tmp_path, [entry])

        running, recorder = _poll(tmp_path, entry, 3, monkeypatch, budget="0")

        assert running == {}
        assert recorder.calls == []
        assert {e["task_key"]: e["status"] for e in launcher._parse_workers_file(queue)}["t001"] == "failed"

    def test_no_fallback_exhausted_lands_failed(self, tmp_path: pathlib.Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
        task_dir = _make_project(tmp_path, None)
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:00+00:00 model={_MAIN} attempt=1")
        _append_trace(task_dir, f"[MODEL_RETRY] 2026-10-15T00:00:01+00:00 model={_MAIN} attempt=2")
        entry = _entry(task_dir)
        queue = _write_queue(tmp_path, [entry])

        running, recorder = _poll(tmp_path, entry, 3, monkeypatch)

        assert running == {} and recorder.calls == []
        assert {e["task_key"]: e["status"] for e in launcher._parse_workers_file(queue)}["t001"] == "failed"

    def test_exit3_without_run_confirmation_lands_failed(self, tmp_path: pathlib.Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        _write_run_json(task_dir, "failed")  # no model_exhausted confirmation
        entry = _entry(task_dir)
        queue = _write_queue(tmp_path, [entry])

        running, recorder = _poll(tmp_path, entry, 3, monkeypatch)

        assert running == {} and recorder.calls == []
        assert {e["task_key"]: e["status"] for e in launcher._parse_workers_file(queue)}["t001"] == "failed"

    def test_non_exit3_never_redispatches(self, tmp_path: pathlib.Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
        entry = _entry(task_dir)
        queue = _write_queue(tmp_path, [entry])

        running, recorder = _poll(tmp_path, entry, 1, monkeypatch)

        assert running == {} and recorder.calls == []
        assert {e["task_key"]: e["status"] for e in launcher._parse_workers_file(queue)}["t001"] == "failed"


# ── [VERIFY] line ──────────────────────────────────────────────────────────────


def test_verify_vc_mep_redispatch(tmp_path: pathlib.Path,
                                  monkeypatch: pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TIMI_API_KEY", "timi-test")
    task_dir = _make_project(tmp_path, {"coding": [_SPARE]})
    recorder = _SpawnRecorder()
    monkeypatch.setattr(launcher, "_spawn", recorder)
    entry = _entry(task_dir)
    results = []
    for _ in range(4):
        results.append(launcher._try_model_redispatch(entry, tmp_path, _HERMETIC_CONFIG, {}, None))
    trace = _trace(task_dir)
    retries = trace.count("[MODEL_RETRY]")
    fallbacks = trace.count("[MODEL_FALLBACK]")
    assert results == [True, True, True, True]
    assert retries == 3 and fallbacks == 1
    _emit_verify(
        capsys,
        f"[VERIFY] VC-MEP-REDISPATCH: retries={retries} fallbacks={fallbacks} "
        f"models={','.join(str(o) for o in recorder.overrides)}",
    )
