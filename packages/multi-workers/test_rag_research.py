"""
test_rag_research.py — `rag-research` type registration on the Python side
(mw-rag-integration T-09; AC-011, VC-015).

Two acceptance clauses live here:

  - **Parity, zero modification**: `test_autopilot_l0.py` is the locked
    acceptance file and must pass untouched. This module reuses its
    `_parse_ts_allowlists` helper (never a copy) to assert the Python
    `REGISTRY["rag-research"]` tool tuple equals the TS `TOOL_ALLOWLISTS`
    entry item-by-item, then asserts the L0 file itself is byte-unchanged
    (`git diff --stat` empty).
  - **Conductor must not dispatch it**: `conductor_dispatchable=False` and
    `dispatch.dispatch(..., "rag-research", ...)` is rejected before any
    task-dir side effect (zero rows + a `type-rejected` timeline event).
    PM/`/worker` dispatch is the only path.

Run: python -m pytest test_rag_research.py -q -s
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import mw_common  # noqa: E402
from autopilot import dispatch  # noqa: E402
from autopilot import timeline as timeline_mod  # noqa: E402
from test_autopilot_l0 import _parse_ts_allowlists  # noqa: E402  (shared helper, no copy)

_HERE = pathlib.Path(__file__).resolve().parent
_L0_TEST = _HERE / "test_autopilot_l0.py"

_RAG_RESEARCH_TOOLS = (
    "read", "find", "grep", "ls",
    "rag_search", "rag_symbol", "rag_graph", "rag_impact",
    "rag_sources", "rag_feedback", "rag_chat",
)


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


def true_str(value: bool) -> str:
    return "true" if value else "false"


# ── registry entry (AC-011 / VC-015) ────────────────────────────────────────

def test_registry_entry_shape() -> None:
    entry = dispatch.REGISTRY["rag-research"]
    assert entry.name == "rag-research"
    assert entry.tools == _RAG_RESEARCH_TOOLS
    assert len(entry.tools) == 11
    assert entry.cli == "pi" and entry.provider == "timi"
    assert entry.requires_read_scope is False
    # PM-only: the conductor must not dispatch it.
    assert entry.conductor_dispatchable is False
    # Every other registered type stays conductor-dispatchable.
    assert all(
        e.conductor_dispatchable
        for name, e in dispatch.REGISTRY.items()
        if name != "rag-research"
    )
    _verify("VC-015", registry_entry="rag-research", tool_count=len(entry.tools))


def test_registry_snapshot_matches_ts_allowlists() -> None:
    ts_reg = _parse_ts_allowlists()
    snapshot = dispatch.registry_snapshot()

    assert "rag-research" in ts_reg, "TS TOOL_ALLOWLISTS has no rag-research entry"
    assert snapshot["rag-research"] == _RAG_RESEARCH_TOOLS
    # Item-by-item, order-exact equality against the TS side (the same rule
    # T-17's L0 parity test applies to every registered type).
    assert ts_reg["rag-research"] == list(_RAG_RESEARCH_TOOLS)
    # And the rest of the registry keeps parity too (guards against a
    # reordering slip while adding the new entry).
    for name, entry in dispatch.REGISTRY.items():
        assert ts_reg[name] == list(entry.tools), name

    _verify(
        "VC-015",
        parity_unchanged="pass",
        tools=len(_RAG_RESEARCH_TOOLS),
        conductor_dispatchable="false",
    )


def test_role_map_is_research() -> None:
    assert mw_common.TASK_TYPE_TO_ROLE["rag-research"] == "research"
    _verify("VC-015", role="research")


# ── conductor refusal (AC-011) ──────────────────────────────────────────────

def test_conductor_dispatch_rejected(tmp_path: pathlib.Path) -> None:
    tl = timeline_mod.Timeline(
        tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "rag-1", "rag-research",
        "Research the symbol graph.",
        loop="exec:k1:rag-1", attempt=1, timeline=tl,
    )

    assert result.ok is False
    assert "must not dispatch" in result.reason, result.reason
    assert result.task_md is None
    # Nothing entered the queue, and no task dir was created.
    assert not mw_common.workers_path(tmp_path).exists()
    assert not (
        tmp_path / ".agenticdoc" / "k1" / "workers" / "ap-k1-rag-1"
    ).exists()

    events = timeline_mod.query_events(tl.path).events
    assert [e["ev"] for e in events] == ["type-rejected"]
    assert "must not dispatch" in events[0]["detail"]
    assert "rag-research" in events[0]["detail"]

    _verify(
        "VC-015",
        conductor_dispatch_refused=true_str(not result.ok),
        queued=0,
        timeline="type-rejected",
    )


# ── first acceptance condition: L0 untouched ────────────────────────────────

def test_autopilot_l0_is_byte_unchanged() -> None:
    proc = subprocess.run(
        ["git", "diff", "--stat", "--", str(_L0_TEST.name)],
        cwd=str(_HERE), capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        _verify("VC-015", l0_unchanged="git-unavailable")
        return
    assert proc.stdout.strip() == "", f"test_autopilot_l0.py was modified:\n{proc.stdout}"
    _verify("VC-015", l0_untouched=true_str(proc.stdout.strip() == ""))
