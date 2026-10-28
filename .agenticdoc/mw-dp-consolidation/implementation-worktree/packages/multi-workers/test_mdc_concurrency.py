"""test_mdc_concurrency.py - MDC B3 Python half (VC-101/102/103/104).

mw-dynamic-concurrency: dependency-frontier-driven dynamic concurrency. The
key layer (`max_parallel_keys`) and the per-key layer
(`max_workers_per_key`) are *upper bounds*; what actually starts each tick is
``min(layer upper bound, |frontier|)``, and a broken/unusable task graph or an
unsafe write face fails closed (serial, audited), never default-amplifies.

This file changes no production behaviour: every case drives the real
``conductor.tick`` -> ``execute_loop`` path and reads the *measured* dispatch
count out of the real queue file via ``mw_common.parse_workers_file``. The
expected value is never re-derived with ``autopilot.task_graph.frontier``
(that would be circular self-validation); it comes from the deliberately
constructed corpus shape -- N independent dep-free tasks is N, a chain head is
1, M eligible keys with disjoint dependencies is M -- and the measurement is
whatever the queue file actually holds.

Observation points (all real files, no private state):

* dispatch rows -> ``.agenticdoc/_workers.parallel`` (``mw_common.workers_path``
  + ``mw_common.parse_workers_file``), filtered to the ``ap-<key>-`` identity.
* audit lines -> ``.agenticdoc/_autopilot/timeline.jsonl`` (``config`` events
  with the "task graph unusable" alarm, or the WFG ``write-face-*`` events).
* stall guard -> absence of a ``stalled`` timeline event.
* key status -> the ``> key-status:`` line of
  ``.agenticdoc/_autopilot/_roadmap.md``.

advance.advance is the only injected seam (a no-op returning exit 0): the
tests must not spawn the real phase-machine subprocess, and the frontier
mechanics they exercise live entirely before/around the advance call.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import config, conductor, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ── harness ──────────────────────────────────────────────────────────────────


def _project(root: pathlib.Path) -> pathlib.Path:
    """Minimal enabled autopilot project (same shape as the M-02 probe)."""
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(root, cfg)
    return root


def _roadmap(project: pathlib.Path, keys: dict[str, str | None]) -> None:
    """One running stage; ``keys`` maps key -> depends_on (None = '-').

    Order is insertion order, so the key-layer consumption order is the order
    the caller declared -- the corpus controls the eligible-key frontier.
    """
    key_status = ", ".join(f"{key}=running" for key in keys)
    rows = "\n".join(f"| {key} | worker | {dep or '-'} |" for key, dep in keys.items())
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: t\n> goal_mtime: 1\n\n"
        "## Stage 1: work\n> goal: deliver\n> status: running\n"
        f"> key-status: {key_status}\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n"
        f"{rows}\n",
        encoding="utf-8",
    )
    index = "\n".join(
        f"| {key} | active | EXECUTE | \u2014 | - | d | 2026-09-10T00:00:00 |"
        for key in keys
    )
    (project / ".agenticdoc" / "_index.parallel").write_text(index + "\n", encoding="utf-8")


def _card(
    project: pathlib.Path,
    key: str,
    stem: str,
    *,
    deps: list[str] | None = None,
    faces: list[str] | None = None,
) -> None:
    """One task card. ``deps`` -> card-header ``- deps:``; ``faces`` -> the
    ``## 写入允许面`` section (absent = undeclared = serial-only)."""
    tasks_dir = project / ".agenticdoc" / key / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}", ""]
    if deps:
        lines += [f"- deps: {', '.join(deps)}", ""]
    if faces:
        lines += ["## 写入允许面", ""]
        lines += [f"- `{face}`" for face in faces]
        lines += [""]
    lines += ["## 上下文", "", "MDC concurrency corpus.", "", "## 要求", "", "Do the work.", ""]
    (tasks_dir / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def _set_bounds(
    project: pathlib.Path,
    *,
    max_parallel_keys: int | None = None,
    max_workers_per_key: int | None = None,
) -> None:
    cfg = config.load_config(project)
    if max_parallel_keys is not None:
        cfg["max_parallel_keys"] = max_parallel_keys
    if max_workers_per_key is not None:
        cfg["max_workers_per_key"] = max_workers_per_key
    config.save_config(project, cfg)


def _noop_advance(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Inject the real advance seam with a zero-exit no-op (auto-restored)."""
    calls: list[tuple[str, str]] = []

    def fake(key: str, phase: str, root, summary=None):  # noqa: ANN001, ARG001
        calls.append((key, phase))
        return 0, "", ""

    monkeypatch.setattr(conductor.advance, "advance", fake)
    return calls


def _state(project: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(project)),
        conductor.goal_mtime_ns(project),
    )


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _rows(project: pathlib.Path, prefix: str = "ap-") -> list[dict]:
    """Measured queue rows: the REAL ``.agenticdoc/_workers.parallel`` file."""
    return [
        row
        for row in mw_common.parse_workers_file(mw_common.workers_path(project))
        if str(row["task_key"]).startswith(prefix)
    ]


def _key_rows(project: pathlib.Path, key: str) -> list[dict]:
    return _rows(project, f"ap-{key}-")


def _task_keys(project: pathlib.Path, key: str) -> set[str]:
    return {row["task_key"] for row in _key_rows(project, key)}


def _started_keys(project: pathlib.Path) -> set[str]:
    """Keys that own at least one measured queue row (key-layer measurement)."""
    return {str(row["task_key"]).split("-")[1] for row in _rows(project)}


def _keys_of(task_keys: set[str]) -> set[str]:
    return {task_key.split("-")[1] for task_key in task_keys}


def _set_row(project: pathlib.Path, task_key: str, status: str) -> None:
    wpath = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wpath)
    for entry in entries:
        if entry["task_key"] == task_key:
            entry["status"] = status
    wpath.write_text(
        "\n".join(mw_common.serialize_entry(entry) for entry in entries) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _graph_audits(project: pathlib.Path) -> list[dict]:
    return [
        event
        for event in _events(project)
        if event["ev"] == "config" and "task graph unusable" in str(event.get("detail", ""))
    ]


def _events_named(project: pathlib.Path, *names: str) -> list[dict]:
    return [event for event in _events(project) if event["ev"] in names]


def _roadmap_key_status(project: pathlib.Path, key: str) -> str:
    text = (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("> key-status:"):
            for pair in line.split(":", 1)[1].split(","):
                name, _, value = pair.strip().partition("=")
                if name == key:
                    return value
    return "<missing>"


# ── VC-101: frontier identity, started = min(layer bound, |frontier|) ─────────


def test_vc101_per_key_cap_above_frontier(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corpus: 3 independent dep-free tasks, disjoint declared faces, cap 4.

    The frontier is 3 by construction (three separate write faces, no deps),
    so one tick must start min(4, 3) = 3. Once all three are in flight the
    same tick's successor starts 0 more (|frontier| = 0).
    """
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    for index in range(3):
        _card(project, "k1", f"T-{index + 1}", faces=[f"src/{index}/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    _noop_advance(monkeypatch)
    st = _state(project)

    assert conductor.tick(project, st) == "ok"
    first = _key_rows(project, "k1")
    # corpus invariant: 3 independent tasks, bound 4 => min(4,3) = 3
    assert len(first) == 3, [row["task_key"] for row in first]

    before = _task_keys(project, "k1")
    assert conductor.tick(project, st) == "ok"
    after = _task_keys(project, "k1")
    _verify(
        "VC-101a",
        corpus="3 independent dep-free tasks",
        per_key_bound=4,
        measured_tick1=len(first),
        measured_tick2_new=len(after - before),
    )
    assert len(after - before) == 0, "all 3 already in flight: frontier is empty"


def test_vc101_per_key_bound_truncates_each_tick(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corpus: 5 independent dep-free tasks, disjoint faces, cap 2.

    Every tick starts min(2, |remaining frontier|) = 2: the bound -- not the
    frontier width -- is what truncates, and it is recomputed per tick.
    """
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    for index in range(5):
        _card(project, "k1", f"T-{index + 1}", faces=[f"src/{index}/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=2)
    _noop_advance(monkeypatch)
    st = _state(project)

    assert conductor.tick(project, st) == "ok"
    tick1 = _key_rows(project, "k1")
    assert len(tick1) == 2, [row["task_key"] for row in tick1]

    for row in tick1:
        _set_row(project, row["task_key"], "done")
    before = _task_keys(project, "k1")
    assert conductor.tick(project, st) == "ok"
    after = _task_keys(project, "k1")
    new = after - before
    _verify(
        "VC-101b",
        corpus="5 independent dep-free tasks",
        per_key_bound=2,
        measured_tick1=len(tick1),
        measured_tick2_new=len(new),
    )
    assert len(new) == 2, sorted(new)


def test_vc101_per_key_chain_starts_one_per_tick(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corpus: chain T-2 deps T-1, cap 4. Each tick starts at most the single
    chain head; after T-1 is terminal the next head (T-2) starts."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    _card(project, "k1", "T-1", faces=["src/a/**"])
    _card(project, "k1", "T-2", deps=["T-1"], faces=["src/b/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    _noop_advance(monkeypatch)
    st = _state(project)

    assert conductor.tick(project, st) == "ok"
    assert len(_key_rows(project, "k1")) == 1

    before = _task_keys(project, "k1")
    assert conductor.tick(project, st) == "ok"
    assert _task_keys(project, "k1") == before, "T-1 in flight: no dependents ready"

    _set_row(project, "ap-k1-T-1", "done")
    before = _task_keys(project, "k1")
    assert conductor.tick(project, st) == "ok"
    after = _task_keys(project, "k1")
    new = after - before
    _verify(
        "VC-101c",
        corpus="chain T-2 deps T-1",
        per_key_bound=4,
        measured_tick3_new=len(new),
        new=sorted(new),
    )
    assert new == {"ap-k1-T-2"}


def test_vc101_key_layer_min_bound_frontier(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corpus: 3 eligible, dependency-free keys (one serial task each). The
    key layer must start min(max_parallel_keys, 3) keys per tick."""
    _noop_advance(monkeypatch)
    measured: dict[int, int] = {}
    for bound, expected in ((1, 1), (2, 2), (8, 3)):
        root = tmp_path / f"cap{bound}"
        root.mkdir()
        project = _project(root)
        _roadmap(project, {"k1": None, "k2": None, "k3": None})
        for key in ("k1", "k2", "k3"):
            _card(project, key, "T-1")  # undeclared face => serial per key
        _set_bounds(project, max_parallel_keys=bound, max_workers_per_key=4)

        assert conductor.tick(project, _state(project)) == "ok"
        started = _started_keys(project)
        measured[bound] = len(started)
        assert len(started) == expected, (bound, sorted(started))
    _verify("VC-101d", corpus="3 eligible keys", measured=measured)
    assert measured == {1: 1, 2: 2, 8: 3}


# ── VC-102: a narrow frontier is never amplified ─────────────────────────────


def test_vc102_chain_frontier_not_amplified(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chain frontier is 1 regardless of a bound of 4 or 8."""
    _noop_advance(monkeypatch)
    for bound in (8, 4):
        root = tmp_path / f"cap{bound}"
        root.mkdir()
        project = _project(root)
        _roadmap(project, {"k1": None})
        _card(project, "k1", "T-1", faces=["src/a/**"])
        _card(project, "k1", "T-2", deps=["T-1"], faces=["src/b/**"])
        _set_bounds(project, max_parallel_keys=8, max_workers_per_key=bound)
        st = _state(project)

        assert conductor.tick(project, st) == "ok"
        got = _key_rows(project, "k1")
        assert len(got) == 1, (bound, [row["task_key"] for row in got])
        # second tick with the head still in flight still starts nothing
        before = _task_keys(project, "k1")
        assert conductor.tick(project, st) == "ok"
        assert _task_keys(project, "k1") == before
    _verify("VC-102", corpus="chain T-2 deps T-1", measured={8: 1, 4: 1})


# ── VC-103: bound=1 is serial, hot config re-read, no restart ────────────────


def test_vc103_bound_one_serial_same_process_no_restart(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One process, one project: widen first (8/4 -> >1 at both layers), then
    rewrite config.json to 1/1 and tick again in the same process. The next
    tick must start at most one task and at most one key, proving the config
    file is re-read per tick (no serve/loop restart).
    """
    _noop_advance(monkeypatch)
    project = _project(tmp_path)
    _roadmap(project, {"k1": None, "k2": None})
    for key in ("k1", "k2"):
        for index in range(6):
            _card(project, key, f"T-{index + 1}", faces=[f"src/{key}/{index}/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    st = _state(project)  # same ConductorState throughout: same process, no restart

    assert conductor.tick(project, st) == "ok"
    wide_keys = _started_keys(project)
    wide_per_key = len(_key_rows(project, "k1"))
    assert len(wide_keys) == 2, sorted(wide_keys)
    assert wide_per_key == 4, wide_per_key

    # Free the queue so the NEXT tick is not blocked by in-flight rows, then
    # flip both bounds down to 1 by editing config.json only.
    for row in _rows(project):
        _set_row(project, row["task_key"], "done")
    _set_bounds(project, max_parallel_keys=1, max_workers_per_key=1)

    before = _task_keys(project, "k1") | _task_keys(project, "k2")
    assert conductor.tick(project, st) == "ok"
    after = _task_keys(project, "k1") | _task_keys(project, "k2")
    new = after - before
    _verify(
        "VC-103",
        wide_keys=len(wide_keys),
        wide_per_key=wide_per_key,
        narrow_new_rows=len(new),
        narrow_new_keys=len(_keys_of(new)),
        same_process=True,
    )
    assert len(new) == 1, sorted(new)  # per-key layer: max_workers_per_key = 1
    assert len(_keys_of(new)) == 1  # key layer: max_parallel_keys = 1


# ── VC-104: fail-closed -- broken graph / unsafe face => serial + audit ──────


def test_vc104_dangling_dep_serial_fallback_audited(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-2 declares a non-existent T-99: the whole key is serial this tick,
    audited once, and the key is not permanently locked."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    _card(project, "k1", "T-1", faces=["src/a/**"])
    _card(project, "k1", "T-2", deps=["T-99-missing"], faces=["src/b/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    _noop_advance(monkeypatch)
    st = _state(project)

    assert conductor.tick(project, st) == "ok"
    rows = _key_rows(project, "k1")
    audits = _graph_audits(project)
    assert len(rows) == 1, [row["task_key"] for row in rows]
    assert len(audits) == 1, [event.get("detail") for event in audits]
    assert "deps-dangling" in str(audits[0].get("detail", ""))

    # Not a permanent lock: once T-1 is terminal, the serial fallback advances.
    _set_row(project, rows[0]["task_key"], "done")
    assert conductor.tick(project, st) == "ok"
    second = _key_rows(project, "k1")
    assert len(second) == 2, [row["task_key"] for row in second]
    assert len(_graph_audits(project)) == 1, "same problem must not re-flood"
    _verify("VC-104a", case="dangling dep", rows_tick1=len(rows), audit_lines=len(audits))


def test_vc104_dependency_cycle_serial_fallback_audited(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-1 deps T-2 and T-2 deps T-1: a cycle makes the key serial + audited."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    _card(project, "k1", "T-1", deps=["T-2"], faces=["src/a/**"])
    _card(project, "k1", "T-2", deps=["T-1"], faces=["src/b/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    _noop_advance(monkeypatch)

    assert conductor.tick(project, _state(project)) == "ok"
    rows = _key_rows(project, "k1")
    audits = _graph_audits(project)
    assert len(rows) == 1, [row["task_key"] for row in rows]
    assert len(audits) == 1, [event.get("detail") for event in audits]
    assert "deps-cycle" in str(audits[0].get("detail", ""))
    _verify("VC-104b", case="dependency cycle", rows_tick1=len(rows), audit_lines=len(audits))


def test_vc104_undeclared_write_face_serial_only_audited(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No card declares a write face (WFG D-003 = serial-only): even with a
    bound of 4 the key starts exactly one task, and the decision is audited."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    for index in range(3):
        _card(project, "k1", f"T-{index + 1}")  # no ## 写入允许面
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    _noop_advance(monkeypatch)

    assert conductor.tick(project, _state(project)) == "ok"
    rows = _key_rows(project, "k1")
    audits = _events_named(project, "write-face-undeclared")
    assert len(rows) == 1, [row["task_key"] for row in rows]
    assert audits, "undeclared write face must leave an audit line"
    _verify(
        "VC-104c",
        case="undeclared write face",
        per_key_bound=4,
        rows_tick1=len(rows),
        audit_lines=len(audits),
    )


def test_vc104_overlapping_write_face_refused_without_stall(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-1 ``src/shared/**`` overlaps T-2 ``src/shared/deep/**``: the second
    dispatch is refused (still zero side effects), the batch simply waits for
    the next tick, and the key must NOT be marked stalled."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    _card(project, "k1", "T-1", faces=["src/shared/**"])
    _card(project, "k1", "T-2", faces=["src/shared/deep/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    _noop_advance(monkeypatch)

    assert conductor.tick(project, _state(project)) == "ok"
    rows = _key_rows(project, "k1")
    overlap = _events_named(project, "write-face-overlap")
    stalled = _events_named(project, "stalled")
    assert len(rows) == 1, [row["task_key"] for row in rows]
    assert str(rows[0]["task_key"]).endswith("T-1")
    assert overlap, "overlap refusal must leave an audit line"
    assert not stalled, [event.get("detail") for event in stalled]
    assert _roadmap_key_status(project, "k1") == "running"
    _verify(
        "VC-104d",
        case="overlapping write faces",
        rows_tick1=len(rows),
        overlap_events=len(overlap),
        stalled_events=len(stalled),
        key_status=_roadmap_key_status(project, "k1"),
    )
