"""
test_autopilot_e2e.py — L2 E2E for the autopilot conductor (goal-autopilot
T-16; AC-001/002/004/012/016/019/020/025, VC-002/004/006/014/018/021/022/027).

Real process chain, no LLM, no network:
  - REAL conductor (autopilot/conductor.py as its own process)
  - REAL launcher (launcher.py spawning queue rows)
  - REAL mw serve (VC-014/VC-027 supervision chain, fixture providers.json
    with a dummy env credential so the route precheck passes hermetically)
  - REAL framework advance (advance_phase.py from a framework copy inside
    the fixture project — the phase gates run for real)
  - STUB workers: the fixture PATH-shadows ``pi`` with a deterministic stub
    driven by the task.md frontmatter labels (writes the artifact the gate
    expects, exits 0)

Run:
    python packages/multi-workers/test_autopilot_e2e.py
    pytest packages/multi-workers/test_autopilot_e2e.py -m e2e_l2 -s

The suite is excluded from the default pytest run (marker e2e_l2; see
pytest.ini). MW_E2E_FAST=1 shrinks the 60s observation windows
proportionally — every threshold below is interval-relative, never an
absolute constant.

Timing assertions print the dual form mandated by the task book:
    [VERIFY] VC-NNN: delay_ms=<d> interval_ms=<i> pass=true
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_FW_SRC = _REPO / ".agents" / "skills" / "agentic-task"
_CONDUCTOR_PY = _HERE / "autopilot" / "conductor.py"
_LAUNCHER_PY = _HERE / "launcher.py"
_MW_PY = _HERE / "mw.py"

sys.path.insert(0, str(_HERE))

import mw_common  # noqa: E402
from autopilot import config, conductor, gates, roadmap, state, timeline, xkey  # noqa: E402

try:
    import pytest
except ImportError:  # script mode
    pytest = None

# The heavy real-process tests below stay behind the ``e2e_l2`` marker
# (pytest.ini excludes it by default).  It is applied per test rather than as
# a module-level ``pytestmark`` so the hermetic cross-key L2 replay tests at
# the bottom of this file run in the default suite (they only need tmp_path +
# one fixture pytest subprocess).
if pytest is not None:
    _e2e_l2 = pytest.mark.e2e_l2
else:  # script mode: markers are inert (``_TESTS`` calls the functions directly)
    def _e2e_l2(func):
        return func

_INTERVAL = 1.0          # conductor tick (seconds) — every threshold scales on it
_STRESS_INTERVAL = 0.5   # denser writes for the concurrency stress
_SERVE_POLL = 1.0        # mw serve supervision loop (mw.py: time.sleep(1))
_FAST = os.environ.get("MW_E2E_FAST", "") == "1"
_BEAT_WINDOW = 15.0 if _FAST else 60.0
_STRESS_WINDOW = 20.0 if _FAST else 60.0
_GRACE_MS = 250.0        # VC-018 erratum (2026-09-10): gate consumption is
                         # "within the first tick after the answer" — the
                         # answer can land mid-tick, so delay <= interval +
                         # tick-processing overhead (poll granularity +
                         # scheduler jitter), never the bare interval.
_TICK_SLACK_MS = _GRACE_MS


def _verify(tag: str, **kv) -> None:
    parts = [f"{k}={v}" for k, v in kv.items()]
    print(f"[VERIFY] {tag}: " + " ".join(parts), flush=True)


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── fixture project ──────────────────────────────────────────────────────────

_PROVIDERS = {
    "credentials": {
        "fake": {"sources": [{"env": "MW_E2E_FAKE_KEY"}]},
        # D-107 registry routes pi tasks at provider "timi"; the launcher's
        # direct-route branch resolves credentials.timi before spawning the
        # PATH-shadowed stub pi (mw-done-closure-repair T-01 root cause:
        # "Timi credential is not available (no credential sources declared)").
        "timi": {"sources": [{"env": "MW_E2E_FAKE_KEY"}]},
    },
    "providers": {
        "pi": {
            "port": 7999,
            "base_url_env": "PI_BASE_URL",
            "api_key_env": "PI_API_KEY",
            "credential": "fake",
        },
    },
}


def _make_project(
    *,
    keys: dict[str, str],
    enabled: bool = True,
    interval: float = _INTERVAL,
    roadmap_text: str | None = None,
) -> pathlib.Path:
    """Fixture project in a fresh temp dir: framework copy, goal, index rows,
    config, providers.json. ``keys`` maps key -> starting phase."""
    project = pathlib.Path(tempfile.mkdtemp(prefix="mw-e2e-"))
    if not _FW_SRC.is_dir():
        raise RuntimeError(f"framework source missing: {_FW_SRC}")
    shutil.copytree(
        _FW_SRC, project / ".agents" / "skills" / "agentic-task",
        ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"),
    )
    adoc = project / ".agenticdoc"
    adoc.mkdir(parents=True)
    (adoc / "goal.md").write_text(
        "# Goal\n\nShip the autopilot e2e chain deterministically.\n", encoding="utf-8"
    )
    index_lines = [
        f"| {key} | active | {phase} | — | - | e2e key | {_iso_now()} |"
        for key, phase in keys.items()
    ]
    (adoc / "_index.parallel").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = enabled
    # config schema is int; sub-1s intervals go via the conductor
    # --poll-interval float flag instead
    cfg["poll_interval_sec"] = int(interval)
    config.save_config(project, cfg)
    if roadmap_text is not None:
        rm = adoc / "_autopilot"
        rm.mkdir(parents=True, exist_ok=True)
        (rm / "_roadmap.md").write_text(roadmap_text, encoding="utf-8")
    (project / "providers-e2e.json").write_text(
        __import__("json").dumps(_PROVIDERS, indent=1), encoding="utf-8"
    )
    return project


def _rm_running(keys: list[str], *, stage_status: str = "running") -> str:
    """Pre-written running roadmap (no gate needed)."""
    key_status = ", ".join(f"{k}=running" for k in keys)
    rows = "\n".join(f"| {k} | worker | - |" for k in keys)
    return (
        "# Roadmap\n"
        f"> generated_at: {_iso_now()}\n"
        "> goal_mtime: 1\n"
        "\n"
        "## Stage 1: deliver\n"
        "> goal: deliver the e2e chain\n"
        f"> status: {stage_status}\n"
        f"> key-status: {key_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        f"{rows}\n"
    )


def _tasks(project: pathlib.Path, key: str, stems: list[str]) -> None:
    tdir = project / ".agenticdoc" / key / "tasks"
    tdir.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (tdir / f"{stem}.md").write_text(f"# {stem}\n\nStub task.\n", encoding="utf-8")


# ── stub worker (PATH-shadowed pi) ───────────────────────────────────────────

_STUB_WORKER = r'''
"""Deterministic e2e stub worker: behaves per the task.md frontmatter
labels (type/loop), writes the artifact the phase gate expects, exits 0.
No LLM, no network."""
import os
import pathlib
import re
import sys
import time

task_path = pathlib.Path(os.environ["PI_WORKER_TASK"])
text = task_path.read_text(encoding="utf-8")
fm = text.split("---", 2)
body = fm[2] if len(fm) > 2 else text


def field(name):
    m = re.search(rf"^{name}: (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


task_type = field("type")
loop = field("loop")
task_dir = task_path.parent
key_dir = task_dir.parents[1]      # .../<key>/workers/<task_key> -> .../<key>
root = task_dir.parents[3]         # -> .agenticdoc -> project root
output = task_dir / "output.md"

trace = task_dir / "trace.log"
with trace.open("a", encoding="utf-8") as fh:
    fh.write(f"[START] pid={os.getpid()}\n")

TS = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

if task_type == "roadmap-writer":
    keys = re.findall(r"^- (\S+) \(phase", body, re.MULTILINE) or ["k1"]
    ap = root / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {k} | worker | - |" for k in keys)
    ks = ", ".join(f"{k}=running" for k in keys)
    (ap / "_roadmap.md").write_text(
        "# Roadmap\n"
        f"> generated_at: {TS}\n"
        "> goal_mtime: 1\n"
        "\n"
        "## Stage 1: deliver the e2e chain\n"
        "> goal: deliver the e2e chain\n"
        "> status: pending\n"
        f"> key-status: {ks}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        f"{rows}\n",
        encoding="utf-8",
    )
    output.write_text("roadmap proposal written\n", encoding="utf-8")
elif loop.startswith("gen:") and loop.endswith(":spec"):
    (key_dir / "spec.md").write_text(
        "# Spec (e2e stub)\n\n"
        "## §0 Goal Alignment\n\n"
        "- 对齐: e2e stub 交付\n"
        "- GC 继承: 无\n"
        "- 冲突: 无\n"
        "- 预期收益: 全链路确定性验证（判定方式: E2E 断言全绿）\n"
        "\n## 验收标准\n\n- AC-101: stub spec 交付\n\n"
        + "背景与范围填充内容。 " * 30 + "\n",
        encoding="utf-8",
    )
    rdir = key_dir / "evidence" / "research"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "spec-e2e.md").write_text(
        "# spec research (stub)\n\n出处: e2e stub。\n", encoding="utf-8"
    )
    output.write_text("spec written\n", encoding="utf-8")
elif loop.startswith("gen:") and loop.endswith(":design"):
    (key_dir / "design.md").write_text(
        "# Design (e2e stub)\n\n- D-201: stub 架构\n\n" + "设计填充内容。 " * 40 + "\n",
        encoding="utf-8",
    )
    rdir = key_dir / "evidence" / "research"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "design-e2e.md").write_text(
        "# design research (stub)\n\n出处: e2e stub。\n", encoding="utf-8"
    )
    output.write_text("design written\n", encoding="utf-8")
elif loop.startswith("gen:") and loop.endswith(":plan"):
    (key_dir / "plan.md").write_text(
        "# Plan (e2e stub)\n\n1. T-01-impl 执行 stub 实现\n\n" + "计划填充内容。 " * 25 + "\n",
        encoding="utf-8",
    )
    output.write_text("plan written\n", encoding="utf-8")
elif loop.startswith("gen:") and loop.endswith(":tasks"):
    tdir = key_dir / "tasks"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "T-01-impl.md").write_text("# T-01-impl\n\nStub task file.\n", encoding="utf-8")
    output.write_text("tasks written\n", encoding="utf-8")
elif loop.startswith("exec:"):
    output.write_text(f"executed {loop} by stub\n", encoding="utf-8")
elif task_type == "reviewer":
    if (
        os.environ.get("MW_E2E_L3_FAIL_FIRST") == "1"
        and "l3-a1" in task_dir.name
    ):
        # mw-l3-fail-marker-forms (VC-011): round-1 reviewer reports its
        # FAIL as a bold bullet (non-pipe form) — the file's only marker.
        output.write_text(
            "# L3 Report (e2e stub, fail-marker round)\n\n"
            "## Quality Gate Report\n\n"
            "| VC | verdict | evidence |\n"
            "|----|---------|----------|\n"
            "| VC-901 | PASS | output.md |\n"
            "| VC-902 | PASS | trace.log |\n"
            "\n"
            "- **FAIL：1**（VC-903: 证据缺失）\n"
            "\n"
            "## Achieved\n\n"
            "e2e stub fail-marker round：判定 below，等待修复轮。\n",
            encoding="utf-8",
        )
    elif (
        os.environ.get("MW_E2E_L3_FAIL_FIRST") == "1"
        and "l3-a2" in task_dir.name
    ):
        # mw-l3-fail-marker-forms (VC-011): the post-repair round-2 reports
        # clean VC verdicts AND a done-gate-compliant Achieved draft (the
        # plain else-branch draft would burn the shared closure-reprompt
        # budget the FAIL round already drew from).
        output.write_text(
            "# L3 Report (e2e stub, post-repair round)\n\n"
            "## Quality Gate Report\n\n"
            "| VC | verdict | evidence |\n"
            "|----|---------|----------|\n"
            "| VC-901 | PASS | output.md |\n"
            "| VC-902 | PASS | trace.log |\n"
            "\n"
            "## Achieved\n\n"
            "### 系统行为变化\n\n"
            "stub 修复轮：EXECUTE 任务全部完成，验证证据齐备，目标收益落地；"
            "结案文书按门禁驳回规则重组，无新增风险面。\n\n"
            "### 遗留\n\n"
            "无遗留阻塞项：全部任务收敛，无需立新 key。\n",
            encoding="utf-8",
        )
    elif "Rejected lines" in body:
        # reprompt round (mw-done-closure-repair): the prompt carries the
        # done-gate rejection verbatim; obey it — reorganize the Achieved
        # section per the listed rules so the closure gate passes.
        output.write_text(
            "# L3 Report (e2e stub, reprompt round)\n\n"
            "## Quality Gate Report\n\n"
            "| VC | verdict | evidence |\n"
            "|----|---------|----------|\n"
            "| VC-901 | PASS | output.md |\n"
            "| VC-902 | PASS | trace.log |\n"
            "\n"
            "## Achieved\n\n"
            "### 系统行为变化\n\n"
            "stub 修复轮：EXECUTE 任务全部完成，验证证据齐备，目标收益落地；"
            "结案文书按门禁驳回规则重组，无新增风险面。\n\n"
            "### 遗留\n\n"
            "无遗留阻塞项：全部任务收敛，无需立新 key。\n",
            encoding="utf-8",
        )
    else:
        output.write_text(
            "# L3 Report (e2e stub)\n\n"
            "## Quality Gate Report\n\n"
            "| VC | verdict | evidence |\n"
            "|----|---------|----------|\n"
            "| VC-901 | PASS | output.md |\n"
            "| VC-902 | PASS | trace.log |\n"
            "\n"
            "## Achieved\n\n"
            + "e2e stub 达成摘要：EXECUTE 任务全部完成，验证证据齐备，目标收益落地，无遗留阻塞项。 " * 6
            + "\n",
            encoding="utf-8",
        )
elif task_type == "verifier":
    output.write_text("verdict: meets (e2e stub, advisory)\n", encoding="utf-8")
elif task_type == "repair":
    output.write_text("repaired (e2e stub)\n", encoding="utf-8")
else:
    # phase-writer fallback: same-round L2 evidence fix shape
    edir = key_dir / "evidence"
    edir.mkdir(parents=True, exist_ok=True)
    (edir / "missing.md").write_text("E-1 (stub fix)\n", encoding="utf-8")
    output.write_text("generic stub done\n", encoding="utf-8")

sys.exit(0)
'''


def _make_stub_bin() -> pathlib.Path:
    """Temp bin dir with a PATH-shadowing ``pi`` shim that runs the stub."""
    bin_dir = pathlib.Path(tempfile.mkdtemp(prefix="mw-e2e-bin-"))
    stub = bin_dir / "stub_worker.py"
    stub.write_text(_STUB_WORKER, encoding="utf-8")
    if sys.platform == "win32":
        shim = bin_dir / "pi.cmd"
        shim.write_text(
            f'@"{sys.executable}" "{stub}" %*\n', encoding="utf-8"
        )
    else:
        shim = bin_dir / "pi"
        shim.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n', encoding="utf-8"
        )
        shim.chmod(0o755)
    return bin_dir


def _child_env(bin_dir: pathlib.Path) -> dict:
    env = dict(os.environ)
    env["MW_E2E_FAKE_KEY"] = "stub-no-network"
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ── real processes ───────────────────────────────────────────────────────────

def _spawn(cmd: list[str], env: dict) -> subprocess.Popen:
    kwargs: dict = {"env": env}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)


def _start_conductor(
    project: pathlib.Path, env: dict, interval: float | None = None
) -> subprocess.Popen:
    cmd = [sys.executable, str(_CONDUCTOR_PY), f"--project={project}"]
    if interval is not None:
        cmd.append(f"--poll-interval={interval}")
    return _spawn(cmd, env)


def _start_launcher(project: pathlib.Path, env: dict) -> subprocess.Popen:
    return _spawn(
        [
            sys.executable, str(_LAUNCHER_PY),
            f"--project={project}", "--poll-interval=1",
            f"--providers={project / 'providers-e2e.json'}",
        ],
        env,
    )


def _start_serve(
    project: pathlib.Path, env: dict, *, pi_port: int = 7097, claude_port: int = 7098
) -> subprocess.Popen:
    return _spawn(
        [
            sys.executable, str(_MW_PY), "serve",
            f"--project={project}",
            f"--pi-port={pi_port}", f"--claude-port={claude_port}",
            f"--providers={project / 'providers-e2e.json'}",
        ],
        env,
    )


def _kill_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True
        )
    else:
        try:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def _kill_pid(pid: int) -> None:
    """Kill one process by PID (no tree) — the AC-022 conductor kill."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _mw_stop(project: pathlib.Path) -> None:
    subprocess.run(
        [sys.executable, str(_MW_PY), "stop", f"--project={project}"],
        capture_output=True, timeout=30,
    )


# ── observation helpers ──────────────────────────────────────────────────────

def _retry_io(fn, attempts: int = 5, backoff: float = 0.05):
    """Windows atomic-replace race: a concurrent open during another
    writer's tmp.replace() window raises PermissionError transiently.
    Production readers (launcher poll / conductor tick) all carry
    catch-alls; mirror that robustness here."""
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(backoff)
    raise AssertionError("unreachable")


def _wait_until(predicate, timeout: float, poll: float = 0.05):
    """Return the monotonic time when the predicate first held, else None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return time.monotonic()
        time.sleep(poll)
    return None


def _rows(project: pathlib.Path, prefix: str = "ap-") -> list[dict]:
    return [
        r for r in mw_common.parse_workers_file(mw_common.workers_path(project))
        if r["task_key"].startswith(prefix)
    ]


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def conductor_gates_dir(project: pathlib.Path) -> pathlib.Path:
    return project / ".agenticdoc" / "_autopilot" / "gates"


def _pending_gate(project: pathlib.Path, kind: str) -> pathlib.Path | None:
    for gate in gates.enumerate(conductor_gates_dir(project)):
        if gate.kind == kind and gate.status == "pending":
            return gate.path
    return None


def _answer_gate(gate_path: pathlib.Path, decision: str, note: str) -> float:
    """Human answer: rewrite the four answer fields (manual file edits are
    legal answers per gates.py). Returns the monotonic write time."""
    text = gate_path.read_text(encoding="utf-8")

    def sub(field: str, value: str) -> None:
        nonlocal text
        text, n = re.subn(rf"^{field}:.*$", f"{field}: {value}", text, count=1, flags=re.M)
        assert n == 1, f"gate field {field} not found in {gate_path}"

    sub("status", decision)
    sub("answered_at", _iso_now())
    sub("answered_by", "e2e-human")
    sub("note", note)
    tmp = gate_path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(gate_path)
    return time.monotonic()


# ── 1. full chain: roadmap -> stage gate -> gen -> execute -> L3 -> done ─────

@_e2e_l2
def test_full_chain_single_key() -> None:
    project = _make_project(keys={"k1": "SPEC"})
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    cond = launcher = None
    try:
        cond = _start_conductor(project, env)
        launcher = _start_launcher(project, env)

        # roadmap-writer dispatched and the stub lands a proposal
        got = _wait_until(lambda: _rows(project, "ap-_scratch-roadmap-"), timeout=30)
        assert got, "roadmap-writer not dispatched"
        got = _wait_until(
            lambda: (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").is_file(),
            timeout=30,
        )
        assert got, "stub roadmap-writer did not write _roadmap.md"

        # VC-002: the stub-produced roadmap passes roadmap_check (all stages)
        check = subprocess.run(
            [sys.executable, str(_HERE / "autopilot" / "roadmap_check.py"),
             f"--project={project}"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        assert check.returncode == 0, check.stderr
        _verify("VC-002", stages_valid="all", roadmap_check_exit=check.returncode)

        # stage-confirm gate appears -> human approves
        got = _wait_until(lambda: _pending_gate(project, "stage-confirm") is not None, timeout=30)
        assert got, "stage-confirm gate not created"
        gate_path = _pending_gate(project, "stage-confirm")
        t_answer = _answer_gate(gate_path, "approved", "e2e: start stage 1")

        # VC-018: gate consumption latency <= 1 interval
        t_consumed = _wait_until(
            lambda: any(
                e["ev"] == "gate-answered" and "approved" in str(e.get("detail", ""))
                for e in _events(project)
            ),
            timeout=30,
        )
        assert t_consumed is not None, "gate-answered event never appeared"
        delay_ms = (t_consumed - t_answer) * 1000
        # VC-018 (erratum): gate consumed within the first tick after the
        # answer — delay <= interval + tick-processing overhead
        assert delay_ms <= _INTERVAL * 1000 + _TICK_SLACK_MS, f"gate delay {delay_ms}ms"

        # first dispatch row for the stage (gen spec)
        t_dispatch = _wait_until(lambda: _rows(project, "ap-k1-"), timeout=30)
        assert t_dispatch is not None, "no dispatch after stage approval"
        d_delay_ms = (t_dispatch - t_answer) * 1000
        # VC-004: stage gate answer -> first dispatch <= 2x interval
        assert d_delay_ms <= 2 * _INTERVAL * 1000 + _GRACE_MS, f"dispatch delay {d_delay_ms}ms"
        _verify(
            "VC-018", delay_ms=round(delay_ms), interval_ms=round(_INTERVAL * 1000),
            slack_ms=round(_TICK_SLACK_MS), **{"pass": "true"},
        )
        _verify(
            "VC-004", delay_ms=round(d_delay_ms), interval_ms=round(_INTERVAL * 1000),
            **{"pass": "true"},
        )

        # the chain runs to completion: key done + stage-close gate
        got = _wait_until(lambda: _pending_gate(project, "stage-close") is not None, timeout=120)
        assert got, "stage-close gate not reached (chain stalled)"

        ks = state.read_key_states(project)["k1"]
        assert ks.phase == "DONE", f"k1 phase {ks.phase}"
        key_dir = project / ".agenticdoc" / "k1"
        achieved = key_dir / "achieved.md"
        assert achieved.is_file() and achieved.stat().st_size >= 200
        assert "PASS" in (key_dir / "pm-state.md").read_text(encoding="utf-8")
        assert list((key_dir / "evidence").glob("quality-gate-report-*.md"))
        rm = roadmap.load_roadmap(
            project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
        )
        assert rm.stages[0].key_status["k1"] == "done"
        adv = [e for e in _events(project) if e["ev"] == "advance"]
        assert any("verify->done exit=0" in e["detail"] for e in adv)
        print(
            f"[chain] k1 done via real advance_phase.py; advances={len(adv)} "
            f"dispatches={len(_rows(project))}",
            flush=True,
        )
    finally:
        _kill_tree(cond)
        _kill_tree(launcher)
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 1b. L3 fail-marker repair chain (mw-l3-fail-marker-forms VC-011) ──────

@_e2e_l2
def test_l3_fail_marker_repair_chain() -> None:
    # Round-1 reviewer reports its FAIL as a bold bullet (non-pipe form):
    # the verdict must land below (no false-meets), the repair prompt must
    # carry the verbatim fail line, and the repaired chain must close DONE
    # via a clean round-2 meets.
    project = _make_project(keys={"k1": "EXECUTE"}, roadmap_text=_rm_running(["k1"]))
    _tasks(project, "k1", ["T-01-one"])
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    env["MW_E2E_L3_FAIL_FIRST"] = "1"  # stub: round-1 reviewer writes the bullet FAIL
    cond = launcher = None
    try:
        cond = _start_conductor(project, env)
        launcher = _start_launcher(project, env)

        # below round-1 -> repair dispatched with the fail line injected
        repair_md = (
            project / ".agenticdoc" / "k1" / "workers" / "ap-k1-repair-a1" / "task.md"
        )
        got = _wait_until(lambda: repair_md.is_file(), timeout=90)
        assert got, "repair never dispatched (round-1 bullet FAIL not detected?)"
        body = repair_md.read_text(encoding="utf-8")
        assert "首个 FAIL 行" in body, "repair prompt lacks the fail-line bullet"
        assert "- **FAIL：1**" in body, "repair prompt lacks the verbatim fail line"

        # no false-meets: the key must not be DONE at the repair point
        assert state.read_key_states(project)["k1"].phase != "DONE"

        # repaired chain closes: round-2 clean meets -> DONE + stage-close
        got = _wait_until(
            lambda: _pending_gate(project, "stage-close") is not None, timeout=150
        )
        assert got, "stage-close gate not reached (chain stalled after repair)"
        ks = state.read_key_states(project)["k1"]
        assert ks.phase == "DONE", f"k1 phase {ks.phase}"
        key_dir = project / ".agenticdoc" / "k1"
        verdict = (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip()
        assert verdict == "meets", f"terminal verdict {verdict!r}"
        # provenance: round l3-a1 recorded the bullet fail_line; l3-a2 clean
        sidecar = key_dir / "l3-verdict-provenance.json"
        records = __import__("json").loads(sidecar.read_text(encoding="utf-8"))
        by_round = {r["round"]: r for r in records}
        assert "- **FAIL：1**" in (by_round["l3-a1"].get("fail_line") or ""), (
            "l3-a1 provenance lost the fail_line"
        )
        assert not by_round["l3-a2"].get("fail_line"), (
            "l3-a2 clean round must carry no fail_line"
        )
        adv = [e for e in _events(project) if e["ev"] == "advance"]
        assert any("verify->done exit=0" in e["detail"] for e in adv)
        _verify(
            "VC-011", fail_form="bullet", repair_prompt="fail-line-injected",
            rounds=len(records), **{"pass": "true"},
        )
    finally:
        _kill_tree(cond)
        _kill_tree(launcher)
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 2. parallel dispatch (VC-006) ────────────────────────────────────────────

@_e2e_l2
def test_parallel_dispatch() -> None:
    keys = {"k1": "EXECUTE", "k2": "EXECUTE"}
    project = _make_project(keys=keys, roadmap_text=_rm_running(list(keys)))
    _tasks(project, "k1", ["T-01-one"])
    _tasks(project, "k2", ["T-09-two"])
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    cond = launcher = None
    try:
        t0 = time.monotonic()
        cond = _start_conductor(project, env)
        launcher = _start_launcher(project, env)

        def both_pending() -> bool:
            r1 = _rows(project, "ap-k1-")
            r2 = _rows(project, "ap-k2-")
            return bool(r1) and bool(r2)

        got = _wait_until(
            both_pending, timeout=15,
        )
        assert got, (
            f"parallel dispatch missing "
            f"(k1={_rows(project, 'ap-k1-')} k2={_rows(project, 'ap-k2-')})"
        )
        elapsed_ms = (got - t0) * 1000
        # both first dispatch rows coexisted within the 10s bound (§2.2)
        assert elapsed_ms < 10_000, f"parallel dispatch took {elapsed_ms}ms"
        assert _rows(project, "ap-k1-")[0]["status"] in ("pending", "done")
        assert _rows(project, "ap-k2-")[0]["status"] in ("pending", "done")
        _verify(
            "VC-006", delay_ms=round(elapsed_ms), interval_ms=round(_INTERVAL * 1000),
            parallel_dispatch=2, **{"pass": "true"},
        )
    finally:
        _kill_tree(cond)
        _kill_tree(launcher)
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 3. beat observation window (VC-021) ──────────────────────────────────────

@_e2e_l2
def test_beat_observation_window() -> None:
    # interval 4s (production default), window scaled by MW_E2E_FAST:
    # 60s@4s -> 15 beats; 15s@1s -> 15 beats. Same duty cycle, threshold 12.
    interval = 4.0 if not _FAST else 1.0
    project = _make_project(keys={"k1": "SPEC"}, interval=interval)
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    cond = None
    try:
        cond = _start_conductor(project, env)
        time.sleep(_BEAT_WINDOW)
        beats = sum(1 for e in _events(project) if e["ev"] == "beat")
        expected = _BEAT_WINDOW / interval
        assert beats >= 12, f"beats={beats} window={_BEAT_WINDOW}s interval={interval}s"
        assert beats >= 0.8 * expected, f"beats={beats} below 80% duty ({expected})"
        _verify(
            "VC-021", beats=beats, window_ms=round(_BEAT_WINDOW * 1000),
            interval_ms=round(interval * 1000), **{"pass": "true"},
        )
    finally:
        _kill_tree(cond)
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 4. concurrent write stress (VC-022) ──────────────────────────────────────

@_e2e_l2
def test_concurrent_write_stress() -> None:
    keys = {f"k{i}": "EXECUTE" for i in range(1, 9)}  # 8 keys -> sustained churn
    project = _make_project(keys=keys, interval=1, roadmap_text=_rm_running(list(keys)))
    for i in range(1, 9):
        _tasks(project, f"k{i}", ["T-01-one", "T-02-two"])
    # k9: index-only row the human flips (absent from the roadmap, so the
    # conductor ignores it, but it exercises concurrent _index.parallel writes)
    ipath = project / ".agenticdoc" / "_index.parallel"
    with ipath.open("a", encoding="utf-8") as fh:
        fh.write(f"| k9 | active | EXECUTE | — | - | human row | {_iso_now()} |\n")
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    cond = launcher = None
    human_keys: list[str] = []
    observed_ap: set[str] = set()
    stop = threading.Event()

    def human_writer() -> None:
        wpath = mw_common.workers_path(project)
        idx = 0
        flip = True
        while not stop.is_set():
            idx += 1
            hkey = f"h-{idx:04d}"
            htask = project / ".agenticdoc" / "k9" / "workers" / hkey / "task.md"
            htask.parent.mkdir(parents=True, exist_ok=True)
            htask.write_text(
                f"---\ntype: phase-writer\norigin: human\nloop: h:{hkey}\n"
                f"attempt: 1\n---\n\nhuman stress row\n",
                encoding="utf-8",
            )
            # locked append to _workers.parallel (the documented protocol)
            mw_common.acquire_lock(mw_common.lock_path(project))
            try:
                def _append() -> None:
                    with wpath.open("a", encoding="utf-8", newline="\n") as fh:
                        fh.write(mw_common.serialize_entry({
                            "task_key": hkey, "status": "pending", "cli": "pi",
                            "provider": "",
                            "task_path": str(
                                project / ".agenticdoc" / "k9" / "workers" / hkey / "task.md"
                            ),
                            "dispatched_at": mw_common.iso_now(),
                            "updated_at": mw_common.iso_now(), "model": "",
                        }) + "\n")
                _retry_io(_append)
            finally:
                mw_common.release_lock(mw_common.lock_path(project))
            human_keys.append(hkey)
            # locked k9 phase flip in _index.parallel
            if idx % 2 == 0:
                flip = not flip
                mw_common.acquire_lock(project / ".mw" / "index.lock")
                try:
                    def _flip() -> None:
                        lines = ipath.read_text(encoding="utf-8").splitlines()
                        out = []
                        for line in lines:
                            if line.startswith("| k9 |"):
                                cols = [c.strip() for c in line.strip("|").split("|")]
                                cols[2] = "VERIFY" if flip else "EXECUTE"
                                line = "| " + " | ".join(cols) + " |"
                            out.append(line)
                        ipath.write_text("\n".join(out) + "\n", encoding="utf-8")
                    _retry_io(_flip)
                finally:
                    mw_common.release_lock(project / ".mw" / "index.lock")
            time.sleep(0.2)

    def observer() -> None:
        while not stop.is_set():
            try:
                for row in _rows(project):
                    observed_ap.add(row["task_key"])
            except PermissionError:
                pass  # transient replace-window loss on Windows; next poll re-reads
            time.sleep(0.2)

    try:
        cond = _start_conductor(project, env, interval=_STRESS_INTERVAL)
        launcher = _start_launcher(project, env)
        th = threading.Thread(target=human_writer, daemon=True)
        ob = threading.Thread(target=observer, daemon=True)
        th.start()
        ob.start()
        time.sleep(_STRESS_WINDOW)
        stop.set()
        th.join(timeout=5)
        ob.join(timeout=5)

        # -- integrity: every line parses with the per-file column count --
        wtext = mw_common.workers_path(project).read_text(encoding="utf-8")
        for lineno, line in enumerate(wtext.splitlines(), 1):
            if not line.startswith("|"):
                continue
            cols = line.strip().strip("|").split("|")
            assert 7 <= len(cols) <= 8, f"workers line {lineno}: {len(cols)} cols"
        final_rows = mw_common.parse_workers_file(mw_common.workers_path(project))
        for row in final_rows:
            assert row.get("task_key") and row.get("status"), f"bad row {row}"
        final_keys = [r["task_key"] for r in final_rows]
        assert len(final_keys) == len(set(final_keys)), "duplicate task_key rows"

        # -- no loss: human rows and every observed conductor row survive --
        missing_human = [k for k in human_keys if k not in final_keys]
        assert not missing_human, f"lost human rows: {missing_human[:5]}"
        missing_ap = sorted(k for k in observed_ap if k not in final_keys)
        assert not missing_ap, f"lost conductor rows: {missing_ap[:5]}"

        # -- index integrity: 7 columns, key set unchanged --
        ilines = [
            ln for ln in ipath.read_text(encoding="utf-8").splitlines()
            if ln.startswith("|")
            and not re.match(r"^\|[-\s|:]+$", ln)
            and not ln.startswith("| Key")
        ]
        for lineno, line in enumerate(ilines, 1):
            cols = line.strip().strip("|").split("|")
            assert len(cols) == 7, f"index line {lineno}: {len(cols)} cols"
        ikeys = {line.strip("|").split("|")[0].strip() for line in ilines}
        assert ikeys == set(keys) | {"k9"}, f"index key set drifted: {ikeys}"

        _verify(
            "VC-022", human_writes=len(human_keys),
            conductor_rows=len([k for k in final_keys if k.startswith("ap-")]),
            window_ms=round(_STRESS_WINDOW * 1000),
            interval_ms=round(_STRESS_INTERVAL * 1000), **{"pass": "true"},
        )
    finally:
        stop.set()
        _kill_tree(cond)
        _kill_tree(launcher)
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 5. serve supervision: disabled isolation + enable chain ─────────────────

@_e2e_l2
def test_serve_enable_chain() -> None:
    project = _make_project(keys={"k1": "SPEC"}, enabled=False)
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    serve = None
    try:
        serve = _start_serve(project, env)
        # serve must be up (precheck passed with the fixture providers)
        got = _wait_until(
            lambda: (project / ".mw" / "mw.pid").is_file(), timeout=20
        )
        assert got, "mw serve did not start (see .mw/mw.log)"

        # -- VC-014: disabled project -> no conductor, no _autopilot writes --
        time.sleep(3 * _SERVE_POLL)
        assert not (project / ".mw" / "conductor.pid").is_file(), \
            "conductor spawned while disabled"
        status = subprocess.run(
            [sys.executable, str(_MW_PY), "status", f"--project={project}"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        assert "conductor: not running" in status.stdout, status.stdout
        # isolation: _autopilot holds only our fixture config — no timeline,
        # no gates, no roadmap proposal while disabled
        ap_files = sorted(
            p.name for p in (project / ".agenticdoc" / "_autopilot").iterdir()
        )
        assert ap_files == ["config.json"], f"_autopilot writes while disabled: {ap_files}"
        assert not (project / ".agenticdoc" / "_autopilot" / "gates").exists()
        # the disabled-project isolation cannot disturb the repo's own manual
        # suites: this test writes only under its temp project (structural).
        _verify("VC-014", conductor_pid="absent", status_row="not running",
                autopilot_writes="none", suites_unchanged="true")

        # -- VC-027: enable -> serve spawns conductor -> first dispatch --
        cfg = config.load_config(project)
        cfg["enabled"] = True
        t_enable = time.monotonic()
        config.save_config(project, cfg)

        got = _wait_until(
            lambda: (project / ".mw" / "conductor.pid").is_file(), timeout=20
        )
        assert got, "conductor not spawned after enable"
        status = subprocess.run(
            [sys.executable, str(_MW_PY), "status", f"--project={project}"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        assert "conductor: running (PID" in status.stdout, status.stdout
        got = _wait_until(lambda: _rows(project, "ap-_scratch-roadmap-"), timeout=30)
        assert got, "roadmap-writer not dispatched after enable"
        delay_ms = (got - t_enable) * 1000
        bound_ms = (_SERVE_POLL + _INTERVAL) * 1000 + 1000
        assert delay_ms <= bound_ms, f"enable chain delay {delay_ms}ms > {bound_ms}ms"
        _verify(
            "VC-027", delay_ms=round(delay_ms), interval_ms=round(_INTERVAL * 1000),
            **{"pass": "true"},
        )
    finally:
        _mw_stop(project)
        if serve is not None:
            try:
                serve.wait(timeout=15)
            except Exception:
                _kill_tree(serve)
        _kill_tree(serve)
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 6. real conductor kill + serve respawn (AC-022, VC-024 process form) ────

@_e2e_l2
def test_conductor_kill_respawn() -> None:
    keys = {"k1": "EXECUTE"}
    project = _make_project(keys=keys, roadmap_text=_rm_running(list(keys)))
    _tasks(project, "k1", ["T-01-one"])
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    serve = None
    try:
        serve = _start_serve(project, env)
        got = _wait_until(
            lambda: (project / ".mw" / "mw.pid").is_file(), timeout=20
        )
        assert got, "mw serve did not start"
        got = _wait_until(
            lambda: (project / ".mw" / "conductor.pid").is_file(), timeout=20
        )
        assert got, "conductor not spawned"
        old_pid = int(
            (project / ".mw" / "conductor.pid").read_text(encoding="utf-8").strip()
        )

        # the exec task completes (stub worker under the launcher)
        got = _wait_until(
            lambda: any(
                r["status"] == "done" for r in _rows(project, "ap-k1-T-01-one")
            ),
            timeout=30,
        )
        assert got, "exec task never completed"
        task_dir = next(
            (project / ".agenticdoc" / "k1" / "workers").glob("ap-k1-T-01-one*")
        )
        trace = task_dir / "trace.log"
        output = task_dir / "output.md"
        start_lines_before = trace.read_text(encoding="utf-8").count("[START]")
        mtime_before = output.stat().st_mtime_ns
        rounds_before = state.used_rounds(conductor._all_workers_dirs(project))

        # kill the conductor process (stage mid-flight; serve must respawn)
        _kill_pid(old_pid)

        respawn_by = _SERVE_POLL + 2.0
        got = _wait_until(
            lambda: (
                (project / ".mw" / "conductor.pid").is_file()
                and int(
                    (project / ".mw" / "conductor.pid").read_text(encoding="utf-8").strip()
                ) != old_pid
            ),
            timeout=respawn_by + 5,
        )
        assert got, "serve did not respawn a new conductor"
        new_pid = int(
            (project / ".mw" / "conductor.pid").read_text(encoding="utf-8").strip()
        )

        # invariants after recovery (AC-022): no re-dispatch, single [START],
        # budget continuity, completed-artifact mtime unchanged
        got = _wait_until(
            lambda: any(
                e["ev"] == "advance" and "execute->verify exit=0" in e["detail"]
                for e in _events(project)
            ),
            timeout=2 * _INTERVAL + respawn_by + 5,
        )
        assert got, "recovered conductor did not resume progression"
        fam = _rows(project, "ap-k1-T-01-one")
        assert len(fam) == 1, f"re-dispatched the completed task: {fam}"
        assert trace.read_text(encoding="utf-8").count("[START]") == start_lines_before
        assert output.stat().st_mtime_ns == mtime_before
        # budget continuity (AC-022): every pre-kill loop's count is
        # unchanged — recovery neither resets nor inflates rounds; NEW loops
        # (e.g. the L3 review after execute->verify) may legitimately appear
        rounds_after = state.used_rounds(conductor._all_workers_dirs(project))
        assert all(
            rounds_after.get(loop_id, 0) == count
            for loop_id, count in rounds_before.items()
        ), (rounds_before, rounds_after)
        _verify(
            "VC-024", kill="real-process", respawned="true", new_pid=new_pid,
            start_lines=start_lines_before, budgets_unchanged="true",
            mtime_unchanged="true",
        )
    finally:
        _mw_stop(project)
        if serve is not None:
            try:
                serve.wait(timeout=15)
            except Exception:
                _kill_tree(serve)
        _kill_tree(serve)
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 7. multi-project isolation (one serve per project, spec "mw serve 托管多项目")

@_e2e_l2
def test_multi_project_isolation() -> None:
    p1 = _make_project(keys={"k1": "EXECUTE"}, roadmap_text=_rm_running(["k1"]))
    _tasks(p1, "k1", ["T-01-one"])
    p2 = _make_project(keys={"k2": "EXECUTE"}, roadmap_text=_rm_running(["k2"]))
    _tasks(p2, "k2", ["T-02-two"])
    bin_dir = _make_stub_bin()
    env = _child_env(bin_dir)
    serve1 = serve2 = None
    try:
        serve1 = _start_serve(p1, env, pi_port=7097, claude_port=7098)
        serve2 = _start_serve(p2, env, pi_port=7197, claude_port=7198)
        for proj in (p1, p2):
            got = _wait_until(
                lambda proj=proj: (proj / ".mw" / "mw.pid").is_file()
                and (proj / ".mw" / "conductor.pid").is_file(),
                timeout=20,
            )
            assert got, f"serve/conductor not up for {proj}"
        pid1 = int((p1 / ".mw" / "conductor.pid").read_text(encoding="utf-8").strip())
        pid2 = int((p2 / ".mw" / "conductor.pid").read_text(encoding="utf-8").strip())
        assert pid1 != pid2, "conductors must be per-project processes"

        # both projects progress independently (own queues, own timelines)
        for proj, prefix in ((p1, "ap-k1-"), (p2, "ap-k2-")):
            got = _wait_until(
                lambda proj=proj, prefix=prefix: any(
                    r["status"] == "done" for r in _rows(proj, prefix)
                ),
                timeout=30,
            )
            assert got, f"no completed dispatch in {proj}"
        # no cross-project leakage: each queue holds only its own key's rows
        assert all(
            r["task_key"].startswith("ap-k1-") for r in _rows(p1)
        ), "foreign rows in project 1 queue"
        assert all(
            r["task_key"].startswith("ap-k2-") for r in _rows(p2)
        ), "foreign rows in project 2 queue"

        # kill project 1's conductor → project 2 is unaffected
        _kill_pid(pid1)
        got = _wait_until(
            lambda: any(
                e["ev"] == "advance" and "execute->verify exit=0" in e["detail"]
                for e in _events(p2)
            ),
            timeout=30,
        )
        assert got, "project 2 progression blocked by project 1's conductor kill"
        pid2_after = int(
            (p2 / ".mw" / "conductor.pid").read_text(encoding="utf-8").strip()
        )
        assert pid2_after == pid2, "project 2 conductor was disturbed"
        # project 1 recovers on its own serve
        got = _wait_until(
            lambda: (
                (p1 / ".mw" / "conductor.pid").is_file()
                and int(
                    (p1 / ".mw" / "conductor.pid").read_text(encoding="utf-8").strip()
                ) != pid1
            ),
            timeout=_SERVE_POLL + 7,
        )
        assert got, "project 1 conductor not respawned"
        _verify(
            "MULTI-PROJECT", conductors=2, per_project_pids="true",
            queues_isolated="true", p2_unaffected="true", p1_respawned="true",
        )
    finally:
        _mw_stop(p1)
        _mw_stop(p2)
        for serve in (serve1, serve2):
            if serve is not None:
                try:
                    serve.wait(timeout=15)
                except Exception:
                    _kill_tree(serve)
        _kill_tree(serve1)
        _kill_tree(serve2)
        shutil.rmtree(p1, ignore_errors=True)
        shutil.rmtree(p2, ignore_errors=True)
        shutil.rmtree(bin_dir, ignore_errors=True)


# ── 8/9/10. cross-key repair channel: L2/e2e replay (VC-009/VC-010) ────────────
#
# The full chain (detected -> ticketed -> approved -> applied -> verified ->
# closed) is driven in-process through the REAL conductor mounts
# (`_xkey_aggregate` -> human gate answer -> `_consume_answered_gates` ->
# `_xkey_apply_stage`) against a throw-away project under ``tmp_path``.  The
# verification stage really spawns the fixture project's own pytest command
# (``xkey_verify_cmd``), so the red count 1->0 is measured, never asserted.
#
# The FeatureMigrator work tree is READ-ONLY.  Every corpus literal below is
# quoted verbatim from the FM evidence with its provenance comment; the
# pre-fix shape is reconstructed under ``tmp_path`` (AC-010 path b).  Anchors
# are byte shas, not line numbers (D-011: repair-r1-out-20260925-r3.txt mixes
# 118 CRLF + 106 LF, so Python reports :220 while PowerShell reports :209).

_XKEY_ROADMAP_TEMPLATE = (
    "# Roadmap\n"
    "> generated_at: 2026-09-26T00:00:00+00:00\n"
    "> goal_mtime: 1\n"
    "\n"
    "## Stage 1: work\n"
    "> goal: deliver\n"
    "> status: running\n"
)


def _xkey_project(root: pathlib.Path, keys: tuple[str, ...]) -> pathlib.Path:
    """Throw-away autopilot project: goal + running roadmap.

    The roadmap file is required by the real gate-consumption step
    (``_consume_answered_gates`` short-circuits without it); the xkey mounts
    themselves read only the provenance sidecars and the xkey directory.
    """
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip.\n", encoding="utf-8")
    rows = "\n".join(f"| {key} | worker | - |" for key in keys)
    statuses = ", ".join(f"{key}=running" for key in keys)
    (root / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        _XKEY_ROADMAP_TEMPLATE
        + f"> key-status: {statuses}\n"
        + "### Keys\n"
        + "| key | role | depends_on |\n"
        + "|-----|------|-----------|\n"
        + rows + "\n",
        encoding="utf-8",
    )
    return root


def _xkey_config(root: pathlib.Path, verify_cmd: list[str]) -> dict:
    """Fixture ``_autopilot/config.json``: channel on, per-project verify argv."""
    cfg = config.default_config()
    cfg["enabled"] = True
    cfg["xkey_repair"] = True
    cfg["xkey_verify_cmd"] = list(verify_cmd)
    cfg["xkey_verify_timeout_s"] = 300
    config.save_config(root, cfg)
    return cfg


def _xkey_state(root: pathlib.Path) -> conductor.ConductorState:
    """Fresh conductor state; the timeline seq is recovered from ``root``."""
    tl = timeline.Timeline(timeline.timeline_path(root))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(root))


def _xkey_plant_below(
    root: pathlib.Path,
    source_key: str,
    registration: dict | None,
    *,
    round_no: int = 1,
    fail_line: str = "",
) -> None:
    """One below-round provenance sidecar — the conductor's only red source.

    ``registration=None`` is exactly what T-03 persists when the coarse
    cross-key marker is present but ``collect_registrations`` abstains
    (prose-only shape) — the aggregation must escalate, never propose.
    """
    key_dir = root / ".agenticdoc" / source_key
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "l3-verdict-provenance.json").write_text(
        json.dumps([{
            "raw_verdict": "below",
            "verdict": "below",
            "round": round_no,
            "fail_line": fail_line,
            "deciding_source": f"{source_key}/workers/l3-a1/output.md",
            "registration": registration,
        }], ensure_ascii=False),
        encoding="utf-8",
    )


def _xkey_write_proposal(
    root: pathlib.Path,
    request_id: str,
    file: str,
    line_range: list[int],
    old_block_sha256: str,
    new_block_text: str,
    reason: str,
) -> pathlib.Path:
    """The T-06 ``proposal.md`` shape: S1 metadata triple + fenced new block."""
    directory = xkey.evidence_dir(str(root), request_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "proposal.md"
    path.write_text(
        "---\n"
        f"file: {file}\n"
        f"line_range: [{line_range[0]}, {line_range[1]}]\n"
        f"old_block_sha256: {old_block_sha256}\n"
        f"reason: {reason}\n"
        "---\n"
        "\n"
        "```python\n"
        f"{new_block_text}"
        "```\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _xkey_chain_events(root: pathlib.Path) -> list[str]:
    """Ordered ``xkey-*`` timeline events (the mechanical state sequence)."""
    return [
        str(event.get("ev")) for event in _events(root)
        if str(event.get("ev", "")).startswith("xkey-")
    ]


def _xkey_evidence_item(root: pathlib.Path, request_id: str, name: str) -> object:
    path = xkey.evidence_dir(str(root), request_id) / name
    return json.loads(path.read_text(encoding="utf-8"))


# -- synthetic fixture (VC-009): minimal frozen-constant project ----------------

_SYNTHETIC_TEST_REL = "tests/test_frozen.py"
_SYNTHETIC_TEST_ID = "test_groups_unchanged"
# Frozen constant (12) vs measured value (13): the single pre-fix red.
_SYNTHETIC_BLOCK_12 = (
    'GROUPS_FROZEN = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                 "install-hooks", "mcp", "mr", "project", "validate")\n'
)
# The R1 repair: refresh the frozen expectation with the new `runs` group.
_SYNTHETIC_BLOCK_13 = (
    'GROUPS_FROZEN = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                 "install-hooks", "mcp", "mr", "project", "runs", "validate")\n'
)
_SYNTHETIC_MACHINE_LINE = (
    "[VERIFY] XKEY-T05-S1: "
    "cross_key_test=tests/test_frozen.py::test_groups_unchanged "
    "rc=1 cli_groups=13 frozen_groups=12 owner=k-owner "
    "handoff=registered not_fixed_by_this_key=True"
)
_SYNTHETIC_SOURCE = (
    _SYNTHETIC_BLOCK_12
    + "\n"
    + "def _measured_groups():\n"
    + '    return ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    + '            "install-hooks", "mcp", "mr", "project", "runs", "validate")\n'
    + "\n"
    + "\n"
    + "def test_groups_unchanged():\n"
    + "    measured = _measured_groups()\n"
    + '    print(f"[COUNT] cli_groups={len(measured)} groups={measured}")\n'
    + '    assert tuple(measured) == GROUPS_FROZEN, f"groups changed: {measured}"\n'
)

# -- FeatureMigrator corpus (VC-010), verbatim (read-only source) ---------------

_FM_TEST_REL = "tests/test_hitl_channel.py"
_FM_TEST_ID = "test_top_level_command_groups_unchanged"
# Machine line: cli-run-state-and-events/evidence/runs/repair-r1-out-20260925-r3.txt:220
# (r1 :209 / r2 :239 report the same payload; r3 is the mixed-EOL file).
_FM_MACHINE_LINE = (
    "[VERIFY] REPAIR-R1-F1: "
    "cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged "
    "rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel "
    "handoff=registered not_fixed_by_this_key=True"
)
# A-side K-1 prose: cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md:68
# (spec 1.1 anchor). No `(file,test_id)`; `owner` is the role 兄弟 key -> abstain.
_FM_K1_PROSE = (
    "- **K-1..K-4**（4 条已知红）：K-1 兄弟 key 新增顶层组 `runs` 致本 key PG-2 "
    "断言（12 组）红；K-2 本 key P1 的 `conftest.py` 子 env 改名（`env`→`child_env`）"
    "触发 `tests/gui_contract/paths_encoding.py` 静态匹配器 0 命中；K-3/K-4 本 key P4 "
    "的 `gate_service.write_acceptance`（design D-007.2/D-008/PG-3 明文要求）与两条"
    "既有只读源码守卫（token 扫描，连 docstring 提及 `write_text` 都判红）冲突。"
    "owner 与一行级修法均已登记（P7 §9.5 / P4 L-2/L-3/L-4；P4 明确拒绝以改名/别名"
    "绕过守卫——避免假绿，处置正确）。"
)
# Pre-fix frozen block = the FM :243-244 block with `"runs"` absent (12 items).
_FM_BLOCK_12 = (
    'TOP_LEVEL_GROUPS = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                    "install-hooks", "mcp", "mr", "project", "validate")\n'
)
# Post-R1 block (the real current FM tree) = only the frozen expectation moved.
_FM_BLOCK_13 = (
    'TOP_LEVEL_GROUPS = ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    '                    "install-hooks", "mcp", "mr", "project", "runs", "validate")\n'
)
# Reconstruction of the FM test shape (block, [COUNT] print, :268 assertion).
_FM_TEST_SOURCE = (
    "# Fixture reconstruction of the FeatureMigrator corpus shape (source tree read-only):\n"
    "#   E:\\CLI_workspace\\FeatureMigrator\\tests\\test_hitl_channel.py\n"
    "#   frozen block :243-244 (pre-R1 = 12 groups); [COUNT] print :265-266; assertion :268\n"
    "#   registration  repair-r1-out-20260925-r3.txt:220 (byte-anchored, D-011)\n"
    + _FM_BLOCK_12
    + "\n"
    + "def _help_groups() -> tuple:\n"
    + '    """Fixture twin of FM `_help_groups` (:253-258): the measured 13 groups."""\n'
    + '    return ("agent", "analyze", "branch", "config", "gate", "gui", "init",\n'
    + '            "install-hooks", "mcp", "mr", "project", "runs", "validate")\n'
    + "\n"
    + "\n"
    + "def _agent_subcommands() -> tuple:\n"
    + '    return ("answer", "run")\n'
    + "\n"
    + "\n"
    + "def test_top_level_command_groups_unchanged():\n"
    + '    """PG-2: `agent answer` is a sub-command; the top level keeps its groups."""\n'
    + "    groups = _help_groups()\n"
    + "    subcommands = _agent_subcommands()\n"
    + '    print(f"[COUNT] cli_groups={len(groups)} groups={groups} "\n'
    + '          f"agent_subcommands={sorted(subcommands)}")\n'
    + "\n"
    + '    assert tuple(groups) == TOP_LEVEL_GROUPS, f"top-level groups changed: {groups}"\n'
    + '    assert "agent" in groups\n'
    + '    assert "answer" in subcommands and "run" in subcommands\n'
)


def test_xkey_synthetic_full_chain(tmp_path: pathlib.Path) -> None:
    """VC-009 / AC-009: synthetic fixture, full ledger->close replay.

    The proposal file is injected by the test (T-08's dispatcher is a parallel
    card and not a precondition).  Every stage is the real conductor mount and
    the verification is a real pytest subprocess, so the frozen assertion's
    red count really goes 1 -> 0.
    """
    root = _xkey_project(tmp_path / "proj", ("k-source", "k-owner"))
    target = root / _SYNTHETIC_TEST_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_SYNTHETIC_SOURCE.encode("utf-8"))
    verify_cmd = [
        sys.executable, "-X", "utf8", "-m", "pytest", "-q", _SYNTHETIC_TEST_REL,
    ]
    cfg = _xkey_config(root, verify_cmd)
    st = _xkey_state(root)
    status_of = {"k-source": "done", "k-owner": "done"}

    # -- pre-fix: exactly one red (the frozen assertion) --
    before = xkey.run_verification(
        verify_cmd, cwd=str(root),
        run_dir=str(root / ".tmp" / "red-before"), timeout=300,
    )
    assert before["red_counts"]["total"] == 1, before["red_counts"]
    assert before["red_counts"]["returncode"] == 1

    # -- detected: machine-line registration -> ledger row + ticket + gate --
    registration = xkey.parse_registration(_SYNTHETIC_MACHINE_LINE)
    assert registration is not None and registration["owner_key"] == "k-owner"
    _xkey_plant_below(root, "k-source", registration, fail_line=_SYNTHETIC_MACHINE_LINE)
    conductor._xkey_aggregate(root, st, status_of, cfg)

    rows = xkey.ledger_load(str(root))["rows"]
    assert len(rows) == 1, rows
    assert rows[0]["status"] == "detected"
    request_id = rows[0]["request_id"]
    ticket = xkey.ticket_load(str(root), request_id)
    assert ticket is not None and ticket["status"] == "ticketed"
    assert len(sorted(conductor.gates_dir(root).glob("gate-*.md"))) == 1

    # -- approved: stub human answer on the gate file, folded by step F --
    gate = _pending_gate(root, "xkey-authorize")
    assert gate is not None, "xkey-authorize gate not raised"
    _answer_gate(gate, "approved", "e2e human approval")
    conductor._consume_answered_gates(root, st, cfg)
    ticket = xkey.ticket_load(str(root), request_id)
    assert ticket["status"] == "approved"
    assert xkey.ledger_load(str(root))["rows"][0]["status"] == "approved"

    # -- proposal + boundary pre-check (D-005): zero write until it passes --
    frozen = ticket["frozen_block"]
    located = xkey.locate_frozen_block(str(root), _SYNTHETIC_TEST_REL, _SYNTHETIC_TEST_ID)
    assert located is not None and located["symbol"] == "GROUPS_FROZEN"
    assert located["line_range"] == frozen["line_range"]
    assert located["old_block_sha256"] == frozen["old_block_sha256"]
    proposal_path = _xkey_write_proposal(
        root, request_id, _SYNTHETIC_TEST_REL, frozen["line_range"],
        frozen["old_block_sha256"], _SYNTHETIC_BLOCK_13,
        "source-key delivery added the top-level group `runs`; refresh the snapshot",
    )
    parsed = conductor._xkey_parse_proposal(proposal_path.read_bytes())
    assert parsed is not None
    assert xkey.check_boundary(parsed, ticket) == "ok"
    assert target.read_bytes() == _SYNTHETIC_SOURCE.encode("utf-8"), "no write before apply"

    # -- applied -> verified -> evidence -> closed (real verify subprocess) --
    conductor._xkey_apply_stage(root, st, status_of, cfg)
    ticket = xkey.ticket_load(str(root), request_id)
    assert ticket["status"] == "closed", ticket.get("status")
    row = xkey.ledger_load(str(root))["rows"][0]
    assert row["status"] == "closed"
    assert [h["event"] for h in row["history"]] == [
        "detected", "approved", "applied", "verified", "closed",
    ]

    after = xkey.run_verification(
        verify_cmd, cwd=str(root),
        run_dir=str(root / ".tmp" / "red-after"), timeout=300,
    )
    assert after["red_counts"]["total"] == 0, after["red_counts"]
    assert after["red_counts"]["returncode"] == 0
    assert b'"runs"' in target.read_bytes()

    events = _xkey_chain_events(root)
    assert events == [
        "xkey-detected", "xkey-ticketed", "xkey-gate-raised",
        "xkey-applied", "xkey-verified", "xkey-closed",
    ], events

    bundle = _xkey_evidence_item(root, request_id, "bundle.json")
    items = bundle["items"]
    assert bundle["closed"] is True and bundle["missing"] == []
    assert items["relaxed_assertion"] is False
    assert items["old_sha256"] and items["new_sha256"]
    assert items["old_sha256"] != items["new_sha256"]
    assert pathlib.Path(items["stdout_path"]).is_file()

    # -- idempotency: another tick adds no row, no gate, no run dir, no write --
    ledger_rows_before = len(xkey.ledger_load(str(root))["rows"])
    sha_before = hashlib.sha256(target.read_bytes()).hexdigest()
    runs_dir = xkey.evidence_dir(str(root), request_id) / "runs"
    runs_before = sorted(entry.name for entry in runs_dir.iterdir())
    conductor._xkey_aggregate(root, st, status_of, cfg)
    conductor._xkey_apply_stage(root, st, status_of, cfg)
    assert len(xkey.ledger_load(str(root))["rows"]) == ledger_rows_before
    assert hashlib.sha256(target.read_bytes()).hexdigest() == sha_before
    assert sorted(entry.name for entry in runs_dir.iterdir()) == runs_before
    assert len(sorted(conductor.gates_dir(root).glob("gate-*.md"))) == 1

    _verify(
        "VC-009", fixture_red="1->0",
        chain=">".join(event.replace("xkey-", "") for event in events),
        ledger_status="closed", idempotent="True", relaxed_assertion="False",
        **{"pass": "true"},
    )


def test_xkey_fm_corpus_replay(tmp_path: pathlib.Path) -> None:
    """VC-010 / AC-010 (path b): replay the FeatureMigrator corpus in a fixture.

    The pre-fix shape is reconstructed from the verbatim corpus: the frozen
    ``TOP_LEVEL_GROUPS`` has 12 entries while the measured CLI yields 13
    (``cli_groups=13``).  Human approval applies R1 (refresh the frozen
    expectation only — the assertion body is never touched), the targeted
    rerun ``pytest tests/test_hitl_channel.py -q`` goes 1 failed -> green and
    the full red count goes 1 -> 0.  The FM work tree is never written.
    """
    root = _xkey_project(
        tmp_path / "fm", ("cli-run-state-and-events", "cli-hitl-channel")
    )
    target = root / _FM_TEST_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_FM_TEST_SOURCE.encode("utf-8"))
    targeted_cmd = [sys.executable, "-X", "utf8", "-m", "pytest", "-q", _FM_TEST_REL]
    full_cmd = [sys.executable, "-X", "utf8", "-m", "pytest", "-q"]
    cfg = _xkey_config(root, targeted_cmd)
    st = _xkey_state(root)
    status_of = {"cli-run-state-and-events": "done", "cli-hitl-channel": "done"}

    # -- pre-fix: the frozen assertion is the whole suite's single red --
    full_before = xkey.run_verification(
        full_cmd, cwd=str(root),
        run_dir=str(root / ".tmp" / "fm-full-before"), timeout=300,
    )
    targeted_before = xkey.run_verification(
        targeted_cmd, cwd=str(root),
        run_dir=str(root / ".tmp" / "fm-targeted-before"), timeout=300,
    )
    assert full_before["red_counts"]["total"] == 1, full_before["red_counts"]
    assert targeted_before["red_counts"]["total"] == 1

    # -- the corpus machine line parses field-for-field (VC-011 L2 echo) --
    registration = xkey.parse_registration(_FM_MACHINE_LINE)
    assert registration == {
        "file": _FM_TEST_REL,
        "test_id": _FM_TEST_ID,
        "owner_key": "cli-hitl-channel",
        "handoff": "registered",
        "frozen_block": None,
    }, registration
    _xkey_plant_below(
        root, "cli-run-state-and-events", registration, fail_line=_FM_MACHINE_LINE,
    )
    conductor._xkey_aggregate(root, st, status_of, cfg)
    rows = xkey.ledger_load(str(root))["rows"]
    assert len(rows) == 1 and rows[0]["owner_key"] == "cli-hitl-channel"
    request_id = rows[0]["request_id"]

    # -- D-006: the AST locator resolves the frozen block mechanically --
    located = xkey.locate_frozen_block(str(root), _FM_TEST_REL, _FM_TEST_ID)
    assert located is not None, "locate_frozen_block must resolve the FM shape"
    assert located["symbol"] == "TOP_LEVEL_GROUPS"
    assert located["line_range"][1] == located["line_range"][0] + 1
    ticket = xkey.ticket_load(str(root), request_id)
    assert ticket is not None and ticket["status"] == "ticketed"
    assert ticket["frozen_block"]["old_block_sha256"] == located["old_block_sha256"]

    # -- human approval -> R1 proposal -> apply -> verify -> close --
    gate = _pending_gate(root, "xkey-authorize")
    assert gate is not None
    _answer_gate(gate, "approved", "e2e human approval (FM corpus replay)")
    conductor._consume_answered_gates(root, st, cfg)
    proposal_path = _xkey_write_proposal(
        root, request_id, _FM_TEST_REL, located["line_range"],
        located["old_block_sha256"], _FM_BLOCK_13,
        "R1: insert `runs` into the frozen TOP_LEVEL_GROUPS snapshot (assertion untouched)",
    )
    parsed = conductor._xkey_parse_proposal(proposal_path.read_bytes())
    assert parsed is not None
    ticket = xkey.ticket_load(str(root), request_id)
    assert xkey.check_boundary(parsed, ticket) == "ok"
    conductor._xkey_apply_stage(root, st, status_of, cfg)

    ticket = xkey.ticket_load(str(root), request_id)
    assert ticket["status"] == "closed", ticket.get("status")
    assert xkey.ledger_load(str(root))["rows"][0]["status"] == "closed"
    assert "assert tuple(groups) == TOP_LEVEL_GROUPS" in target.read_text(encoding="utf-8")

    targeted_after = xkey.run_verification(
        targeted_cmd, cwd=str(root),
        run_dir=str(root / ".tmp" / "fm-targeted-after"), timeout=300,
    )
    full_after = xkey.run_verification(
        full_cmd, cwd=str(root),
        run_dir=str(root / ".tmp" / "fm-full-after"), timeout=300,
    )
    assert targeted_after["red_counts"]["total"] == 0, targeted_after["red_counts"]
    assert full_after["red_counts"]["total"] == 0, full_after["red_counts"]

    bundle = _xkey_evidence_item(root, request_id, "bundle.json")
    items = bundle["items"]
    assert bundle["closed"] is True
    assert isinstance(items["old_sha256"], str) and items["old_sha256"]
    assert isinstance(items["new_sha256"], str) and items["new_sha256"]
    assert items["old_sha256"] != items["new_sha256"]
    assert items["relaxed_assertion"] is False

    _verify(
        "VC-010", fm_replay_red="1->0", targeted="1 failed -> green",
        relaxed_assertion="False", old_sha256=items["old_sha256"][:12],
        new_sha256=items["new_sha256"][:12],
        **{"pass": "true"},
    )


def test_xkey_prose_registration_escalates_only(tmp_path: pathlib.Path) -> None:
    """VC-002 (L2 echo): a K-1 prose registration escalates, zero tickets.

    The A-side corpus line carries no ``(file,test_id)`` and only the role
    ``兄弟 key`` as owner.  The parser abstains (no guessing) and the real
    aggregator must record exactly one escalation with zero tickets/gates.
    """
    root = _xkey_project(tmp_path / "prose", ("cli-hitl-channel",))
    cfg = _xkey_config(root, [sys.executable, "-X", "utf8", "-m", "pytest", "-q"])
    st = _xkey_state(root)

    assert xkey.parse_registration(_FM_K1_PROSE) is None
    assert xkey.collect_registrations([("l3-a1/report.md", _FM_K1_PROSE)]) is None
    _xkey_plant_below(root, "cli-hitl-channel", None, fail_line=_FM_K1_PROSE)
    conductor._xkey_aggregate(root, st, {"cli-hitl-channel": "done"}, cfg)

    assert xkey.tickets_iter(str(root)) == []
    assert sorted(conductor.gates_dir(root).glob("gate-*.md")) == []
    rows = xkey.ledger_load(str(root))["rows"]
    assert len(rows) == 1 and rows[0]["status"] == "escalated", rows
    assert set(rows[0]["unresolvable_fields"]) == {"file", "test_id", "owner_key"}

    _verify(
        "VC-002", prose_shape="K-1 (no test_id/owner)", tickets=0, gates=0,
        escalations=len(rows), **{"pass": "true"},
    )


# -- script-mode wrappers (pytest injects tmp_path; ``_TESTS`` cannot) ----------

def _script_xkey_synthetic_full_chain() -> None:
    with tempfile.TemporaryDirectory(prefix="mw-e2e-xkey-") as tmp:
        test_xkey_synthetic_full_chain(pathlib.Path(tmp))


def _script_xkey_fm_corpus_replay() -> None:
    with tempfile.TemporaryDirectory(prefix="mw-e2e-xkey-fm-") as tmp:
        test_xkey_fm_corpus_replay(pathlib.Path(tmp))


def _script_xkey_prose_registration_escalates_only() -> None:
    with tempfile.TemporaryDirectory(prefix="mw-e2e-xkey-prose-") as tmp:
        test_xkey_prose_registration_escalates_only(pathlib.Path(tmp))


# ── script mode ──────────────────────────────────────────────────────────────

_TESTS = [
    test_full_chain_single_key,
    test_l3_fail_marker_repair_chain,
    test_parallel_dispatch,
    test_beat_observation_window,
    test_concurrent_write_stress,
    test_serve_enable_chain,
    test_conductor_kill_respawn,
    test_multi_project_isolation,
    _script_xkey_synthetic_full_chain,
    _script_xkey_fm_corpus_replay,
    _script_xkey_prose_registration_escalates_only,
]


def main() -> int:
    print(f"# autopilot L2 e2e — fast={_FAST} interval={_INTERVAL}s "
          f"beat_window={_BEAT_WINDOW}s stress_window={_STRESS_WINDOW}s", flush=True)
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
