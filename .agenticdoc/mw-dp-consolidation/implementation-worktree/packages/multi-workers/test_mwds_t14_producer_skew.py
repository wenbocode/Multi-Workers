"""test_mwds_t14_producer_skew.py — G-3 producer version-skew at the service layer.

mw-dispatch-card-gate T-14 (AC-009 / P-10). The envelope gate lives in the
*global* service (`launcher.py`) while the injection that satisfies it lives in
each project's framework copy (`autopilot/dispatch.py`): two version domains.
A service that enforces the gate while a project copy is still old refuses
every dispatch of that key, which is indistinguishable from autopilot being
dead (incident `autopilot-producer-paralysis-20261012`: 675 done / 33 failed /
0 pending / 0 running, queue file untouched for two days).

The card's five requirements are pinned here:

1. three distinguishable branches: (a) compliant -> spawn, (b) missing envelope
   + a producer identity line whose version predates the service baseline ->
   greppable ``failed(producer-skew ...)`` + an actionable upgrade pointer,
   (c) no identity line -> T-09 fail-closed unchanged, but loud (guidance);
2. no silent zero-output: one aggregate ``[ENVELOPE-SKEW]`` alarm per key per
   poll (not one per row), carrying key / row count / producer / baseline /
   upgrade pointer, in the existing doctor-readable surface (launcher.log) and
   persisted once into the first rejected row's trace.log;
3. an explicit escape hatch that is OFF by default and, when on, injects a
   canonical skeleton + writes a ``[ENVELOPE_FALLBACK]`` audit fact per row —
   envelope judgement only, never a write-face (``allow_foreign_write``)
   relaxation;
4. a narrowed blast radius: a skew only affects the rejected row, never the
   same key's other rows or another key (no early return / raise);
5. interoperability with the T-13 producer output (real ``dispatch()`` render
   when T-13 is on the tree, an equivalent shaped fixture otherwise — the
   source actually used is printed for the report).

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_mwds_t14_producer_skew.py
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher  # noqa: E402
import mw_common  # noqa: E402
from launcher import (  # noqa: E402
    ENVELOPE_PRODUCER_BASELINE,
    ENVELOPE_PRODUCER_BASELINE_SEMVER,
    _load_providers,
    _parse_workers_file,
    _poll_once,
    _serialize_entry,
    classify_envelope_refusal,
    envelope_fallback_inject,
    has_producer_identity,
    producer_identity,
    producer_version_before_baseline,
)

_HERMETIC_CONFIG = {
    "credentials": {"timi": {"sources": [{"env": "TIMI_API_KEY"}]}},
    "providers": {"timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"}},
}

# Branch (c): no identity line, no canonical envelope. `type:` is present so the
# escape hatch could in principle repair it. The body is deliberately free of
# every section-semantics hint (background/AC/report.md) so the T-09 wide
# judge really reports it missing.
_LEGACY_CODING = "type: coding\nDo something useful.\n"

# Branch (b): the producer identity line names a version that predates the
# service baseline (the incident's "project framework copy not yet synced").
_SKEW_CODING = (
    "type: coding\n"
    "envelope_producer: autopilot-conductor@0.60.0\n"
    "Do something useful.\n"
)

# Branch (a): the T-02/T-10 canonical envelope + coding extras (the shape every
# current producer renders).
_COMPLIANT_CODING = (
    "type: coding\n"
    "envelope_producer: autopilot-conductor@" + ENVELOPE_PRODUCER_BASELINE_SEMVER + "\n"
    "\n"
    "## 上下文\n"
    "\n"
    "背景：T-14 服务层夹具；种子锚点 .agenticdoc/goal.md。\n"
    "\n"
    "## 要求\n"
    "\n"
    "实现 T-14 服务层偏移判定。AC-009 判据成立。\n"
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
    "python -X utf8 -m pytest packages/multi-workers/test_mwds_t14_producer_skew.py -q\n"
    "\n"
    "## 改动历史\n"
    "\n"
    "trace.log 写入事件。\n"
)

# T-13-shaped fixture (used when the live producer is not on the tree): the
# canonical envelope + extras + the machine-readable producer identity line.
_T13_SHAPED_FIXTURE = _COMPLIANT_CODING


@pytest.fixture()
def providers(tmp_path: pathlib.Path) -> dict:
    path = tmp_path / "providers.json"
    path.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return _load_providers(path)


@pytest.fixture()
def queue_file(tmp_path: pathlib.Path) -> pathlib.Path:
    agentic = tmp_path / ".agenticdoc"
    agentic.mkdir(exist_ok=True)
    return agentic / "_workers.parallel"


class _FakeProc:
    returncode = None

    def poll(self) -> None:
        return None


def _write_card(
    tmp_path: pathlib.Path, text: str, key: str = "t001", owner: str = "test-key"
) -> pathlib.Path:
    directory = tmp_path / ".agenticdoc" / owner / "workers" / key
    directory.mkdir(parents=True, exist_ok=True)
    card = directory / "task.md"
    card.write_text(text, encoding="utf-8")
    return card


def _set_mtime(path: pathlib.Path, iso: str) -> None:
    """Pin a fixture's mtime so the T-12/F-03 boundary cross-check is explicit."""
    ts = datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.timezone.utc).timestamp()
    os.utime(path, (ts, ts))


def _entry(task_path: pathlib.Path, **overrides: str) -> dict[str, str]:
    entry = {
        "cli": "pi", "provider": "timi", "task_path": str(task_path),
        "task_key": task_path.parent.name, "status": "pending",
        "dispatched_at": "2026-10-12T00:00:00+00:00",
        "updated_at": "2026-10-12T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


def _enable_fallback(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write the explicit T-14 escape-hatch config key (the only way in)."""
    path = tmp_path / ".agenticdoc" / "_autopilot" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"envelope_fallback": True}), encoding="utf-8")
    return path


def _poll(
    tmp_path: pathlib.Path,
    providers: dict,
    queue_file: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    entries: list[dict[str, str]],
) -> dict:
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "absent-machine-config.json"))
    monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    queue_file.write_text(
        "".join(_serialize_entry(entry) + "\n" for entry in entries), encoding="utf-8"
    )
    running: dict = {}
    _poll_once(tmp_path, providers, running, {}, [], None)
    return running


def _statuses(queue_file: pathlib.Path) -> dict[str, str]:
    return {row["task_key"]: row["status"] for row in _parse_workers_file(queue_file)}


def _worker_log(card: pathlib.Path) -> str:
    path = card.parent / "worker.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _alarm_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if "[ENVELOPE-SKEW]" in line]


def _t13_render(tmp_path: pathlib.Path) -> tuple[str, str]:
    """T-13 producer output when it is on the tree, else the shaped fixture.

    Returns (task_md_text, source_label); the label is printed as evidence so
    the report can state whether the interop case measured the real producer.
    """
    try:
        from autopilot import dispatch  # noqa: PLC0415 - optional live dependency

        result = dispatch.dispatch(
            tmp_path, "k1", "t-13", "phase-writer", "Do the task.",
            loop="exec:k1:t-13", attempt=1,
        )
        if result.ok and result.task_md is not None:
            text = pathlib.Path(result.task_md).read_text(encoding="utf-8")
            if "envelope_producer:" in text:
                return (text, "autopilot.dispatch.dispatch()")
    except Exception as exc:  # noqa: BLE001 - T-13 may be mid-edit; fixture fallback
        print(f"[T-14 note] live T-13 producer unavailable ({exc!r}); using shaped fixture")
    return (_T13_SHAPED_FIXTURE, "shaped-fixture")


# ── 1. three distinguishable branches ────────────────────────────────────────

class TestThreeBranches:
    def test_compliant_card_is_branch_a(self, tmp_path: pathlib.Path) -> None:
        card = _write_card(tmp_path, _COMPLIANT_CODING)
        assert classify_envelope_refusal(_entry(card)) is None
        assert launcher._envelope_refusal(_entry(card)) is None

    def test_skew_card_is_branch_b(self, tmp_path: pathlib.Path) -> None:
        card = _write_card(tmp_path, _SKEW_CODING)
        verdict = classify_envelope_refusal(_entry(card))
        assert verdict is not None and verdict["kind"] == "skew"
        assert verdict["producer"] == "autopilot-conductor@0.60.0"
        assert "failed(producer-skew autopilot-conductor@0.60.0" in verdict["reason"]
        assert f"baseline={ENVELOPE_PRODUCER_BASELINE}" in verdict["reason"]
        assert verdict["guidance"] and any(
            "upgrade" in line for line in verdict["guidance"]
        )

    def test_legacy_card_is_branch_c(self, tmp_path: pathlib.Path) -> None:
        card = _write_card(tmp_path, _LEGACY_CODING)
        verdict = classify_envelope_refusal(_entry(card))
        assert verdict is not None and verdict["kind"] == "legacy"
        assert verdict["producer"] == ""
        # T-09 refusal text is preserved exactly (no skew label).
        assert verdict["reason"].startswith("envelope missing: ")
        assert "producer-skew" not in verdict["reason"]
        assert verdict["guidance"]

    def test_identity_line_with_unprovable_version_is_plain_missing(
        self, tmp_path: pathlib.Path
    ) -> None:
        # A producer line whose version cannot be proven old keeps the T-09
        # refusal (never a false skew label on a current producer).
        card = _write_card(
            tmp_path, "type: coding\nenvelope_producer: dispatch.py@unknown\nDo something.\n"
        )
        verdict = classify_envelope_refusal(_entry(card))
        assert verdict is not None and verdict["kind"] == "missing"
        assert verdict["reason"].startswith("envelope missing: ")


class TestSkewRowOutcome:
    def test_skew_row_fails_loudly_with_guidance_and_aggregate_alarm(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        card = _write_card(tmp_path, _SKEW_CODING)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        assert running == {}, "a skewed producer row must not spawn by default"
        assert _statuses(queue_file)["t001"] == "failed"
        log = _worker_log(card)
        err = capsys.readouterr().err
        print(f"[T-14 evidence] skew worker.log:\n{log}")
        print(f"[T-14 evidence] skew stderr tail:\n{err.strip()}")
        assert "failed(producer-skew autopilot-conductor@0.60.0" in log
        assert f"baseline={ENVELOPE_PRODUCER_BASELINE}" in log
        assert "envelope-skew guidance" in log
        assert "upgrade this project's framework copy" in log
        # The aggregate alarm is persisted in the rejected row's worker.log too.
        assert "[ENVELOPE-SKEW]" in log
        # Requirement 2: exactly one aggregate alarm for the key (not per row).
        alarms = _alarm_lines(err)
        assert len(alarms) == 1, err
        assert "key=test-key" in alarms[0]
        assert "refused_rows=1" in alarms[0]
        assert "autopilot-conductor@0.60.0" in alarms[0]
        assert f"baseline={ENVELOPE_PRODUCER_BASELINE}" in alarms[0]
        assert "upgrade this project's framework copy" in alarms[0]
        # Persisted once into the PM-readable trace.log.
        trace = (card.parent / "trace.log").read_text(encoding="utf-8")
        assert "[ENVELOPE-SKEW]" in trace


# ── 2. aggregate alarm: one line per key per poll ────────────────────────────

class TestAggregateAlarm:
    def test_two_skew_rows_of_one_key_yield_one_alarm_line(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        first = _write_card(tmp_path, _SKEW_CODING, key="t001")
        second = _write_card(tmp_path, _SKEW_CODING, key="t002")
        _set_mtime(first, "2026-10-12T00:00:00+00:00")
        _set_mtime(second, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [
                _entry(first, dispatched_at="2026-10-12T00:00:00+00:00"),
                _entry(second, dispatched_at="2026-10-12T00:00:00+00:00"),
            ],
        )
        assert running == {}
        err = capsys.readouterr().err
        alarms = _alarm_lines(err)
        assert len(alarms) == 1, f"aggregate, not per row: {alarms}"
        assert "refused_rows=2" in alarms[0]
        assert "key=test-key" in alarms[0]
        # One persisted copy only, in the first rejected row of the key.
        assert "[ENVELOPE-SKEW]" in _worker_log(first)
        assert "[ENVELOPE-SKEW]" not in _worker_log(second)

    def test_skew_is_not_silent_zero_output(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The incident's failure mode: spawned=[] AND no visible alarm."""
        card = _write_card(tmp_path, _SKEW_CODING)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        err = capsys.readouterr().err
        assert "[ENVELOPE-SKEW]" in err, "zero output must be visible"
        assert "failed(producer-skew" in err  # the per-row reason is also loud


# ── 3. narrowed blast radius (requirement 4) ─────────────────────────────────

class TestNarrowBlastRadius:
    def test_skew_row_does_not_stop_same_key_or_other_key_rows(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The executable counterexample: skew first, then a compliant row of
        # the SAME key and one of ANOTHER key. An early `return`/`raise` in the
        # skew branch would leave the other two unspawned.
        skew = _write_card(tmp_path, _SKEW_CODING, key="t001")
        same_key = _write_card(tmp_path, _COMPLIANT_CODING, key="t002")
        other_key = _write_card(
            tmp_path, _COMPLIANT_CODING, key="t003", owner="other-key"
        )
        _set_mtime(skew, "2026-10-12T00:00:00+00:00")
        entries = [
            _entry(skew, dispatched_at="2026-10-12T00:00:00+00:00"),
            _entry(same_key, dispatched_at="2026-10-12T00:00:00+00:00"),
            _entry(other_key, dispatched_at="2026-10-12T00:00:00+00:00"),
        ]
        running = _poll(tmp_path, providers, queue_file, monkeypatch, entries)
        statuses = _statuses(queue_file)
        err = capsys.readouterr().err
        print(f"[T-14 evidence] narrow failure surface: spawned={sorted(running)} statuses={statuses}")
        assert set(running) == {"t002", "t003"}, running
        assert statuses["t001"] == "failed"
        assert statuses["t002"] == "running"
        assert statuses["t003"] == "running"
        assert len(_alarm_lines(err)) == 1

    def test_skew_row_last_in_the_batch_still_does_not_stop_earlier_rows(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        good = _write_card(tmp_path, _COMPLIANT_CODING, key="t001")
        skew = _write_card(tmp_path, _SKEW_CODING, key="t002")
        _set_mtime(skew, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [
                _entry(good, dispatched_at="2026-10-12T00:00:00+00:00"),
                _entry(skew, dispatched_at="2026-10-12T00:00:00+00:00"),
            ],
        )
        assert "t001" in running
        assert _statuses(queue_file)["t002"] == "failed"

    def test_poll_does_not_raise_on_skew(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        card = _write_card(tmp_path, _SKEW_CODING)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        # _poll calls _poll_once directly: any exception would propagate here.
        _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )


# ── 4. escape hatch (default OFF) ────────────────────────────────────────────

class TestEscapeHatch:
    def test_default_is_off_and_refuses(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        assert launcher.autopilot_config.envelope_fallback_enabled(tmp_path) is False
        card = _write_card(tmp_path, _LEGACY_CODING)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        assert running == {}
        assert _statuses(queue_file)["t001"] == "failed"
        assert "[ENVELOPE_FALLBACK]" not in _worker_log(card)

    def test_off_keeps_the_legacy_branch_loud(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        card = _write_card(tmp_path, _LEGACY_CODING)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        log = _worker_log(card)
        print(f"[T-14 evidence] legacy worker.log:\n{log}")
        assert "envelope missing:" in log            # T-09 fail-closed text kept
        assert "failed(producer-skew" not in log     # not mislabelled as skew
        assert "envelope guidance:" in log           # requirement 1c: loud
        assert "envelope_producer" in log            # names what is missing

    def test_on_injects_skeleton_spawns_and_audits(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _enable_fallback(tmp_path)
        card = _write_card(tmp_path, _LEGACY_CODING)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        assert "t001" in running
        assert _statuses(queue_file)["t001"] == "running"
        log = _worker_log(card)
        text = card.read_text(encoding="utf-8")
        print(f"[T-14 evidence] fallback worker.log: {log.strip()}")
        assert "[ENVELOPE_FALLBACK]" in log
        assert "kind=legacy" in log
        assert "envelope_fallback=true" in log
        assert "<!-- mw-envelope-fallback -->" in text
        assert "## 上下文" in text and "## 要求" in text and "## 交付格式" in text
        for extra in ("写入允许面", "写入禁止面", "验收命令", "改动历史"):
            assert extra in text
        # The injected card is really compliant now.
        assert launcher._envelope_refusal(_entry(card)) is None

    def test_on_also_covers_the_skew_branch(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _enable_fallback(tmp_path)
        card = _write_card(tmp_path, _SKEW_CODING)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        assert "t001" in running
        log = _worker_log(card)
        assert "[ENVELOPE_FALLBACK]" in log
        assert "kind=skew" in log

    def test_on_does_not_loosen_write_face_judgement(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The hatch is envelope-only: it never edits or adds a write-face key."""
        _enable_fallback(tmp_path)
        original = (
            "type: coding\n"
            "allow_foreign_write: false\n"
            "写入禁止面: ../foreign/**\n"
            "Do something useful.\n"
        )
        card = _write_card(tmp_path, original)
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        assert "t001" in running
        text = card.read_text(encoding="utf-8")
        print(f"[T-14 evidence] write-face preserved:\n{text}")
        assert text.startswith(original.rstrip("\n")), "pure append, no rewrite"
        assert "allow_foreign_write: false" in text
        assert "allow_foreign_write: true" not in text
        assert "allow_foreign_write" not in "".join(
            line for line in text.splitlines() if line.startswith(("[ENVELOPE_FALLBACK]",))
        )

    def test_on_cannot_invent_a_type_so_it_stays_fail_closed(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _enable_fallback(tmp_path)
        card = _write_card(tmp_path, "Do something useful.\n")
        _set_mtime(card, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        assert running == {}, "a role-less card cannot be auto-completed"
        assert _statuses(queue_file)["t001"] == "failed"
        assert "[ENVELOPE_FALLBACK]" not in _worker_log(card)

    def test_inject_is_idempotent(self, tmp_path: pathlib.Path) -> None:
        once = envelope_fallback_inject(_LEGACY_CODING)
        assert once is not None
        twice = envelope_fallback_inject(once)
        assert twice == once, "a second poll must not duplicate the skeleton"
        assert once.count("<!-- mw-envelope-fallback -->") == 1


class TestFallbackConfigKey:
    def test_absent_file_means_off(self, tmp_path: pathlib.Path) -> None:
        assert launcher.autopilot_config.envelope_fallback_enabled(tmp_path) is False

    def test_wrong_type_fails_closed(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "absent-machine-config.json"))
        path = tmp_path / ".agenticdoc" / "_autopilot" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"envelope_fallback": "yes"}', encoding="utf-8")
        with pytest.raises(launcher.autopilot_config.ConfigError):
            launcher.autopilot_config.load_config(tmp_path)
        assert launcher.autopilot_config.envelope_fallback_enabled(tmp_path) is False

    def test_key_stays_outside_the_frozen_20_key_schema(self) -> None:
        config = launcher.autopilot_config
        assert config.ENVELOPE_FALLBACK_KEY not in config.DEFAULT_CONFIG
        assert len(config.DEFAULT_CONFIG) == 21
        assert config.ENVELOPE_FALLBACK_KEY in config._BOOL_FIELDS


# ── 5. producer identity + version comparison ────────────────────────────────

class TestProducerIdentity:
    def test_line_is_parsed_with_leading_indent_and_tabs(self) -> None:
        assert producer_identity(
            "type: coding\n  envelope_producer:\tautopilot-conductor@0.83.0\n"
        ) == ("autopilot-conductor", "0.83.0")
        assert has_producer_identity("type: coding\nenvelope_producer: x@1\n") is True

    def test_missing_line_is_legacy_not_an_error(self) -> None:
        assert producer_identity("type: coding\n") == ("", "")
        assert has_producer_identity("type: coding\n") is False

    def test_value_without_at_still_has_an_identity(self) -> None:
        assert producer_identity("envelope_producer: dispatch.py\n") == ("dispatch.py", "")
        assert has_producer_identity("envelope_producer: dispatch.py\n") is True


class TestVersionComparison:
    def test_calendar_family_uses_the_enforcement_boundary(self) -> None:
        assert producer_version_before_baseline("2026-01-01") is True
        assert producer_version_before_baseline("2026-10-11T23:59:59Z") is True
        assert producer_version_before_baseline("2026-10-12") is False
        assert producer_version_before_baseline("2026-10-13") is False

    def test_numeric_family_uses_the_framework_release(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(launcher, "ENVELOPE_PRODUCER_BASELINE_SEMVER", "1.9.9")
        assert producer_version_before_baseline("1.9.8") is True
        assert producer_version_before_baseline("1.9.9") is False
        assert producer_version_before_baseline("2.0.0") is False

    def test_unprovable_versions_are_never_labelled_skew(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(launcher, "ENVELOPE_PRODUCER_BASELINE_SEMVER", "")
        assert producer_version_before_baseline("unknown") is False
        assert producer_version_before_baseline("") is False
        assert producer_version_before_baseline("v0.1.0") is False
        assert producer_version_before_baseline("1.2.3") is False  # no baseline source

    def test_families_are_never_cross_compared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A numeric baseline paired with a date version: not comparable.
        monkeypatch.setattr(launcher, "ENVELOPE_PRODUCER_BASELINE_SEMVER", "2026-01-01")
        assert producer_version_before_baseline("2026-10-12") is False
        # A date baseline paired with a numeric version under a numeric baseline.
        monkeypatch.setattr(launcher, "ENVELOPE_PRODUCER_BASELINE_SEMVER", "9.9.9")
        assert producer_version_before_baseline("0.1.0") is True

    def test_real_baseline_semver_comes_from_the_existing_version_source(self) -> None:
        package = (
            pathlib.Path(launcher.__file__).resolve().parent.parent
            / "coding-agent" / "package.json"
        )
        assert package.is_file(), "the baseline's version source must exist"
        assert ENVELOPE_PRODUCER_BASELINE_SEMVER == json.loads(
            package.read_text(encoding="utf-8")
        )["version"]

    def test_baseline_date_is_the_single_enforcement_boundary(self) -> None:
        assert ENVELOPE_PRODUCER_BASELINE == launcher.ENVELOPE_ENFORCE_SINCE


# ── 6. T-13 producer interop ─────────────────────────────────────────────────

class TestT13Interop:
    def test_producer_output_spawns_and_identity_parser_agrees(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        text, source = _t13_render(tmp_path)
        print(f"[T-14 evidence] T-13 producer source = {source}")

        # Parser parity with the producer's own parser when it is on the tree
        # (the service keeps its own copy on purpose: two version domains, P-10).
        try:
            from autopilot import dispatch  # noqa: PLC0415

            assert producer_identity(text) == dispatch.parse_producer_identity(text)
        except ImportError:  # pragma: no cover - producer absent
            pass

        card = _write_card(tmp_path, text, key="t013")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(card, dispatched_at="2026-10-12T00:00:00+00:00", task_key="t013")],
        )
        print(f"[T-14 evidence] T-13 interop spawned={sorted(running)}")
        assert "t013" in running, "a compliant T-13 render must pass the gate"
        assert _statuses(queue_file)["t013"] == "running"

    def test_fixture_shape_is_the_producer_shape(self) -> None:
        # Even on the fixture path the contract is pinned: identity line +
        # canonical envelope + coding extras, and it judges as compliant.
        assert has_producer_identity(_T13_SHAPED_FIXTURE) is True
        assert launcher.type_extras_missing("coding", _T13_SHAPED_FIXTURE) == []

    def test_old_producer_shape_would_be_skew(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The AC-009 counterexample: an old framework copy (no injection, old
        version) must not be a silent zero-output — loud skew + guidance."""
        old = _write_card(
            tmp_path,
            "type: coding\nenvelope_producer: autopilot-conductor@0.60.0\nDo the task.\n",
        )
        _set_mtime(old, "2026-10-12T00:00:00+00:00")
        running = _poll(
            tmp_path, providers, queue_file, monkeypatch,
            [_entry(old, dispatched_at="2026-10-12T00:00:00+00:00")],
        )
        err = capsys.readouterr().err
        assert running == {}
        assert "failed(producer-skew" in _worker_log(old)
        assert "[ENVELOPE-SKEW]" in err
