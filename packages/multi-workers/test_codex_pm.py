"""Real PM dispatch, queue, launcher and acceptance processes, with an offline worker."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_integration import _wait_for, fakebin, proj, start_launcher
from autopilot.advance import advance_script

CLI = Path(__file__).with_name("codex_pm.py")
KEY = "counter"
COMMAND = [sys.executable, "check counter.py"]


def framework(project, script, *args):
    scripts = advance_script(CLI.resolve().parents[2]).parent
    proc = subprocess.run([sys.executable, "-X", "utf8", str(scripts / script), *args], cwd=project,
                          capture_output=True, encoding="utf-8", timeout=20)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    return proc.stdout.strip()


def invoke(project, command, *args, expected=0, claim=None):
    env = {**os.environ, "PI_CODING_AGENT_DIR": str(project / ".pi-test-agent"), "PYTHONUTF8": "1"}
    writer = [] if command == "status" else ["--claim-id", claim or framework(project, "update_index.py", "get-claim", KEY)]
    result = subprocess.run([sys.executable, str(CLI), command, "--project", str(project),
                             "--key", KEY, *writer, *args], capture_output=True, text=True, encoding="utf-8",
                            cwd=project, env=env, timeout=45)
    assert result.returncode == expected, (result.stdout, result.stderr)
    return json.loads(result.stdout or result.stderr)


@pytest.fixture()
def card(proj):
    root = proj / ".agenticdoc"
    key = root / KEY
    (key / "tasks").mkdir(parents=True)
    for name in ("spec", "design"):
        (key / f"{name}.md").write_text("AC-001 Increase the counter by one.\n" * 20, encoding="utf-8")
        notes = key / "evidence" / "research"
        notes.mkdir(parents=True, exist_ok=True)
        (notes / f"{name}-counter.md").write_text("Counter contract at counter.py:1", encoding="utf-8")
    with (key / "spec.md").open("a", encoding="utf-8") as stream:
        stream.write("\n### 可复用资产\nUse the MW queue and launcher.\n### 需规避坑点\nTest the code independently.\n")
    (key / "plan.md").write_text("T-01 implement the counter, then check counter.py against its acceptance test.\n" * 5)
    framework(proj, "advance_phase.py", KEY, "spec")
    framework(proj, "update_index.py", "claim", KEY)
    for phase in ("design", "plan", "tasks"):
        framework(proj, "advance_phase.py", KEY, phase)
    source = key / "tasks" / "T-01.md"
    source.write_text(
        "type: coding\n\n## 上下文\n.agenticdoc/goal.md and counter.py:1 define the counter.\n"
        "## 要求\nIncrement by one.\n## 交付格式\nWrite counter.py and output.md.\n"
        "## 写入允许面\n- counter.py\n## 写入禁止面\n- production/\n"
        f"## 验收命令\n```json\n{json.dumps(COMMAND)}\n```\n## 改动历史\nFirst implementation.\n",
        encoding="utf-8")
    framework(proj, "advance_phase.py", KEY, "execute")
    return source


def test_develop_reconnect_and_verify(proj, card, fakebin, start_launcher, monkeypatch):
    # Publish the acceptance test before dispatch, so the same assertion covers
    # the initial implementation, the negative control and the repaired product.
    (proj / "check counter.py").write_text("from counter import increment\nassert increment(4) == 5\nprint('counter verified')\n")
    (fakebin / "fake_cli.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "task = Path(os.environ['PI_WORKER_TASK'])\n"
        "assert 'Increment by one' in task.read_text(encoding='utf-8')\n"
        "Path('counter.py').write_text('def increment(value): return value + 1\\n')\n"
        "(task.parent / 'output.md').write_text('Implemented increment in counter.py.')\n", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: invoke(proj, "dispatch", "--card", card.stem), range(2)))
    assert sorted(r["reused"] for r in replies) == [False, True]
    task = replies[0]["task"]
    assert invoke(proj, "status")["tasks"][0]["verification"] == "unverified"
    invoke(proj, "verify", "--card", card.stem, "--", *COMMAND, expected=2)

    launcher = start_launcher({"TEST_TIMI_API_KEY": "fixture", "MW_USAGE_DIR": str(proj / ".usage")})
    assert _wait_for(proj, task, {"done", "failed"}, proc=launcher, timeout=20) == "done"
    found = invoke(proj, "status")["tasks"]
    assert len(found) == 1 and found[0]["card"] == "tasks/T-01.md"
    assert found[0]["queue"] == "done" and found[0]["verification"] == "unverified"
    assert "Implemented" in Path(found[0]["artifacts"]["output.md"]).read_text()
    invoke(proj, "verify", "--card", card.stem, "--", "echo", "pass", expected=2)
    other = proj / "other"
    other.mkdir()
    with monkeypatch.context() as changed:
        changed.setenv("MW_TARGET_GAME", str(other))
        error = invoke(proj, "verify", "--card", card.stem, "--", *COMMAND, expected=2)
        assert "workspace differs" in error["error"]
    # A real red/green acceptance run with the SAME test and argv.
    framework(proj, "advance_phase.py", KEY, "verify")
    worker_product = proj / "counter.py"
    good = worker_product.read_bytes()
    worker_product.write_text("def increment(value): return value\n")
    failed = invoke(proj, "verify", "--card", card.stem, "--", *COMMAND, expected=1)
    assert failed["verdict"] == "failed" and "AssertionError" in Path(failed["log"]).read_text()
    worker_product.write_bytes(good)
    passed = invoke(proj, "verify", "--card", card.stem, "--", *COMMAND)
    assert passed["exit_code"] == 0 and "counter verified" in Path(passed["log"]).read_text()
    recovered = invoke(proj, "status")["tasks"][0]
    assert recovered["verification"] == "passed" and recovered["checks"] == [failed["evidence"], passed["evidence"]]
    Path(recovered["artifacts"]["output.md"]).write_text("")
    assert invoke(proj, "status")["tasks"][0]["verification"] == "stale"
    invoke(proj, "verify", "--card", card.stem, "--", *COMMAND, expected=2)
    Path(recovered["artifacts"]["output.md"]).write_text("Restored worker report for the counter implementation.")
    accepted = invoke(proj, "verify", "--card", card.stem, "--", *COMMAND)
    key_dir = card.parents[1]
    (key_dir / "evidence" / "quality-gate-report-counter.md").write_text(
        f"AC-001 / VC-001 PASS. increment(4) == 5. Command output: {accepted['log']}", encoding="utf-8")
    with (key_dir / "pm-state.md").open("a", encoding="utf-8") as stream:
        stream.write(f"\nPASS AC-001: {accepted['evidence']}\n")
    (key_dir / "achieved.md").write_text(
        "## 系统行为变化\nThe implementation of increment in counter.py returns the input plus one. "
        "A separate process loaded the implementation and asserted its return value. "
        "The PM can reopen both verification attempts and the worker report.\n## 遗留\nNone.\n", encoding="utf-8")
    framework(proj, "advance_phase.py", KEY, "done", "--summary", "Counter implemented and independently verified")
    assert "PASS" in framework(proj, "audit_phase.py", KEY)
    assert invoke(proj, "status")["phase"] == "DONE"


def test_refusals_do_not_enqueue(proj, card):
    invoke(proj, "dispatch", "--card", "../T-01", expected=2)
    assert "Claim changed" in invoke(proj, "dispatch", "--card", card.stem, claim="old:1", expected=2)["error"]
    original = card.read_text(encoding="utf-8")
    card.write_text(original.replace("## 写入允许面\n- counter.py", ""), encoding="utf-8")
    error = invoke(proj, "dispatch", "--card", card.stem, expected=2)
    assert "dispatch-card" in error["error"]
    card.write_text(original, encoding="utf-8")
    claim = framework(proj, "update_index.py", "get-claim", KEY)
    live_claim = f"{claim.rpartition(':')[0]}:{os.getpid()}"
    for file in (card.parents[1] / "pm-state.md", proj / ".agenticdoc" / "_index.parallel"):
        text = file.read_text(encoding="utf-8")
        file.write_text(text.replace(claim, live_claim), encoding="utf-8")
    assert "another PM" in invoke(proj, "dispatch", "--card", card.stem, expected=2)["error"]
    assert not (proj / ".agenticdoc" / "_workers.parallel").exists()


def test_failed_worker_with_output_cannot_verify(proj, card, fakebin, start_launcher):
    (fakebin / "fake_cli.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['PI_WORKER_TASK']).with_name('output.md').write_text('Partial result')\n"
        "raise SystemExit(1)\n")
    submitted = invoke(proj, "dispatch", "--card", card.stem)
    launcher = start_launcher({"TEST_TIMI_API_KEY": "fixture", "MW_USAGE_DIR": str(proj / ".usage")})
    assert _wait_for(proj, submitted["task"], {"done", "failed"}, proc=launcher, timeout=20) == "failed"
    assert "completed worker" in invoke(proj, "verify", "--card", card.stem, "--", *COMMAND, expected=2)["error"]
    assert invoke(proj, "status")["tasks"][0]["checks"] == []


def test_autopilot_key_has_one_dispatch_owner(proj, card):
    directory = proj / ".agenticdoc" / "_autopilot"
    directory.mkdir(exist_ok=True)
    (directory / "config.json").write_text('{"enabled":true}')
    (directory / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: now\n> goal_mtime: 1\n\n## Stage 1: counters\n"
        "> goal: increment\n> status: running\n> key-status: counter=running\n"
        "### Keys\n| key | role | depends_on |\n|---|---|---|\n| counter | worker | - |\n")
    assert "Autopilot owns" in invoke(proj, "dispatch", "--card", card.stem, expected=2)["error"]
    assert invoke(proj, "status")["tasks"] == []
