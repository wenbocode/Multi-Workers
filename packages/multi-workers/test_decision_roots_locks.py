"""
test_decision_roots_locks.py - T01 root/lock foundation (mw-decision-dashboard).

Covers design §3.1 (one fail-closed control-root resolver; an unknown or
ambiguous root is refused instead of silently creating a second archive tree)
and design §9 (explicit monotonic lock deadline plus owner PID/start identity
observation for the monitor start lock; an unknown owner is never stealable).

Every fixture is an isolated tmp tree. Nothing here reads or writes a
production archive / authority / signoff / triage path, and no test sends a
network request or spawns a shared service.
"""
import json
import os
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common


# ── helpers ──────────────────────────────────────────────────────────────────

def _same(a: pathlib.Path | str, b: pathlib.Path | str) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _make_control(root: pathlib.Path) -> pathlib.Path:
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    return root


def _write_target_yml(root: pathlib.Path, body: str) -> None:
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc" / "target.yml").write_text(body, encoding="utf-8", newline="\n")


def _owner_lock(path: pathlib.Path, payload: dict | str) -> pathlib.Path:
    body = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


# ── resolve_control_root: accepted shapes (AC-007 / VC-018) ─────────────────

def test_resolve_control_root_accepts_project_shape(tmp_path):
    project = _make_control(tmp_path / "proj")
    control, source = mw_common.resolve_control_root(project)
    assert source == "project"
    assert _same(control, project)
    assert control.is_absolute()


def test_resolve_control_root_peels_agenticdoc_and_key_shapes(tmp_path):
    project = _make_control(tmp_path / "proj")
    key = project / ".agenticdoc" / "key-a"
    (key / "workers").mkdir(parents=True)

    from_agenticdoc, src_a = mw_common.resolve_control_root(project / ".agenticdoc")
    from_key, src_k = mw_common.resolve_control_root(key)

    assert (src_a, src_k) == ("agenticdoc", "key")
    assert _same(from_agenticdoc, project)
    assert _same(from_key, project)


def test_resolve_control_root_accepts_relative_project(tmp_path, monkeypatch):
    project = _make_control(tmp_path / "proj")
    monkeypatch.chdir(tmp_path)
    control, source = mw_common.resolve_control_root(pathlib.Path("proj"))
    assert source == "project"
    assert control.is_absolute()
    assert _same(control, project)


# ── resolve_control_root: refusal paths (AC-007 / VC-007 / VC-018) ──────────

def test_resolve_control_root_refuses_unknown_root(tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir()
    with pytest.raises(mw_common.ControlRootError) as exc:
        mw_common.resolve_control_root(loose)
    assert exc.value.kind == "not-control"
    assert str(exc.value).startswith("E-ROOT-NOT-CONTROL")
    # Fail-closed must mean "no second archive tree", not "mkdir and continue".
    assert not (loose / ".agenticdoc").exists()


def test_resolve_control_root_require_control_false_reports_refused(tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir()
    control, source = mw_common.resolve_control_root(loose, require_control=False)
    assert source == "refused"
    assert _same(control, loose)
    assert control.is_absolute()
    assert not (loose / ".agenticdoc").exists()


def test_resolve_control_root_require_control_false_still_uses_evidence(tmp_path):
    project = _make_control(tmp_path / "proj")
    control, source = mw_common.resolve_control_root(project, require_control=False)
    assert source == "project"
    assert _same(control, project)


def test_resolve_control_root_probes_declared_workspace_root(tmp_path):
    control_root = _make_control(tmp_path / "ctl")
    _write_target_yml(control_root, "active: dual\ndual:\n  game: game\n")
    game = control_root / "game"
    game.mkdir()

    control, source = mw_common.resolve_control_root(game)

    assert source == "target-root"
    assert _same(control, control_root)


def test_resolve_control_root_does_not_guess_distant_control(tmp_path):
    control_root = _make_control(tmp_path / "ctl")
    _write_target_yml(control_root, "active: dual\ndual:\n  game: ../game\n")
    game = tmp_path / "game"
    game.mkdir()

    with pytest.raises(mw_common.ControlRootError) as exc:
        mw_common.resolve_control_root(game)

    assert exc.value.kind == "not-control"
    assert not (game / ".agenticdoc").exists()


def test_resolve_control_root_refuses_ambiguous_second_root(tmp_path):
    control_root = _make_control(tmp_path / "ctl")
    _write_target_yml(control_root, "active: dual\ndual:\n  game: game\n")
    game = control_root / "game"
    # A stray .agenticdoc under a control-declared game root is exactly the
    # "two plausible controls" shape: refuse instead of picking one.
    (game / ".agenticdoc").mkdir(parents=True)

    with pytest.raises(mw_common.ControlRootError) as exc:
        mw_common.resolve_control_root(game)

    assert exc.value.kind == "ambiguous-root"
    assert str(exc.value).startswith("E-ROOT-AMBIGUOUS")


def test_resolve_control_root_refuses_nested_agenticdoc_shapes(tmp_path):
    project = _make_control(tmp_path / "proj")
    outer = project / ".agenticdoc"
    (outer / ".agenticdoc").mkdir()  # p=outer: "agenticdoc" -> proj, "project" -> outer

    with pytest.raises(mw_common.ControlRootError) as exc:
        mw_common.resolve_control_root(outer)

    assert exc.value.kind == "ambiguous-root"


def test_resolve_control_root_propagates_bad_target_config(tmp_path):
    yaml_root = _make_control(tmp_path / "bad-yaml")
    _write_target_yml(yaml_root, "active: dual\ndual: [unclosed\n")
    (yaml_root / "game").mkdir()
    with pytest.raises(mw_common.TargetConfigError) as exc:
        mw_common.resolve_control_root(yaml_root / "game")
    assert exc.value.kind == "invalid-yaml"

    shape_root = _make_control(tmp_path / "bad-shape")
    _write_target_yml(shape_root, "active: dual\n")
    (shape_root / "game").mkdir()
    with pytest.raises(mw_common.TargetConfigError) as exc2:
        mw_common.resolve_control_root(shape_root / "game")
    assert exc2.value.kind == "invalid-config"


# ── acquire_lock: unchanged default semantics (AC-008 / VC-017) ─────────────

def test_acquire_lock_default_message_and_release(tmp_path):
    lock = tmp_path / ".mw" / "workers.lock"
    mw_common.acquire_lock(lock)
    try:
        assert lock.is_file()
        with pytest.raises(RuntimeError) as exc:
            mw_common.acquire_lock(lock, retries=0)
        assert str(exc.value) == f"Could not acquire lock at {lock} after 0 retries"
        # A refused acquisition never deletes the foreign lock.
        assert lock.is_file()
    finally:
        mw_common.release_lock(lock)
    assert not lock.exists()

    mw_common.acquire_lock(lock)
    mw_common.release_lock(lock)
    assert not lock.exists()


def test_acquire_lock_default_retry_budget_is_unchanged(tmp_path):
    lock = tmp_path / "held.lock"
    mw_common.acquire_lock(lock)
    started = time.monotonic()
    with pytest.raises(RuntimeError) as exc:
        # retries=3 with no deadline keeps the historical exponential backoff:
        # 0.01 * (1 + 2 + 4) = 70ms of sleeps.
        mw_common.acquire_lock(lock, retries=3, base_delay=0.01)
    elapsed = time.monotonic() - started
    assert str(exc.value) == f"Could not acquire lock at {lock} after 3 retries"
    assert elapsed >= 0.06
    mw_common.release_lock(lock)


# ── acquire_lock: optional monotonic deadline (AC-007 / VC-007) ─────────────

def test_acquire_lock_deadline_stops_within_budget(tmp_path):
    lock = tmp_path / "decide-monitor.start.lock"
    mw_common.acquire_lock(lock)
    started = time.monotonic()
    with pytest.raises(RuntimeError) as exc:
        mw_common.acquire_lock(lock, retries=200, base_delay=0.5, deadline_s=0.15)
    elapsed = time.monotonic() - started
    try:
        assert elapsed < 2.0, f"deadline budget ignored: waited {elapsed:.3f}s"
        assert "budget" in str(exc.value)
        assert lock.is_file()
    finally:
        mw_common.release_lock(lock)


def test_acquire_lock_zero_deadline_fails_fast(tmp_path):
    lock = tmp_path / "zero.lock"
    mw_common.acquire_lock(lock)
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError) as exc:
            mw_common.acquire_lock(lock, base_delay=5.0, deadline_s=0)
        assert time.monotonic() - started < 1.0
        assert "budget" in str(exc.value)
    finally:
        mw_common.release_lock(lock)


def test_acquire_lock_deadline_success_path_is_immediate(tmp_path):
    lock = tmp_path / "free.lock"
    started = time.monotonic()
    mw_common.acquire_lock(lock, deadline_s=5.0)
    try:
        assert time.monotonic() - started < 1.0
        assert lock.is_file()
    finally:
        mw_common.release_lock(lock)


def test_acquire_lock_rejects_negative_deadline(tmp_path):
    lock = tmp_path / "neg.lock"
    with pytest.raises(ValueError):
        mw_common.acquire_lock(lock, deadline_s=-1)
    assert not lock.exists()


# ── lock owner identity (AC-007 / VC-007 start-lock recovery input) ─────────

def test_lock_owner_state_absent_then_alive_then_absent(tmp_path):
    lock = tmp_path / "start.lock"
    assert mw_common.lock_owner_state(lock)["state"] == "absent"

    mw_common.acquire_lock(lock)
    try:
        record = mw_common.write_lock_owner(lock, start_ms=111_000)
        assert record["pid"] == os.getpid()
        assert record["start_ms"] == 111_000
        assert record["schema"] == 1
        assert set(record) <= {"schema", "pid", "start_ms", "written_at"}

        state = mw_common.lock_owner_state(
            lock, alive_probe=lambda pid: True, start_ms_probe=lambda pid: 111_000
        )
        assert state["state"] == "alive"
        assert state["pid"] == os.getpid()
        assert state["start_ms"] == 111_000
    finally:
        mw_common.release_lock(lock)
    assert mw_common.lock_owner_state(lock)["state"] == "absent"


def test_write_lock_owner_requires_an_existing_lock(tmp_path):
    lock = tmp_path / "missing.lock"
    with pytest.raises(RuntimeError):
        mw_common.write_lock_owner(lock)
    assert not lock.exists()


def test_lock_owner_state_dead_owner(tmp_path):
    lock = _owner_lock(tmp_path / "start.lock", {"schema": 1, "pid": 4242, "start_ms": 100_000})
    state = mw_common.lock_owner_state(lock, alive_probe=lambda pid: False, start_ms_probe=lambda pid: None)
    assert state["state"] == "dead"
    assert state["pid"] == 4242
    assert state["detail"]


def test_lock_owner_state_pid_reuse_is_unknown(tmp_path):
    lock = _owner_lock(tmp_path / "start.lock", {"schema": 1, "pid": 4242, "start_ms": 100_000})
    state = mw_common.lock_owner_state(lock, alive_probe=lambda pid: True, start_ms_probe=lambda pid: 900_000)
    assert state["state"] == "unknown"
    assert state["pid"] == 4242


def test_lock_owner_state_unprobeable_start_is_unknown(tmp_path):
    lock = _owner_lock(tmp_path / "start.lock", {"schema": 1, "pid": 4242, "start_ms": 100_000})
    state = mw_common.lock_owner_state(lock, alive_probe=lambda pid: True, start_ms_probe=lambda pid: None)
    assert state["state"] == "unknown"

    no_start = _owner_lock(tmp_path / "no-start.lock", {"schema": 1, "pid": 4242, "start_ms": None})
    state2 = mw_common.lock_owner_state(no_start, alive_probe=lambda pid: True, start_ms_probe=lambda pid: 100_000)
    assert state2["state"] == "unknown"


def test_lock_owner_state_legacy_empty_file_is_not_stealable(tmp_path):
    lock = _owner_lock(tmp_path / "legacy.lock", "")
    state = mw_common.lock_owner_state(lock)
    assert state["state"] == "legacy"
    assert state["pid"] is None
    assert "manual" in state["detail"].lower()


def test_lock_owner_state_garbage_and_unknown_schema_are_unknown(tmp_path):
    garbage = _owner_lock(tmp_path / "garbage.lock", "not json at all\n")
    assert mw_common.lock_owner_state(garbage)["state"] == "unknown"

    bad_pid = _owner_lock(tmp_path / "bad-pid.lock", {"schema": 1, "pid": 0, "start_ms": 1})
    assert mw_common.lock_owner_state(bad_pid)["state"] == "unknown"

    bad_schema = _owner_lock(tmp_path / "bad-schema.lock", {"schema": 2, "pid": 4242, "start_ms": 1})
    assert mw_common.lock_owner_state(bad_schema)["state"] == "unknown"

    list_payload = _owner_lock(tmp_path / "list.lock", "[1, 2, 3]")
    assert mw_common.lock_owner_state(list_payload)["state"] == "unknown"


def test_lock_owner_state_matches_real_process_identity(tmp_path):
    if mw_common.process_start_ms(os.getpid()) is None:
        pytest.skip("OS process start time is not available on this platform")
    lock = tmp_path / "real.lock"
    mw_common.acquire_lock(lock)
    try:
        mw_common.write_lock_owner(lock)
        state = mw_common.lock_owner_state(lock)
        assert state["state"] == "alive"
        assert state["pid"] == os.getpid()
    finally:
        mw_common.release_lock(lock)


def test_read_lock_owner_normalizes_and_rejects_noise(tmp_path):
    assert mw_common.read_lock_owner(tmp_path / "nope.lock") is None

    good = _owner_lock(tmp_path / "good.lock", {"schema": 1, "pid": 7, "start_ms": None, "written_at": "x"})
    assert mw_common.read_lock_owner(good) == {"pid": 7, "start_ms": None}

    boom = _owner_lock(tmp_path / "bool.lock", '{"schema": 1, "pid": true}')
    assert mw_common.read_lock_owner(boom) is None

    str_start = _owner_lock(tmp_path / "str.lock", '{"schema": 1, "pid": 7, "start_ms": "1"}')
    assert mw_common.read_lock_owner(str_start) is None


def test_lock_owner_states_constant_is_exhaustive():
    assert set(mw_common.LOCK_OWNER_STATES) == {"absent", "legacy", "alive", "dead", "unknown"}


# ── conservative tri-state liveness probe (P1-4 / D-001) ──────────────────

def test_process_alive_state_reports_the_current_process_as_alive():
    assert mw_common.process_alive_state(os.getpid()) == "alive"


def test_process_alive_state_proves_a_missing_pid_dead():
    # Evidence-based: only a probe that positively says "no such process" may
    # return dead. Skips rather than guessing when the OS reports something else.
    state = mw_common.process_alive_state(2**31 - 1)
    if state != "dead":  # pragma: no cover - platform probe difference
        pytest.skip(f"this platform reports {state!r} for a missing pid")
    assert state == "dead"


def test_process_alive_state_rejects_invalid_pid_as_unknown():
    for bad in (0, -1, None, "42", True):
        assert mw_common.process_alive_state(bad) == "unknown", bad


def test_process_alive_state_survives_a_raising_probe(monkeypatch):
    def boom(pid):
        raise OSError("probe exploded")

    monkeypatch.setattr(mw_common, "_posix_process_state", boom)
    monkeypatch.setattr(mw_common, "_win32_process_state", boom)
    assert mw_common.process_alive_state(os.getpid()) == "unknown"


class _FakeKernel32:
    """Minimal Win32 liveness surface used to simulate an ACCESS_DENIED probe."""

    def __init__(
        self,
        *,
        handle: int = 1,
        exit_code: int = 259,
        exit_ok: bool = True,
        last_error: int | None = None,
    ) -> None:
        self.handle = handle
        self.exit_code = exit_code
        self.exit_ok = exit_ok
        self.last_error = last_error
        self.closed: list[int] = []

    def OpenProcess(self, access, inherit, pid):  # noqa: N802 - Win32 API name
        return self.handle

    def GetExitCodeProcess(self, handle, ref):  # noqa: N802 - Win32 API name
        if not self.exit_ok:
            return 0
        ref._obj.value = self.exit_code
        return 1

    def GetLastError(self):  # noqa: N802 - Win32 API name
        if self.last_error is None:
            raise OSError("no last error available")
        return self.last_error

    def CloseHandle(self, handle):  # noqa: N802 - Win32 API name
        self.closed.append(handle)
        return 1


def test_win32_access_denied_owner_probe_is_unknown_not_dead():
    # OpenProcess -> 0 with GetLastError()==ERROR_ACCESS_DENIED (a live process
    # in another integrity level/session) must never be classified dead.
    fake = _FakeKernel32(handle=0, last_error=5)
    assert mw_common._win32_process_state(4242, fake) == "unknown"


def test_win32_missing_pid_probe_is_dead():
    fake = _FakeKernel32(handle=0, last_error=87)  # ERROR_INVALID_PARAMETER
    assert mw_common._win32_process_state(4242, fake) == "dead"


def test_win32_unexpected_or_missing_error_code_is_unknown():
    assert mw_common._win32_process_state(4242, _FakeKernel32(handle=0, last_error=6)) == "unknown"
    assert mw_common._win32_process_state(4242, _FakeKernel32(handle=0)) == "unknown"


def test_win32_handle_without_exit_code_is_unknown():
    fake = _FakeKernel32(exit_ok=False)
    assert mw_common._win32_process_state(4242, fake) == "unknown"
    assert fake.closed == [1]


def test_win32_exit_code_distinguishes_alive_and_exited():
    assert mw_common._win32_process_state(4242, _FakeKernel32(exit_code=259)) == "alive"
    assert mw_common._win32_process_state(4242, _FakeKernel32(exit_code=0)) == "dead"


def test_lock_owner_state_unknown_probe_result_is_never_stealable(tmp_path):
    lock = _owner_lock(tmp_path / "start.lock", {"schema": 1, "pid": 4242, "start_ms": 100_000})
    for probe in (lambda pid: "unknown", lambda pid: None, lambda pid: "weird"):
        state = mw_common.lock_owner_state(
            lock, alive_state_probe=probe, start_ms_probe=lambda pid: 100_000
        )
        assert state["state"] == "unknown", probe
        assert state["detail"]


def test_lock_owner_state_raising_liveness_probe_is_unknown(tmp_path):
    lock = _owner_lock(tmp_path / "start.lock", {"schema": 1, "pid": 4242, "start_ms": 100_000})

    def boom(pid):
        raise PermissionError("access denied")

    state = mw_common.lock_owner_state(lock, alive_state_probe=boom, start_ms_probe=lambda pid: 100_000)
    assert state["state"] == "unknown"
    legacy = mw_common.lock_owner_state(lock, alive_probe=boom, start_ms_probe=lambda pid: 100_000)
    assert legacy["state"] == "unknown"


def test_lock_owner_state_dead_requires_a_proven_dead_probe(tmp_path):
    lock = _owner_lock(tmp_path / "start.lock", {"schema": 1, "pid": 4242, "start_ms": 100_000})
    dead = mw_common.lock_owner_state(
        lock, alive_state_probe=lambda pid: "dead", start_ms_probe=lambda pid: None
    )
    assert dead["state"] == "dead"
    alive = mw_common.lock_owner_state(
        lock, alive_state_probe=lambda pid: "alive", start_ms_probe=lambda pid: 100_000
    )
    assert alive["state"] == "alive"


def test_is_alive_keeps_its_historical_boolean_semantics(tmp_path):
    # check_pid/doctor/heartbeat share this probe; P1-4 must not change it.
    assert mw_common._is_alive(os.getpid()) is True
    assert mw_common._is_alive(2**31 - 1) is False
    pid_file = tmp_path / "mw.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    assert mw_common.check_pid(pid_file) == os.getpid()
