"""
test_autopilot_l0.py — L0 static gates + dual-side registry parity
(goal-autopilot T-17; AC-005/AC-021, VC-007/VC-023).

Three groups, no process orchestration, no LLM, no network:

  1. VC-007 static scan (AST over autopilot/*.py):
     - zero "- Phase:" string constants outside docstrings — without the
       literal no code path can write the pm-state Phase interface line
       (the framework's advance_phase.py owns it; AC-005)
     - zero write-family call segments referencing goal.md / goal_path()
       (write family: write_text/write_bytes/replace/rename/touch,
       open(..., "w"/"a"), shutil move/copy) — goal.md is read/stat only
     - runtime half: every timeline "advance" event carries the script
       exit code (in-process tick with a mocked advance returning 0 and 1)

  2. VC-023 parity + fail-closed:
     - registry parity: the Python REGISTRY (imported live) vs the TS
       TOOL_ALLOWLISTS (parsed from worker-mode.ts source) — per-type
       order-exact equality, verifier entry explicit; TS-only legacy
       buckets (coding/review/research/fallback) documented exactly
     - unknown type: conductor dispatch refuses (0 rows + type-rejected
       timeline event) — dynamic, in-process
     - worker fail-closed: static shape assertions on worker-mode.ts plus
       (when node_modules is present) a live run of the T-14 suite
       autopilot-protocol.test.ts, which locks exit-1 fail-closed and the
       GC-8 manual fallback

Scan limits (documented): the write-family scan catches literal-targeted
writes and goal_path() token usage inside write segments; combined with
the Phase-literal ban it locks the AC-005 contract at source level.

Run:
    python packages/multi-workers/test_autopilot_l0.py
"""
from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys
import tempfile
import time

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_AP_DIR = _HERE / "autopilot"
_TS_WORKER = (
    _REPO / "packages" / "coding-agent" / "src" / "extensions"
    / "agent-team-loop" / "worker" / "worker-mode.ts"
)
_TS_TEST = (
    _REPO / "packages" / "coding-agent" / "test" / "suite"
    / "autopilot-protocol.test.ts"
)

sys.path.insert(0, str(_HERE))

import mw_common  # noqa: E402
from autopilot import config, conductor, dispatch, timeline  # noqa: E402

try:
    import pytest
except ImportError:  # script mode
    pytest = None


def _verify(tag: str, **kv) -> None:
    parts = [f"{k}={v}" for k, v in kv.items()]
    print(f"[VERIFY] {tag}: " + " ".join(parts), flush=True)


# ── 1. VC-007: static source scan ────────────────────────────────────────────

_WRITE_ATTRS = {"write_text", "write_bytes", "replace", "rename", "touch"}
_SHUTIL_WRITES = {"move", "copy", "copy2", "copyfile"}
_GOAL_TOKENS = ("goal.md", "goal_path")


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Node ids of every docstring (module/class/function first statement)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _write_segment(node: ast.Call) -> str | None:
    """Source segment when the call looks like a file write, else None."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr in _WRITE_ATTRS:
            return ast.unparse(node)
        if func.attr in _SHUTIL_WRITES:
            return ast.unparse(node)
        if func.attr == "open":
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    if "w" in str(kw.value.value) or "a" in str(kw.value.value):
                        return ast.unparse(node)
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
                if "w" in mode or "a" in mode:
                    return ast.unparse(node)
        return None
    if isinstance(func, ast.Name) and func.id == "open":
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
            if "w" in mode or "a" in mode:
                return ast.unparse(node)
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                if "w" in str(kw.value.value) or "a" in str(kw.value.value):
                    return ast.unparse(node)
    return None


def test_vc007_static_scan() -> None:
    phase_literals: list[tuple[str, str]] = []
    goal_writes: list[tuple[str, str]] = []
    scanned = 0
    for py in sorted(_AP_DIR.glob("*.py")):
        scanned += 1
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        doc_ids = _docstring_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in doc_ids
                and "- Phase:" in node.value
            ):
                phase_literals.append((py.name, node.value.strip()[:60]))
            if isinstance(node, ast.Call):
                seg = _write_segment(node)
                if seg and any(tok in seg for tok in _GOAL_TOKENS):
                    goal_writes.append((py.name, seg[:100]))

    assert scanned >= 10, f"autopilot package unexpectedly small ({scanned} files)"
    assert not phase_literals, f"Phase-interface write literals: {phase_literals}"
    assert not goal_writes, f"goal.md write-family segments: {goal_writes}"
    _verify(
        "VC-007", phase_direct_writes=0, goal_writes=0,
        advance_via_script="all", files_scanned=scanned,
    )


def test_vc007_runtime_exit_codes() -> None:
    """Every timeline advance event carries the script exit code (both the
    success and failure paths)."""
    project = pathlib.Path(tempfile.mkdtemp(prefix="mw-l0-"))
    ap = project / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True)
    (project / ".agenticdoc" / "goal.md").write_text("# Goal\n\ng\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(project, cfg)
    (ap / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: t\n> goal_mtime: 1\n\n"
        "## Stage 1: w\n> goal: g\n> status: running\n> key-status: k1=running, k2=running\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        "| k1 | worker | - |\n| k2 | worker | - |\n",
        encoding="utf-8",
    )
    (project / ".agenticdoc" / "_index.parallel").write_text(
        "| k1 | active | SPEC | — | - | d | t |\n"
        "| k2 | active | SPEC | — | - | d | t |\n",
        encoding="utf-8",
    )
    for key in ("k1", "k2"):
        kd = project / ".agenticdoc" / key
        (kd / "evidence" / "research").mkdir(parents=True)
        (kd / "evidence" / "research" / "spec-r.md").write_text("r\n", encoding="utf-8")
        (kd / "spec.md").write_text(
            "# Spec\n\n- AC-001: ok\n\n" + "pad. " * 40, encoding="utf-8"
        )

    codes = iter((0, 1))
    calls: list[tuple[str, str]] = []
    real_advance = conductor.advance.advance

    def fake_advance(key: str, phase: str, root, summary=None):
        calls.append((key, phase))
        code = next(codes)
        return code, "", "" if code == 0 else "boom"

    conductor.advance.advance = fake_advance
    try:
        tl = timeline.Timeline(timeline.timeline_path(project))
        st = conductor.ConductorState(tl, conductor.goal_mtime_ns(project))
        assert conductor.tick(project, st) == "ok"
    finally:
        conductor.advance.advance = real_advance

    assert sorted(calls) == [("k1", "design"), ("k2", "design")], calls
    events = timeline.query_events(timeline.timeline_path(project)).events
    adv = [e for e in events if e["ev"] == "advance"]
    assert len(adv) == 2, adv
    for e in adv:
        assert re.search(r"exit=\d+", str(e.get("detail", ""))), e
    codes_seen = {re.search(r"exit=(\d+)", e["detail"]).group(1) for e in adv}
    assert codes_seen == {"0", "1"}, codes_seen
    _verify(
        "VC-007", runtime_advance_events=len(adv),
        exit_codes=",".join(sorted(codes_seen)), schema="exit=<n> on all",
    )


# ── 2. VC-023: registry parity ───────────────────────────────────────────────

def _parse_ts_allowlists() -> dict[str, list[str]]:
    src = _TS_WORKER.read_text(encoding="utf-8")
    m = re.search(
        r"const TOOL_ALLOWLISTS[^=]*=\s*\{(.*?)\n\};", src, re.DOTALL
    )
    assert m, "TOOL_ALLOWLISTS block not found in worker-mode.ts"
    block = m.group(1)
    entries: dict[str, list[str]] = {}
    for em in re.finditer(
        r'"?([\w-]+)"?\s*:\s*\[([^\]]*)\]', block
    ):
        name = em.group(1)
        tools = re.findall(r'"([\w-]+)"', em.group(2))
        entries[name] = tools
    assert entries, "no TOOL_ALLOWLISTS entries parsed"
    return entries


def test_vc023_registry_parity() -> None:
    py_reg = {name: list(entry.tools) for name, entry in dispatch.REGISTRY.items()}
    ts_reg = _parse_ts_allowlists()

    # every conductor dispatch type exists on the TS side, order-exact
    missing = sorted(set(py_reg) - set(ts_reg))
    assert not missing, f"TS TOOL_ALLOWLISTS missing types: {missing}"
    for name, tools in py_reg.items():
        assert ts_reg[name] == tools, (
            f"{name}: py={tools} ts={ts_reg[name]} (order-exact required)"
        )
    # the TS side holds exactly the conductor types + the documented legacy
    # worker buckets (coding/review/research) + the internal fallback bucket
    expected_ts_keys = set(py_reg) | {"coding", "review", "research", "fallback"}
    assert set(ts_reg) == expected_ts_keys, (
        f"TS key drift: extra={sorted(set(ts_reg) - expected_ts_keys)} "
        f"missing={sorted(expected_ts_keys - set(ts_reg))}"
    )
    # GC-8: the fallback bucket is the full coding set
    assert ts_reg["fallback"] == ts_reg["coding"], (
        f"fallback={ts_reg['fallback']} coding={ts_reg['coding']}"
    )
    _verify(
        "VC-023", registry_parity="per-type-exact", types=len(py_reg),
        verifier_entry="explicit", ts_buckets=sorted(set(ts_reg) - set(py_reg)),
    )


def test_vc023_unknown_type_rejected() -> None:
    project = pathlib.Path(tempfile.mkdtemp(prefix="mw-l0-"))
    (project / ".agenticdoc").mkdir(parents=True)
    tl = timeline.Timeline(timeline.timeline_path(project))
    result = dispatch.dispatch(
        project, "k1", "bogus-1", "not-a-registered-type", "prompt",
        loop="l:k1", attempt=1, timeline=tl,
    )
    assert result.ok is False
    assert result.reason == "unknown-type"
    rows = [
        r for r in mw_common.parse_workers_file(mw_common.workers_path(project))
        if r["task_key"].startswith("ap-k1-")
    ]
    assert rows == [], rows  # zero queue rows — never a tool-set fallback
    events = timeline.query_events(timeline.timeline_path(project)).events
    rejected = [e for e in events if e["ev"] == "type-rejected"]
    assert rejected and "not-a-registered-type" in rejected[0]["detail"]
    _verify("VC-023", unknown_rows=0, rejection="type-rejected", fallback="none")


# ── 3. VC-023: worker fail-closed + manual fallback (TS side) ────────────────

def test_vc023_worker_fail_closed() -> None:
    src = _TS_WORKER.read_text(encoding="utf-8")
    # the gate scopes to conductor-origin tasks only (others get fallback)
    assert 'meta.origin !== "conductor"' in src, "gate scope check drifted"
    # fail-closed: refuse + exit 1 with a reason (D-107)
    assert "Fail-closed (D-107/VC-023)" in src
    assert "process.exit(1)" in src
    # GC-8: manual/unknown non-conductor types resolve to the fallback set
    assert "TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback" in src

    # the T-14 suite locks the behavior dynamically; run it when the JS
    # toolchain is available, otherwise cite the static shape + suite presence
    vitest = _REPO / "node_modules" / "vitest" / "dist" / "cli.js"
    ran = None
    if vitest.is_file() and _TS_TEST.is_file():
        proc = subprocess.run(
            [
                "node", str(vitest), "--run",
                "test/suite/autopilot-protocol.test.ts",
            ],
            cwd=str(_REPO / "packages" / "coding-agent"),
            capture_output=True, text=True, timeout=300,
            encoding="utf-8", errors="replace",
        )
        ran = proc.returncode
        assert ran == 0, (
            f"autopilot-protocol.test.ts failed (exit {ran}):\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
    ts_test = _TS_TEST.read_text(encoding="utf-8") if _TS_TEST.is_file() else ""
    assert "fails closed" in ts_test, "T-14 fail-closed test missing"
    assert "GC-8/AC-012" in ts_test, "T-8 manual-fallback test missing"
    assert "exactly equal to the Python REGISTRY" in ts_test, "T-14 parity test missing"

    _verify(
        "VC-023", worker_fail_closed=1,
        ts_suite="autopilot-protocol.test.ts",
        ts_run="passed" if ran == 0 else ("skipped-no-toolchain" if ran is None else ran),
        manual_fallback="full-set",
    )


# ── script mode ──────────────────────────────────────────────────────────────

_TESTS = [
    test_vc007_static_scan,
    test_vc007_runtime_exit_codes,
    test_vc023_registry_parity,
    test_vc023_unknown_type_rejected,
    test_vc023_worker_fail_closed,
]


def main() -> int:
    print("# autopilot L0 static gates + registry parity", flush=True)
    failures = []
    for test in _TESTS:
        print(f"\n=== {test.__name__} ===", flush=True)
        t0 = time.monotonic()
        try:
            test()
        except Exception as exc:  # noqa: BLE001 — report and continue
            failures.append((test.__name__, exc))
            print(f"FAIL {test.__name__}: {exc!r}", flush=True)
        else:
            print(f"PASS {test.__name__} ({time.monotonic() - t0:.1f}s)", flush=True)
    print(f"\n# {len(_TESTS) - len(failures)}/{len(_TESTS)} passed", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
