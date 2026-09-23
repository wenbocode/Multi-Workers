"""
test_autopilot_dispatch.py — L1 tests for autopilot/dispatch.py (T-06,
AC-021 / VC-023 conductor side).

Fixtures build their own project trees under tmp_path (queue file, lock dir,
timeline). The tool-set expectations here are the Python half of the L0
parity contract — T-17 locks them against the TS TOOL_ALLOWLISTS.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from autopilot import dispatch
from autopilot import timeline as timeline_mod


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def true_str(b: bool) -> str:
    return "true" if b else "false"


# ── registry (D-107 type table; parity source for T-17) ───────────────────────

def test_registry_types_and_tools() -> None:
    assert set(dispatch.REGISTRY) == {
        "roadmap-writer", "phase-writer", "verifier", "reviewer", "repair",
        "rag-research",
    }
    assert dispatch.tool_set("roadmap-writer") == (
        "read", "write", "edit", "find", "grep", "ls",
    )
    assert dispatch.tool_set("phase-writer") == (
        "read", "write", "edit", "bash", "find", "grep", "ls",
    )
    assert dispatch.tool_set("verifier") == ("read", "find", "grep", "ls")
    assert dispatch.tool_set("reviewer") == ("read", "find", "grep", "ls")
    assert dispatch.tool_set("repair") == (
        "read", "write", "edit", "bash", "find", "grep", "ls",
    )
    for entry in dispatch.REGISTRY.values():
        assert entry.cli == "pi"
        assert entry.provider == "timi"
    assert dispatch.REGISTRY["verifier"].requires_read_scope is True
    assert all(
        not e.requires_read_scope for n, e in dispatch.REGISTRY.items() if n != "verifier"
    )
    # mw-rag-integration T-09: the RAG research bucket is registered but
    # PM-only; the conductor must never dispatch it.
    assert dispatch.REGISTRY["rag-research"].conductor_dispatchable is False
    assert all(
        e.conductor_dispatchable for n, e in dispatch.REGISTRY.items() if n != "rag-research"
    )
    # Unknown type: no tools, never a fallback set.
    assert dispatch.tool_set("coding") == ()
    assert dispatch.tool_set("") == ()
    _verify("VC-023", registry_types=len(dispatch.REGISTRY), unknown_tools=0)


def test_registry_snapshot_for_parity() -> None:
    snap = dispatch.registry_snapshot()
    assert set(snap) == set(dispatch.REGISTRY)
    assert all(isinstance(tools, tuple) for tools in snap.values())
    _verify("VC-023", parity_snapshot_types=len(snap))


# ── task.md rendering (design §4.1 frontmatter) ──────────────────────────────

def test_render_task_md_fields() -> None:
    text = dispatch.render_task_md(
        "verifier",
        "Verify the spec-to-design evidence.",
        loop="l2:k1:spec-to-design",
        attempt=2,
        read_scope=[".agenticdoc/k1", ".agenticdoc/goal.md"],
        model="some-model",
    )
    assert text.startswith("---\n")
    lines = text.splitlines()
    assert "type: verifier" in lines
    assert "model: some-model" in lines
    assert "origin: conductor" in lines
    assert "loop: l2:k1:spec-to-design" in lines
    assert "attempt: 2" in lines
    assert "read_scope:" in lines
    assert "  - .agenticdoc/k1" in lines
    assert "  - .agenticdoc/goal.md" in lines
    assert "Verify the spec-to-design evidence." in lines
    assert text.endswith("\n") and "\r" not in text


def test_render_task_md_without_read_scope_and_model() -> None:
    text = dispatch.render_task_md(
        "repair", "fix it", loop="repair:k1", attempt=1,
    )
    assert "read_scope:" not in text
    assert "model:" not in text
    assert "origin: conductor" in text.splitlines()
    _verify("VC-023", optional_fields_omitted=true_str("read_scope:" not in text))


# ── dispatch: happy path ──────────────────────────────────────────────────────

def test_dispatch_writes_task_and_verified_row(tmp_path: pathlib.Path) -> None:
    tl = timeline_mod.Timeline(
        tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "t-05", "phase-writer",
        "Implement the gates protocol.",
        loop="exec:k1:t-05", attempt=1, timeline=tl,
    )
    assert result.ok and result.reason == ""
    assert result.task_key == "ap-k1-t-05"
    task_md = tmp_path / ".agenticdoc" / "k1" / "workers" / "ap-k1-t-05" / "task.md"
    assert result.task_md == task_md and task_md.is_file()
    assert "origin: conductor" in task_md.read_text(encoding="utf-8")

    rows = mw_common.parse_workers_file(mw_common.workers_path(tmp_path))
    assert len(rows) == 1
    row = rows[0]
    assert row["task_key"] == "ap-k1-t-05"
    assert row["status"] == "pending"
    assert row["cli"] == "pi" and row["provider"] == "timi"
    assert row["task_path"] == str(task_md)
    assert row["model"] == ""
    assert result.row_verified is True
    # Lock protocol cleaned up.
    assert not mw_common.lock_path(tmp_path).exists()
    # Dispatch event on the timeline (AC-017).
    events = timeline_mod.query_events(tl.path).events
    assert [e["ev"] for e in events] == ["dispatch"]
    assert events[0]["key"] == "k1"
    assert "ap-k1-t-05" in events[0]["detail"]
    _verify(
        "VC-023",
        rows=1, row_verified=true_str(result.row_verified),
        lock_cleaned=true_str(not mw_common.lock_path(tmp_path).exists()),
        timeline_dispatch=true_str(len(events) == 1),
    )


def test_dispatch_scratch_owner_sentinel(tmp_path: pathlib.Path) -> None:
    tl = timeline_mod.Timeline(
        tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )
    result = dispatch.dispatch(
        tmp_path, dispatch.SCRATCH_OWNER, "roadmap", "roadmap-writer",
        "Propose the roadmap.",
        loop="roadmap:stage-1", attempt=1, timeline=tl,
    )
    assert result.ok
    assert result.task_key == "ap-_scratch-roadmap"
    task_md = (
        tmp_path / ".agenticdoc" / "_scratch" / "workers" / "ap-_scratch-roadmap" / "task.md"
    )
    assert task_md.is_file()
    events = timeline_mod.query_events(tl.path).events
    assert events[0]["key"] == timeline_mod.KEY_SENTINEL  # never null
    _verify("VC-023", scratch_sentinel_key=true_str(events[0]["key"] == "-"))


def test_dispatch_appends_to_existing_queue(tmp_path: pathlib.Path) -> None:
    wpath = mw_common.workers_path(tmp_path)
    wpath.parent.mkdir(parents=True, exist_ok=True)
    wpath.write_text(
        mw_common.serialize_entry({
            "task_key": "manual-task", "status": "done", "cli": "pi", "provider": "",
            "task_path": str(tmp_path / "x" / "task.md"),
            "dispatched_at": "t0", "updated_at": "t0", "model": "",
        }) + "\n",
        encoding="utf-8",
    )
    assert dispatch.dispatch(
        tmp_path, "k1", "t-06", "reviewer", "Judge.",
        loop="l3:k1", attempt=1,
    ).ok
    rows = mw_common.parse_workers_file(wpath)
    assert [r["task_key"] for r in rows] == ["manual-task", "ap-k1-t-06"]
    assert rows[0]["status"] == "done"  # untouched


# ── dispatch: rejections (zero rows + timeline type-rejected) ────────────────

def test_dispatch_unknown_type_rejected(tmp_path: pathlib.Path) -> None:
    tl = timeline_mod.Timeline(
        tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "t-99", "coding",  # unregistered (manual type, not in registry)
        "should never dispatch",
        loop="exec:k1:t-99", attempt=1, timeline=tl,
    )
    assert not result.ok
    assert result.reason == "unknown-type"
    assert result.task_md is None
    assert not mw_common.workers_path(tmp_path).exists()  # zero rows written
    events = timeline_mod.query_events(tl.path).events
    assert [e["ev"] for e in events] == ["type-rejected"]
    assert "coding" in events[0]["detail"] and "ap-k1-t-99" in events[0]["detail"]
    _verify(
        "VC-023",
        unknown_rows=0,
        type_rejected_event=true_str(len(events) == 1),
        no_fallback=true_str(not mw_common.workers_path(tmp_path).exists()),
    )


def test_dispatch_verifier_requires_read_scope(tmp_path: pathlib.Path) -> None:
    tl = timeline_mod.Timeline(
        tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "t-07", "verifier", "Verify.",
        loop="l2:k1:spec-to-design", attempt=1, timeline=tl,
    )
    assert not result.ok
    assert result.reason == "verifier-read-scope-required"
    assert not mw_common.workers_path(tmp_path).exists()
    events = timeline_mod.query_events(tl.path).events
    assert [e["ev"] for e in events] == ["type-rejected"]
    assert "read_scope" in events[0]["detail"]
    # With a scope it dispatches fine.
    ok = dispatch.dispatch(
        tmp_path, "k1", "t-07", "verifier", "Verify.",
        loop="l2:k1:spec-to-design", attempt=1,
        read_scope=[".agenticdoc/k1"], timeline=tl,
    )
    assert ok.ok and ok.row_verified
    rows = mw_common.parse_workers_file(mw_common.workers_path(tmp_path))
    assert len(rows) == 1 and rows[0]["task_key"] == "ap-k1-t-07"
    _verify(
        "VC-023",
        verifier_scope_required=true_str(not result.ok),
        verifier_with_scope_rows=1,
    )


def test_dispatch_no_timeline_writer_still_works(tmp_path: pathlib.Path) -> None:
    """Timeline is optional: dispatch itself must not depend on it."""
    result = dispatch.dispatch(
        tmp_path, "k1", "t-08", "repair", "Fix.",
        loop="repair:k1", attempt=1,
    )
    assert result.ok and result.row_verified
    assert not (tmp_path / ".agenticdoc" / "_autopilot").exists()


# ── workspace-profile injection (mw-dual-workspace D-005/D-007, Task 006) ─────

def _clear_target_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic: MW_TARGET_* overrides would flip the mode behind the test."""
    monkeypatch.delenv("MW_TARGET_GAME", raising=False)
    monkeypatch.delenv("MW_TARGET_ENGINE", raising=False)


def _write_target_yml(
    control: pathlib.Path, body: str
) -> None:
    agentic = control / ".agenticdoc"
    agentic.mkdir(parents=True, exist_ok=True)
    (agentic / "target.yml").write_text(body, encoding="utf-8")


def test_dispatch_single_mode_no_yml_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression lock: with no target.yml the dispatch output is
    byte-identical to the pre-dual-workspace rendering."""
    _clear_target_env(monkeypatch)
    result = dispatch.dispatch(
        tmp_path, "k1", "snap", "verifier", "Verify.",
        loop="l2:k1", attempt=1, read_scope=[".agenticdoc/k1"],
    )
    assert result.ok and result.row_verified
    expected = (
        "---\n"
        "type: verifier\n"
        "origin: conductor\n"
        "loop: l2:k1\n"
        "attempt: 1\n"
        "read_scope:\n"
        "  - .agenticdoc/k1\n"
        "---\n"
        "\n"
        "Verify.\n"
        "\n"
    )
    assert result.task_md is not None
    assert result.task_md.read_text(encoding="utf-8") == expected
    _verify("VC-013", single_no_yml_snapshot=true_str(True))


def test_dispatch_dual_mode_expands_scope_and_injects_deny_globs(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VC-013/VC-009 generation side: dual mode expands relative entries
    against the game root, passes absolute entries through, appends the
    control root, and injects ignore.deny_globs as quoted frontmatter."""
    _clear_target_env(monkeypatch)
    game = tmp_path / "game"
    engine = tmp_path / "engine"
    game.mkdir()
    engine.mkdir()
    _write_target_yml(
        tmp_path,
        "mode: dual\n"
        f"game: '{game}'\n"
        f"engine: '{engine}'\n"
        "ignore:\n"
        "  deny_globs:\n"
        '    - "**/*.uasset"\n'
        '    - "**/DerivedDataCache/**"\n',
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "dual-01", "verifier", "Verify.",
        loop="l2:k1", attempt=1,
        read_scope=["Content", str(engine / "Source")],
    )
    assert result.ok and result.row_verified
    assert result.task_md is not None
    text = result.task_md.read_text(encoding="utf-8")

    game_content = str((game / "Content").resolve())
    assert f"  - {game_content}" in text  # VC-009: game-root absolute
    assert f"  - {engine / 'Source'}" in text  # VC-009: engine root passthrough
    control_line = f"  - {tmp_path.resolve()}"  # VC-013: control root appended
    assert control_line in text
    assert text.count("deny_globs:") == 1
    assert "  - '**/*.uasset'" in text  # VC-013: quoted (YAML alias marker)
    assert "  - '**/DerivedDataCache/**'" in text
    _verify(
        "VC-013",
        deny_globs_line=true_str("deny_globs:" in text),
        control_scope=true_str(control_line in text),
    )
    _verify(
        "VC-009",
        game_abs=true_str(f"  - {game_content}" in text),
        engine_abs=true_str(f"  - {engine / 'Source'}" in text),
    )


def test_dispatch_dual_scopeless_type_gets_deny_globs_without_scope(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No read_scope given -> no scope rendered, no control-root entry
    (appending one would CREATE containment that was never asked for),
    but the deny firewall still injects (deny-only is valid, AC-006)."""
    _clear_target_env(monkeypatch)
    game = tmp_path / "game"
    game.mkdir()
    _write_target_yml(
        tmp_path,
        "mode: dual\n"
        f"game: '{game}'\n"
        "ignore:\n"
        "  deny_globs:\n"
        '    - "**/*.uasset"\n',
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "dual-02", "phase-writer", "Write.",
        loop="gen:k1", attempt=1,
    )
    assert result.ok
    assert result.task_md is not None
    text = result.task_md.read_text(encoding="utf-8")
    assert "read_scope:" not in text
    assert f"  - {tmp_path.resolve()}" not in text
    assert "  - '**/*.uasset'" in text
    _verify(
        "VC-013",
        scopeless_deny_injected=true_str("deny_globs:" in text),
        no_scope_forced=true_str("read_scope:" not in text),
    )


def test_dispatch_dual_control_root_deduped(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control root already present as an entry is not appended twice."""
    _clear_target_env(monkeypatch)
    game = tmp_path / "game"
    game.mkdir()
    _write_target_yml(
        tmp_path, f"mode: dual\ngame: '{game}'\n",
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "dual-03", "verifier", "Verify.",
        loop="l2:k1", attempt=1,
        read_scope=[str(tmp_path.resolve()), "Source"],
    )
    assert result.ok
    assert result.task_md is not None
    text = result.task_md.read_text(encoding="utf-8")
    control_line = f"  - {tmp_path.resolve()}"
    # Line-exact count: a substring count would also hit the game/Source
    # entry, which contains the control root as a path prefix.
    assert text.splitlines().count(control_line) == 1


def test_dispatch_deny_globs_explicit_override(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit per-task deny_globs list wins over the yml default;
    an explicit empty list suppresses injection entirely."""
    _clear_target_env(monkeypatch)
    game = tmp_path / "game"
    game.mkdir()
    _write_target_yml(
        tmp_path,
        "mode: dual\n"
        f"game: '{game}'\n"
        "ignore:\n"
        "  deny_globs:\n"
        '    - "**/*.uasset"\n',
    )
    r1 = dispatch.dispatch(
        tmp_path, "k1", "ovr-01", "repair", "Fix.",
        loop="repair:k1", attempt=1, deny_globs=["Saved/**"],
    )
    assert r1.ok
    assert r1.task_md is not None
    t1 = r1.task_md.read_text(encoding="utf-8")
    assert "  - 'Saved/**'" in t1
    assert "*.uasset" not in t1  # yml default fully overridden

    r2 = dispatch.dispatch(
        tmp_path, "k1", "ovr-02", "repair", "Fix.",
        loop="repair:k1", attempt=1, deny_globs=[],
    )
    assert r2.ok
    assert r2.task_md is not None
    assert "deny_globs:" not in r2.task_md.read_text(encoding="utf-8")


def test_dispatch_single_mode_with_yml_injects_deny_globs_only(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single mode WITH a target.yml: deny globs inject (any mode — a
    single-root UE project can still deny its DDC), but scope passes through
    untouched (relative entries already anchor cwd = the control root)."""
    _clear_target_env(monkeypatch)
    _write_target_yml(
        tmp_path,
        "mode: single\n"
        "ignore:\n"
        "  deny_globs:\n"
        '    - "**/*.uasset"\n',
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "sgl-01", "verifier", "Verify.",
        loop="l2:k1", attempt=1, read_scope=[".agenticdoc/k1"],
    )
    assert result.ok
    assert result.task_md is not None
    text = result.task_md.read_text(encoding="utf-8")
    assert "  - .agenticdoc/k1" in text  # relative entry untouched
    assert f"  - {tmp_path.resolve()}" not in text  # no control append
    assert "  - '**/*.uasset'" in text  # deny firewall injected


def test_dispatch_broken_target_yml_rejected(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: an unusable target.yml rejects the dispatch (zero rows,
    zero task.md, target-config-rejected timeline event) — never a silently
    un-injected task.md."""
    _clear_target_env(monkeypatch)
    _write_target_yml(tmp_path, "mode: [unclosed\n")
    tl = timeline_mod.Timeline(
        tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )
    result = dispatch.dispatch(
        tmp_path, "k1", "brk-01", "verifier", "Verify.",
        loop="l2:k1", attempt=1, read_scope=[".agenticdoc/k1"], timeline=tl,
    )
    assert not result.ok
    assert result.reason.startswith("target-config-unusable")
    assert result.task_md is None
    assert not mw_common.workers_path(tmp_path).exists()  # zero rows
    assert not (tmp_path / ".agenticdoc" / "k1" / "workers").exists()
    events = timeline_mod.query_events(tl.path).events
    assert [e["ev"] for e in events] == ["target-config-rejected"]
    assert "ap-k1-brk-01" in events[0]["detail"]
    _verify(
        "VC-013",
        broken_yml_rows=0,
        fail_closed=true_str(result.reason.startswith("target-config-unusable")),
    )
