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
from autopilot import config, conductor, gates, roadmap, state, timeline  # noqa: E402

try:
    import pytest
    pytestmark = pytest.mark.e2e_l2
except ImportError:  # script mode
    pytest = None

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
