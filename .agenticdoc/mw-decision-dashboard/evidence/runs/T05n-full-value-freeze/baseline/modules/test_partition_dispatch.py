"""
test_partition_dispatch.py — mw-target-partition S2 dispatch-chain tests
(T-05/T-06): launcher spawn cwd + config-tear refusal (AC-006/AC-020),
read-scope partition anchoring (AC-008), doctor partition checks + probe
fingerprint cache (AC-009 / AC-018c/d).

Existing suites stay untouched: dual/single dispatch behavior is asserted
here only as zero-change guards; the byte-exact dual/single contract lives
in test/test_target_baseline.py + test_launcher.py + test_mw_target.py.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import launcher
import mw_common
from autopilot.dispatch import _expand_read_scope
from launcher import _parse_workers_file, _serialize_entry, _spawn
from mw_common import toolchain_probe_path

_HERMETIC_CONFIG = {
    "credentials": {
        "timi": {"sources": [{"env": "TIMI_API_KEY"}]},
    },
    "providers": {
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
    },
}

_PARTITION_YML = """\
active: partition
partition:
  parent: '{parent}'
  partition: '{partition}'
  roots:
    sdk: '{sdk}'
  toolchain:
    build: 'make -C {partition} SDK={sdk}'
"""

# mw-target-partition FIX-13 parity sample: every partition profile field
# (parent/partition/roots/toolchain with placeholders/firewall/contract) —
# byte-for-byte the same sample as PARTITION_GOLDEN_YML in
# packages/coding-agent/test/extensions/agent-team-loop-profile-injection.test.ts
# (keep both in sync); the shared golden it renders against lives at
# test/fixtures/partition-profile-block.golden.md.
_PARTITION_GOLDEN_YML = """\
# mw-target-partition FIX-13 parity sample: full partition profile fields.
active: partition
partition:
  parent: parent
  partition: shard
  roots:
    sdk: sdk
    data: data
  vcs: git
  toolchain:
    build: 'make -C {partition} SDK={sdk} --parent {parent}'
    regen: 'python {data}/Tools/regen.py'
  ignore:
    deny_globs:
      - "**/*.uasset"
      - "**/DerivedDataCache/**"
  contract:
    forbidden_paths:
      - "**/Generated/*"
    conventions: |
      Line one of the conventions.
      Line two of the conventions.
    docs:
      - docs/contract-notes.md
"""

# task.md carrying a v2 partition profile block (what the TS dispatcher
# injects at dispatch time — the tear-check input, AC-020/D-013).
_TASK_MD_V2_PARTITION_BLOCK = """\
---
type: coding
---

Do the partition work.

<!-- mw-profile: v2 -->
[mw] mode: partition
[mw] Workspace profile (target.yml essentials, injected at dispatch;
full file: {control}/.agenticdoc/target.yml)
Control workspace: {control}
Parent root (extended workspace, writable): {parent}
Partition root (worker cwd): {partition}
"""

# task.md carrying a v1 legacy profile block in its DUAL shape (Game root
# line present — dual injections carry it, single ones do not).
_TASK_MD_V1_DUAL_BLOCK = """\
---
type: coding
---

Do the dual work.

<!-- mw-profile: v1 -->
[mw] Workspace profile (target.yml essentials, injected at dispatch;
full file: {control}/.agenticdoc/target.yml)
Control workspace: {control}
Game root: {game}
"""

# task.md carrying a v1 legacy profile block in its SINGLE shape (sections
# only — no Game root line; the shape single+sections dispatches inject).
_TASK_MD_V1_SINGLE_BLOCK = """\
---
type: coding
---

Do the single work.

<!-- mw-profile: v1 -->
[mw] Workspace profile (target.yml essentials, injected at dispatch;
full file: {control}/.agenticdoc/target.yml)
Toolchain commands (placeholders resolved):
- build: echo ok
"""


@pytest.fixture(autouse=True)
def _no_target_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No env overrides may leak into the resolved modes (rule-table row 3
    would turn a cwd/torn test into a cross-env error test)."""
    for var in (
        mw_common.ENV_TARGET_GAME,
        mw_common.ENV_TARGET_ENGINE,
        mw_common.ENV_PARTITION_PARENT,
        mw_common.ENV_PARTITION_ROOT,
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def providers(tmp_path: pathlib.Path) -> dict:
    p = tmp_path / "providers.json"
    p.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return launcher._load_providers(p)


def _entry(task_file: pathlib.Path, **overrides) -> dict[str, str]:
    entry = {
        "task_key": "t001",
        "status": "pending",
        "cli": "pi",
        "provider": "timi",
        "model": "",
        "task_path": str(task_file),
        "dispatched_at": "2026-09-19T00:00:00+00:00",
        "updated_at": "2026-09-19T00:00:00+00:00",
    }
    entry.update(overrides)
    return entry


def _make_task(tmp_path: pathlib.Path, key: str, body: str) -> pathlib.Path:
    """task.md at the real worker location (.agenticdoc/{key}/workers/...)."""
    t = tmp_path / ".agenticdoc" / "test-key" / "workers" / key / "task.md"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(body, encoding="utf-8")
    return t


def _write_yml(project: pathlib.Path, text: str) -> None:
    yml = mw_common.target_yml_path(project)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(text, encoding="utf-8")


def _write_partition_yml(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """v2 partition workspace with three distinct roots (parent/partition/
    sdk as siblings — none nested in another, AC-003(g) legal)."""
    control = tmp_path / "control"
    parent = tmp_path / "parent"
    partition = tmp_path / "shard"
    sdk = tmp_path / "sdk"
    for d in (control, parent, partition, sdk):
        d.mkdir(exist_ok=True)
    _write_yml(control, _PARTITION_YML.format(parent=parent, partition=partition, sdk=sdk))
    return control, parent, partition


class _FakeProc:
    def __init__(self) -> None:
        self.returncode = 0

    def poll(self) -> int | None:
        return self.returncode


def _capture_popen(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}

    def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN202
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    return captured


# ── T-05: launcher spawn cwd (AC-006) ─────────────────────────────────────────


class TestWorkerCwdDispatch:
    def test_worker_cwd_partition_root(self, tmp_path: pathlib.Path) -> None:
        control, _, partition = _write_partition_yml(tmp_path)
        assert launcher._worker_cwd(control) == pathlib.Path(partition.resolve())
        print(f"[VERIFY] VC-006: spawn-cwd={launcher._worker_cwd(control)}")

    def test_worker_cwd_dual_single_unchanged(self, tmp_path: pathlib.Path) -> None:
        control = tmp_path / "control"
        game = tmp_path / "game"
        control.mkdir()
        game.mkdir()
        _write_yml(control, f"mode: dual\ngame: '{game}'\n")
        assert launcher._worker_cwd(control) == pathlib.Path(game.resolve())
        (control / ".agenticdoc" / "target.yml").unlink()
        assert launcher._worker_cwd(control) == control

    def test_spawn_partition_cwd_and_control_anchored_task(
        self, tmp_path: pathlib.Path, providers: dict, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-006: the worker process runs with cwd=partition root while
        PI_WORKER_TASK stays anchored at the CONTROL-root task.md — the
        coordination writeback (trace.log/output.md) derives from it, so it
        never lands inside the partition directory."""
        control, _, partition = _write_partition_yml(tmp_path)
        task = _make_task(tmp_path, "t001", "type: coding\nDo work.\n")
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = _capture_popen(monkeypatch)

        running: dict = {}
        _spawn(_entry(task), control, providers, running)
        assert "t001" in running
        assert captured["kwargs"]["cwd"] == str(partition.resolve())
        assert captured["kwargs"]["env"]["PI_WORKER_TASK"] == str(task.resolve())
        assert pathlib.Path(captured["kwargs"]["env"]["PI_WORKER_TASK"]).is_absolute()
        assert tmp_path in pathlib.Path(captured["kwargs"]["env"]["PI_WORKER_TASK"]).parents


# ── T-05: config-tear refusal (AC-020) ────────────────────────────────────────


class TestConfigTorn:
    def test_profile_mode_extraction(self, tmp_path: pathlib.Path) -> None:
        assert launcher._task_profile_mode(str(_make_task(tmp_path, "a", "no block\n"))) is None
        # FIX-3: a v2 marker without a parseable mode line at the block head
        # is a MALFORMED block — it raises (fail-closed), never reads as
        # "no profile" (which would let the spawn pass un-checked).
        v2_no_mode = _make_task(
            tmp_path, "b", "x\n<!-- mw-profile: v2 -->\n[mw] Workspace profile\n"
        )
        with pytest.raises(RuntimeError, match="profile malformed"):
            launcher._task_profile_mode(str(v2_no_mode))
        # The mode line must sit in the block HEAD: a valid-looking mode line
        # further down the file must not mask a malformed head.
        v2_mode_not_in_head = _make_task(
            tmp_path, "c", "<!-- mw-profile: v2 -->\nrandom line\n[mw] mode: partition\n"
        )
        with pytest.raises(RuntimeError, match="profile malformed"):
            launcher._task_profile_mode(str(v2_mode_not_in_head))
        v2 = _make_task(
            tmp_path, "d", "x\n<!-- mw-profile: v2 -->\n[mw] mode: partition\ny\n"
        )
        assert launcher._task_profile_mode(str(v2)) == "partition"

    def test_profile_mode_head_tolerates_blank_and_comment_lines(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """mw-target-partition FIX-11 (block-head tolerance): blank lines
        and comment lines (`<!-- ... -->` / `#`) between the v2 marker and
        the mode line are skipped, but only within the block-head window
        (the first 8 lines after the marker) — a head that overflows the
        window stays malformed, and a mode line beyond it never masks the
        orphaned marker."""
        tolerant = _make_task(
            tmp_path, "fx11a",
            "x\n<!-- mw-profile: v2 -->\n\n<!-- hand note -->\n# another note\n"
            "[mw] mode: dual\ny\n",
        )
        assert launcher._task_profile_mode(str(tolerant)) == "dual"
        # 8 comment lines and no mode line at all -> malformed
        only_comments = _make_task(
            tmp_path, "fx11b", "<!-- mw-profile: v2 -->\n" + "# c\n" * 8
        )
        with pytest.raises(RuntimeError, match="profile malformed"):
            launcher._task_profile_mode(str(only_comments))
        # a legal mode line beyond the window does not rescue the head
        beyond_window = _make_task(
            tmp_path, "fx11c", "<!-- mw-profile: v2 -->\n" + "# c\n" * 8 + "[mw] mode: single\n"
        )
        with pytest.raises(RuntimeError, match="profile malformed"):
            launcher._task_profile_mode(str(beyond_window))
        print("[VERIFY] FIX-11: head comments tolerated, window overflow malformed")

    def test_malformed_v2_profile_fails_closed(
        self, tmp_path: pathlib.Path, providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FIX-3 (fail-closed): a hand-corrupted v2 block (marker without a
        parseable mode line) refuses the spawn — task failed, reason carries
        'profile malformed', trace.log records the refusal — instead of being
        treated as an un-profiled legal task and silently spawned."""
        control, _, _ = _write_partition_yml(tmp_path)
        task = _make_task(
            control,
            "t001",
            "Do the work.\n\n<!-- mw-profile: v2 -->\n[mw] Workspace profile (corrupted)\n",
        )
        queue = control / ".agenticdoc" / "_workers.parallel"
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = _capture_popen(monkeypatch)

        entry = _entry(task)
        queue.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        running: dict = {}
        _spawn(entry, control, providers, running)  # isolated: no exception
        assert "t001" not in running  # not spawned
        assert captured == {}  # Popen never reached
        worker_log = (task.parent / "worker.log").read_text(encoding="utf-8")
        assert "profile malformed" in worker_log
        trace = (task.parent / "trace.log").read_text(encoding="utf-8")
        assert "[LAUNCHER]" in trace and "profile malformed" in trace
        statuses = {e["task_key"]: e["status"] for e in _parse_workers_file(queue)}
        assert statuses["t001"] == "failed"
        print("[VERIFY] FIX-3: malformed-v2=failed, spawned=no, reason=profile-malformed")

    def test_torn_partition_block_under_dual(
        self, tmp_path: pathlib.Path, providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dispatch recorded partition; active was switched to dual before
        spawn -> failed, never spawned, reason carries 'config torn' + both
        mode names, trace.log records the refusal (AC-020)."""
        control = tmp_path / "control"
        game = tmp_path / "game"
        control.mkdir()
        game.mkdir()
        _write_yml(control, f"active: dual\ndual:\n  game: '{game}'\n")
        task = _make_task(
            control,
            "t001",
            _TASK_MD_V2_PARTITION_BLOCK.format(
                control=control, parent=tmp_path / "parent", partition=tmp_path / "shard"
            ),
        )
        queue = control / ".agenticdoc" / "_workers.parallel"
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = _capture_popen(monkeypatch)

        entry = _entry(task)
        queue.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        running: dict = {}
        _spawn(entry, control, providers, running)  # isolated: no exception
        assert "t001" not in running  # not spawned
        assert captured == {}  # Popen never reached
        worker_log = (task.parent / "worker.log").read_text(encoding="utf-8")
        assert "config torn" in worker_log
        assert "'partition'" in worker_log
        assert "'dual'" in worker_log
        trace = (task.parent / "trace.log").read_text(encoding="utf-8")
        assert "[LAUNCHER]" in trace and "config torn" in trace
        statuses = {e["task_key"]: e["status"] for e in _parse_workers_file(queue)}
        assert statuses["t001"] == "failed"
        print("[VERIFY] VC-020: task=failed, reason=config_torn, spawned=no")

    def test_torn_v1_dual_block_under_partition(
        self, tmp_path: pathlib.Path, providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A v1-marker dual block (Game root line) under partition
        activation is provably stale — a silent spawn would move the cwd
        from the game root to the partition root."""
        control, _, _ = _write_partition_yml(tmp_path)
        game = tmp_path / "game"
        game.mkdir(exist_ok=True)
        task = _make_task(
            control,
            "t001",
            _TASK_MD_V1_DUAL_BLOCK.format(control=control, game=game),
        )
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        _capture_popen(monkeypatch)

        entry = _entry(task)
        (control / ".agenticdoc" / "_workers.parallel").write_text(
            _serialize_entry(entry) + "\n", encoding="utf-8"
        )
        running: dict = {}
        _spawn(entry, control, providers, running)
        assert "t001" not in running
        worker_log = (task.parent / "worker.log").read_text(encoding="utf-8")
        assert "config torn" in worker_log
        assert "'dual'" in worker_log and "'partition'" in worker_log

    def test_single_injected_v1_block_not_torn(
        self, tmp_path: pathlib.Path, providers: dict, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A v1 block WITHOUT the Game root line is a single-injection (the
        legacy single+sections dispatch shape) — under single mode it must
        spawn normally. Reading every v1 block as dual would fail-closed
        this legit pre-partition task."""
        control = tmp_path / "control"
        control.mkdir()
        _write_yml(control, 'mode: single\nignore:\n  deny_globs:\n    - "**/*.x"\n')
        task = _make_task(control, "t001", _TASK_MD_V1_SINGLE_BLOCK.format(control=control))
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = _capture_popen(monkeypatch)

        running: dict = {}
        _spawn(_entry(task), control, providers, running)
        assert "t001" in running  # spawned: no tear
        assert captured["kwargs"]["cwd"] == str(control)

    def test_no_profile_block_never_torn(
        self, tmp_path: pathlib.Path, providers: dict, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No marker = no profile (legal): pre-partition/conductor task.mds
        carry no block and must spawn under any active mode."""
        control, _, partition = _write_partition_yml(tmp_path)
        task = _make_task(tmp_path, "t001", "type: coding\nDo work.\n")
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = _capture_popen(monkeypatch)

        running: dict = {}
        _spawn(_entry(task), control, providers, running)
        assert "t001" in running
        assert captured["kwargs"]["cwd"] == str(partition.resolve())


# ── FIX-1: conductor dispatch injects the partition profile ──────────────────


class TestConductorProfileInjection:
    """mw-target-partition FIX-1 (AC-007/AC-020): the TS dispatcher skips
    origin: conductor tasks (D-104), so the conductor must inject the v2
    profile block itself — the block the launcher's tear check reads."""

    def test_conductor_dispatch_injects_v2_profile(
        self, tmp_path: pathlib.Path,
    ) -> None:
        from autopilot import dispatch as dispatch_mod

        control, parent, partition = _write_partition_yml(tmp_path)
        sdk = tmp_path / "sdk"
        result = dispatch_mod.dispatch(
            control, "test-key", "prof", "repair", "the prompt",
            loop="L", attempt=1,
        )
        assert result.ok
        text = result.task_md.read_text(encoding="utf-8")  # type: ignore[union-attr]
        # v2 marker + explicit mode line (the tear-check anchor)
        assert "<!-- mw-profile: v2 -->" in text
        assert "[mw] mode: partition" in text
        # line protocol mirrors the TS renderPartitionProfileBlock
        assert f"Control workspace: {control.resolve()}" in text
        assert f"Parent root (extended workspace, writable): {parent.resolve()}" in text
        assert f"Partition root (worker cwd): {partition.resolve()}" in text
        assert f"- sdk: {sdk.resolve()}" in text
        assert f"- build: make -C {partition.resolve()} SDK={sdk.resolve()}" in text
        # origin marker untouched (D-104: the TS dispatcher still skips it)
        assert "origin: conductor" in text
        print("[VERIFY] FIX-1: conductor task.md carries the v2 profile block")

    def test_conductor_dispatch_then_active_switch_is_torn(
        self, tmp_path: pathlib.Path, providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FIX-1 + AC-020 end to end: dispatch under partition (block injected),
        switch active to dual before spawn -> the tear check now has a
        recorded mode to compare and refuses the spawn (config torn)."""
        from autopilot import dispatch as dispatch_mod

        control, _, _ = _write_partition_yml(tmp_path)
        game = tmp_path / "game"
        game.mkdir(exist_ok=True)
        result = dispatch_mod.dispatch(
            control, "test-key", "torn", "repair", "the prompt",
            loop="L", attempt=1,
        )
        assert result.ok
        task = pathlib.Path(result.task_md)  # type: ignore[arg-type]
        assert "[mw] mode: partition" in task.read_text(encoding="utf-8")

        # active switched after dispatch, before spawn
        _write_yml(control, f"active: dual\ndual:\n  game: '{game}'\n")
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = _capture_popen(monkeypatch)
        queue = control / ".agenticdoc" / "_workers.parallel"
        entry = _entry(task)
        queue.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        running: dict = {}
        _spawn(entry, control, providers, running)
        assert "t001" not in running  # not spawned
        assert captured == {}
        worker_log = (task.parent / "worker.log").read_text(encoding="utf-8")
        assert "config torn" in worker_log
        assert "'partition'" in worker_log and "'dual'" in worker_log
        statuses = {e["task_key"]: e["status"] for e in _parse_workers_file(queue)}
        assert statuses["t001"] == "failed"
        print("[VERIFY] FIX-1: post-dispatch active switch -> config torn, spawned=no")

    def test_conductor_dispatch_dual_single_never_inject(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """AC-016d zero change: dual/single conductor dispatches keep the
        historical no-profile task.md (the v2 block is partition-only)."""
        from autopilot import dispatch as dispatch_mod

        control = tmp_path / "control"
        game = tmp_path / "game"
        control.mkdir()
        game.mkdir()
        _write_yml(control, f"mode: dual\ngame: '{game}'\n")
        result = dispatch_mod.dispatch(
            control, "test-key", "dual", "repair", "p", loop="L", attempt=1,
        )
        assert result.ok
        text = result.task_md.read_text(encoding="utf-8")  # type: ignore[union-attr]
        assert "mw-profile" not in text
        (control / ".agenticdoc" / "target.yml").unlink()
        result2 = dispatch_mod.dispatch(
            control, "test-key", "single", "repair", "p", loop="L", attempt=1,
        )
        assert result2.ok
        assert "mw-profile" not in result2.task_md.read_text(encoding="utf-8")  # type: ignore[union-attr]

    def test_conductor_dispatch_fail_closed_render(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """AC-004 fail-closed on the conductor path: an undefined toolchain
        placeholder rejects the dispatch before anything is written."""
        from autopilot import dispatch as dispatch_mod

        control = tmp_path / "control"
        parent = tmp_path / "parent"
        partition = tmp_path / "shard"
        for d in (control, parent, partition):
            d.mkdir()
        _write_yml(
            control,
            f"active: partition\npartition:\n  parent: '{parent}'\n"
            f"  partition: '{partition}'\n  toolchain:\n    build: 'x {{game}}'\n",
        )
        result = dispatch_mod.dispatch(
            control, "test-key", "bad", "repair", "p", loop="L", attempt=1,
        )
        assert result.ok is False
        assert result.reason == "target-config-unusable"
        assert result.task_md is None
        assert not (control / ".agenticdoc" / "test-key" / "workers").exists()

    def test_partition_profile_matches_ts_golden(self, tmp_path: pathlib.Path) -> None:
        """mw-target-partition FIX-13 (full-text parity): the Py conductor
        renderer (mw_common.render_partition_profile_md) and the TS
        dispatcher renderer (renderPartitionProfileBlock) emit
        byte-identical profile blocks for the same sample config. The
        golden is recorded by the TS side from _PARTITION_GOLDEN_YML
        (agent-team-loop-profile-injection.test.ts) with the control root
        replaced by "<CTRL>"; this side renders the same sample and must
        match every byte (CRLF normalized on read — fixture-runner
        convention: both sides compare \n)."""
        control = tmp_path / "control"
        for name in ("parent", "shard", "sdk", "data", "docs"):
            (control / name).mkdir(parents=True)
        _write_yml(control, _PARTITION_GOLDEN_YML)
        config = mw_common.load_target_config(control)
        assert config["mode"] == "partition"
        profile = mw_common.render_partition_profile_md(config) + "\n"
        golden_path = (
            pathlib.Path(__file__).parent / "test" / "fixtures" / "partition-profile-block.golden.md"
        )
        assert golden_path.exists(), (
            f"shared golden missing: {golden_path} (record it via the TS-side "
            "FIX-13 test in agent-team-loop-profile-injection.test.ts)"
        )
        golden = golden_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert profile.replace(str(control.resolve()), "<CTRL>") == golden
        print("[VERIFY] FIX-13: partition_profile_parity=byte-identical")


# ── T-05: read-scope anchoring (AC-008) ───────────────────────────────────────


class TestExpandReadScopePartition:
    def test_partition_anchors_at_partition_root(self, tmp_path: pathlib.Path) -> None:
        control, parent, partition = _write_partition_yml(tmp_path)
        config = mw_common.load_target_config(control)
        outside = tmp_path / "outside"
        outside.mkdir()
        scope = ["src/", "docs/readme.md", str(outside)]
        expanded = _expand_read_scope(scope, config, control)
        assert expanded == [
            str((partition / "src").resolve()),
            str((partition / "docs" / "readme.md").resolve()),
            str(outside),
            str(control.resolve()),  # control appended (was absent)
            str(parent.resolve()),  # parent appended: extended workspace (AC-001)
        ]
        print(f"[VERIFY] VC-001: expanded=[entries, control, parent], legacy=unchanged")

    def test_partition_parent_dedup(self, tmp_path: pathlib.Path) -> None:
        """AC-001 dedup: an explicitly listed parent (or a parent equal to
        the control root) is not appended a second time."""
        control, parent, partition = _write_partition_yml(tmp_path)
        config = mw_common.load_target_config(control)
        # (a) parent already listed as an explicit entry
        expanded = _expand_read_scope([str(parent)], config, control)
        assert expanded.count(str(parent.resolve())) == 1
        assert expanded == [str(parent.resolve()), str(control.resolve())]
        # (b) parent == control root (legal: only parent/partition nesting is
        # rejected; a partition elsewhere with parent == control must not
        # duplicate)
        yml = control / ".agenticdoc" / "target.yml"
        yml.write_text(
            f"active: partition\npartition:\n  parent: '{control}'\n  partition: '{partition}'\n",
            encoding="utf-8",
        )
        config = mw_common.load_target_config(control)
        expanded = _expand_read_scope(["src/"], config, control)
        assert expanded == [
            str((partition / "src").resolve()),
            str(control.resolve()),  # control appended; parent == control → no duplicate
        ]
        print("[VERIFY] VC-001: dedup=pass")

    def test_partition_no_duplicate_control(self, tmp_path: pathlib.Path) -> None:
        control, _, partition = _write_partition_yml(tmp_path)
        config = mw_common.load_target_config(control)
        expanded = _expand_read_scope(["src/", str(control)], config, control)
        assert expanded.count(str(control)) == 1

    def test_dual_single_unchanged(self, tmp_path: pathlib.Path) -> None:
        control = tmp_path / "control"
        game = tmp_path / "game"
        control.mkdir()
        game.mkdir()
        _write_yml(control, f"mode: dual\ngame: '{game}'\n")
        dual = mw_common.load_target_config(control)
        assert _expand_read_scope(["src/"], dual, control) == [
            str((game / "src").resolve()), str(control.resolve()),
        ]
        (control / ".agenticdoc" / "target.yml").unlink()
        single = mw_common.load_target_config(control)
        assert _expand_read_scope(["src/"], single, control) == ["src/"]


# ── T-05: dynamic unusable-config description (D-007) ────────────────────────


class _TimelineStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, object, str]] = []

    def append(self, ev: str, key: object = None, detail: str = "") -> None:
        self.events.append((ev, key, detail))


class TestDynamicErrorDescription:
    def test_v2_error_names_active_mode(self, tmp_path: pathlib.Path) -> None:
        control = tmp_path / "control"
        control.mkdir()
        _write_yml(control, "active: partition\n")  # row 4: block missing
        with pytest.raises(RuntimeError) as ei:
            launcher._worker_cwd(control)
        assert "target.yml is unusable" in str(ei.value)
        assert "active: partition" in str(ei.value)

    def test_v1_error_keeps_historical_text(self, tmp_path: pathlib.Path) -> None:
        control = tmp_path / "control"
        control.mkdir()
        _write_yml(control, "mode: dual\n")  # dual without game
        with pytest.raises(RuntimeError) as ei:
            launcher._worker_cwd(control)
        assert str(ei.value).startswith("target.yml is unusable (invalid-config):")
        assert "active:" not in str(ei.value)

    def test_dispatch_reject_shares_the_description(self, tmp_path: pathlib.Path) -> None:
        """dispatch.py and launcher share mw_common.describe_target_error —
        the reject timeline detail carries the same dynamic text."""
        from autopilot import dispatch as dispatch_mod

        control = tmp_path / "control"
        control.mkdir()
        _write_yml(control, "active: partition\n")
        timeline = _TimelineStub()
        result = dispatch_mod.dispatch(
            control, "_scratch", "stem", "repair", "prompt",
            loop="L", attempt=1, timeline=timeline,  # type: ignore[arg-type]
        )
        assert result.ok is False
        assert result.reason == "target-config-unusable"
        assert result.task_md is None  # nothing written, nothing queued
        ev, _key, detail = timeline.events[0]
        assert ev == "target-config-rejected"
        assert "active: partition" in detail


# ── T-06: doctor partition section + fingerprint cache (AC-009/AC-018c/d) ─────


def _doctor(project: pathlib.Path) -> dict:
    return mw_common.doctor_report(project, config=mw_common.load_providers(None))


class TestDoctorPartition:
    def test_partition_checks_and_config_keys(self, tmp_path: pathlib.Path) -> None:
        control, parent, partition = _write_partition_yml(tmp_path)
        sdk = tmp_path / "sdk"
        report = _doctor(control)
        target = report["target"]
        cfg = target["config"]
        # AC-018(c): partition-only keys on top of the legacy key set.
        assert cfg["mode"] == "partition"
        assert cfg["source"] == "target-yml"
        assert cfg["parent_root"] == str(parent.resolve())
        assert cfg["partition_root"] == str(partition.resolve())
        assert cfg["roots"] == {"sdk": str(sdk.resolve())}
        # AC-009: one isdir check per root; no engine/uproject checks.
        assert [(c["name"], c["ok"]) for c in target["checks"]] == [
            ("parent_root", True), ("partition_root", True), ("root:sdk", True),
        ]
        assert not any("uproject" in c["name"] or "engine" in c["name"] for c in target["checks"])
        assert target["probe_cache"] == "probed"
        # A named root that does not exist fails its check and surfaces as
        # a doctor issue (fail-visible, not fail-silent).
        _write_yml(
            control,
            _PARTITION_YML.format(parent=parent, partition=partition, sdk=tmp_path / "missing"),
        )
        report2 = _doctor(control)
        checks2 = {c["name"]: c for c in report2["target"]["checks"]}
        assert checks2["root:sdk"]["ok"] is False
        assert any(
            "target toolchain check failed: root:sdk" in i for i in report2["summary"]["issues"]
        )
        text = mw_common.format_doctor_text(report2)
        assert "target: partition (source target-yml)" in text
        print("[VERIFY] VC-009: checks=[parent_root,partition_root,root:*]")

    def test_dual_section_key_set_unchanged(self, tmp_path: pathlib.Path) -> None:
        control = tmp_path / "control"
        game = tmp_path / "game"
        control.mkdir()
        game.mkdir()
        (game / "Proj.uproject").write_text("{}", encoding="utf-8")
        _write_yml(control, f"mode: dual\ngame: '{game}'\n")
        cfg = _doctor(control)["target"]["config"]
        assert set(cfg) == {"mode", "source", "game_root", "engine_root", "vcs", "uproject"}

    def test_fingerprint_reprobes_on_env_change(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-009/AC-018(d): the env overlay changes the resolved parent
        root WITHOUT touching target.yml (mtime frozen) — only the
        fingerprint can force the re-probe."""
        control, _, _ = _write_partition_yml(tmp_path)
        other_parent = tmp_path / "other-parent"
        other_parent.mkdir()

        assert _doctor(control)["target"]["probe_cache"] == "probed"
        cache = toolchain_probe_path(control)
        first_epoch = json.loads(cache.read_text(encoding="utf-8"))["probed_at_epoch"]
        assert _doctor(control)["target"]["probe_cache"] == "fresh"

        monkeypatch.setenv(mw_common.ENV_PARTITION_PARENT, str(other_parent))
        report = _doctor(control)
        target = report["target"]
        assert target["probe_cache"] == "probed"  # fingerprint moved -> re-probe
        assert target["config"]["source"] == "env"
        assert target["config"]["parent_root"] == str(other_parent.resolve())
        assert target["checks"][0]["name"] == "parent_root"
        assert target["checks"][0]["detail"] == str(other_parent.resolve())
        assert json.loads(cache.read_text(encoding="utf-8"))["probed_at_epoch"] >= first_epoch
        # Idempotent afterwards: same resolution -> fresh cache.
        assert _doctor(control)["target"]["probe_cache"] == "fresh"
        print("[VERIFY] VC-009: reprobe=on-fingerprint-change (env overlay)")

    def test_old_cache_without_fingerprint_reprobes_once(self, tmp_path: pathlib.Path) -> None:
        control, _, _ = _write_partition_yml(tmp_path)
        assert _doctor(control)["target"]["probe_cache"] == "probed"
        # A pre-partition cache carries no fingerprint: stale exactly once.
        cache = toolchain_probe_path(control)
        data = json.loads(cache.read_text(encoding="utf-8"))
        del data["fingerprint"]
        cache.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        assert _doctor(control)["target"]["probe_cache"] == "probed"
        assert _doctor(control)["target"]["probe_cache"] == "fresh"

    def test_active_switch_reprobes(self, tmp_path: pathlib.Path) -> None:
        """AC-018(d): switching active (partition -> dual) changes the mode
        and the root set -> re-probe even though the cache was fresh."""
        control, parent, partition = _write_partition_yml(tmp_path)
        _doctor(control)
        assert _doctor(control)["target"]["probe_cache"] == "fresh"
        _write_yml(control, f"active: dual\ndual:\n  game: '{parent}'\n")
        report = _doctor(control)
        assert report["target"]["probe_cache"] == "probed"
        assert report["target"]["config"]["mode"] == "dual"
