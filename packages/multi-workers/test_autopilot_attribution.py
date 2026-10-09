"""test_autopilot_attribution.py — T-12 (AC-013/AC-021, VC-015/VC-027/VC-028):
queue-row attribution column + unified owner predicate + `worker_timeout_min`
wiring.

Three components used to disagree about who owns a `_workers.parallel` row:

  * `conductor._row_belongs_to`   — `ap-{key}-` prefix **OR** `task_path`
  * `monitor.ts` (TS panel)       — `ap-{key}-` prefix only
  * `mw._rag_terminal_workers`    — `task_path` only

and the `ap-` prefix turned out to be a false signal (6 measured rows carry it
with no conductor origin). The unification is:

  * the producer stamps the row: conductor -> `conductor`, PM/TS -> `manual`
    (row column appended after `model`; the TS writer in worker-store.ts uses
    the same order — locked by the literal-line test below);
  * `mw_common.row_belongs_to` is the single predicate: `origin` decides first,
    the path anchors the owner key, and the `ap-` prefix alone is never a
    signal (VC-028: a missing origin falls back to path and is NOT misjudged as
    a conductor row).

The two non-vacuous counterfactuals required by the task card are encoded here:
(a) the 6 false-signal rows must read `manual` and own no slot — a
prefix-based predicate returns True for them, which this file asserts
explicitly so the fixture is provably discriminating; (b) the `timeout:` header
must actually appear in the rendered task.md (see the report for the
remove-the-line red run).
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402  (third call site: path-only RAG grouping)
import mw_common  # noqa: E402
from autopilot import conductor  # noqa: E402  (first call site: prefix OR path)
from autopilot import dispatch  # noqa: E402
from autopilot import timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(value: bool) -> str:
    return "true" if value else "false"


def _row(task_key: str, task_path: str, origin: str | None = None,
         status: str = "running") -> dict[str, str]:
    row = {
        "task_key": task_key,
        "status": status,
        "cli": "pi",
        "provider": "timi",
        "task_path": task_path,
        "dispatched_at": "2026-09-26T00:00:00+00:00",
        "updated_at": "2026-09-26T00:00:00+00:00",
        "model": "",
    }
    if origin is not None:
        row["origin"] = origin
    return row


def _keyed_path(key: str, task_key: str) -> str:
    return f"H:/proj/.agenticdoc/{key}/workers/{task_key}/task.md"


# ── (1) column layout: parse/serialize tolerance + TS order lock ─────────────

def test_parse_tolerates_7_8_and_9_columns(tmp_path: pathlib.Path) -> None:
    wf = tmp_path / "_workers.parallel"
    wf.write_text(
        "legacy7 | pending | pi | timi | /p/a.md | t1 | t1\n"
        "legacy8 | pending | pi | timi | /p/b.md | t2 | t2 | my-model\n"
        "current9 | pending | pi | timi | /p/c.md | t3 | t3 | my-model | conductor\n"
        "broken | pending | pi | timi | /p/d.md | t4 | t4 | m | conductor | extra\n",
        encoding="utf-8",
    )
    rows = mw_common.parse_workers_file(wf)
    assert [r["task_key"] for r in rows] == ["legacy7", "legacy8", "current9"]
    assert (rows[0]["model"], rows[0]["origin"]) == ("", "")
    assert (rows[1]["model"], rows[1]["origin"]) == ("my-model", "")
    assert (rows[2]["model"], rows[2]["origin"]) == ("my-model", "conductor")
    _verify(
        "VC-015",
        columns="7/8/9",
        ts_order_locked=_true(
            rows[2]["model"] == "my-model" and rows[2]["origin"] == "conductor"
        ),
    )


def test_serialize_keeps_legacy_shape_and_appends_origin() -> None:
    legacy = _row("t1", "/p/a.md")
    conductor_row = _row("t2", _keyed_path("k", "t2"), "conductor")
    assert mw_common.serialize_entry(legacy).split(" | ") == [
        "t1", "running", "pi", "timi", "/p/a.md",
        "2026-09-26T00:00:00+00:00", "2026-09-26T00:00:00+00:00", "",
    ]
    assert mw_common.serialize_entry(conductor_row).split(" | ")[-1] == "conductor"
    # A legacy row rewritten for another reason (launcher update_status) must
    # keep its 8-column shape: no write-side migration of historical rows.
    assert len(mw_common.serialize_entry(legacy).split(" | ")) == 8


def test_ts_writer_column_order_is_locked(tmp_path: pathlib.Path) -> None:
    """The exact line worker-store.ts serializeWorkerLine emits for a
    `manual` row: `... | model | origin`. Parsed here with the Python reader,
    so a column-order drift between the two writers fails both suites."""
    line = (
        "manual-task | running | pi | timi | "
        "H:/proj/.agenticdoc/k/workers/manual-task/task.md | "
        "2026-09-26T00:00:00.000Z | 2026-09-26T00:00:00.000Z | gpt-5 | manual"
    )
    wf = tmp_path / "_workers.parallel"
    wf.write_text(line + "\n", encoding="utf-8")
    row = mw_common.parse_workers_file(wf)[0]
    assert row["model"] == "gpt-5"
    assert row["origin"] == "manual"
    assert mw_common.worker_origin(row) == "manual"
    assert mw_common.worker_owner_key(row) == "k"
    print(json.dumps(row, ensure_ascii=False, sort_keys=True))


# ── (2) the unified owner predicate (VC-027 / VC-028) ───────────────────────

def test_origin_decides_slot_ownership() -> None:
    task_key = "ap-k-writer"
    path = _keyed_path("k", task_key)
    assert mw_common.row_belongs_to(_row(task_key, path, "conductor"), "k") is True
    assert mw_common.row_belongs_to(_row(task_key, path, "manual"), "k") is False
    assert mw_common.row_belongs_to(_row(task_key, path), "k") is False
    # origin=conductor but filed under another key -> not this key's slot
    assert mw_common.row_belongs_to(_row(task_key, path, "conductor"), "other") is False
    # unknown / blank cell fails closed to manual
    assert mw_common.worker_origin({"origin": "  CONDUCTOR "}) == "conductor"
    assert mw_common.worker_origin({"origin": "pm-manual"}) == "manual"
    assert mw_common.worker_origin({}) == "manual"
    _verify(
        "VC-027",
        distinguishable=_true(
            mw_common.row_belongs_to(_row(task_key, path, "conductor"), "k")
            and not mw_common.row_belongs_to(_row(task_key, path, "manual"), "k")
            and not mw_common.row_belongs_to(_row(task_key, path), "k")
        ),
    )


def test_legacy_row_falls_back_to_path_and_is_not_conductor() -> None:
    legacy = _row("ap-k-writer", _keyed_path("k", "ap-k-writer"))  # no origin
    assert mw_common.worker_origin(legacy) == "manual"          # never conductor
    assert mw_common.worker_owner_key(legacy) == "k"            # fallback=path
    assert mw_common.row_belongs_to(legacy, "k") is False
    # The `ap-` prefix alone never attributes a row filed outside a keyed
    # `.agenticdoc/<key>/workers/` dir.
    scratch = _row("ap-k-writer", "H:/proj/.agenticdoc/_scratch/workers/ap-k-writer/task.md")
    assert mw_common.worker_owner_key(scratch) == "_scratch"
    assert mw_common.row_belongs_to(scratch, "k") is False
    _verify(
        "VC-028",
        fallback=(
            "path" if mw_common.worker_owner_key(legacy) == "k" else "none"
        ),
        misjudged_conductor=_true(mw_common.worker_origin(legacy) == "conductor"),
    )


# ── (3) counterfactual (a): the 6 false-signal rows ────────────────────────

# Row shapes measured in RQ-9 (spec-cap-breach-attribution-20260926.md F1/F2):
# PM-hand-started `ap-`-prefixed rows with no `origin: conductor` (E2 project
# L407/L413/L414/L470/L480 + FM's single `ap-` row). Task keys/paths are the
# evidence-documented shapes; the two unrecovered keys are marked (recon).
_FALSE_SIGNAL_ROWS = [
    ("feature-sampling-human-channel", "ap-feature-sampling-human-channel-repair-a2-achieved-terminal"),
    ("feature-cigate-install-kit", "ap-feature-cigate-install-kit-repair-a3-achieved-terminal"),
    ("feature-gui-time-mvp-board", "ap-feature-gui-time-mvp-board-unratified-disclosure"),
    ("feature-l3-verdict-source-fallback", "ap-feature-l3-verdict-source-fallback-l3-a5-recon"),
    ("feature-false-meets-remediation", "ap-feature-false-meets-remediation-l3-a5-recon"),
    ("gui-run-control-hitl", "ap-gui-run-control-hitl-001-contract-input-and-red-baseline"),
]


def _legacy_prefix_rule(row: dict[str, str], key: str) -> bool:
    """The pre-T-12 prefix branch (conductor.py:2135-2138 first line): the
    implementation this fixture must defeat."""
    return str(row.get("task_key", "")).startswith(f"ap-{key}-")


def test_six_prefix_rows_are_manual_and_consume_no_slot() -> None:
    rows = [
        _row(task_key, _keyed_path(key, task_key))  # no origin column at all
        for key, task_key in _FALSE_SIGNAL_ROWS
    ]
    roadmap_keys = [key for key, _ in _FALSE_SIGNAL_ROWS]

    assert {mw_common.worker_origin(r) for r in rows} == {"manual"}
    assert sum(1 for r in rows if not mw_common.worker_is_conductor(r)) == 6

    # Capacity (conductor's in_flight_keys caliber): no key is owned.
    canonical_keys = {
        key for key in roadmap_keys if any(mw_common.row_belongs_to(r, key) for r in rows)
    }
    assert canonical_keys == set()

    # The fixture is discriminating: a prefix-based implementation would have
    # counted all 6 as conductor slots (this is counterfactual (a)'s red).
    prefix_keys = {key for key in roadmap_keys if any(_legacy_prefix_rule(r, key) for r in rows)}
    assert prefix_keys == set(roadmap_keys) and len(prefix_keys) == 6

    # Control: one genuine new-format conductor row does own its slot, so the
    # assertion above is not vacuously true.
    live = _row("ap-feature-gui-time-mvp-board-l2-a1",
                _keyed_path("feature-gui-time-mvp-board", "ap-feature-gui-time-mvp-board-l2-a1"),
                "conductor")
    control = {
        key for key in roadmap_keys
        if any(mw_common.row_belongs_to(r, key) for r in [*rows, live])
    }
    assert control == {"feature-gui-time-mvp-board"}
    _verify(
        "counterfactual-a",
        rows=len(rows),
        judged="/".join(sorted({mw_common.worker_origin(r) for r in rows})),
        capacity=len(canonical_keys),
        prefix_would_count=len(prefix_keys),
    )


# ── (4) the three call sites ───────────────────────────────────────────────

def _site_path(row: dict[str, str], key: str) -> bool:
    """`mw.py:1801-1820` caliber (path only)."""
    return mw_common.worker_owner_key(row) == key


def test_three_call_sites_agree_on_writer_rows() -> None:
    """Every row the unified writer emits carries `origin`, and on those rows
    the three historical calibers (conductor prefix-OR-path, mw.py path-only,
    the unified predicate) return the same verdict."""
    rows = [
        _row("ap-k1-exec-01", _keyed_path("k1", "ap-k1-exec-01"), "conductor"),
        _row("ap-k1-exec-02", _keyed_path("k1", "ap-k1-exec-02"), "conductor"),
        _row("ap-k2-l3-a1", _keyed_path("k2", "ap-k2-l3-a1"), "conductor"),
    ]
    for row in rows:
        for key in ("k1", "k2", "k3"):
            verdicts = {
                "conductor": conductor._row_belongs_to(row, key),
                "mw_path": _site_path(row, key),
                "unified": mw_common.row_belongs_to(row, key),
            }
            assert len(set(verdicts.values())) == 1, (row["task_key"], key, verdicts)
    assert conductor._row_belongs_to(rows[0], "k1") is True
    _verify("call-sites", agree=f"{len(rows)}/{len(rows)}", rows=len(rows))


def test_mw_rag_grouping_matches_the_unified_owner_key(tmp_path: pathlib.Path) -> None:
    """The real mw.py call site (`_rag_terminal_workers`, path-only grouping)
    resolves the same owner key as the unified predicate."""
    agentic = tmp_path / ".agenticdoc"
    key = "k1"
    task_key = "ap-k1-exec-01"
    task_dir = agentic / key / "workers" / task_key
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text("type: coding\n", encoding="utf-8")
    row = _row(task_key, str(task_dir / "task.md"), "conductor", status="done")
    (agentic / "_workers.parallel").write_text(
        mw_common.serialize_entry(row) + "\n", encoding="utf-8"
    )
    grouped = mw._rag_terminal_workers(tmp_path, agentic)
    assert list(grouped) == [key]
    assert grouped[key][0][0] == task_key
    assert mw_common.worker_owner_key(row) == key
    # A manual row with the same shape is still grouped under its key for the
    # panel, but never holds the conductor slot.
    manual = _row(task_key, str(task_dir / "task.md"), "manual", status="done")
    assert mw_common.worker_owner_key(manual) == key
    assert mw_common.row_belongs_to(manual, key) is False


# ── (5) counterfactual (b): the timeout header ─────────────────────────────

def test_render_task_md_renders_timeout_header() -> None:
    with_timeout = dispatch.render_task_md(
        "coding", "Do the work.", loop="l", attempt=1, worker_timeout_min=45
    )
    assert "\ntimeout: 45\n" in with_timeout
    # Unconfigured -> byte-identical to the pre-fix renderer (no header).
    without = dispatch.render_task_md("coding", "Do the work.", loop="l", attempt=1)
    assert "timeout:" not in without
    _verify(
        "counterfactual-b",
        header=next(
            line for line in with_timeout.splitlines() if line.startswith("timeout:")
        ).strip(),
        absent_when_unconfigured=_true("timeout:" not in without),
    )


def test_worker_timeout_min_reads_only_explicit_project_config(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MW_TARGET_CONFIG", raising=False)
    assert dispatch._worker_timeout_min(tmp_path) is None  # no config file
    cfg_dir = tmp_path / ".agenticdoc" / "_autopilot"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text('{"enabled": true}\n', encoding="utf-8")
    # The built-in default (30m) must NOT materialise as a task.md header:
    # task.md wins the wall chain, so it would cut every worker from 60m.
    assert dispatch._worker_timeout_min(tmp_path) is None
    (cfg_dir / "config.json").write_text(
        '{"enabled": true, "worker_timeout_min": 45}\n', encoding="utf-8"
    )
    assert dispatch._worker_timeout_min(tmp_path) == 45


def test_dispatch_writes_origin_and_reachable_timeout(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MW_TARGET_CONFIG", raising=False)
    cfg_dir = tmp_path / ".agenticdoc" / "_autopilot"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(
        '{"enabled": true, "worker_timeout_min": 45}\n', encoding="utf-8"
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "t-12", "phase-writer", "Wire it.",
        loop="exec:k1:t-12", attempt=1,
    )
    assert result.ok and result.row_verified
    task_md = result.task_md.read_text(encoding="utf-8")
    assert "timeout: 45" in task_md
    rows = mw_common.parse_workers_file(mw_common.workers_path(tmp_path))
    assert rows[0]["origin"] == "conductor"
    assert mw_common.row_belongs_to(rows[0], "k1") is True
    _verify(
        "dispatch",
        origin=rows[0]["origin"],
        timeout=next(
            line for line in task_md.splitlines() if line.startswith("timeout:")
        ).strip().split(": ")[1],
        row_verified=_true(result.row_verified),
    )


# ── (6) T-16: the third producer (reconcile_orphans) stamps origin ──────────

def test_reconcile_orphans_stamps_conductor_origin(tmp_path: pathlib.Path) -> None:
    """`reconcile_orphans` re-creates an orphaned conductor row; it must stamp
    `origin: conductor` like `dispatch.py`, or the read side normalises the
    missing column to `manual` and the row stops holding its key's slot
    (T-16/AC-021: the panel's `slotsUsed` under-counts)."""
    orphan_dir = (
        tmp_path / ".agenticdoc" / "k1" / "workers" / "ap-k1-l2-spec-to-design-a1"
    )
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "task.md").write_text(
        "---\ntype: verifier\norigin: conductor\n"
        "loop: l2:k1:spec-to-design\nattempt: 1\n---\n\nverify\n",
        encoding="utf-8",
    )
    st = conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(tmp_path)),
        conductor.goal_mtime_ns(tmp_path),
    )
    conductor.reconcile_orphans(tmp_path, st)

    rows = mw_common.parse_workers_file(mw_common.workers_path(tmp_path))
    assert [r["task_key"] for r in rows] == ["ap-k1-l2-spec-to-design-a1"]
    row = rows[0]
    assert row["status"] == "pending"
    assert row["origin"] == mw_common.WORKER_ORIGIN_CONDUCTOR
    assert mw_common.worker_origin(row) == "conductor"
    # Capacity caliber (conductor's in_flight_keys shape): the re-created row
    # must own k1's slot. Without the stamp this set is empty (slotsUsed 0).
    slots = {key for key in ("k1",) if any(mw_common.row_belongs_to(r, key) for r in rows)}
    assert slots == {"k1"}
    _verify(
        "counterfactual-a",
        reconcile_origin=row["origin"],
        slotsUsed_after=len(slots),
        # counterfactual baseline: the pre-T-16 writer stamped no origin, so the
        # read side normalised the row to `manual` and this set was empty. It is
        # deliberately NOT measured from the current code (which is fixed).
        slotsUsed_before_without_stamp=0,
        row_belongs_to_k1=mw_common.row_belongs_to(row, "k1"),
    )


# ── (7) T-16: `_row_belongs_to` is a one-line delegation (equivalence) ──────

# One row per shape the three historical calibers disagreed about. The set is
# discriminating (counterfactual b): the `ap-k1-legacy-prefix` row is exactly
# where the old prefix-OR-path rule diverges from the canonical predicate.
_EQUIVALENCE_ROWS: list[tuple[str, dict[str, str]]] = [
    ("conductor/keyed/k1", _row("ap-k1-exec-01", _keyed_path("k1", "ap-k1-exec-01"), "conductor")),
    ("conductor/keyed/k2", _row("ap-k2-l3-a1", _keyed_path("k2", "ap-k2-l3-a1"), "conductor")),
    ("conductor/scratch", _row("ap-k1-x", _keyed_path("_scratch", "ap-k1-x"), "conductor")),
    ("manual/keyed", _row("ap-k1-exec-02", _keyed_path("k1", "ap-k1-exec-02"), "manual")),
    ("legacy/no-origin/keyed-prefix", _row("ap-k1-exec-03", _keyed_path("k1", "ap-k1-exec-03"))),
    ("legacy/no-origin/scratch", _row("ap-k1-exec-04", "H:/p/.agenticdoc/_scratch/workers/ap-k1-exec-04/task.md")),
    ("legacy/no-origin/backslash", _row("ap-k2-l3-a2", "H:\\p\\.agenticdoc\\k2\\workers\\ap-k2-l3-a2\\task.md")),
    ("unknown-origin", _row("ap-k1-exec-05", _keyed_path("k1", "ap-k1-exec-05"), "pm-manual")),
    ("empty-origin", _row("ap-k1-exec-06", _keyed_path("k1", "ap-k1-exec-06"), "  ")),
    ("manual/other-key", _row("ap-k1-exec-07", _keyed_path("k3", "ap-k1-exec-07"), "manual")),
]
_EQUIVALENCE_KEYS = ("k1", "k2", "k3")


def test_row_belongs_to_delegates_to_canonical_predicate() -> None:
    """`conductor._row_belongs_to(row, key)` must equal
    `mw_common.row_belongs_to(row, key)` for every fixture row/key pair, and the
    local prefix/path rule must be gone (T-16)."""
    mismatches: list[tuple[str, str, bool, bool]] = []
    for label, row in _EQUIVALENCE_ROWS:
        for key in _EQUIVALENCE_KEYS:
            local = conductor._row_belongs_to(row, key)
            canonical = mw_common.row_belongs_to(row, key)
            print(
                f"[VERIFY] equivalence row={label} key={key} "
                f"local={local} canonical={canonical} equal={local == canonical}"
            )
            if local != canonical:
                mismatches.append((label, key, local, canonical))
    assert mismatches == [], mismatches
    # Non-vacuous: the fixture separates the old prefix rule from the canonical
    # predicate, so restoring the prefix rule would break this assertion.
    old_prefix_true = sum(
        1
        for _, row in _EQUIVALENCE_ROWS
        if str(row.get("task_key", "")).startswith("ap-k1-")
        and not mw_common.row_belongs_to(row, "k1")
    )
    assert old_prefix_true >= 3  # legacy/manual k1-prefixed rows the old rule counted
    _verify(
        "counterfactual-b",
        rows=len(_EQUIVALENCE_ROWS),
        pairs=len(_EQUIVALENCE_ROWS) * len(_EQUIVALENCE_KEYS),
        mismatches=len(mismatches),
        prefix_divergence_rows=old_prefix_true,
    )
